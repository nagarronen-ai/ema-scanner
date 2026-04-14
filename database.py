"""
SQLite database for EMA Scanner
Stores: trades, settings, my lists, scan cache
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.environ.get("DB_PATH", "data/scanner.db")

class Database:
    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kv (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
            """)

    # ── Generic key/value store ───────────────────────────────────────────────
    def _get(self, key, default=None):
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
            return json.loads(row["value"]) if row else default

    def _set(self, key, value):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv(key,value,updated_at) VALUES(?,?,datetime('now'))",
                (key, json.dumps(value, ensure_ascii=False))
            )

    # ── Settings ──────────────────────────────────────────────────────────────
    def get_settings(self):
        return self._get("settings", {
            "tradier_env": "sandbox",
            "tradier_token": "",
            "tradier_account": "",
            "rs_filter": "-2",
            "ema_tol": "0.5",
            "vol_mult": "1.5",
            "batch_size": "5",
            "atr_period": "14",
            "atr_mult": "1.5",
            "entry_max_dist": "3",
            "entry_lookback": "2",
        })

    def save_settings(self, data: dict):
        self._set("settings", data)

    # ── Trade Log ─────────────────────────────────────────────────────────────
    def get_trades(self):
        return self._get("trades", [])

    def save_trades(self, trades: list):
        self._set("trades", trades)

    def clear_trades(self):
        self._set("trades", [])

    # ── My Lists ──────────────────────────────────────────────────────────────
    def get_lists(self):
        return self._get("lists", {})

    def save_lists(self, data: dict):
        self._set("lists", data)

    # ── Scan Cache ────────────────────────────────────────────────────────────
    def get_bars_cache(self):
        return self._get("bars_cache", {"ts": 0, "cache": []})

    def save_bars_cache(self, data: dict):
        self._set("bars_cache", data)

    def get_results_cache(self):
        return self._get("results_cache", {"ts": 0, "data": []})

    def save_results_cache(self, data: dict):
        self._set("results_cache", data)
