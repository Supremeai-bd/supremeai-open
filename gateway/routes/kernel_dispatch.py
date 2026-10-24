"""backend/api/routes/kernel_dispatch.py — Headless Universal Dispatch Endpoint.

Exposes POST /api/v1/kernel/dispatch:
- Requires authenticated user and resolved tenant
- Delegates to supreme_kernel
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.deps import get_current_tenant, get_current_user_token
from core.kernel.dispatcher import supreme_kernel
from core.kernel.interface import CircleScope, ExecutionMode, KernelRequest, KernelResponse

router = APIRouter(
    prefix="/api/v1/kernel",
    tags=["SupremeKernel"],
    dependencies=[Depends(get_current_user_token)],
)


class InboundDispatchRequest(BaseModel):
    target_circle: CircleScope
    capability: str = Field(min_length=1, max_length=160)
    mode: ExecutionMode = ExecutionMode.SYNC
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    deadline_ms: int = Field(default=30_000, ge=1, le=300_000)
    idempotency_key: str | None = None


@router.post("/dispatch", response_model=KernelResponse)
async def dispatch_kernel_request(
    request: InboundDispatchRequest,
    user_token: dict[str, Any] = Depends(get_current_user_token),
    tenant_id: str = Depends(get_current_tenant),
) -> KernelResponse:
    """Headless single-door dispatch endpoint for any capability in SupremeAI."""
    actor_id = (
        user_token.get("sub") or user_token.get("uid") or user_token.get("user_id") or "anonymous"
    )
    resolved_tenant = str(tenant_id)

    kernel_req = KernelRequest(
        target_circle=request.target_circle,
        capability=request.capability,
        mode=request.mode,
        actor_id=str(actor_id),
        tenant_id=str(resolved_tenant),
        workspace_id=request.metadata.get("workspace_id"),
        idempotency_key=request.idempotency_key,
        deadline_ms=request.deadline_ms,
        payload=request.payload,
        metadata=request.metadata,
    )

    response = await supreme_kernel.dispatch(kernel_req)
    if response.status == "rejected":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=response.error_message or "Capability rejected by policy",
        )
    return response
