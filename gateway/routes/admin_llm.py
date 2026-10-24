"""Admin LLM Gateway control endpoints.

FIX(phantom-api): the CommandCenter LlmGatewayPage has always called
``/api/admin/llm/*`` — endpoints that never existed in the backend, so the
page rendered a permanent error state in every deployment. This module makes
that contract REAL by exposing actual routing state and control:

- ``GET  /providers``        — live provider stats from the latency-aware
                               weighted router (readiness, measured latency,
                               models derived from the routing policy).
- ``GET  /router``           — the real chat fallback chain, the active
                               runtime override (if any) and the live
                               cost/quality preference knob if configured.
- ``POST /router/override``  — activates a real routing override consumed by
                               the gateway's actual request path.
- ``GET  /rules``            — constitutional rules (God layer) as an object.
- ``POST /rules``            — bulk-persist rule key/values.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_admin
from api.routes.admin import god_layer  # shared God-layer instance (single SQLite handle)
from core.logging_config import logger

router = APIRouter(prefix="/api/admin/llm", tags=["Admin LLM Gateway"])


class RouterOverridePayload(BaseModel):
    provider: str
    model: str | None = None
    remaining_requests: int | None = None


class BulkRulesPayload(BaseModel):
    rules: dict[str, str]


@router.get("/providers")
async def get_llm_providers(admin_user: dict = Depends(get_current_admin)):
    """Live provider readiness, measured latency and routing-policy models."""
    from core.llm.llm_gateway import get_llm_gateway
    from core.llm.provider_router import router_instance

    try:
        gateway = get_llm_gateway()
        policy = getattr(gateway, "routing_policy", {}) or {}
        known_models: list[str] = []

        fallbacks = policy.get("fallback_chain", [])
        if isinstance(fallbacks, list):
            known_models.extend(str(m) for m in fallbacks)
        for candidates in (policy.get("complexity_rules", {}) or {}).values():
            if isinstance(candidates, list):
                known_models.extend(str(m) for m in candidates)

        providers = []
        for name, stats in router_instance.stats.items():
            models = sorted({m.split("/", 1)[1] for m in known_models if m.startswith(f"{name}/")})
            is_healthy = stats.ready and not stats.is_circuit_open()
            providers.append(
                {
                    "id": name,
                    "name": name,
                    "status": "healthy" if is_healthy else stats.readiness_status or "unavailable",
                    # Measured rolling average; 0 = no samples yet.
                    "latency_ms": round(stats.avg_latency_ms, 1),
                    "models": [
                        # Full "provider/model" ids — the switcher posts them back.
                        f"{name}/{m}" if "/" not in m else m
                        for m in models
                    ],
                    "mode": "latency-weighted",
                }
            )
        return providers
    except Exception as exc:
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(f"llm providers listing failed correlation_id={correlation_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (correlation_id: {correlation_id})",
        ) from exc


@router.get("/router")
async def get_llm_router(admin_user: dict = Depends(get_current_admin)):
    """Real fallback chain + active runtime override state."""
    from core.llm.llm_gateway import get_llm_gateway
    from core.llm.llm_gateway.routing import get_runtime_override

    try:
        gateway = get_llm_gateway()
        chain = gateway._build_call_chain(None, None, "chat")
        provider_order: list[str] = []
        for entry in chain:
            provider = entry.split("/", 1)[0]
            if provider and provider not in provider_order:
                provider_order.append(provider)

        override = get_runtime_override()
        current_override = (
            {"provider": override["provider"], "model": override["model"] or ""}
            if override["provider"]
            else None
        )

        return {
            "current_override": current_override,
            "provider_order": provider_order,
            "cost_quality_preference": None,
            "fallback_chain": chain,
            "override_remaining_requests": override["remaining_requests"],
        }
    except Exception as exc:
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(f"llm router state failed correlation_id={correlation_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (correlation_id: {correlation_id})",
        ) from exc


@router.post("/router/override")
async def set_llm_router_override(
    payload: RouterOverridePayload, admin_user: dict = Depends(get_current_admin)
):
    """Activate a real routing override (consumed by the gateway request path)."""
    from core.llm.llm_gateway.routing import set_runtime_override

    try:
        set_runtime_override(
            provider=payload.provider,
            model=payload.model,
            remaining_requests=payload.remaining_requests,
        )
        logger.critical(
            f"🔒 LLM routing override set to {payload.provider}/{payload.model or '(chain default)'}"
            f" by {admin_user.get('sub')}"
        )
        return {
            "status": "success",
            "provider": payload.provider,
            "model": payload.model,
            "remaining_requests": payload.remaining_requests,
        }
    except Exception as exc:
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(f"llm router override failed correlation_id={correlation_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (correlation_id: {correlation_id})",
        ) from exc


@router.get("/rules")
async def get_llm_rules(admin_user: dict = Depends(get_current_admin)):
    """Constitutional rules as a plain key/value object for the editor."""
    try:
        rules = god_layer.list_rules()
        as_object: dict[str, str] = {}
        for entry in rules or []:
            if isinstance(entry, dict) and "key" in entry:
                as_object[str(entry["key"])] = str(entry.get("value", ""))
        return as_object
    except Exception as exc:
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(f"llm rules read failed correlation_id={correlation_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (correlation_id: {correlation_id})",
        ) from exc


@router.post("/rules")
async def update_llm_rules(
    payload: BulkRulesPayload, admin_user: dict = Depends(get_current_admin)
):
    """Bulk-persist rule key/values through the God layer."""
    try:
        for key, value in payload.rules.items():
            god_layer.set_rule(key, value)
        logger.critical(
            f"🔒 {len(payload.rules)} constitutional rule(s) updated via LLM gateway by {admin_user.get('sub')}"
        )
        return {"status": "success", "updated": len(payload.rules)}
    except Exception as exc:
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(f"llm rules write failed correlation_id={correlation_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (correlation_id: {correlation_id})",
        ) from exc
