"""Tenant-scoped capability discovery and lifecycle operations."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_token
from core.connection_registry import connection_registry
from core.logging_config import logger

router = APIRouter(prefix="/api/v1/workspace", tags=["Workspace Capabilities"])


class CapabilityRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)
    name: str = Field(..., min_length=1, max_length=255)
    connection_type: str = Field(default="mcp", max_length=32)
    capabilities: list[dict] = Field(default_factory=list)
    tool_permissions: dict[str, str] = Field(default_factory=dict)


class PermissionRequest(BaseModel):
    permission_level: str = Field(..., pattern="^(user|admin|system)$")


class ToolPermissionRequest(BaseModel):
    tool_permissions: dict[str, str]


def _identity(user: dict) -> dict:
    tenant = str(
        user.get("tenant_id") or user.get("org_id") or user.get("organization_id") or ""
    ).strip()
    actor = str(
        user.get("sub") or user.get("user_id") or user.get("id") or user.get("email") or ""
    ).strip()
    if not tenant or not actor:
        raise HTTPException(status_code=403, detail="Tenant and actor context required")
    return {
        **user,
        "tenant_id": tenant,
        "user_id": actor,
        "role": user.get("role") or user.get("user_role") or "user",
    }


def _record(record) -> dict:
    return record.model_dump(mode="json")


def _call(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/capabilities")
async def list_workspace_capabilities(user: dict = Depends(get_current_user_token)) -> dict:
    identity = _identity(user)
    records = connection_registry.list_for_tenant(identity)
    return {
        "tenant_id": identity["tenant_id"],
        "actor_id": identity["user_id"],
        "capabilities": [_record(item) for item in records],
    }


@router.post("/capabilities", status_code=status.HTTP_202_ACCEPTED)
async def register_workspace_capability(
    req: CapabilityRequest, user: dict = Depends(get_current_user_token)
) -> dict:
    identity = _identity(user)
    parsed = urlparse(req.url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail="A valid capability URL is required")
    record = _call(
        connection_registry.register,
        user=identity,
        url=req.url,
        name=req.name,
        capabilities=req.capabilities,
        tool_permissions=req.tool_permissions,
    )
    logger.info(
        "Capability registration accepted",
        extra={"tenant_id": identity["tenant_id"], "connection_id": record.id},
    )
    return {
        "connection": _record(record),
        "message": "Connection registered. Provider consent may still be required.",
    }


@router.post("/capabilities/{connection_id}/health")
async def check_capability_health(
    connection_id: str, user: dict = Depends(get_current_user_token)
) -> dict:
    record = _call(connection_registry.health, user=_identity(user), connection_id=connection_id)
    return {"connection": _record(record)}


@router.post("/capabilities/{connection_id}/reactivate")
async def reactivate_capability(
    connection_id: str, user: dict = Depends(get_current_user_token)
) -> dict:
    record = _call(
        connection_registry.reactivate, user=_identity(user), connection_id=connection_id
    )
    return {"connection": _record(record)}


@router.post("/capabilities/{connection_id}/revoke")
async def revoke_capability(
    connection_id: str, user: dict = Depends(get_current_user_token)
) -> dict:
    record = _call(connection_registry.revoke, user=_identity(user), connection_id=connection_id)
    return {"connection": _record(record)}


@router.patch("/capabilities/{connection_id}/permission")
async def update_capability_permission(
    connection_id: str, req: PermissionRequest, user: dict = Depends(get_current_user_token)
) -> dict:
    record = _call(
        connection_registry.set_permission,
        user=_identity(user),
        connection_id=connection_id,
        permission_level=req.permission_level,
    )
    return {"connection": _record(record)}


@router.patch("/capabilities/{connection_id}/tools")
async def update_tool_permissions(
    connection_id: str, req: ToolPermissionRequest, user: dict = Depends(get_current_user_token)
) -> dict:
    record = _call(
        connection_registry.set_tool_permissions,
        user=_identity(user),
        connection_id=connection_id,
        tool_permissions=req.tool_permissions,
    )
    return {"connection": _record(record)}
