from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from api.dependencies import get_current_user_token
from core.connection_registry import connection_registry
from core.mcp_client import MCPRegistryClient
from tools.tenant_rate_limiter import TenantRateLimiter

router = APIRouter(prefix="/api/v1/mcp", tags=["mcp"])


class MCPConnectRequest(BaseModel):
    mcp_url: HttpUrl
    name: str | None = None
    permission_level: str = "user"


class MCPPermissionRequest(BaseModel):
    permission_level: str


class MCPToolPermissionRequest(BaseModel):
    tool_permissions: dict[str, str]


@router.post("/discover")
async def discover_mcp_server(
    req: MCPConnectRequest,
    user: dict = Depends(get_current_user_token),
):
    """
    Connects to a user-provided MCP server URL, validates it for SSRF,
    and returns the tools it provides.
    """
    tenant_id = user.get("tenant_id") or user.get("organization_id")
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Authenticated tenant context is required")
    quota = await TenantRateLimiter().check_quota(str(tenant_id), cost=0.0)
    if not quota.get("allowed"):
        raise HTTPException(status_code=429, detail="MCP connection quota exceeded")

    client = MCPRegistryClient()
    try:
        # Convert HttpUrl to string
        tools = await client.connect_and_discover(str(req.mcp_url))
        record = connection_registry.register(
            user=user,
            url=str(req.mcp_url),
            capabilities=tools,
            name=req.name,
            permission_level=req.permission_level,
        )
        return {"status": "success", "connection": record.model_dump(mode="json")}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe)) from pe
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve)) from ve
    except Exception:
        # Keep provider URLs, credentials, and internal network details out of responses.
        raise HTTPException(status_code=502, detail="MCP server connection failed")


@router.patch("/connections/{connection_id}/permission")
async def update_mcp_permission(
    connection_id: str,
    req: MCPPermissionRequest,
    user: dict = Depends(get_current_user_token),
):
    """Allow an authorized tenant administrator to change one connection's role."""
    try:
        connection = connection_registry.set_permission(
            user=user,
            connection_id=connection_id,
            permission_level=req.permission_level,
        )
        return {"status": "success", "connection": connection.model_dump(mode="json")}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/connections/{connection_id}/tools")
async def update_mcp_tool_permissions(
    connection_id: str,
    req: MCPToolPermissionRequest,
    user: dict = Depends(get_current_user_token),
):
    """Allow a tenant administrator to set capability-level tool permissions."""
    try:
        connection = connection_registry.set_tool_permissions(
            user=user,
            connection_id=connection_id,
            tool_permissions=req.tool_permissions,
        )
        return {"status": "success", "connection": connection.model_dump(mode="json")}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/connections/{connection_id}/reactivate")
async def reactivate_mcp_connection(
    connection_id: str,
    user: dict = Depends(get_current_user_token),
):
    """Reactivate a revoked connection after rechecking its URL policy."""
    try:
        connection = connection_registry.reactivate(user=user, connection_id=connection_id)
        return {"status": "success", "connection": connection.model_dump(mode="json")}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/connections/{connection_id}/health")
async def check_mcp_connection_health(
    connection_id: str,
    user: dict = Depends(get_current_user_token),
):
    """Return the tenant-scoped connection status after a policy check."""
    try:
        connection = await connection_registry.health(user=user, connection_id=connection_id)
        return {"status": "success", "connection": connection.model_dump(mode="json")}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/connections/{connection_id}")
async def revoke_mcp_connection(
    connection_id: str,
    user: dict = Depends(get_current_user_token),
):
    """Revoke a tenant connection without deleting its audit history."""
    try:
        connection = connection_registry.revoke(user=user, connection_id=connection_id)
        return {"status": "success", "connection": connection.model_dump(mode="json")}
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/connections")
async def list_mcp_connections(
    user: dict = Depends(get_current_user_token),
):
    """List only the authenticated actor's tenant-owned connections."""
    try:
        return {
            "connections": [
                connection.model_dump(mode="json")
                for connection in connection_registry.list_for_tenant(user)
            ]
        }
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
