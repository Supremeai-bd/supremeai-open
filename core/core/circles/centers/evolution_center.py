"""Evolution Circle Center — learning and self-improvement governance.

Owns (per FCC plan): evolution and learning, gated behind approval.
Domain adapter: ``adaptive_engine.approval_workflow`` (lazy import; the
evolution engine's own HITL store). SQLite-backed calls run in a worker
thread.
"""

from __future__ import annotations

import asyncio

from core.circles.centers.base import CircleCenter, ExecutionEnvelope, LocalCapability
from core.circles.contracts import CircleName, RiskLevel


class EvolutionCenter(CircleCenter):
    circle = CircleName.EVOLUTION
    display_name = "Evolution and learning"
    owner = "backend/adaptive_engine"

    def __init__(self) -> None:
        super().__init__()
        self.register(
            LocalCapability(
                name="evolution.approval.required",
                description="Check whether a proposed evolution action needs approval",
                risk_level=RiskLevel.LOW,
                timeout_ms=5_000,
                cache_ttl_ms=10_000,
            ),
            self._approval_required,
        )
        self.register(
            LocalCapability(
                name="evolution.proposals.pending",
                description="List pending evolution proposals for the caller tenant",
                risk_level=RiskLevel.LOW,
                timeout_ms=10_000,
                cache_ttl_ms=3_000,
            ),
            self._pending_proposals,
        )
        self.register(
            LocalCapability(
                name="evolution.evaluate",
                description="Submit an evolution proposal for evaluation (approval-gated)",
                risk_level=RiskLevel.HIGH,
                approval_required=True,
                timeout_ms=15_000,
            ),
            self._evaluate,
        )

    def local_permission(self, envelope: ExecutionEnvelope) -> str | None:
        if (
            envelope.capability == "evolution.approval.required"
            and not str(envelope.payload.get("kind", "")).strip()
        ):
            return "kind is required for evolution.approval.required"
        return None

    def resolve_adapter(self, envelope: ExecutionEnvelope):  # noqa: ANN201
        from adaptive_engine.approval_workflow import get_approval_workflow

        return get_approval_workflow()

    async def _approval_required(self, request) -> dict:
        from adaptive_engine.approval_workflow import ProposalKind

        workflow = self.resolve_adapter(request)
        kind = str(request.payload.get("kind", ""))
        try:
            proposal_kind = ProposalKind(kind)
        except ValueError as exc:
            raise ValueError(f"unknown_proposal_kind:{kind}") from exc
        required = workflow.requires_approval(
            str(request.payload.get("risk_level", "low")), proposal_kind
        )
        return {"kind": kind, "approval_required": required}

    async def _pending_proposals(self, request) -> dict:
        workflow = self.resolve_adapter(request)
        limit = min(int(request.payload.get("limit", 50)), 200)
        rows = await asyncio.to_thread(
            workflow.list_pending,
            tenant_id=request.context.tenant_id,
            limit=limit,
        )
        return {
            "proposals": [proposal.model_dump(mode="json") for proposal in rows],
            "count": len(rows),
        }

    async def _evaluate(self, request) -> dict:
        # Reached only after an approval has been granted for the proposal.
        workflow = self.resolve_adapter(request)
        proposal_id = str(request.payload.get("proposal_id", ""))
        proposal = await asyncio.to_thread(workflow.get, proposal_id)
        if proposal is None:
            raise LookupError("evolution_proposal_not_found")
        return {"proposal": proposal.model_dump(mode="json"), "evaluated": True}


__all__ = ["EvolutionCenter"]
