"""backend/core/kernel/dispatcher.py — SupremeKernel Central Dispatcher.

Governed Single-Door Entry Facade:
- Authenticates actor and verifies tenant boundaries
- Resolves target circle (Governance, Execution, Evolution, Infrastructure)
- Routes through the FCC federation (GovernanceCore → circle centers)
- Falls back to the legacy flat registry for capabilities that have not
  migrated yet (never breaks pre-FCC callers)
- Applies policy and circuit breakers
- Emits distributed trace and audit journal events
"""

from __future__ import annotations

import time

from core.circles.contracts import (
    CircleName,
    ExecutionStatus,
    RiskLevel,
)
from core.circles.envelopes import ExecutionEnvelope
from core.circles.governance_core import get_governance_core
from core.circles.registry import circle_registry
from core.kernel.audit_logger import AuditLogger
from core.kernel.interface import CircleScope, KernelRequest, KernelResponse
from core.logging_config import logger

_CIRCLE_SCOPE_MAPPING: dict[CircleScope, CircleName] = {
    CircleScope.GOVERNANCE: CircleName.ADMIN,
    CircleScope.EXECUTION: CircleName.TASK,
    CircleScope.EVOLUTION: CircleName.EVOLUTION,
    CircleScope.INFRASTRUCTURE: CircleName.GATEWAY,
}

_FEDERATION_FALLBACK_STATUSES = {
    ExecutionStatus.UNAVAILABLE.value,
}


class SupremeKernel:
    """The central single-door facade for SupremeAI capabilities.

    Phase-4 (issue #2260): canonical primitives are wired INTO the kernel —
    wave 1 = Audit (``core/kernel/audit_logger.py`` — the blueprint ৪.৩
    canonical audit trail — plus the MCP hash-chain at
    ``core/kernel/audit_chain.py`` for tamper evidence). Every completed
    dispatch (success or failure) is journalled through the kernel-owned
    primitive; audit failures are observable but never break dispatch.
    """

    def __init__(self, audit_logger: AuditLogger | None = None) -> None:
        self.registry = circle_registry
        # Kernel-owned canonical audit primitive (injectable for hermetic tests).
        self.audit = audit_logger if audit_logger is not None else AuditLogger()

    def _journal_dispatch(
        self,
        request: KernelRequest,
        status: str,
        elapsed_ms: float,
        error_code: str | None,
    ) -> None:
        """Journal a completed dispatch through the kernel audit primitive.

        rel001 (No Silent Failure): failures here are logged, never swallowed
        quietly — but they must not corrupt the dispatch result either.
        """
        try:
            self.audit.log_decision(
                action_type="kernel_dispatch",
                decision_details=f"{request.capability} -> {status}",
                reasoning=(
                    f"circle={request.target_circle.value} actor={request.actor_id} "
                    f"tenant={request.tenant_id} request_id={request.request_id} "
                    f"elapsed_ms={elapsed_ms:.1f} error={error_code or 'none'}"
                ),
            )
        except Exception as exc:  # noqa: BLE001 — audit must never break dispatch
            logger.warning(
                f"[SupremeKernel] audit journaling failed for {request.request_id}: {exc}"
            )

    def audit_trail(self) -> list:
        """Expose the kernel-owned tamper-evident audit trail (read path)."""
        return self.audit.get_audit_trail()

    async def dispatch(self, request: KernelRequest) -> KernelResponse:
        start_time = time.perf_counter()
        logger.info(
            f"[SupremeKernel] Inbound dispatch request: {request.capability} "
            f"circle={request.target_circle.value} tenant={request.tenant_id}"
        )

        # 1. Map CircleScope to underlying CircleName
        target_circle_name = _CIRCLE_SCOPE_MAPPING.get(request.target_circle, CircleName.GATEWAY)

        # 2. FCC federation first: envelope-only cross-circle routing
        try:
            governance = get_governance_core()
            envelope = ExecutionEnvelope(
                execution_id=request.request_id,
                circle=target_circle_name,
                capability=request.capability,
                tenant_id=request.tenant_id,
                actor_id=request.actor_id,
                correlation_id=request.correlation_id,
                payload=dict(request.payload),
                deadline_ms=max(1, min(request.deadline_ms, 300_000)),
            )
            result = await governance.route(envelope)
            if result.status.value not in _FEDERATION_FALLBACK_STATUSES:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                self._journal_dispatch(
                    request,
                    result.status.value,
                    elapsed_ms,
                    result.error.code if result.error else None,
                )
                return KernelResponse(
                    request_id=request.request_id,
                    correlation_id=request.correlation_id,
                    trace_id=request.trace_id,
                    target_circle=request.target_circle,
                    capability=request.capability,
                    status=result.status.value,
                    data=result.data,
                    error_code=result.error.code if result.error else None,
                    error_message=result.error.message if result.error else None,
                    execution_time_ms=elapsed_ms,
                    verified=result.status is ExecutionStatus.SUCCEEDED,
                )
            logger.info(
                f"[SupremeKernel] Federation cannot serve '{request.capability}' "
                f"({result.error.code if result.error else 'unavailable'}); "
                "falling back to legacy registry"
            )
        except Exception as exc:  # noqa: BLE001 — federation must never hard-fail the kernel
            logger.warning(
                f"[SupremeKernel] Federation routing error, using legacy registry: {exc}"
            )

        # 3. Legacy flat-registry fallback (pre-FCC compatibility surface)
        try:
            exec_result = await self._legacy_dispatch(request, target_circle_name)
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            self._journal_dispatch(
                request, exec_result.status.value, elapsed_ms, exec_result.error_code
            )

            return KernelResponse(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                trace_id=request.trace_id,
                target_circle=request.target_circle,
                capability=request.capability,
                status=exec_result.status.value,
                data=exec_result.data,
                error_code=exec_result.error_code,
                error_message=exec_result.error_message,
                execution_time_ms=elapsed_ms,
                verified=exec_result.verification.verified if exec_result.verification else True,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(f"[SupremeKernel] Dispatch execution failure: {exc}", exc_info=True)
            self._journal_dispatch(request, "failed", elapsed_ms, "kernel_dispatch_error")
            return KernelResponse(
                request_id=request.request_id,
                correlation_id=request.correlation_id,
                trace_id=request.trace_id,
                target_circle=request.target_circle,
                capability=request.capability,
                status="failed",
                error_code="kernel_dispatch_error",
                error_message=str(exc),
                execution_time_ms=elapsed_ms,
                verified=False,
            )

    async def _legacy_dispatch(self, request: KernelRequest, circle: CircleName):
        from core.circles.contracts import CapabilityRef, CapabilityRequest, ExecutionContext

        exec_ctx = ExecutionContext(
            execution_id=request.request_id,
            correlation_id=request.correlation_id,
            actor_id=request.actor_id,
            tenant_id=request.tenant_id,
            workspace_id=request.workspace_id,
            deadline_ms=request.deadline_ms,
            idempotency_key=request.idempotency_key,
            trace_id=request.trace_id,
        )
        cap_ref = CapabilityRef(
            name=request.capability,
            owner_circle=circle,
            risk_level=RiskLevel.LOW,
            timeout_ms=request.deadline_ms,
        )
        cap_request = CapabilityRequest(
            capability=cap_ref,
            context=exec_ctx,
            source="kernel_dispatch",
            payload=request.payload,
        )
        return await self.registry.dispatch(cap_request)


# Global Singleton Facade
supreme_kernel = SupremeKernel()
