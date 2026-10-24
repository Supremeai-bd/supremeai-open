"""Gateway Circle Center — entry orchestration capabilities.

Owns (per FCC plan): gateway-level orchestration entry points.
Domain adapters (function-level lazy imports): conversation orchestrator,
cognitive pipeline dispatcher, canonical health checks.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.circles.centers.base import CircleCenter, LocalCapability
from core.circles.contracts import CircleName, RiskLevel


class GatewayCenter(CircleCenter):
    circle = CircleName.GATEWAY
    display_name = "Gateway and orchestration"
    owner = "backend/core/orchestration"

    def __init__(self) -> None:
        super().__init__()
        self.register(
            LocalCapability(
                name="system.health.read",
                description="Read database and cache health for the caller tenant",
                risk_level=RiskLevel.LOW,
                timeout_ms=10_000,
                cache_ttl_ms=5_000,
            ),
            self._health_read,
        )
        self.register(
            LocalCapability(
                name="conversation.orchestrate",
                description="Dispatch a conversation turn through the orchestrator",
                risk_level=RiskLevel.MEDIUM,
                timeout_ms=60_000,
            ),
            self._chat_orchestrate,
        )
        self.register(
            LocalCapability(
                name="customer_support.resolve",
                description="Resolve a support intent through the cognitive pipeline",
                risk_level=RiskLevel.MEDIUM,
                timeout_ms=60_000,
            ),
            self._customer_support_resolve,
        )

    # ── local adapters (lazy: keeps federation import-light) ─────────
    async def _health_read(self, request) -> Mapping[str, Any]:
        from api.routes.health import _check_database, _check_redis

        database, cache = await _check_database(), await _check_redis()
        return {
            "capability": request.capability.name,
            "tenant_id": request.context.tenant_id,
            "services": {"database": database, "cache": cache},
            "verified": database in {"healthy", "unhealthy"}
            and cache in {"healthy", "unhealthy", "not_configured"},
        }

    async def _chat_orchestrate(self, request) -> Mapping[str, Any]:
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

    async def _customer_support_resolve(self, request) -> Mapping[str, Any]:
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


__all__ = ["GatewayCenter"]
