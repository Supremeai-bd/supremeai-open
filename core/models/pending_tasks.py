import enum
import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from core.degraded_mode import sqlite_fallback_allowed

# ---------------------------------------------------------------------------
# AUD-4 hardening (P0): the previous implementation stored approvals in plain
# sqlite with NO tenant/owner binding (AUD-4.1), NO expiration (AUD-4.2),
# unconditional status updates (replay of approved/rejected tasks was possible,
# AUD-4.3), NO payload integrity check (AUD-4.4), NO duplicate-execution guard
# (AUD-4.5) and NO atomic compare-and-set transition (concurrent approvals both
# "succeeded", AUD-4.6). This module now enforces all of those invariants.
# ---------------------------------------------------------------------------

DEFAULT_APPROVAL_TTL_SECONDS = 24 * 60 * 60  # 24h approval validity window


class TaskType(enum.StrEnum):
    CODE_PUSH = "CODE_PUSH"
    NEW_SITE_VISIT = "NEW_SITE_VISIT"
    SKILL_GENERATION = "SKILL_GENERATION"
    VPN_SWITCH = "VPN_SWITCH"
    AUTO_EVOLUTION_PATCH = "AUTO_EVOLUTION_PATCH"
    # M17 P-D (seven→one): HITLEngine suspend-র canonical mirror —
    # দ্বৈত-লেখা পর্বে উভয় store-ই সত্য; cutover-এর পরে pending_tasks-ই একমাত্র।
    HITL_SUSPENSION = "HITL_SUSPENSION"


class TaskStatus(enum.StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"


# AUD-4.6: legal transitions out of PENDING (single canonical state machine).
_ALLOWED_FINAL_STATES = {TaskStatus.APPROVED, TaskStatus.REJECTED, TaskStatus.CANCELLED}


class ApprovalStateError(Exception):
    """Raised when an approval transition violates the state machine (AUD-4.3/4.5/4.6)."""


class TaskExpiredError(ApprovalStateError):
    """Raised when a decision is attempted on an expired approval (AUD-4.3)."""


class TaskAlreadyResolvedError(ApprovalStateError):
    """Raised when a decision is attempted on an already-resolved task (replay/duplicate)."""


class PayloadTamperedError(ApprovalStateError):
    """Raised when the stored payload hash does not match the recomputed hash (AUD-4.4)."""


class PendingTask(BaseModel):
    task_id: str
    task_type: TaskType
    payload: dict
    status: TaskStatus
    created_at: str
    resolved_by: str | None = None
    resolved_at: str | None = None
    reason: str | None = None
    # AUD-4.1: ownership / tenant binding.
    created_by: str | None = None
    tenant_id: str | None = None
    # AUD-4.8: risk classification for approval-level routing.
    risk_level: str = "medium"
    # AUD-4.2: expiration bound.
    expires_at: str | None = None
    # AUD-4.4/4.9: tamper-evident integrity hash of the canonical payload.
    payload_hash: str | None = None
    execution_id: str | None = None
    execution_status: str = "pending"
    execution_started_at: str | None = None
    execution_finished_at: str | None = None
    execution_error: str | None = None
    idempotency_key: str | None = None


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "pending_tasks.db"


def compute_payload_hash(payload: dict) -> str:
    """Canonical SHA-256 over the sorted-JSON payload (AUD-4.4 tamper evidence)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _get_conn():
    # P0 (Task 9-c2 + Wave 0.1): SQLite-only-by-design. In production the
    # ephemeral pending_tasks.db file is REFUSED unconditionally (the
    # degradation flag no longer permits SQLite fallback; CRITICAL logged once
    # by core.degraded_mode). The module must not
    # 500-crash its callers (approval routes, ecosystem workflow, tests), so the
    # degraded mode hands out a fresh IN-MEMORY connection per call: the schema
    # still auto-creates, reads return empty lists and writes are per-process
    # only — the feature is loudly disabled, never silently persisted.
    degraded = not sqlite_fallback_allowed("pending_tasks")
    if degraded:
        # Fresh per-call in-memory DB: schema auto-creates, but NOTHING survives
        # the connection — persistence is loudly disabled, never falsely durable.
        conn = sqlite3.connect(":memory:", timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
    else:
        # বাংলা মন্তব্য: ডাটাবেস ডিরেক্টরি তৈরি এবং অটোমেটিক টেবিল ও ইনডেক্স ইনিশিয়ালাইজেশন
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_tasks (
            task_id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            resolved_by TEXT,
            resolved_at TEXT,
            reason TEXT,
            created_by TEXT,
            tenant_id TEXT,
            risk_level TEXT DEFAULT 'medium',
            expires_at TEXT,
            payload_hash TEXT,
            execution_id TEXT,
            execution_status TEXT DEFAULT 'pending',
            execution_started_at TEXT,
            execution_finished_at TEXT,
            execution_error TEXT,
            idempotency_key TEXT UNIQUE
        )
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_pending_status_time ON pending_tasks(status, created_at)
        """)
    # Lightweight migration for pre-existing databases (add missing columns).
    existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(pending_tasks)").fetchall()}
    migrations = {
        "created_by": "ALTER TABLE pending_tasks ADD COLUMN created_by TEXT",
        "tenant_id": "ALTER TABLE pending_tasks ADD COLUMN tenant_id TEXT",
        "risk_level": "ALTER TABLE pending_tasks ADD COLUMN risk_level TEXT DEFAULT 'medium'",
        "expires_at": "ALTER TABLE pending_tasks ADD COLUMN expires_at TEXT",
        "payload_hash": "ALTER TABLE pending_tasks ADD COLUMN payload_hash TEXT",
        "execution_id": "ALTER TABLE pending_tasks ADD COLUMN execution_id TEXT",
        "execution_status": "ALTER TABLE pending_tasks ADD COLUMN execution_status TEXT DEFAULT 'pending'",
        "execution_started_at": "ALTER TABLE pending_tasks ADD COLUMN execution_started_at TEXT",
        "execution_finished_at": "ALTER TABLE pending_tasks ADD COLUMN execution_finished_at TEXT",
        "execution_error": "ALTER TABLE pending_tasks ADD COLUMN execution_error TEXT",
        "idempotency_key": "ALTER TABLE pending_tasks ADD COLUMN idempotency_key TEXT",
    }
    for col, ddl in migrations.items():
        if col not in existing_cols:
            conn.execute(ddl)
    conn.commit()
    return conn


