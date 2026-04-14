"""
EMA Crossover Scanner — FastAPI Backend
"""
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional, List, Any
import uvicorn
import json
from database import Database

app = FastAPI(title="EMA Scanner")
db = Database()

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
def save_settings(data: dict):
    db.save_settings(data)
    return {"ok": True}

# ── Trade Log ─────────────────────────────────────────────────────────────────
@app.get("/api/trades")
def get_trades():
    return db.get_trades()

@app.post("/api/trades")
def save_trades(trades: List[Any]):
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
def save_lists(data: dict):
    db.save_lists(data)
    return {"ok": True}

# ── Scan Cache ────────────────────────────────────────────────────────────────
@app.get("/api/cache/bars")
def get_bars_cache():
    return db.get_bars_cache()

@app.post("/api/cache/bars")
def save_bars_cache(data: dict):
    db.save_bars_cache(data)
    return {"ok": True}

@app.get("/api/cache/results")
def get_results_cache():
    return db.get_results_cache()

@app.post("/api/cache/results")
def save_results_cache(data: dict):
    db.save_results_cache(data)
    return {"ok": True}

# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "version": "v2.9"}

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
