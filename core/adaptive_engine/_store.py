"""Shared storage helpers for the ecosystem foundation layer.

বাংলা: ecosystem টেবিলগুলো pending_tasks.py-র একই self-contained SQLite প্যাটার্ন
ব্যবহার করে — কোন Alembic migration ছাড়াই idempotent auto-create হয়, WAL mode,
lightweight column migration সাপোর্ট। এটি production-এ zero-risk deploy দেয়।
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from core.degraded_mode import sqlite_fallback_allowed

# বাংলা: সব ecosystem table একই DB file-এ রাখা হয় — single WAL lock, সহজ backup।
_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = _DATA_DIR / "ecosystem.db"

_lock = threading.Lock()


def get_db_path() -> Path:
    """Return the canonical ecosystem SQLite path (created lazily).

    P0 (Task 9-c2): when the SQLite fallback is refused in production this
    returns the canonical path WITHOUT creating the data directory — callers
    that go through :func:`get_conn` get an in-memory database instead.
    """
    if not sqlite_fallback_allowed("ecosystem_store"):
        return _DB_PATH
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DB_PATH


def get_conn() -> sqlite3.Connection:
    """Open a short-lived, WAL-mode SQLite connection (audited pattern).

    P0 (Task 9-c2 + Wave 0.1): SQLite-only-by-design store. In production the
    ephemeral ecosystem.db file is REFUSED unconditionally (the degradation
    flag no longer permits SQLite fallback; CRITICAL logged once by
    core.degraded_mode) and every call gets a
    fresh IN-MEMORY connection: schema auto-creates via the usual
    ``CREATE TABLE IF NOT EXISTS`` calls, reads return empty results and writes
    are per-connection only — the feature is loudly disabled, never falsely
    durable. Dev/test behaviour is unchanged.
    """
    if not sqlite_fallback_allowed("ecosystem_store"):
        conn = sqlite3.connect(":memory:", timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_columns(conn: sqlite3.Connection, table: str, migrations: dict[str, str]) -> None:
    """Lightweight additive column migration (mirrors pending_tasks.py pattern)."""
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for col, ddl in migrations.items():
        if col not in existing:
            conn.execute(ddl)


def jdump(value: Any) -> str:
    """Canonical JSON for storage (sorted keys → stable hashes)."""
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def jload(value: str | None, default: Any = None) -> Any:
    if not value:
        return default if default is not None else {}
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default if default is not None else {}


__all__ = ["get_db_path", "get_conn", "ensure_columns", "jdump", "jload"]