def create_pending_task(
    task_type: TaskType,
    payload: dict,
    created_by: str = "system",
    tenant_id: str | None = None,
    risk_level: str = "medium",
    ttl_seconds: int | None = None,
    idempotency_key: str | None = None,
) -> PendingTask:
    """Create a PENDING approval bound to its owner/tenant with a TTL (AUD-4.1/4.2)."""
    now = datetime.now(UTC)
    ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_APPROVAL_TTL_SECONDS
    task = PendingTask(
        task_id=str(uuid.uuid4()),
        task_type=task_type,
        payload=payload,
        status=TaskStatus.PENDING,
        created_at=now.isoformat(),
        created_by=created_by,
        tenant_id=tenant_id,
        risk_level=risk_level,
        expires_at=(now + timedelta(seconds=ttl)).isoformat(),
        payload_hash=compute_payload_hash(payload),
        execution_id=f"exec_{uuid.uuid4().hex}",
        idempotency_key=idempotency_key,
    )
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO pending_tasks (
            task_id, task_type, payload, status, created_at,
            resolved_by, resolved_at, reason,
            created_by, tenant_id, risk_level, expires_at, payload_hash,
            execution_id, execution_status, idempotency_key
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            task.task_id,
            task.task_type,
            json.dumps(task.payload),
            task.status,
            task.created_at,
            task.resolved_by,
            task.resolved_at,
            task.reason,
            task.created_by,
            task.tenant_id,
            task.risk_level,
            task.expires_at,
            task.payload_hash,
            task.execution_id,
            task.execution_status,
            task.idempotency_key,
        ),
    )
    conn.commit()
    conn.close()
    return task


