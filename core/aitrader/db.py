"""SQLite persistence for AI-TRADER (stdlib only, WAL, thread-safe)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from typing import Any, Iterable

from .config import DB_PATH, SAFE_DEFAULTS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS providers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'openai',
    base_url TEXT NOT NULL,
    api_key_enc TEXT DEFAULT '',
    model TEXT NOT NULL,
    models_json TEXT DEFAULT '[]',
    headers_json TEXT DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    is_default INTEGER DEFAULT 0,
    last_status TEXT DEFAULT '',
    last_latency_ms INTEGER DEFAULT 0,
    last_checked REAL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS mcp_servers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    transport TEXT NOT NULL DEFAULT 'stdio',
    command TEXT DEFAULT '',
    args_json TEXT DEFAULT '[]',
    url TEXT DEFAULT '',
    env_json TEXT DEFAULT '{}',
    enabled INTEGER DEFAULT 1,
    auto_start INTEGER DEFAULT 0,
    category TEXT DEFAULT 'general',
    notes TEXT DEFAULT '',
    tools_json TEXT DEFAULT '[]',
    last_status TEXT DEFAULT 'stopped',
    last_error TEXT DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    path TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    source TEXT DEFAULT 'local',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    broker TEXT NOT NULL,
    environment TEXT NOT NULL DEFAULT 'paper',
    config_json TEXT DEFAULT '{}',
    secret_enc TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    status TEXT DEFAULT 'disconnected',
    last_error TEXT DEFAULT '',
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New chat',
    model TEXT DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    meta_json TEXT DEFAULT '{}',
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    account_id TEXT DEFAULT 'paper',
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    volume REAL NOT NULL DEFAULT 0,
    order_type TEXT DEFAULT 'market',
    price REAL DEFAULT 0,
    sl REAL DEFAULT 0,
    tp REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending_approval',
    risk_usd REAL DEFAULT 0,
    risk_pct REAL DEFAULT 0,
    reason TEXT DEFAULT '',
    ticket TEXT DEFAULT '',
    broker_response TEXT DEFAULT '',
    created_at REAL NOT NULL,
    approved_at REAL DEFAULT 0,
    closed_at REAL DEFAULT 0,
    pnl REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS positions (
    ticket TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    volume REAL NOT NULL,
    entry REAL NOT NULL,
    sl REAL DEFAULT 0,
    tp REAL DEFAULT 0,
    pnl REAL DEFAULT 0,
    status TEXT DEFAULT 'open',
    opened_at REAL NOT NULL,
    closed_at REAL DEFAULT 0,
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS approvals (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    conversation_id TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    created_at REAL NOT NULL,
    resolved_at REAL DEFAULT 0,
    result_json TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    actor TEXT DEFAULT 'system',
    action TEXT NOT NULL,
    detail TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS decisions (
    id TEXT PRIMARY KEY,
    ts REAL NOT NULL,
    account_id TEXT DEFAULT '',
    symbol TEXT NOT NULL,
    action TEXT NOT NULL,
    confidence REAL DEFAULT 0,
    price REAL DEFAULT 0,
    reason TEXT DEFAULT '',
    model TEXT DEFAULT '',
    status TEXT DEFAULT '',
    order_id TEXT DEFAULT '',
    risk_usd REAL DEFAULT 0,
    pnl REAL DEFAULT 0,
    votes_json TEXT DEFAULT '[]',
    snapshot_json TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_decisions_ts ON decisions(ts DESC);
CREATE TABLE IF NOT EXISTS equity_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    account_id TEXT NOT NULL,
    equity REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_equity_account ON equity_points(account_id, ts DESC);
"""


def new_id(prefix: str = "") -> str:
    raw = uuid.uuid4().hex[:16]
    return f"{prefix}{raw}" if prefix else raw


def now() -> float:
    return time.time()


class Database:
    def __init__(self, path=DB_PATH):
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # -- raw helpers -------------------------------------------------------
    def query(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: Iterable[Any] = ()) -> None:
        with self._lock:
            self._conn.execute(sql, tuple(params))
            self._conn.commit()

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, [tuple(r) for r in rows])
            self._conn.commit()

    # -- settings ----------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        if not row:
            return SAFE_DEFAULTS.get(key, default)
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def set_setting(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )

    def all_settings(self) -> dict:
        merged = dict(SAFE_DEFAULTS)
        for row in self.query("SELECT key,value FROM settings"):
            try:
                merged[row["key"]] = json.loads(row["value"])
            except json.JSONDecodeError:
                merged[row["key"]] = row["value"]
        return merged

    # -- audit -------------------------------------------------------------
    def audit(self, action: str, detail: str = "", actor: str = "system") -> None:
        self.execute(
            "INSERT INTO audit(ts,actor,action,detail) VALUES(?,?,?,?)",
            (now(), actor, action, detail[:4000]),
        )


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db
