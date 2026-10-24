from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from core.capability_activation import capability_activation_store
from core.circles.contracts import (
    CapabilityRef,
    CapabilityRequest,
    CircleName,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    PolicyDecision,
    RiskLevel,
)
from core.circles.registry import circle_registry

HEALTH_CAPABILITY = "system.health.read"
CHAT_CAPABILITY = "conversation.orchestrate"
CUSTOMER_SUPPORT_CAPABILITY = "customer_support.resolve"


def _policy(request: CapabilityRequest) -> PolicyDecision:
    """Small central policy boundary for the first migrated capability."""
    if not request.context.actor_id.strip() or not request.context.tenant_id.strip():
        return PolicyDecision(allowed=False, reason="actor_context_invalid")
    if (
        request.capability.name == HEALTH_CAPABILITY
        and request.capability.risk_level is not RiskLevel.LOW
    ):
        return PolicyDecision(allowed=False, reason="health_read_must_be_low_risk")
    return PolicyDecision(allowed=True)


async def _chat_orchestrate(request: CapabilityRequest) -> Mapping[str, Any]:
    from core.orchestration.conversation_orchestrator import (
        ConversationCommand,
        get_conversation_orchestrator,
    )

    result = await get_conversation_orchestrator().dispatch(
        ConversationCommand(
            prompt=str(request.payload.get("prompt", "")),
            user_id=request.context.actor_id,
            tenant_id=request.context.tenant_id,
            role=str(request.payload.get("role", "user")),
            project_id=request.payload.get("project_id"),
            conversation_id=request.payload.get("conversation_id"),
            confirmation=bool(request.payload.get("confirmation", False)),
            metadata=dict(request.payload.get("metadata", {})),
        )
    )
    return {
        "status": result.status,
        "correlation_id": result.correlation_id,
        "capability": result.capability,
        "response": result.response,
        "requires_confirmation": result.requires_confirmation,
        "error": result.error,
        "events": result.events,
    }


async def _customer_support_resolve(request: CapabilityRequest) -> Mapping[str, Any]:
    from core.orchestration.cognitive_pipeline_dispatcher import (
        CognitiveIntent,
        get_cognitive_pipeline_dispatcher,
    )

    result = await get_cognitive_pipeline_dispatcher().dispatch(
        CognitiveIntent.CUSTOMER_SUPPORT,
        {
            **dict(request.payload),
            "actor_id": request.context.actor_id,
            "tenant_id": request.context.tenant_id,
            "conversation_id": request.context.conversation_id,
            "correlation_id": request.context.correlation_id,
        },
    )
    return result.to_dict()


async def _health_read(request: CapabilityRequest) -> Mapping[str, Any]:
    from api.routes.health import _check_database, _check_redis

    database, cache = await _check_database(), await _check_redis()
    return {
        "capability": request.capability.name,
        "tenant_id": request.context.tenant_id,
        "services": {"database": database, "cache": cache},
        "verified": database in {"healthy", "unhealthy"}
        and cache in {"healthy", "unhealthy", "not_configured"},
    }


def register_core_capabilities() -> None:
    """Register only capabilities that have a canonical gateway contract."""
    if HEALTH_CAPABILITY not in circle_registry.capabilities():
        circle_registry.register_handler(HEALTH_CAPABILITY, _health_read)
    if CHAT_CAPABILITY not in circle_registry.capabilities():
        circle_registry.register_handler(CHAT_CAPABILITY, _chat_orchestrate)
    if CUSTOMER_SUPPORT_CAPABILITY not in circle_registry.capabilities():
        circle_registry.register_handler(CUSTOMER_SUPPORT_CAPABILITY, _customer_support_resolve)
    circle_registry.set_policy_evaluator(_policy)


async def execute_capability(
    *,
    actor_id: str,
    tenant_id: str,
    source: str,
    capability: str = HEALTH_CAPABILITY,
    payload: Mapping[str, Any] | None = None,
) -> ExecutionResult:
    register_core_capabilities()
    metadata = circle_registry.describe(capability)
    if metadata is None:
        return await circle_registry.dispatch(
            CapabilityRequest(
                capability=CapabilityRef(
                    name=capability, owner_circle=CircleName.GATEWAY, risk_level=RiskLevel.LOW
                ),
                context=ExecutionContext(actor_id=actor_id, tenant_id=tenant_id),
                source=source,
                payload=payload or {},
            )
        )
    if metadata.tenant_activation_required and not capability_activation_store.is_enabled(
        tenant_id, capability
    ):
        return ExecutionResult(
            execution_id=f"exec_{uuid4().hex}",
            status=ExecutionStatus.REJECTED,
            error_code="capability_not_enabled",
            error_message="Capability is not enabled for this tenant",
            circle=metadata.owner_circle,
            capability=capability,
        )
    request = CapabilityRequest(
        capability=CapabilityRef(
            name=capability,
            owner_circle=CircleName.GATEWAY,
            risk_level=RiskLevel.LOW,
            tenant_activation_required=False,
        ),
        context=ExecutionContext(actor_id=actor_id, tenant_id=tenant_id),
        source=source,
        payload=payload or {},
    )
    return await circle_registry.dispatch(request)