def list_pending(tenant_id: str | None = None) -> list[PendingTask]:
    """List pending approvals; optionally scoped to a tenant (AUD-2.2/4.1)."""
    conn = _get_conn()
    cursor = conn.cursor()
    now_iso = datetime.now(UTC).isoformat()
    if tenant_id is not None:
        cursor.execute(
            """
            SELECT * FROM pending_tasks
            WHERE status = ? AND tenant_id = ? AND (expires_at IS NULL OR expires_at > ?)
            """,
            (TaskStatus.PENDING, tenant_id, now_iso),
        )
    else:
        cursor.execute(
            "SELECT * FROM pending_tasks WHERE status = ? AND (expires_at IS NULL OR expires_at > ?)",
            (TaskStatus.PENDING, now_iso),
        )
    rows = cursor.fetchall()
    conn.close()
    return [row_to_task(row) for row in rows]


def get_task(task_id: str) -> PendingTask | None:
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pending_tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_task(row) if row else None


def get_task_by_idempotency(idempotency_key: str) -> PendingTask | None:
    """Fetch a task by its unique idempotency key (M17 P-D mirror lookup)."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM pending_tasks WHERE idempotency_key = ?", (idempotency_key,))
    row = cursor.fetchone()
    conn.close()
    return row_to_task(row) if row else None


def update_task_status(
    task_id: str,
    status: TaskStatus,
    resolved_by: str,
    reason: str | None = None,
    expected_payload_hash: str | None = None,
    tenant_id: str | None = None,
) -> PendingTask | None:
    """Atomically resolve a PENDING task (AUD-4.3/4.5/4.6).

    The UPDATE is a compare-and-set: it only succeeds when the row is still
    PENDING and unexpired, so concurrent decisions and replays of already
    resolved tasks cannot go through. Raises:
      * ``TaskAlreadyResolvedError`` — the task was already approved/rejected/cancelled/executed;
      * ``TaskExpiredError`` — the approval TTL elapsed before the decision;
      * ``PayloadTamperedError`` — the stored payload hash no longer matches
        (or does not match ``expected_payload_hash`` when supplied).
    Returns ``None`` when the task does not exist.
    """
    if status not in _ALLOWED_FINAL_STATES:
        raise ApprovalStateError(f"Cannot transition task directly to {status}")

    conn = _get_conn()
    cursor = conn.cursor()
    now_iso = datetime.now(UTC).isoformat()
    resolved_at = now_iso

    # AUD-4.4: verify payload integrity before deciding.
    cursor.execute(
        "SELECT payload, payload_hash, status, expires_at, tenant_id FROM pending_tasks WHERE task_id = ?",
        (task_id,),
    )
    row = cursor.fetchone()
    if row is None:
        conn.close()
        return None

    stored_hash = row["payload_hash"]
    recomputed = compute_payload_hash(json.loads(row["payload"]))
    if stored_hash is not None and stored_hash != recomputed:
        conn.close()
        raise PayloadTamperedError("Stored approval payload failed integrity check")
    if expected_payload_hash is not None and expected_payload_hash != recomputed:
        conn.close()
        raise PayloadTamperedError("Supplied payload hash does not match the stored approval")

    # AUD-4.3: expired approvals can no longer be decided.
    expires_at = row["expires_at"]
    if expires_at and expires_at <= now_iso:
        conn.close()
        raise TaskExpiredError(f"Approval {task_id} expired at {expires_at}")

    # AUD-4.6: atomic compare-and-set — only PENDING rows can transition.
    cursor.execute(
        """
        UPDATE pending_tasks
        SET status = ?, resolved_by = ?, resolved_at = ?, reason = ?
        WHERE task_id = ? AND status = ? AND (? IS NULL OR tenant_id = ?)
        """,
        (
            status,
            resolved_by,
            resolved_at,
            reason,
            task_id,
            TaskStatus.PENDING,
            tenant_id,
            tenant_id,
        ),
    )
    if cursor.rowcount == 0:
        cursor.execute("SELECT status FROM pending_tasks WHERE task_id = ?", (task_id,))
        current = cursor.fetchone()
        conn.close()
        if current is None:
            return None
        raise TaskAlreadyResolvedError(
            f"Approval {task_id} already resolved (status={current['status']})"
        )
    conn.commit()
    cursor.execute("SELECT * FROM pending_tasks WHERE task_id = ?", (task_id,))
    task_row = cursor.fetchone()
    conn.close()
    return row_to_task(task_row) if task_row else None


def mark_execution_started(task_id: str) -> PendingTask | None:
    """Atomically claim an approved task for execution exactly once."""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now(UTC).isoformat()
    cursor.execute(
        "UPDATE pending_tasks SET execution_status = 'running', execution_started_at = ? WHERE task_id = ? AND status = ? AND execution_status = 'pending'",
        (now, task_id, TaskStatus.APPROVED),
    )
    if cursor.rowcount == 0:
        conn.close()
        raise TaskAlreadyResolvedError(f"Task {task_id} is not claimable for execution")
    conn.commit()
    cursor.execute("SELECT * FROM pending_tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_task(row) if row else None


def mark_execution_result(
    task_id: str, *, success: bool, error: str | None = None
) -> PendingTask | None:
    """Persist the terminal execution result; repeated terminal writes are rejected."""
    conn = _get_conn()
    cursor = conn.cursor()
    now = datetime.now(UTC).isoformat()
    cursor.execute(
        "UPDATE pending_tasks SET status = ?, execution_status = ?, execution_finished_at = ?, execution_error = ? WHERE task_id = ? AND status = ? AND execution_status = 'running'",
        (
            TaskStatus.EXECUTED if success else TaskStatus.APPROVED,
            "succeeded" if success else "failed",
            now,
            error,
            task_id,
            TaskStatus.APPROVED,
        ),
    )
    if cursor.rowcount == 0:
        conn.close()
        raise TaskAlreadyResolvedError(f"Task {task_id} has no running execution")
    conn.commit()
    cursor.execute("SELECT * FROM pending_tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_task(row) if row else None


def mark_executed(task_id: str, executed_by: str) -> PendingTask | None:
    """Record post-approval execution (AUD-4.5: duplicate executions are rejected)."""
    conn = _get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE pending_tasks
        SET status = ?, resolved_by = ?, resolved_at = ?
        WHERE task_id = ? AND status = ?
        """,
        (
            TaskStatus.EXECUTED,
            executed_by,
            datetime.now(UTC).isoformat(),
            task_id,
            TaskStatus.APPROVED,
        ),
    )
    if cursor.rowcount == 0:
        conn.close()
        raise TaskAlreadyResolvedError(
            f"Task {task_id} is not in APPROVED state; cannot mark executed (duplicate guard)"
        )
    conn.commit()
    cursor.execute("SELECT * FROM pending_tasks WHERE task_id = ?", (task_id,))
    row = cursor.fetchone()
    conn.close()
    return row_to_task(row) if row else None


