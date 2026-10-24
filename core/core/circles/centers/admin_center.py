"""Admin Circle Center — approvals, policy actions, command execution.

Owns (per FCC plan): approvals, policy editing, command execution.
Domain adapter: ``models.pending_tasks`` HITL approval service (lazy import).
Local rules: decisions require a reason; every query is tenant-scoped.
``admin.approve``/``admin.reject`` stay CRITICAL + approval-gated: the
federation returns ``approval_required`` and the decision itself flows
through the HITL surface (governed path).
"""

from __future__ import annotations

import asyncio

from core.circles.centers.base import CircleCenter, ExecutionEnvelope, LocalCapability
from core.circles.contracts import CircleName, RiskLevel


class AdminCenter(CircleCenter):
    circle = CircleName.ADMIN
    display_name = "Admin governance"
    owner = "backend/api/routes/approval_manager.py"

    def __init__(self) -> None:
        super().__init__()
        self.register(
            LocalCapability(
                name="admin.approvals.list",
                description="List pending HITL approvals for the caller tenant",
                risk_level=RiskLevel.LOW,
                timeout_ms=10_000,
                cache_ttl_ms=3_000,
            ),
            self._list_pending,
        )
        self.register(
            LocalCapability(
                name="admin.approve",
                description="Approve a pending HITL task (approval-gated)",
                risk_level=RiskLevel.CRITICAL,
                approval_required=True,
                timeout_ms=10_000,
            ),
            self._approve,
        )
        self.register(
            LocalCapability(
                name="admin.reject",
                description="Reject a pending HITL task (approval-gated)",
                risk_level=RiskLevel.CRITICAL,
                approval_required=True,
                timeout_ms=10_000,
            ),
            self._reject,
        )
        self.register(
            LocalCapability(
                name="admin.cancel",
                description="Cancel a pending HITL task",
                risk_level=RiskLevel.HIGH,
                timeout_ms=10_000,
            ),
            self._cancel,
        )

    def local_permission(self, envelope: ExecutionEnvelope) -> str | None:
        if envelope.capability in {"admin.approve", "admin.reject", "admin.cancel"}:
            if not str(envelope.payload.get("task_id", "")).strip():
                return f"task_id is required for {envelope.capability}"
            if (
                envelope.capability != "admin.cancel"
                and not str(envelope.payload.get("reason", "")).strip()
            ):
                return f"reason is required for {envelope.capability}"
        return None

    def resolve_adapter(self, envelope: ExecutionEnvelope):  # noqa: ANN201
        from models import pending_tasks  # local adapter selection

        return pending_tasks

    async def _list_pending(self, request) -> dict:
        adapter = self.resolve_adapter(request)
        rows = await asyncio.to_thread(adapter.list_pending, request.context.tenant_id)
        return {
            "tasks": [task.model_dump(mode="json") for task in rows],
            "count": len(rows),
        }

    async def _approve(self, request) -> dict:
        return await self._decide(request, "approve")

    async def _reject(self, request) -> dict:
        return await self._decide(request, "reject")

    async def _decide(self, request, action: str) -> dict:
        from models.pending_tasks import TaskStatus, update_task_status

        self.resolve_adapter(request)  # validates the adapter is importable
        status = TaskStatus.APPROVED if action == "approve" else TaskStatus.REJECTED
        task = await asyncio.to_thread(
            update_task_status,
            str(request.payload.get("task_id", "")),
            status,
            request.context.actor_id,
            str(request.payload.get("reason", "")),
            tenant_id=request.context.tenant_id,
        )
        if task is None:
            raise LookupError("approval_task_not_found")
        return {"task": task.model_dump(mode="json"), "action": action}

    async def _cancel(self, request) -> dict:
        adapter = self.resolve_adapter(request)
        task = await asyncio.to_thread(
            adapter.cancel_task,
            str(request.payload.get("task_id", "")),
            request.context.actor_id,
            str(request.payload.get("reason", "") or ""),
            request.context.tenant_id,
        )
        if task is None:
            raise LookupError("approval_task_not_found")
        return {"task": task.model_dump(mode="json"), "action": "cancel"}


__all__ = ["AdminCenter"]
