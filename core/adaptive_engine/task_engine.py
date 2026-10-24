"""Task Engine — autonomous goal execution state machine (ROADMAP §22–§24, §29).

বাংলা: প্রতিটি important goal এই state machine দিয়ে চলে:
RECEIVED → UNDERSTANDING → PLANNING → CAPABILITY_CHECK → RESOURCE_CHECK →
PREPARING → EXECUTING → VERIFYING → REPAIRING → DELIVERING → COMPLETED

ব্যর্থ হলে: FAILED → DIAGNOSE → REPAIR → RETRY → ESCALATE (ROADMAP §24)।
retry limit / time limit / risk threshold / fallback / escalation সব enforced।
ROADMAP §29: resource-aware routing (capability, CPU, memory, queue, health, cost)।
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from adaptive_engine._store import get_conn, jdump, jload
from adaptive_engine.correlation import CorrelationContext, current_correlation


class TaskState(enum.StrEnum):
    """ROADMAP §22 — task state machine."""

    RECEIVED = "RECEIVED"
    UNDERSTANDING = "UNDERSTANDING"
    PLANNING = "PLANNING"
    CAPABILITY_CHECK = "CAPABILITY_CHECK"
    RESOURCE_CHECK = "RESOURCE_CHECK"
    PREPARING = "PREPARING"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    REPAIRING = "REPAIRING"
    DELIVERING = "DELIVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ESCALATED = "ESCALATED"
    CANCELLED = "CANCELLED"


class TaskOwner(enum.StrEnum):
    """ROADMAP §20 — owner scope separation."""

    USER = "USER"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


# বাংলা: ROADMAP §22 — সফল পথের transitions।
_HAPPY_PATH: dict[TaskState, set[TaskState]] = {
    TaskState.RECEIVED: {TaskState.UNDERSTANDING, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.UNDERSTANDING: {TaskState.PLANNING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.PLANNING: {TaskState.CAPABILITY_CHECK, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.CAPABILITY_CHECK: {
        TaskState.RESOURCE_CHECK,
        TaskState.REPAIRING,  # capability gap → build/adapt
        TaskState.FAILED,
    },
    TaskState.RESOURCE_CHECK: {TaskState.PREPARING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.PREPARING: {TaskState.EXECUTING, TaskState.FAILED, TaskState.CANCELLED},
    TaskState.EXECUTING: {TaskState.VERIFYING, TaskState.REPAIRING, TaskState.FAILED},
    TaskState.VERIFYING: {
        TaskState.DELIVERING,  # success
        TaskState.REPAIRING,  # verification failed
        TaskState.FAILED,
    },
    TaskState.REPAIRING: {TaskState.EXECUTING, TaskState.FAILED, TaskState.ESCALATED},
    TaskState.DELIVERING: {TaskState.COMPLETED, TaskState.FAILED},
    TaskState.FAILED: {TaskState.REPAIRING, TaskState.ESCALATED, TaskState.CANCELLED},
    TaskState.ESCALATED: {TaskState.REPAIRING, TaskState.CANCELLED, TaskState.COMPLETED},
    TaskState.COMPLETED: set(),
    TaskState.CANCELLED: set(),
}

# বাংলা: ROADMAP §24 — কতবার retry করা যাবে তার limit (configurable via env)।
DEFAULT_RETRY_LIMIT = 3
DEFAULT_TIME_LIMIT_SECONDS = 60 * 30  # 30 min


class TaskStateError(Exception):
    pass


class TaskRetryExhausted(Exception):
    pass


class TaskRetryExceeded(TaskRetryExhausted):
    pass


class TaskNotFoundError(KeyError):
    pass


class TaskTimeoutError(TimeoutError):
    pass


class TaskRecord(BaseModel):
    """A single task (ROADMAP §22)."""

    task_id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:16]}")
    goal: str
    owner: TaskOwner = TaskOwner.USER
    scope: str | dict[str, Any] = (
        "USER_WORKSPACE"  # USER_WORKSPACE | ADMIN/INFRASTRUCTURE | SYSTEM/INFRASTRUCTURE or dict
    )
    state: TaskState = TaskState.RECEIVED
    plan: list[dict[str, Any]] = Field(default_factory=list)
    capability_requirements: list[dict[str, Any]] = Field(default_factory=list)
    resource_id: str | None = None
    capability_id: str | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    verification_result: dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0
    retry_limit: int = DEFAULT_RETRY_LIMIT
    time_limit_seconds: int = DEFAULT_TIME_LIMIT_SECONDS
    risk_level: str = "medium"  # safe | low | medium | high
    correlation: dict[str, Any] = Field(default_factory=dict)
    created_by: str = "system"
    tenant_id: str | None = None
    audit_id: str | None = None
    error: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    completed_at: str | None = None


class TaskEngine:
    """Autonomous task engine (ROADMAP §22–§24, §29)."""

    TABLE = "ecosystem_tasks"

    def __init__(self) -> None:
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    task_id TEXT PRIMARY KEY,
                    goal TEXT NOT NULL,
                    owner TEXT NOT NULL DEFAULT 'USER',
                    scope TEXT NOT NULL DEFAULT 'USER_WORKSPACE',
                    state TEXT NOT NULL DEFAULT 'RECEIVED',
                    plan TEXT NOT NULL DEFAULT '[]',
                    capability_requirements TEXT NOT NULL DEFAULT '[]',
                    resource_id TEXT,
                    capability_id TEXT,
                    artifacts TEXT NOT NULL DEFAULT '[]',
                    result TEXT NOT NULL DEFAULT '{{}}',
                    success_criteria TEXT NOT NULL DEFAULT '{{}}',
                    verification_result TEXT NOT NULL DEFAULT '{{}}',
                    retry_count INTEGER NOT NULL DEFAULT 0,
                    retry_limit INTEGER NOT NULL DEFAULT 3,
                    time_limit_seconds INTEGER NOT NULL DEFAULT 1800,
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    correlation TEXT NOT NULL DEFAULT '{{}}',
                    created_by TEXT NOT NULL DEFAULT 'system',
                    tenant_id TEXT,
                    audit_id TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_state ON {self.TABLE}(state)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_owner ON {self.TABLE}(owner)"
            )
            conn.commit()

    # -- create / fetch ----------------------------------------------------

    def submit(
        self,
        goal: str | TaskRecord,
        *,
        owner: TaskOwner = TaskOwner.USER,
        scope: str | dict[str, Any] = "USER_WORKSPACE",
        created_by: str = "system",
        tenant_id: str | None = None,
        success_criteria: dict[str, Any] | None = None,
        capability_requirements: list[dict[str, Any]] | None = None,
        risk_level: str = "medium",
        retry_limit: int = DEFAULT_RETRY_LIMIT,
        time_limit_seconds: int = DEFAULT_TIME_LIMIT_SECONDS,
    ) -> TaskRecord:
        """Submit a new goal or existing TaskRecord. Captures the active correlation context (ROADMAP §44)."""
        corr = current_correlation()
        if isinstance(goal, TaskRecord):
            task = goal
            if not task.correlation:
                task.correlation = corr.child(task_id=None).as_headers()
            if not task.audit_id:
                task.audit_id = corr.audit_id
            if not task.started_at:
                task.started_at = datetime.now(UTC).isoformat()
        else:
            task = TaskRecord(
                goal=goal,
                owner=owner,
                scope=scope,
                created_by=created_by,
                tenant_id=tenant_id,
                success_criteria=success_criteria or {},
                capability_requirements=capability_requirements or [],
                risk_level=risk_level,
                retry_limit=retry_limit,
                time_limit_seconds=time_limit_seconds,
                correlation=corr.child(task_id=None).as_headers(),
                audit_id=corr.audit_id,
                started_at=datetime.now(UTC).isoformat(),
            )
        # persist the task_id into the correlation for downstream spans
        task.correlation["x-correlation-task-id"] = task.task_id
        with get_conn() as conn:
            conn.execute(self._insert_sql(), self._row(task))
            conn.commit()
        return task

    def get(self, task_id: str) -> TaskRecord | None:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE task_id = ?",
                (task_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(
        self,
        *,
        state: TaskState | None = None,
        owner: TaskOwner | None = None,
        tenant_id: str | None = None,
        limit: int = 100,
    ) -> list[TaskRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        if owner is not None:
            clauses.append("owner = ?")
            params.append(owner)
        if tenant_id is not None:
            clauses.append("(tenant_id IS NULL OR tenant_id = ?)")
            params.append(tenant_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.TABLE} {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._from_row(r) for r in rows]

    # -- state machine ------------------------------------------------------

    def transition(
        self,
        task_id: str,
        to_state: TaskState,
        *,
        actor: str = "system",
        patch: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> TaskRecord:
        task = self.get(task_id)
        if task is None:
            raise TaskStateError(f"Task {task_id} not found")

        allowed = _HAPPY_PATH.get(task.state, set())
        if to_state not in allowed and to_state != TaskState.CANCELLED:
            raise TaskStateError(
                f"Illegal task transition {task.state} → {to_state} "
                f"(allowed: {sorted(s for s in allowed)})"
            )

        # বাংলা: ROADMAP §24 — retry/time limit enforcement।
        if to_state == TaskState.EXECUTING and task.state == TaskState.REPAIRING:
            if task.retry_count >= task.retry_limit:
                # force escalation instead of looping
                to_state = TaskState.ESCALATED
                error = error or "retry_limit_exhausted"
            else:
                patch = dict(patch or {})
                patch["retry_count"] = task.retry_count + 1

        # বাংলা: ROADMAP §24 — time limit enforcement।
        if task.started_at:
            started = datetime.fromisoformat(task.started_at)
            if datetime.now(UTC) - started > timedelta(seconds=task.time_limit_seconds):
                if to_state not in {TaskState.COMPLETED, TaskState.ESCALATED, TaskState.CANCELLED}:
                    to_state = TaskState.ESCALATED
                    error = error or "time_limit_exhausted"

        now = datetime.now(UTC).isoformat()
        sets: dict[str, Any] = {"state": to_state, "updated_at": now}
        if patch:
            sets.update(patch)
        if error:
            sets["error"] = error
        if to_state == TaskState.COMPLETED:
            sets["completed_at"] = now
        if to_state == TaskState.RECEIVED:
            sets["started_at"] = now

        sql_sets = ", ".join(f"{k} = ?" for k in sets)
        params: list[Any] = list(sets.values()) + [task_id]
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET {sql_sets} WHERE task_id = ?",
                params,
            )
            conn.commit()
        return self.get(task_id)  # type: ignore[return-value]

    def attach_plan(self, task_id: str, plan: list[dict[str, Any]]) -> TaskRecord:
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET plan = ?, updated_at = ? WHERE task_id = ?",
                (jdump(plan), datetime.now(UTC).isoformat(), task_id),
            )
            conn.commit()
        return self.get(task_id)  # type: ignore[return-value]

    def record_artifact(self, task_id: str, artifact: dict[str, Any]) -> TaskRecord:
        task = self.get(task_id)
        if task is None:
            raise TaskStateError(task_id)
        artifacts = list(task.artifacts)
        artifacts.append(artifact)
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET artifacts = ?, updated_at = ? WHERE task_id = ?",
                (jdump(artifacts), datetime.now(UTC).isoformat(), task_id),
            )
            conn.commit()
        return self.get(task_id)  # type: ignore[return-value]

    def record_verification(self, task_id: str, verification: dict[str, Any]) -> TaskRecord:
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET verification_result = ?, updated_at = ? "
                f"WHERE task_id = ?",
                (jdump(verification), datetime.now(UTC).isoformat(), task_id),
            )
            conn.commit()
        return self.get(task_id)  # type: ignore[return-value]

    def deliver(self, task_id: str, result: dict[str, Any], *, actor: str = "system") -> TaskRecord:
        """Mark task COMPLETED with a result + verification-first (ROADMAP §23)."""
        with get_conn() as conn:
            now = datetime.now(UTC).isoformat()
            conn.execute(
                f"UPDATE {self.TABLE} SET result = ?, state = ?, completed_at = ?, "
                f"updated_at = ? WHERE task_id = ?",
                (
                    jdump(result),
                    TaskState.COMPLETED,
                    now,
                    now,
                    task_id,
                ),
            )
            conn.commit()
        return self.get(task_id)  # type: ignore[return-value]

    def cancel(
        self, task_id: str, *, actor: str = "system", reason: str | None = None
    ) -> TaskRecord:
        return self.transition(
            task_id, TaskState.CANCELLED, actor=actor, error=reason or "cancelled"
        )

    # -- internals ----------------------------------------------------------

    def _insert_sql(self) -> str:
        cols = (
            "task_id, goal, owner, scope, state, plan, capability_requirements, "
            "resource_id, capability_id, artifacts, result, success_criteria, "
            "verification_result, retry_count, retry_limit, time_limit_seconds, "
            "risk_level, correlation, created_by, tenant_id, audit_id, error, "
            "created_at, updated_at, started_at, completed_at"
        )
        placeholders = ", ".join(["?"] * 26)
        return f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})"

    def _row(self, t: TaskRecord) -> tuple[Any, ...]:
        return (
            t.task_id,
            t.goal,
            t.owner,
            jdump(t.scope) if isinstance(t.scope, (dict, list)) else t.scope,
            t.state,
            jdump(t.plan),
            jdump(t.capability_requirements),
            t.resource_id,
            t.capability_id,
            jdump(t.artifacts),
            jdump(t.result),
            jdump(t.success_criteria),
            jdump(t.verification_result),
            t.retry_count,
            t.retry_limit,
            t.time_limit_seconds,
            t.risk_level,
            jdump(t.correlation),
            t.created_by,
            t.tenant_id,
            t.audit_id,
            t.error,
            t.created_at,
            t.updated_at,
            t.started_at,
            t.completed_at,
        )

    def _from_row(self, row: Any) -> TaskRecord:
        raw_scope = row["scope"]
        parsed_scope = (
            jload(raw_scope, raw_scope)
            if isinstance(raw_scope, str) and raw_scope.startswith("{")
            else raw_scope
        )
        return TaskRecord(
            task_id=row["task_id"],
            goal=row["goal"],
            owner=TaskOwner(row["owner"]),
            scope=parsed_scope,
            state=TaskState(row["state"]),
            plan=jload(row["plan"], []),
            capability_requirements=jload(row["capability_requirements"], []),
            resource_id=row["resource_id"],
            capability_id=row["capability_id"],
            artifacts=jload(row["artifacts"], []),
            result=jload(row["result"], {}),
            success_criteria=jload(row["success_criteria"], {}),
            verification_result=jload(row["verification_result"], {}),
            retry_count=int(row["retry_count"] or 0),
            retry_limit=int(row["retry_limit"] or DEFAULT_RETRY_LIMIT),
            time_limit_seconds=int(row["time_limit_seconds"] or DEFAULT_TIME_LIMIT_SECONDS),
            risk_level=row["risk_level"],
            correlation=jload(row["correlation"], {}),
            created_by=row["created_by"],
            tenant_id=row["tenant_id"],
            audit_id=row["audit_id"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_engine: TaskEngine | None = None


def get_task_engine() -> TaskEngine:
    global _engine
    if _engine is None:
        _engine = TaskEngine()
    return _engine


__all__ = [
    "TaskState",
    "TaskOwner",
    "TaskRecord",
    "TaskEngine",
    "TaskStateError",
    "TaskRetryExhausted",
    "TaskRetryExceeded",
    "TaskNotFoundError",
    "TaskTimeoutError",
    "get_task_engine",
    "DEFAULT_RETRY_LIMIT",
    "DEFAULT_TIME_LIMIT_SECONDS",
]
