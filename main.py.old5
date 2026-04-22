"""
EMA Crossover Scanner — FastAPI Backend v3.1
Multi-broker journal + TastyTrade proxy
"""
from fastapi import FastAPI, HTTPException, Request, Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx, json, os, uvicorn
from database import Database

app = FastAPI(title="EMA Scanner")
db  = Database()

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── TastyTrade Proxy ──────────────────────────────────────────────────────────
TT_LIVE    = "https://api.tastytrade.com"
TT_SANDBOX = "https://api.cert.tastyworks.com"

@app.api_route("/tt-proxy/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH"])
async def tt_proxy(path: str, request: Request):
    env  = request.query_params.get("_env") or request.headers.get("X-TT-Env", "sandbox")
    base = TT_LIVE if env == "live" else TT_SANDBOX
    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length", "x-tt-env")}
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

# ── Multi-broker Journal ──────────────────────────────────────────────────────
@app.get("/api/journal/{broker}/{env}")
def get_journal(broker: str, env: str):
    return db.get_journal(broker, env)

@app.post("/api/journal/{broker}/{env}")
async def save_journal(broker: str, env: str, request: Request):
    trades = await request.json()
    if isinstance(trades, list):
        db.save_journal(broker, env, trades)
    return {"ok": True}

# ── Permanent Closed Trades ───────────────────────────────────────────────────
@app.get("/api/closed_trades")
def get_closed():
    return db.get_closed_trades()

@app.post("/api/closed_trades")
async def save_closed(request: Request):
    trades = await request.json()
    if isinstance(trades, list):
        db.save_closed_trades(trades)
    return {"ok": True}

# ── Legacy trades endpoint (backward compat) ──────────────────────────────────
@app.get("/api/trades")
def get_trades():
    return db.get_journal("tradier", "live")

@app.post("/api/trades")
async def save_trades(request: Request):
    trades = await request.json()
    if isinstance(trades, list):
        db.save_journal("tradier", "live", trades)
    return {"ok": True}

# ── Settings ──────────────────────────────────────────────────────────────────
@app.get("/api/settings")
def get_settings():
    return db.get_settings()

@app.post("/api/settings")
async def save_settings(request: Request):
    db.save_settings(await request.json())
    return {"ok": True}

# ── Lists ─────────────────────────────────────────────────────────────────────
@app.get("/api/lists")
def get_lists():
    return db.get_lists()

@app.post("/api/lists")
async def save_lists(request: Request):
    db.save_lists(await request.json())
    return {"ok": True}

# ── Cache ─────────────────────────────────────────────────────────────────────
@app.get("/api/cache/bars")
def get_bars():  return db.get_bars_cache()

@app.post("/api/cache/bars")
async def save_bars(request: Request):
    db.save_bars_cache(await request.json()); return {"ok": True}

@app.get("/api/cache/results")
def get_results(): return db.get_results_cache()

@app.post("/api/cache/results")
async def save_results(request: Request):
    db.save_results_cache(await request.json()); return {"ok": True}

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "v3.2",
            "journals": ["tradier/live","tradier/sandbox","tt/live","tt/sandbox"]}

# ── Static ────────────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root(): return FileResponse("static/index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