def cancel_task(
    task_id: str, cancelled_by: str, reason: str | None = None, tenant_id: str | None = None
) -> PendingTask | None:
    """Authoritative cancellation scoped to the owning tenant."""
    return update_task_status(
        task_id, TaskStatus.CANCELLED, cancelled_by, reason, tenant_id=tenant_id
    )


def row_to_task(row: sqlite3.Row) -> PendingTask:
    return PendingTask(
        task_id=row["task_id"],
        task_type=TaskType(row["task_type"]),
        payload=json.loads(row["payload"]),
        status=TaskStatus(row["status"]),
        created_at=row["created_at"],
        resolved_by=row["resolved_by"],
        resolved_at=row["resolved_at"],
        reason=row["reason"],
        created_by=row["created_by"] if "created_by" in row else None,
        tenant_id=row["tenant_id"] if "tenant_id" in row else None,
        risk_level=row["risk_level"] if "risk_level" in row and row["risk_level"] else "medium",
        expires_at=row["expires_at"] if "expires_at" in row else None,
        payload_hash=row["payload_hash"] if "payload_hash" in row else None,
        execution_id=row["execution_id"] if "execution_id" in row else None,
        execution_status=row["execution_status"]
        if "execution_status" in row and row["execution_status"]
        else "pending",
        execution_started_at=row["execution_started_at"] if "execution_started_at" in row else None,
        execution_finished_at=row["execution_finished_at"]
        if "execution_finished_at" in row
        else None,
        execution_error=row["execution_error"] if "execution_error" in row else None,
        idempotency_key=row["idempotency_key"] if "idempotency_key" in row else None,
    )
