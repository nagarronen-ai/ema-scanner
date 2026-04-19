"""
SQLite database for EMA Scanner v3.1
Multi-broker journal: tradier-live, tradier-sandbox, tt-live, tt-sandbox
"""
import sqlite3
import json
import os

if os.path.exists('/data'):
    DB_PATH = '/data/scanner.db'
else:
    DB_PATH = os.environ.get("DB_PATH", "data/scanner.db")

VALID_BROKERS = {'tradier', 'tt'}
VALID_ENVS    = {'live', 'sandbox'}

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
                    key        TEXT PRIMARY KEY,
                    value      TEXT NOT NULL,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
            """)

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

    # ── Journal (per broker + env) ─────────────────────────────────────────────
    def journal_key(self, broker: str, env: str) -> str:
        b = broker.lower() if broker in VALID_BROKERS else 'tradier'
        e = env.lower() if env in VALID_ENVS else 'sandbox'
        return f"journal_{b}_{e}"

    def get_journal(self, broker: str, env: str) -> list:
        return self._get(self.journal_key(broker, env), [])

    def save_journal(self, broker: str, env: str, trades: list):
        """Merge — never lose closed trades"""
        existing = self.get_journal(broker, env)
        existing_ids = {str(t.get('orderId', '')) for t in existing}
        # Add new entries not already stored
        merged = existing[:]
        for t in trades:
            if str(t.get('orderId', '')) not in existing_ids:
                merged.append(t)
            else:
                # Update existing entry
                idx = next((i for i, e in enumerate(merged)
                            if str(e.get('orderId')) == str(t.get('orderId'))), None)
                if idx is not None:
                    merged[idx] = t
        self._set(self.journal_key(broker, env), merged)

    # ── Permanent closed trades ────────────────────────────────────────────────
    def get_closed_trades(self) -> list:
        return self._get("closed_trades_permanent", [])

    def save_closed_trades(self, trades: list):
        existing = self._get("closed_trades_permanent", [])
        if not trades and existing:
            return  # Never clear with empty list
        existing_ids = {str(e.get('orderId', '')) for e in existing}
        new = [t for t in trades if str(t.get('orderId', '')) not in existing_ids]
        self._set("closed_trades_permanent", existing + new)

    # ── Settings ──────────────────────────────────────────────────────────────
    def get_settings(self):
        return self._get("settings", {})

    def save_settings(self, data: dict):
        self._set("settings", data)

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
