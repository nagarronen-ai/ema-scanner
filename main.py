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

# ── Earnings Date Proxy (Yahoo Finance) ──────────────────────────────────────
@app.get("/earnings-proxy/{symbol}")
async def earnings_proxy(symbol: str):
    """Fetch next earnings date via Yahoo Finance chart API"""
    from datetime import datetime
    sym = symbol.upper()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json,text/html,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://finance.yahoo.com/",
        "Origin": "https://finance.yahoo.com",
        "Cache-Control": "no-cache",
    }
    
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, 
                                  headers=headers) as client:
        # Try chart v8 — has earningsTimestamp in meta
        for host in ["query1", "query2"]:
            try:
                r = await client.get(
                    f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}",
                    params={"interval": "1d", "range": "1d", "includePrePost": "false"}
                )
                if r.status_code == 200:
                    data = r.json()
                    meta = data.get("chart",{}).get("result",[{}])[0].get("meta",{})
                    # earningsTimestampStart = next earnings
                    for key in ["earningsTimestampStart", "earningsTimestamp", "earningsTimestampEnd"]:
                        ts = meta.get(key)
                        if ts and int(ts) > datetime.now().timestamp():
                            return {"earningsDate": datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d"), "symbol": sym}
            except Exception:
                continue
        
        # Fallback: quoteSummary calendarEvents
        for host in ["query1", "query2"]:
            for ver in ["v10", "v11"]:
                try:
                    r = await client.get(
                        f"https://{host}.finance.yahoo.com/{ver}/finance/quoteSummary/{sym}",
                        params={"modules": "calendarEvents,earnings"}
                    )
                    if r.status_code != 200:
                        continue
                    data = r.json()
                    res = (data.get("quoteSummary",{}).get("result") or [{}])[0]
                    dates = (res.get("calendarEvents",{})
                               .get("earnings",{})
                               .get("earningsDate",[]))
                    now_ts = datetime.now().timestamp()
                    for d in dates:
                        ts = d.get("raw",0) if isinstance(d,dict) else d
                        if ts and int(ts) > now_ts:
                            return {"earningsDate": datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d"), "symbol": sym}
                except Exception:
                    continue

    return {"earningsDate": None, "symbol": sym}

# ── Earnings Debug ───────────────────────────────────────────────────────────
@app.get("/earnings-debug/{symbol}")
async def earnings_debug(symbol: str):
    """Debug: try all Yahoo Finance endpoints for earnings"""
    from datetime import datetime
    sym = symbol.upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://finance.yahoo.com/",
        "Accept": "application/json",
    }
    results = {}
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
        # Test quoteSummary calendarEvents
        try:
            r = await client.get(
                f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}",
                params={"modules": "calendarEvents"}
            )
            data = r.json()
            res = (data.get("quoteSummary",{}).get("result") or [{}])[0]
            cal = res.get("calendarEvents",{})
            results["v10_calendarEvents"] = {"status": r.status_code, "data": cal}
        except Exception as e:
            results["v10_calendarEvents"] = {"error": str(e)}

        # Test quote endpoint
        try:
            r = await client.get(
                f"https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": sym, "fields": "earningsDate,earningsTimestamp"}
            )
            data = r.json()
            quote = data.get("quoteResponse",{}).get("result",[{}])[0]
            results["v7_quote_earnings"] = {
                "status": r.status_code,
                "earningsDate": quote.get("earningsDate"),
                "earningsTimestamp": quote.get("earningsTimestamp"),
                "earningsCurrentEstimate": quote.get("earningsCurrentEstimate"),
            }
        except Exception as e:
            results["v7_quote"] = {"error": str(e)}

    return results

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "v3.3",
            "journals": ["tradier/live","tradier/sandbox","tt/live","tt/sandbox"]}

# ── Static ────────────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root(): return FileResponse("static/index.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
