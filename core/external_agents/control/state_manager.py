"""
backend/external_agents/control/state_manager.py
================================================
ISSUE-1572 (Part 3): the durable asynchronous state machine for external
agent tasks.

State flow (strict):
    QUEUED → CLAIMED → RUNNING → CHECKPOINT → VERIFYING → COMPLETED
with terminal FAILED / CANCELLED branches and the stale-run safety valve
RUNNING|CHECKPOINT|VERIFYING → WAITING_FOR_CHANNEL → RUNNING (safe resume
after a local-PC / browser / channel disconnect).

Durability: records live in a ``StateStore`` — the default ``JsonFileStore``
writes atomically under ``EXTERNAL_AGENTS_STATE_DIR`` (default
``~/.supremeai/external_agents``), so state survives process restarts. The
``agent_tasks`` / ``agent_runs`` / ``agent_checkpoints`` collections of the
issue map 1:1 onto the store's three collections.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from external_agents.contracts.task_contract import TaskContract, TaskState

__all__ = [
    "AgentStateManager",
    "CheckpointRecord",
    "InMemoryStore",
    "InvalidTransitionError",
    "JsonFileStore",
    "RunRecord",
    "StateStore",
    "TaskRecord",
    "default_state_dir",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def default_state_dir() -> Path:
    env = os.getenv("EXTERNAL_AGENTS_STATE_DIR", "").strip()
    return Path(env) if env else Path.home() / ".supremeai" / "external_agents"


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
class TaskRecord(BaseModel):
    task_id: str
    contract: dict[str, Any] = Field(description="Serialised TaskContract")
    state: TaskState = TaskState.QUEUED
    worker_id: str | None = None
    job_id: str | None = None
    attempt: int = 0
    last_error: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: f"run-{uuid.uuid4().hex[:10]}")
    task_id: str
    worker_id: str | None = None
    started_at: datetime = Field(default_factory=_utcnow)
    ended_at: datetime | None = None
    status: str = "running"
    detail: dict[str, Any] = Field(default_factory=dict)


class CheckpointRecord(BaseModel):
    task_id: str
    seq: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    note: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class InvalidTransitionError(RuntimeError):
    """Raised when a state transition violates the strict flow."""

    def __init__(self, task_id: str, current: TaskState, target: TaskState):
        self.task_id = task_id
        self.current = current
        self.target = target
        super().__init__(f"task '{task_id}': illegal transition {current.value} → {target.value}")


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------
class StateStore(Protocol):
    """Persistence seam — three collections: tasks / runs / checkpoints."""

    def put_task(self, record: TaskRecord) -> None: ...
    def get_task(self, task_id: str) -> TaskRecord | None: ...
    def list_tasks(self) -> list[TaskRecord]: ...
    def delete_task(self, task_id: str) -> None: ...

    def put_run(self, record: RunRecord) -> None: ...
    def list_runs(self, task_id: str) -> list[RunRecord]: ...

    def put_checkpoint(self, record: CheckpointRecord) -> None: ...
    def list_checkpoints(self, task_id: str) -> list[CheckpointRecord]: ...


class InMemoryStore(StateStore):
    """Zero-dependency store for unit tests and short-lived workers."""

    def __init__(self) -> None:
        self.tasks: dict[str, TaskRecord] = {}
        self.runs: dict[str, list[RunRecord]] = {}
        self.checkpoints: dict[str, list[CheckpointRecord]] = {}

    def put_task(self, record: TaskRecord) -> None:
        self.tasks[record.task_id] = record

    def get_task(self, task_id: str) -> TaskRecord | None:
        return self.tasks.get(task_id)

    def list_tasks(self) -> list[TaskRecord]:
        return list(self.tasks.values())

    def delete_task(self, task_id: str) -> None:
        self.tasks.pop(task_id, None)
        self.runs.pop(task_id, None)
        self.checkpoints.pop(task_id, None)

    def put_run(self, record: RunRecord) -> None:
        self.runs.setdefault(record.task_id, []).append(record)

    def list_runs(self, task_id: str) -> list[RunRecord]:
        return list(self.runs.get(task_id, []))

    def put_checkpoint(self, record: CheckpointRecord) -> None:
        self.checkpoints.setdefault(record.task_id, []).append(record)

    def list_checkpoints(self, task_id: str) -> list[CheckpointRecord]:
        return list(self.checkpoints.get(task_id, []))


class JsonFileStore(StateStore):
    """Durable store — atomic JSON files under ``base_dir``.

    Layout (the issue's three collections):
        base_dir/agent_tasks/<task_id>.json
        base_dir/agent_runs/<task_id>/<run_id>.json
        base_dir/agent_checkpoints/<task_id>/<seq>.json
    """

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else default_state_dir()

    # -- internals -------------------------------------------------------
    def _atomic_write(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, default=str, ensure_ascii=False))
        os.replace(tmp, path)  # atomic on POSIX & Windows

    @staticmethod
    def _read_model(path: Path, model_cls: type[BaseModel]) -> Any | None:
        if not path.exists():
            return None
        try:
            return model_cls.model_validate(json.loads(path.read_text()))
        except Exception:
            return None

    def _task_path(self, task_id: str) -> Path:
        return self.base_dir / "agent_tasks" / f"{task_id}.json"

    # -- tasks -----------------------------------------------------------
    def put_task(self, record: TaskRecord) -> None:
        self._atomic_write(
            self._task_path(record.task_id),
            record.model_dump(mode="json"),
        )

    def get_task(self, task_id: str) -> TaskRecord | None:
        record = self._read_model(self._task_path(task_id), TaskRecord)
        return record if isinstance(record, TaskRecord) else None

    def list_tasks(self) -> list[TaskRecord]:
        out: list[TaskRecord] = []
        tasks_dir = self.base_dir / "agent_tasks"
        if tasks_dir.is_dir():
            for path in sorted(tasks_dir.glob("*.json")):
                record = self._read_model(path, TaskRecord)
                if isinstance(record, TaskRecord):
                    out.append(record)
        return out

    def delete_task(self, task_id: str) -> None:
        self._task_path(task_id).unlink(missing_ok=True)
        for sub in ("agent_runs", "agent_checkpoints"):
            dir_path = self.base_dir / sub / task_id
            if dir_path.is_dir():
                for p in dir_path.glob("*.json"):
                    p.unlink(missing_ok=True)

    # -- runs ------------------------------------------------------------
    def put_run(self, record: RunRecord) -> None:
        path = self.base_dir / "agent_runs" / record.task_id / f"{record.run_id}.json"
        self._atomic_write(path, record.model_dump(mode="json"))

    def list_runs(self, task_id: str) -> list[RunRecord]:
        out: list[RunRecord] = []
        runs_dir = self.base_dir / "agent_runs" / task_id
        if runs_dir.is_dir():
            for path in sorted(runs_dir.glob("*.json")):
                record = self._read_model(path, RunRecord)
                if isinstance(record, RunRecord):
                    out.append(record)
        return out

    # -- checkpoints -------------------------------------------------------
    def put_checkpoint(self, record: CheckpointRecord) -> None:
        path = self.base_dir / "agent_checkpoints" / record.task_id / f"{record.seq:04d}.json"
        self._atomic_write(path, record.model_dump(mode="json"))

    def list_checkpoints(self, task_id: str) -> list[CheckpointRecord]:
        out: list[CheckpointRecord] = []
        cp_dir = self.base_dir / "agent_checkpoints" / task_id
        if cp_dir.is_dir():
            for path in sorted(cp_dir.glob("*.json")):
                record = self._read_model(path, CheckpointRecord)
                if isinstance(record, CheckpointRecord):
                    out.append(record)
        return out


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------
_VALID_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.QUEUED: {TaskState.CLAIMED, TaskState.CANCELLED, TaskState.FAILED},
    TaskState.CLAIMED: {
        TaskState.RUNNING,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.WAITING_FOR_CHANNEL,
    },
    TaskState.RUNNING: {
        TaskState.CHECKPOINT,
        TaskState.VERIFYING,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.WAITING_FOR_CHANNEL,
    },
    TaskState.CHECKPOINT: {
        TaskState.RUNNING,
        TaskState.VERIFYING,
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.WAITING_FOR_CHANNEL,
    },
    TaskState.VERIFYING: {
        TaskState.COMPLETED,
        TaskState.RUNNING,  # bounded repair rounds (issue #1575)
        TaskState.FAILED,
        TaskState.CANCELLED,
        TaskState.WAITING_FOR_CHANNEL,
    },
    TaskState.COMPLETED: set(),
    TaskState.FAILED: set(),
    TaskState.CANCELLED: set(),
    TaskState.WAITING_FOR_CHANNEL: {
        TaskState.RUNNING,  # safe resume on reconnection
        TaskState.FAILED,
        TaskState.CANCELLED,
    },
}


class AgentStateManager:
    """Durable task checkpoints across the strict external-agent state flow."""

    def __init__(self, store: StateStore | None = None) -> None:
        self.store: StateStore = store or JsonFileStore()

    # -- core transition engine ------------------------------------------
    def _transition(self, task_id: str, target: TaskState, **updates: Any) -> TaskRecord:
        record = self.store.get_task(task_id)
        if record is None:
            raise KeyError(f"task '{task_id}' not found")
        current = record.state
        if target not in _VALID_TRANSITIONS.get(current, set()):
            raise InvalidTransitionError(task_id, current, target)
        record.state = target
        for key, value in updates.items():
            if value is not None:
                setattr(record, key, value)
        record.updated_at = _utcnow()
        self.store.put_task(record)
        return record

    # -- lifecycle -------------------------------------------------------
    def create_task(self, contract: TaskContract, job_id: str | None = None) -> TaskRecord:
        record = TaskRecord(
            task_id=contract.task_id, contract=contract.model_dump(mode="json"), job_id=job_id
        )
        self.store.put_task(record)
        return record

    def claim(self, task_id: str, worker_id: str) -> TaskRecord:
        return self._transition(task_id, TaskState.CLAIMED, worker_id=worker_id)

    def start(self, task_id: str, worker_id: str | None = None) -> TaskRecord:
        record = self.store.get_task(task_id)
        if record is None:
            raise KeyError(f"task '{task_id}' not found")
        # attempt counts RUN starts (claim→start cycles = retries)
        updates: dict[str, Any] = {"attempt": record.attempt + 1}
        if worker_id:
            updates["worker_id"] = worker_id
        return self._transition(task_id, TaskState.RUNNING, **updates)

    def checkpoint(
        self, task_id: str, payload: dict[str, Any] | None = None, note: str = ""
    ) -> CheckpointRecord:
        record = self.store.get_task(task_id)
        if record is None:
            raise KeyError(f"task '{task_id}' not found")
        if record.state is not TaskState.RUNNING and record.state is not TaskState.CHECKPOINT:
            raise InvalidTransitionError(task_id, record.state, TaskState.CHECKPOINT)
        existing = self.store.list_checkpoints(task_id)
        cp = CheckpointRecord(
            task_id=task_id, seq=len(existing) + 1, payload=payload or {}, note=note
        )
        self.store.put_checkpoint(cp)
        if record.state is TaskState.RUNNING:
            self._transition(task_id, TaskState.CHECKPOINT)
        return cp

    def resume_from_checkpoint(self, task_id: str) -> TaskRecord:
        """CHECKPOINT → RUNNING (continue the mission)."""
        return self._transition(task_id, TaskState.RUNNING)

    def begin_verification(self, task_id: str) -> TaskRecord:
        return self._transition(task_id, TaskState.VERIFYING)

    def complete(self, task_id: str, result: dict[str, Any] | None = None) -> TaskRecord:
        return self._transition(task_id, TaskState.COMPLETED, result=result)

    def fail(self, task_id: str, error: str) -> TaskRecord:
        return self._transition(task_id, TaskState.FAILED, last_error=error)

    def cancel(self, task_id: str, reason: str = "") -> TaskRecord:
        return self._transition(task_id, TaskState.CANCELLED, last_error=reason or None)

    # -- stale run resumption (disconnect safety) ------------------------
    def mark_waiting_for_channel(
        self, task_id: str, reason: str = "channel disconnected"
    ) -> TaskRecord:
        """Local PC / browser disconnect → park the run for safe resumption."""
        record = self.store.get_task(task_id)
        if record is None:
            raise KeyError(f"task '{task_id}' not found")
        resumable = {
            TaskState.CLAIMED,
            TaskState.RUNNING,
            TaskState.CHECKPOINT,
            TaskState.VERIFYING,
        }
        if record.state not in resumable:
            raise InvalidTransitionError(task_id, record.state, TaskState.WAITING_FOR_CHANNEL)
        return self._transition(task_id, TaskState.WAITING_FOR_CHANNEL, last_error=reason)

    def resume_from_channel(self, task_id: str) -> TaskRecord:
        """Reconnection → back to RUNNING; checkpoints replayed by the worker."""
        return self._transition(task_id, TaskState.RUNNING)

    # -- runs / queries ---------------------------------------------------
    def record_run(
        self, task_id: str, worker_id: str | None = None, detail: dict[str, Any] | None = None
    ) -> RunRecord:
        run = RunRecord(task_id=task_id, worker_id=worker_id, detail=detail or {})
        self.store.put_run(run)
        return run

    def finish_run(
        self, run: RunRecord, status: str = "completed", detail: dict[str, Any] | None = None
    ) -> RunRecord:
        run.ended_at = _utcnow()
        run.status = status
        if detail:
            run.detail.update(detail)
        self.store.put_run(run)
        return run

    def get(self, task_id: str) -> TaskRecord | None:
        return self.store.get_task(task_id)

    def list_by_state(self, state: TaskState) -> list[TaskRecord]:
        return [r for r in self.store.list_tasks() if r.state is state]

    def checkpoints(self, task_id: str) -> list[CheckpointRecord]:
        return self.store.list_checkpoints(task_id)

    def runs(self, task_id: str) -> list[RunRecord]:
        return self.store.list_runs(task_id)
