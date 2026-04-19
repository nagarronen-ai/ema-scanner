"""
EMA Crossover Scanner — FastAPI Backend v3.0
Includes proxy for TastyTrade API (CORS bypass)
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import json
import os
import uvicorn
from database import Database

app = FastAPI(title="EMA Scanner")
db = Database()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── TastyTrade Proxy ──────────────────────────────────────────────────────────
TT_LIVE = "https://api.tastytrade.com"
TT_SANDBOX = "https://api.cert.tastyworks.com"

@app.api_route("/tt-proxy/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH"])
async def tt_proxy(path: str, request: Request):
    """Proxy all TastyTrade API calls to bypass CORS"""
    env = request.headers.get("X-TT-Env", "sandbox")
    base = TT_LIVE if env == "live" else TT_SANDBOX
    
    # Forward headers (auth token etc)
    headers = {k: v for k, v in request.headers.items() 
               if k.lower() not in ("host", "content-length", "x-tt-env")}
    
    body = await request.body()
    
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.request(
                method=request.method,
                url=f"{base}/{path}",
                headers=headers,
                content=body,
                params=dict(request.query_params)
            )
            return JSONResponse(
                content=resp.json() if resp.content else {},
                status_code=resp.status_code
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))

# ── Serve static files ────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def root():
    return FileResponse("static/index.html")

# ── Settings ──────────────────────────────────────────────────────────────────
@app.get("/api/settings")
def get_settings():
    return db.get_settings()

@app.post("/api/settings")
async def save_settings(request: Request):
    data = await request.json()
    db.save_settings(data)
    return {"ok": True}

# ── Trade Log ─────────────────────────────────────────────────────────────────
@app.get("/api/trades")
def get_trades():
    return db.get_trades()

@app.post("/api/trades")
async def save_trades(request: Request):
    trades = await request.json()
    db.save_trades(trades)
    return {"ok": True}

@app.delete("/api/trades")
def clear_trades():
    db.clear_trades()
    return {"ok": True}

# ── My Lists ──────────────────────────────────────────────────────────────────
@app.get("/api/lists")
def get_lists():
    return db.get_lists()

@app.post("/api/lists")
async def save_lists(request: Request):
    data = await request.json()
    db.save_lists(data)
    return {"ok": True}

# ── Scan Cache ────────────────────────────────────────────────────────────────
@app.get("/api/cache/bars")
def get_bars_cache():
    return db.get_bars_cache()

@app.post("/api/cache/bars")
async def save_bars_cache(request: Request):
    data = await request.json()
    db.save_bars_cache(data)
    return {"ok": True}

@app.get("/api/cache/results")
def get_results_cache():
    return db.get_results_cache()

@app.post("/api/cache/results")
async def save_results_cache(request: Request):
    data = await request.json()
    db.save_results_cache(data)
    return {"ok": True}

# ── Permanent Closed Trades ──────────────────────────────────────────────────
@app.get("/api/closed_trades")
def get_closed_trades():
    return db.get_closed_trades()

@app.post("/api/closed_trades")
async def save_closed_trades(request: Request):
    trades = await request.json()
    if isinstance(trades, list):
        db.save_closed_trades(trades)
    return {"ok": True}

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "v3.0"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
