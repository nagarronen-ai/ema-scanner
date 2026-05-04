"""
EMA Crossover Scanner — FastAPI Backend v3.7
Multi-broker journal + TastyTrade proxy + encrypted credentials + admin auth
"""
from fastapi import FastAPI, HTTPException, Request, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx, os, uvicorn, secrets, pyotp
from datetime import datetime
from database import Database

app = FastAPI(title="EMA Scanner")
db  = Database()

# CORS — explicit allowlist via env var. Default: same-origin only (no middleware).
_CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-App-Token", "X-TT-Env"],
    )

# Bootstrap secret — required for first-time admin/user creation when nothing
# is set yet. Closes the TOCTOU race where any unauthenticated caller could
# claim admin on a fresh deploy.
BOOTSTRAP_TOKEN = os.environ.get("BOOTSTRAP_TOKEN", "")

def _check_bootstrap(provided: str):
    if not BOOTSTRAP_TOKEN:
        raise HTTPException(status_code=500, detail="BOOTSTRAP_TOKEN not configured on server")
    if not provided or not secrets.compare_digest(provided, BOOTSTRAP_TOKEN):
        raise HTTPException(status_code=403, detail="Invalid bootstrap token")

# ── Admin Token Verification ──────────────────────────────────────────────────
async def verify_admin(authorization: str = Header(None)):
    """Bearer admin/session token in Authorization header. Fails closed."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing admin token")
    token = authorization[7:]
    if not db.verify_admin_token(token):
        raise HTTPException(status_code=403, detail="Invalid admin token")
    return True

async def verify_app_token(x_app_token: str = Header(None, alias="X-App-Token")):
    """For endpoints (like the TT proxy) where Authorization is reserved for
    the upstream service. Caller passes the same admin/session token in
    X-App-Token instead."""
    if not x_app_token:
        raise HTTPException(status_code=401, detail="Missing app token")
    if not db.verify_admin_token(x_app_token):
        raise HTTPException(status_code=403, detail="Invalid app token")
    return True

@app.post("/api/admin/setup")
async def setup_admin(request: Request):
    body = await request.json()
    new_token = body.get("token", "").strip()
    if not new_token or len(new_token) < 8:
        raise HTTPException(status_code=400, detail="Token must be at least 8 chars")
    if db.is_admin_set():
        old_token = body.get("current_token", "")
        if not db.verify_admin_token(old_token):
            raise HTTPException(status_code=403, detail="Current token incorrect")
    else:
        _check_bootstrap(body.get("bootstrap_token", ""))
    db.set_admin_token(new_token)
    return {"ok": True}

@app.post("/api/admin/verify")
async def verify_admin_endpoint(request: Request):
    body = await request.json()
    token = body.get("token", "")
    return {"valid": db.verify_admin_token(token)}

@app.get("/api/admin/status")
def admin_status():
    return {"isSet": db.is_admin_set()}

# ── User Login + 2FA ──────────────────────────────────────────────────────────

@app.post("/api/auth/setup_user")
async def setup_user(request: Request):
    """First-time user creation requires the BOOTSTRAP_TOKEN. Once a user is
    set, rotation requires the admin token."""
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not username or len(password) < 8:
        raise HTTPException(status_code=400, detail="Username + password (8+ chars) required")
    if db.is_user_set():
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or not db.verify_admin_token(auth[7:]):
            raise HTTPException(status_code=403, detail="Admin token required to change user")
    else:
        _check_bootstrap(body.get("bootstrap_token", ""))
    db.set_user(username, password, None)
    return {"ok": True}

@app.get("/api/auth/status")
def auth_status():
    return {"userSet": db.is_user_set(), "adminSet": db.is_admin_set()}

@app.post("/api/auth/login")
async def auth_login(request: Request):
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    if not db.is_user_set():
        raise HTTPException(status_code=400, detail="System not initialized")
    if not db.verify_user_password(username, password):
        raise HTTPException(status_code=401, detail="שם משתמש או סיסמה שגויים")
    # Issue session token — register it without replacing admin_token_hash
    token = secrets.token_urlsafe(32)
    db.add_session_token(token)
    return {"token": token}


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        db.remove_session_token(auth[7:])
    return {"ok": True}

@app.post("/api/auth/verify_2fa")
async def auth_verify_2fa(request: Request):
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    code = body.get("code", "").strip()
    if not db.verify_user_password(username, password):
        raise HTTPException(status_code=401, detail="פרטי התחברות שגויים")
    user = db.get_user()
    secret = user.get("totp_secret")
    if not secret:
        raise HTTPException(status_code=400, detail="2FA not configured")
    totp = pyotp.TOTP(secret)
    if not totp.verify(code, valid_window=1):
        raise HTTPException(status_code=401, detail="קוד 2FA שגוי")
    # Issue session token (do NOT overwrite the master admin hash)
    token = secrets.token_urlsafe(32)
    db.add_session_token(token)
    return {"token": token}


# ── Encrypted Credentials ─────────────────────────────────────────────────────
@app.get("/api/credentials", dependencies=[Depends(verify_admin)])
def get_credentials():
    return db.get_credentials()

@app.post("/api/credentials", dependencies=[Depends(verify_admin)])
async def save_credentials(request: Request):
    db.save_credentials(await request.json())
    return {"ok": True}

@app.get("/api/finnhub_key", dependencies=[Depends(verify_admin)])
def get_finnhub():
    return {"key": db.get_finnhub_key()}

@app.post("/api/finnhub_key", dependencies=[Depends(verify_admin)])
async def save_finnhub(request: Request):
    body = await request.json()
    db.save_finnhub_key(body.get("key", ""))
    return {"ok": True}

# ── Tradier Sandbox Credentials (encrypted, synced) ──────────────────────────
@app.get("/api/tradier_sandbox", dependencies=[Depends(verify_admin)])
def get_tradier_sandbox():
    return db._get("tradier_sandbox", {})

@app.post("/api/tradier_sandbox", dependencies=[Depends(verify_admin)])
async def save_tradier_sandbox(request: Request):
    data = await request.json()
    db._set("tradier_sandbox", data)
    return {"ok": True}



# ── TastyTrade Proxy ──────────────────────────────────────────────────────────
TT_LIVE    = "https://api.tastytrade.com"
TT_SANDBOX = "https://api.cert.tastyworks.com"

@app.api_route("/tt-proxy/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH"],
               dependencies=[Depends(verify_app_token)])
async def tt_proxy(path: str, request: Request):
    env  = request.query_params.get("_env") or request.headers.get("X-TT-Env", "sandbox")
    base = TT_LIVE if env == "live" else TT_SANDBOX
    # Strip headers that shouldn't be forwarded — including our own app-auth header.
    drop = {"host", "content-length", "x-tt-env", "x-app-token"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in drop}
    body = await request.body()
    params = {k: v for k, v in request.query_params.items() if k != "_env"}
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.request(
                method=request.method, url=f"{base}/{path}",
                headers=headers, content=body, params=params)
            return JSONResponse(
                content=resp.json() if resp.content else {},
                status_code=resp.status_code)
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))


# ── Snapshots ─────────────────────────────────────────────────────────────────
@app.post("/api/snapshots/create", dependencies=[Depends(verify_admin)])
async def create_snapshot(request: Request):
    body = await request.json() if await request.body() else {}
    label = body.get("label", "manual")
    ts = db.create_snapshot(label)
    return {"ok": True, "ts": ts}

@app.get("/api/snapshots", dependencies=[Depends(verify_admin)])
def list_snapshots():
    return db.list_snapshots()

@app.post("/api/snapshots/restore", dependencies=[Depends(verify_admin)])
async def restore_snapshot(request: Request):
    body = await request.json()
    ts = body.get("ts", "")
    ok = db.restore_snapshot(ts)
    if not ok:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return {"ok": True}

# ── Earnings (Finnhub) ────────────────────────────────────────────────────────
@app.get("/earnings-proxy/{symbol}", dependencies=[Depends(verify_admin)])
async def earnings_proxy(symbol: str):
    sym = symbol.upper()
    key = db.get_finnhub_key()
    if not key:
        return {"earningsDate": None, "symbol": sym, "error": "Finnhub key not set"}
    try:
        from datetime import timedelta
        now = datetime.now()
        f, t = (now - timedelta(days=90)).strftime("%Y-%m-%d"), (now + timedelta(days=180)).strftime("%Y-%m-%d")
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://finnhub.io/api/v1/calendar/earnings?symbol={sym}&from={f}&to={t}&token={key}")
            data = r.json()
        events = sorted(data.get("earningsCalendar", []), key=lambda e: e["date"])
        today = now.strftime("%Y-%m-%d")
        future = [e for e in events if e["date"] >= today]
        if future:
            return {"earningsDate": future[0]["date"], "symbol": sym}
        if events:
            return {"earningsDate": events[-1]["date"] + " (past)", "symbol": sym}
    except Exception as e:
        return {"earningsDate": None, "symbol": sym, "error": str(e)}
    return {"earningsDate": None, "symbol": sym}

# ── Journal ───────────────────────────────────────────────────────────────────
@app.get("/api/journal/{broker}/{env}", dependencies=[Depends(verify_admin)])
def get_journal(broker: str, env: str):
    return db.get_journal(broker, env)

@app.post("/api/journal/{broker}/{env}", dependencies=[Depends(verify_admin)])
async def save_journal(broker: str, env: str, request: Request):
    trades = await request.json()
    if isinstance(trades, list):
        db.save_journal(broker, env, trades)
    return {"ok": True}

# ── Closed trades ─────────────────────────────────────────────────────────────
@app.get("/api/closed_trades", dependencies=[Depends(verify_admin)])
def get_closed():
    return db.get_closed_trades()

@app.post("/api/closed_trades", dependencies=[Depends(verify_admin)])
async def save_closed(request: Request):
    trades = await request.json()
    if isinstance(trades, list):
        db.save_closed_trades(trades)
    return {"ok": True}

# Legacy compat
@app.get("/api/trades", dependencies=[Depends(verify_admin)])
def get_trades():
    return db.get_journal("tradier", "live")

@app.post("/api/trades", dependencies=[Depends(verify_admin)])
async def save_trades(request: Request):
    trades = await request.json()
    if isinstance(trades, list):
        db.save_journal("tradier", "live", trades)
    return {"ok": True}

# ── Settings, Lists, Cache ────────────────────────────────────────────────────
@app.get("/api/settings", dependencies=[Depends(verify_admin)])
def get_settings(): return db.get_settings()

@app.post("/api/settings", dependencies=[Depends(verify_admin)])
async def save_settings(request: Request):
    db.save_settings(await request.json()); return {"ok": True}

@app.get("/api/lists", dependencies=[Depends(verify_admin)])
def get_lists(): return db.get_lists()

@app.post("/api/lists", dependencies=[Depends(verify_admin)])
async def save_lists(request: Request):
    db.save_lists(await request.json()); return {"ok": True}

@app.get("/api/cache/bars", dependencies=[Depends(verify_admin)])
def get_bars():  return db.get_bars_cache()

@app.post("/api/cache/bars", dependencies=[Depends(verify_admin)])
async def save_bars(request: Request):
    db.save_bars_cache(await request.json()); return {"ok": True}

@app.get("/api/cache/results", dependencies=[Depends(verify_admin)])
def get_results(): return db.get_results_cache()

@app.post("/api/cache/results", dependencies=[Depends(verify_admin)])
async def save_results(request: Request):
    db.save_results_cache(await request.json()); return {"ok": True}


# ── AI Lesson Generator (Anthropic API proxy) ────────────────────────────────
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

@app.post("/api/ai_lesson", dependencies=[Depends(verify_admin)])
async def ai_lesson(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="Missing prompt")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured on server")

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}]
                }
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Network error calling Anthropic: {e}")

    # Surface Anthropic errors instead of silently returning empty.
    if resp.status_code >= 400:
        try:
            err = resp.json().get("error", {})
            msg = f"{err.get('type', 'error')}: {err.get('message', resp.text[:200])}"
        except Exception:
            msg = resp.text[:200] or resp.reason_phrase
        raise HTTPException(status_code=resp.status_code,
                            detail=f"Anthropic API {resp.status_code}: {msg}")

    data = resp.json()
    content = data.get("content") or []
    text = content[0].get("text", "") if content and isinstance(content[0], dict) else ""
    if not text:
        raise HTTPException(status_code=502,
                            detail=f"Empty response from Anthropic (model={ANTHROPIC_MODEL})")
    return {"lesson": text}

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "v3.9",
            "secure_storage": True,
            "admin_set": db.is_admin_set(),
            "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
            "anthropic_model": ANTHROPIC_MODEL}

# ── Static ────────────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root(): return FileResponse("static/index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
