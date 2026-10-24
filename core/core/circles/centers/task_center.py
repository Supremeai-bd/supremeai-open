"""Task Circle Center — queue, retry, cancellation, progress.

Owns (per FCC plan): queue, retry, cancellation, progress.
Domain adapter: ``core.queue.task_queue.RedisTaskQueue`` (lazy import).
Zero-infrastructure principle honored: when Redis is not configured the
center fails the execution with a clear, machine-readable error instead of
pretending success.
"""

from __future__ import annotations

from core.circles.centers.base import CircleCenter, ExecutionEnvelope, LocalCapability
from core.circles.contracts import CircleName, RiskLevel


class TaskCenter(CircleCenter):
    circle = CircleName.TASK
    display_name = "Tasks and workers"
    owner = "backend/core/queue"

    def __init__(self) -> None:
        super().__init__()
        self.register(
            LocalCapability(
                name="task.submit",
                description="Enqueue a durable task on the worker queue",
                risk_level=RiskLevel.MEDIUM,
                timeout_ms=15_000,
            ),
            self._submit,
        )

    def local_permission(self, envelope: ExecutionEnvelope) -> str | None:
        if (
            envelope.capability == "task.submit"
            and not str(envelope.payload.get("task_type", "")).strip()
        ):
            return "task_type is required for task.submit"
        return None

    def resolve_adapter(self, envelope: ExecutionEnvelope):  # noqa: ANN201
        from core.queue import task_queue  # local adapter selection

        return task_queue

    async def _submit(self, request) -> dict:
        adapter = self.resolve_adapter(request)
        if not adapter.redis_configured():
            raise RuntimeError("task_queue_unavailable:redis_not_configured")
        task_id = await adapter.RedisTaskQueue().enqueue(
            str(request.payload.get("task_type", "")),
            dict(request.payload.get("payload", {})),
            request.context.actor_id,
        )
        return {"task_id": task_id, "queued": True}


__all__ = ["TaskCenter"]
