"""
Uptime Tracker
──────────────
Lightweight, dependency-free persistence layer that records every service
health check result and computes rolling uptime percentages (24h / 7d / 30d).

Uses a small local SQLite file so it works out of the box on Render's free
tier without needing a Postgres migration. Safe for concurrent async access
because each call opens/closes its own short-lived connection.

P0 (Task 9-c2 + Wave 0.1): this module is SQLite-only by design. In
production the uptime history is DISABLED loudly (the degradation flag no
longer permits SQLite fallback; CRITICAL logged once via core.degraded_mode):
``record_check`` becomes a no-op, and read helpers return "no data" (None / [])
instead of ever touching an ephemeral file. Dev/test behaviour is unchanged.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta

from core.degraded_mode import sqlite_fallback_allowed

_DB_PATH = os.environ.get(
    "UPTIME_DB_PATH",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "uptime_history.db"
    ),
)
_LOCK = threading.Lock()
_LOGGER = logging.getLogger(__name__)


def _sqlite_ok() -> bool:
    """P0 gate — lazy, evaluated at first use so boot never crashes."""
    return sqlite_fallback_allowed("uptime_tracker")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=5)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS uptime_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            status TEXT NOT NULL,
            response_time_ms REAL,
            checked_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_uptime_service_time ON uptime_checks(service_name, checked_at)"
    )
    return conn


def record_check(service_name: str, status: str, response_time_ms: float | None = None) -> None:
    """Persist a single health-check result without breaking the health check.

    Persistence is deliberately best-effort because telemetry storage must not
    turn a healthy service into an unhealthy health endpoint. Failures are,
    however, logged with a traceback so storage incidents remain observable.
    """
    try:
        if not _sqlite_ok():
            # P0: uptime history disabled in production (no durable backend).
            return
        with _LOCK, _connect() as conn:
            conn.execute(
                "INSERT INTO uptime_checks (service_name, status, response_time_ms, checked_at) "
                "VALUES (?, ?, ?, ?)",
                (service_name, status, response_time_ms, datetime.utcnow().isoformat()),
            )
            cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
            conn.execute("DELETE FROM uptime_checks WHERE checked_at < ?", (cutoff,))
    except Exception:
        _LOGGER.exception(
            "Failed to persist uptime check for service=%r status=%r",
            service_name,
            status,
        )


def get_uptime_percentage(service_name: str, hours: int) -> float | None:
    """Return % of checks that were 'healthy' in the last `hours`, or None if no data."""
    try:
        if not _sqlite_ok():
            # P0: no history is recorded when the SQLite fallback is refused.
            return None
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with _connect() as conn:
            row = conn.execute(
                "SELECT "
                "  SUM(CASE WHEN status = 'healthy' THEN 1 ELSE 0 END) as ok, "
                "  COUNT(*) as total "
                "FROM uptime_checks WHERE service_name = ? AND checked_at >= ?",
                (service_name, cutoff),
            ).fetchone()
        if not row or not row[1]:
            return None
        ok, total = row
        return round((ok / total) * 100, 2)
    except Exception:
        _LOGGER.exception(
            "Failed to calculate uptime percentage for service=%r hours=%d",
            service_name,
            hours,
        )
        return None


def get_uptime_summary(service_name: str) -> dict:
    """Convenience helper returning 24h/7d/30d uptime percentages for one service."""
    return {
        "uptime_24h": get_uptime_percentage(service_name, 24),
        "uptime_7d": get_uptime_percentage(service_name, 24 * 7),
        "uptime_30d": get_uptime_percentage(service_name, 24 * 30),
    }


def get_history(service_name: str, hours: int = 24) -> list[dict]:
    """Return raw check history for charting (oldest first)."""
    try:
        if not _sqlite_ok():
            # P0: no history is recorded when the SQLite fallback is refused.
            return []
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT status, response_time_ms, checked_at FROM uptime_checks "
                "WHERE service_name = ? AND checked_at >= ? ORDER BY checked_at ASC",
                (service_name, cutoff),
            ).fetchall()
        return [{"status": r[0], "response_time_ms": r[1], "checked_at": r[2]} for r in rows]
    except Exception:
        _LOGGER.exception(
            "Failed to read uptime history for service=%r hours=%d",
            service_name,
            hours,
        )
        return []
