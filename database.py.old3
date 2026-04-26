"""
SQLite database for EMA Scanner v3.4
Multi-broker journal + encrypted credentials at rest
"""
import sqlite3, json, os, base64, secrets, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

if os.path.exists('/data'):
    DB_PATH = '/data/scanner.db'
else:
    DB_PATH = os.environ.get("DB_PATH", "data/scanner.db")

# Server-side encryption key derived from environment variable
# Set ENCRYPTION_KEY in Railway environment for production
SERVER_SECRET = os.environ.get("ENCRYPTION_KEY", "default-dev-key-change-in-prod-please")

def _derive_key():
    """Derive 32-byte AES key from server secret"""
    return hashlib.sha256(SERVER_SECRET.encode()).digest()

def _encrypt(plaintext: str) -> str:
    """Encrypt string with AES-GCM, return base64(nonce + ciphertext)"""
    key = _derive_key()
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()

def _decrypt(stored: str) -> str:
    """Decrypt AES-GCM blob"""
    key = _derive_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(stored)
    nonce, ct = raw[:12], raw[12:]
    return aesgcm.decrypt(nonce, ct, None).decode()

VALID_BROKERS = {'tradier', 'tt'}
VALID_ENVS    = {'live', 'sandbox'}
SENSITIVE_KEYS = {'credentials', 'tt_credentials', 'tradier_credentials',
                  'finnhub_key', 'admin_token_hash'}

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
                    encrypted  INTEGER DEFAULT 0,
                    updated_at TEXT DEFAULT (datetime('now'))
                );
            """)
            # Migration: add encrypted column if not exists
            try:
                conn.execute("ALTER TABLE kv ADD COLUMN encrypted INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

    def _get(self, key, default=None):
        with self._conn() as conn:
            row = conn.execute("SELECT value, encrypted FROM kv WHERE key=?", (key,)).fetchone()
            if not row:
                return default
            value = row["value"]
            if row["encrypted"]:
                try:
                    value = _decrypt(value)
                except Exception:
                    return default
            try:
                return json.loads(value)
            except Exception:
                return default

    def _set(self, key, value):
        encrypted = 1 if key in SENSITIVE_KEYS else 0
        serialized = json.dumps(value, ensure_ascii=False)
        if encrypted:
            serialized = _encrypt(serialized)
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv(key,value,encrypted,updated_at) VALUES(?,?,?,datetime('now'))",
                (key, serialized, encrypted)
            )

    # ── Admin token (PBKDF2 hash) ────────────────────────────────────────────
    def set_admin_token(self, token: str):
        """Hash and store admin token"""
        salt = secrets.token_bytes(16)
        h = hashlib.pbkdf2_hmac('sha256', token.encode(), salt, 100000)
        self._set("admin_token_hash", {
            "salt": base64.b64encode(salt).decode(),
            "hash": base64.b64encode(h).decode()
        })

    def verify_admin_token(self, token: str) -> bool:
        """Verify admin token against stored hash"""
        stored = self._get("admin_token_hash")
        if not stored:
            # No admin set — allow first write to set it
            return True
        salt = base64.b64decode(stored["salt"])
        expected = base64.b64decode(stored["hash"])
        actual = hashlib.pbkdf2_hmac('sha256', token.encode(), salt, 100000)
        return secrets.compare_digest(expected, actual)

    def is_admin_set(self) -> bool:
        return self._get("admin_token_hash") is not None

    # ── Credentials (encrypted) ──────────────────────────────────────────────
    def get_credentials(self):
        return self._get("credentials", {})

    def save_credentials(self, data):
        self._set("credentials", data)

    # ── Finnhub key (encrypted) ──────────────────────────────────────────────
    def get_finnhub_key(self):
        return self._get("finnhub_key", "")

    def save_finnhub_key(self, key: str):
        self._set("finnhub_key", key)

    # ── Journal ──────────────────────────────────────────────────────────────
    def journal_key(self, broker, env):
        b = broker.lower() if broker in VALID_BROKERS else 'tradier'
        e = env.lower() if env in VALID_ENVS else 'sandbox'
        return f"journal_{b}_{e}"

    def get_journal(self, broker, env):
        return self._get(self.journal_key(broker, env), [])

    def save_journal(self, broker, env, trades):
        existing = self.get_journal(broker, env)
        existing_ids = {str(t.get('orderId', '')) for t in existing}
        merged = existing[:]
        for t in trades:
            tid = str(t.get('orderId', ''))
            if tid not in existing_ids:
                merged.append(t)
            else:
                idx = next((i for i, e in enumerate(merged)
                            if str(e.get('orderId')) == tid), None)
                if idx is not None:
                    merged[idx] = t
        self._set(self.journal_key(broker, env), merged)

    # ── Closed trades ────────────────────────────────────────────────────────
    def get_closed_trades(self):
        return self._get("closed_trades_permanent", [])

    def save_closed_trades(self, trades):
        if not isinstance(trades, list):
            return
        self._set("closed_trades_permanent", trades)

    # ── Settings, Lists, Cache ───────────────────────────────────────────────
    def get_settings(self): return self._get("settings", {})
    def save_settings(self, data): self._set("settings", data)

    def get_lists(self):
        return self._get("lists", {})

    def save_lists(self, data):
        existing = self._get("lists", {}) or {}
        if not isinstance(data, dict):
            return
        merged = {**existing, **data}
        self._set("lists", merged)

    def get_bars_cache(self): return self._get("bars_cache", {"ts": 0, "cache": []})
    def save_bars_cache(self, data): self._set("bars_cache", data)

    def get_results_cache(self): return self._get("results_cache", {"ts": 0, "data": []})
    def save_results_cache(self, data): self._set("results_cache", data)
