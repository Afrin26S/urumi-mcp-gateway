import os
import sqlite3
import threading
from datetime import datetime, timezone

import config  # noqa: F401

DB_PATH = os.environ.get("GATEWAY_DB_PATH", "gateway.db")
_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin','member')),
  password_hash TEXT NOT NULL,
  disabled INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id),
  name TEXT NOT NULL,
  prefix TEXT NOT NULL UNIQUE,
  key_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT,
  revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS servers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  url TEXT NOT NULL,
  auth_type TEXT NOT NULL DEFAULT 'none' CHECK (auth_type IN ('none','bearer','header')),
  header_name TEXT,
  credential_enc TEXT,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user_id INTEGER,
  user_email TEXT,
  source TEXT NOT NULL,
  server_slug TEXT,
  tool TEXT,
  duration_ms INTEGER,
  outcome TEXT NOT NULL,
  error TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")  # always UTC, ISO 8601


def conn() -> sqlite3.Connection:
    c = getattr(_local, "conn", None)  # one connection per thread: sqlite3 connections are not thread-safe
    if c is None:
        c = sqlite3.connect(DB_PATH, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")  # readers don't block the writer
        c.execute("PRAGMA foreign_keys=ON")
        _local.conn = c
    return c


def init_db() -> None:
    conn().executescript(SCHEMA)


def query(sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn().execute(sql, params).fetchall()]


def one(sql: str, params: tuple = ()) -> dict | None:
    row = conn().execute(sql, params).fetchone()
    return dict(row) if row else None


def execute(sql: str, params: tuple = ()) -> int:
    c = conn()
    cur = c.execute(sql, params)
    c.commit()
    return cur.lastrowid or 0