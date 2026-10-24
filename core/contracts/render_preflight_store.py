"""Deterministic Render preflight storage layer.

Supports SQLite persistence for local testing/offline execution/CI,
and integrates with Supabase / PostgreSQL when available.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.contracts.redaction import redact as redact_secrets

DEFAULT_DB_PATH = Path("data/render_preflight.db")


class RenderPreflightStore:
    """Persistent store for Render account preflight records and audit events."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        if db_path is None:
            self.db_path = DEFAULT_DB_PATH
        elif str(db_path) == ":memory:":
            self.db_path = Path(":memory:")
        else:
            self.db_path = Path(db_path)

        if str(self.db_path) != ":memory:":
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        else:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)

        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS render_account_status (
                    id TEXT PRIMARY KEY,
                    account_role TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT 'render',
                    service_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason_code TEXT,
                    reason_message TEXT,
                    usage_minutes REAL,
                    safe_build_minutes REAL DEFAULT 450.0,
                    detected_at TEXT,
                    last_checked_at TEXT,
                    recheck_at TEXT,
                    reset_at TEXT,
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    last_render_payload TEXT,
                    manual_override INTEGER NOT NULL DEFAULT 0,
                    manual_override_by TEXT,
                    manual_override_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(provider, account_role, service_id)
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS render_preflight_events (
                    id TEXT PRIMARY KEY,
                    account_status_id TEXT NOT NULL,
                    workflow_run_id TEXT,
                    commit_sha TEXT,
                    event_type TEXT NOT NULL,
                    old_status TEXT,
                    new_status TEXT NOT NULL,
                    reason_code TEXT,
                    details TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS render_preflight_alerts (
                    id TEXT PRIMARY KEY,
                    account_role TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'warning',
                    message TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    resolved_at TEXT,
                    notification_status TEXT NOT NULL DEFAULT 'pending',
                    reason_code TEXT,
                    UNIQUE(account_role, reason_code, notification_status)
                )
                """
            )

    def get_account(self, role: str) -> dict[str, Any] | None:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM render_account_status WHERE account_role = ?", (role,))
        row = cursor.fetchone()
        if not row:
            return None
        data = dict(row)
        data["manual_override"] = bool(data["manual_override"])
        if data.get("last_render_payload"):
            try:
                data["last_render_payload"] = json.loads(data["last_render_payload"])
            except Exception as e:
                logging.getLogger(__name__).debug(f"Failed to parse last_render_payload JSON: {e}")
        return data

    def get_all_accounts(self) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM render_account_status ORDER BY account_role ASC")
        rows = cursor.fetchall()
        accounts = []
        for r in rows:
            data = dict(r)
            data["manual_override"] = bool(data["manual_override"])
            if data.get("last_render_payload"):
                try:
                    data["last_render_payload"] = json.loads(data["last_render_payload"])
                except Exception as e:
                    logging.getLogger(__name__).debug(
                        f"Failed to parse last_render_payload JSON: {e}"
                    )
            accounts.append(data)
        return accounts

    def upsert_account_and_record_event(
        self,
        account_role: str,
        service_id: str,
        status: str,
        reason_code: str | None = None,
        reason_message: str | None = None,
        usage_minutes: float | None = None,
        safe_build_minutes: float = 450.0,
        detected_at: str | None = None,
        recheck_at: str | None = None,
        reset_at: str | None = None,
        last_error: str | None = None,
        payload: Any = None,
        workflow_run_id: str | None = None,
        commit_sha: str | None = None,
        event_type: str = "check",
        increment_retry: bool = False,
        retry_count: int | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC).isoformat()
        clean_payload = json.dumps(redact_secrets(payload)) if payload is not None else None

        with self._conn:
            existing = self.get_account(account_role)
            old_status = existing["status"] if existing else None
            record_id = existing["id"] if existing else str(uuid.uuid4())
            if retry_count is not None:
                effective_retry = retry_count
            elif increment_retry:
                effective_retry = (existing["retry_count"] + 1) if existing else 1
            else:
                effective_retry = existing["retry_count"] if existing else 0

            # If transitioning to ready, clear recheck_at unless explicitly passed
            if status == "ready" and recheck_at is None:
                effective_recheck = None
            else:
                effective_recheck = (
                    recheck_at
                    if recheck_at is not None
                    else (existing.get("recheck_at") if existing else None)
                )

            effective_detected = (
                detected_at
                if detected_at is not None
                else (existing.get("detected_at") if existing else None)
            )

            self._conn.execute(
                """
                INSERT INTO render_account_status (
                    id, account_role, provider, service_id, status, reason_code, reason_message,
                    usage_minutes, safe_build_minutes, detected_at, last_checked_at, recheck_at,
                    reset_at, retry_count, last_error, last_render_payload, manual_override,
                    created_at, updated_at
                ) VALUES (?, ?, 'render', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                ON CONFLICT(provider, account_role, service_id) DO UPDATE SET
                    status=excluded.status,
                    reason_code=excluded.reason_code,
                    reason_message=excluded.reason_message,
                    usage_minutes=excluded.usage_minutes,
                    safe_build_minutes=excluded.safe_build_minutes,
                    detected_at=excluded.detected_at,
                    last_checked_at=excluded.last_checked_at,
                    recheck_at=excluded.recheck_at,
                    reset_at=excluded.reset_at,
                    retry_count=excluded.retry_count,
                    last_error=excluded.last_error,
                    last_render_payload=excluded.last_render_payload,
                    updated_at=excluded.updated_at
                """,
                (
                    record_id,
                    account_role,
                    service_id,
                    status,
                    reason_code,
                    reason_message,
                    usage_minutes,
                    safe_build_minutes,
                    effective_detected,
                    now,
                    effective_recheck,
                    reset_at,
                    effective_retry,
                    last_error,
                    clean_payload,
                    now,
                    now,
                ),
            )

            # Record audit event atomically
            event_id = str(uuid.uuid4())
            self._conn.execute(
                """
                INSERT INTO render_preflight_events (
                    id, account_status_id, workflow_run_id, commit_sha, event_type,
                    old_status, new_status, reason_code, details, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    record_id,
                    workflow_run_id,
                    commit_sha,
                    event_type,
                    old_status,
                    status,
                    reason_code,
                    clean_payload,
                    now,
                ),
            )

            return self.get_account(account_role) or {}

    def set_manual_override(
        self,
        account_role: str,
        override_by: str,
        reason: str,
    ) -> dict[str, Any]:
        existing = self.get_account(account_role)
        if not existing:
            raise ValueError(f"Account for role '{account_role}' does not exist.")

        now = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute(
                """
                UPDATE render_account_status
                SET status = 'ready',
                    manual_override = 1,
                    manual_override_by = ?,
                    manual_override_reason = ?,
                    updated_at = ?
                WHERE account_role = ?
                """,
                (override_by, reason, now, account_role),
            )

            # Record event
            event_id = str(uuid.uuid4())
            self._conn.execute(
                """
                INSERT INTO render_preflight_events (
                    id, account_status_id, event_type, old_status, new_status,
                    reason_code, details, created_at
                ) VALUES (?, ?, 'manual_override', ?, 'ready', 'admin_override', ?, ?)
                """,
                (
                    event_id,
                    existing["id"],
                    existing["status"],
                    json.dumps({"override_by": override_by, "reason": reason}),
                    now,
                ),
            )
        return self.get_account(account_role) or {}

    def get_events(self, account_role: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        cursor = self._conn.cursor()
        if account_role:
            account = self.get_account(account_role)
            if not account:
                return []
            cursor.execute(
                "SELECT * FROM render_preflight_events WHERE account_status_id = ? ORDER BY created_at DESC LIMIT ?",
                (account["id"], limit),
            )
        else:
            cursor.execute(
                "SELECT * FROM render_preflight_events ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        rows = cursor.fetchall()
        events = []
        for r in rows:
            data = dict(r)
            if data.get("details"):
                try:
                    data["details"] = json.loads(data["details"])
                except Exception as e:
                    logging.getLogger(__name__).debug(f"Failed to parse details JSON: {e}")
            events.append(data)
        return events
