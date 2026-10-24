"""
backend/external_agents/control/job_api.py
==========================================
ISSUE-1572 (Part 3): the asynchronous Job API — delegation returns INSTANTLY
with a ``job_id`` while the worker coroutine runs in the background, so
callers never block on long-running agent work.

    delegate_web_agent(task)  -> AgentJob   (immediate)
    get_web_agent_job(job_id) -> AgentJob | None
    cancel_web_agent_job(job_id) -> bool
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from external_agents.contracts.task_contract import TaskContract, TaskState
from external_agents.control.state_manager import AgentStateManager, TaskRecord

__all__ = ["AgentJob", "ExternalAgentJobAPI", "WorkerFn"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


WorkerFn = Callable[[TaskContract, TaskRecord], Awaitable[dict[str, Any] | None]]


class AgentJob(BaseModel):
    """The instant, lightweight handle returned by the Job API."""

    job_id: str = Field(default_factory=lambda: f"job-{uuid.uuid4().hex[:12]}")
    task_id: str
    state: TaskState = TaskState.QUEUED
    worker_id: str | None = None
    queued_at: datetime = Field(default_factory=_utcnow)
    finished_at: datetime | None = None
    last_error: str | None = None
    result: dict[str, Any] | None = None


class ExternalAgentJobAPI:
    """Non-blocking facade over the durable state machine."""

    def __init__(
        self,
        state_manager: AgentStateManager | None = None,
        worker: WorkerFn | None = None,
        worker_id: str = "external-agent-worker",
    ) -> None:
        self.state_manager = state_manager or AgentStateManager()
        self.worker = worker
        self.worker_id = worker_id
        self._jobs: dict[str, AgentJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    # ------------------------------------------------------------------
    # Job API (issue #1572 scope 3)
    # ------------------------------------------------------------------
    async def delegate_web_agent(self, task: TaskContract) -> AgentJob:
        """Register the task durably and return the job handle IMMEDIATELY."""
        job = AgentJob(task_id=task.task_id)
        self._jobs[job.job_id] = job
        self.state_manager.create_task(task, job_id=job.job_id)
        job.state = TaskState.QUEUED

        if self.worker is not None:
            # Fire-and-forget worker — delegate_web_agent never awaits it.
            bg = asyncio.create_task(self._run_job(job, task))
            self._tasks[job.job_id] = bg
        return job

    async def get_web_agent_job(self, job_id: str) -> AgentJob | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        # Reflect the durable state machine truth (a worker may have advanced it).
        record = self.state_manager.get(job.task_id)
        if record is not None:
            job.state = record.state
            job.last_error = record.last_error
            job.result = record.result
            if record.state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}:
                job.finished_at = job.finished_at or record.updated_at
        return job

    async def cancel_web_agent_job(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        bg = self._tasks.pop(job_id, None)
        if bg is not None and not bg.done():
            bg.cancel()
            try:
                await bg
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        record = self.state_manager.get(job.task_id)
        if record is None:
            return False
        if record.state in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}:
            return False  # too late — already terminal
        try:
            self.state_manager.cancel(job.task_id, reason="cancelled via job api")
        except Exception:
            return False
        job.state = TaskState.CANCELLED
        job.finished_at = _utcnow()
        return True

    # ------------------------------------------------------------------
    async def _run_job(self, job: AgentJob, task: TaskContract) -> None:
        """Background worker loop: claim → start → hand to worker fn."""
        sm = self.state_manager
        try:
            sm.claim(task.task_id, worker_id=self.worker_id)
            record = sm.start(task.task_id, worker_id=self.worker_id)
            run = sm.record_run(task.task_id, worker_id=self.worker_id)
            await self.get_web_agent_job(job.job_id)  # refresh handle

            assert self.worker is not None  # guarded by delegate
            result = await self.worker(task, record)
            if result is None:
                result = {"ok": True}

            sm.finish_run(run, status="completed", detail={"result": result})
            sm.begin_verification(task.task_id)
            sm.complete(task.task_id, result=result)
        except asyncio.CancelledError:
            # Cancelled via cancel_web_agent_job — the durable record was
            # already CANCELLED there; just propagate.
            raise
        except Exception as exc:
            try:
                sm.fail(task.task_id, error=str(exc))
            except Exception:
                pass
        finally:
            self._tasks.pop(job.job_id, None)

    def shutdown(self) -> None:
        """Cancel any still-running background workers (process exit)."""
        for bg in self._tasks.values():
            if not bg.done():
                bg.cancel()
        self._tasks.clear()
