"""Federated Circles API — FCC topology, health and governed dispatch.

The canonical cross-circle door for external callers:

    GET  /api/v1/circles           federation topology (centers + capabilities)
    GET  /api/v1/circles/health    aggregated center health
    GET  /api/v1/circles/events    recent realtime event mirror
    POST /api/v1/circles/dispatch  governed envelope dispatch (admin only)

Identity is ALWAYS derived from the JWT (actor_id/tenant_id) — never from
the request body. Dispatch goes through the Global Governance Core, so
global policy, the approval gate and audit fan-out all apply.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import get_current_admin, get_current_user_token
from core.circles.contracts import CircleName
from core.circles.envelopes import ExecutionEnvelope
from core.circles.governance_core import get_governance_core
from core.logging_config import logger

router = APIRouter(prefix="/api/v1/circles", tags=["Federated Circles"])


class DispatchBody(BaseModel):
    """FCC execution envelope minus identity (identity comes from the JWT)."""

    circle: str = Field(min_length=1, max_length=40)
    capability: str = Field(min_length=1, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    deadline_ms: int = Field(default=30_000, ge=1, le=300_000)
    correlation_id: str | None = Field(default=None, max_length=120)


def _identity(user: dict) -> tuple[str, str]:
    tenant = str(
        user.get("tenant_id") or user.get("org_id") or user.get("organization_id") or ""
    ).strip()
    actor = str(
        user.get("sub") or user.get("user_id") or user.get("id") or user.get("email") or ""
    ).strip()
    if not tenant or not actor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant and actor context required",
        )
    return actor, tenant


def _resolve_circle(name: str) -> CircleName:
    try:
        return CircleName(name)
    except ValueError as exc:
        known = ", ".join(member.value for member in CircleName)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown circle '{name}'. Known circles: {known}",
        ) from exc


@router.get("")
async def federation_topology(user: dict = Depends(get_current_user_token)) -> dict:
    actor, tenant = _identity(user)
    governance = get_governance_core()
    return {
        "architecture": "Federated Capability Circles (FCC)",
        "tenant_id": tenant,
        "actor_id": actor,
        "centers": governance.topology(),
        "capabilities": list(governance.capabilities()),
    }


@router.get("/health")
async def federation_health(user: dict = Depends(get_current_user_token)) -> dict:
    _identity(user)
    return get_governance_core().federation_health()


@router.get("/events")
async def federation_events(limit: int = 50, user: dict = Depends(get_current_user_token)) -> dict:
    _identity(user)
    governance = get_governance_core()
    realtime = governance.resolve(CircleName.REALTIME)
    if realtime is None:
        return {"events": [], "count": 0}
    recent = realtime.recent(min(max(limit, 1), 200))  # type: ignore[union-attr]
    return {"events": recent, "count": len(recent)}


@router.post("/dispatch")
async def dispatch_envelope(body: DispatchBody, user: dict = Depends(get_current_admin)) -> dict:
    actor, tenant = _identity(user)
    circle = _resolve_circle(body.circle)
    envelope = ExecutionEnvelope(
        circle=circle,
        capability=body.capability,
        tenant_id=tenant,
        actor_id=actor,
        payload=body.payload,
        policy=body.policy,
        deadline_ms=body.deadline_ms,
        correlation_id=body.correlation_id,
    )
    governance = get_governance_core()
    result = await governance.route(envelope)
    payload_out = result.to_dict()
    logger.info(
        f"[CirclesAPI] dispatch circle={circle.value} "
        f"capability={body.capability} status={result.status.value} "
        f"actor={actor} tenant={tenant}"
    )
    return payload_out
