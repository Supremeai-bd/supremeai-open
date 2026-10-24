from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security.authentication.rbac import get_current_admin
from database.supabase_client import db

router = APIRouter(
    prefix="/api/v1/tools-registry",
    tags=["tools-registry"],
    dependencies=[Depends(get_current_admin)],
)


class ToolCreate(BaseModel):
    id: str
    name: str
    file_path: str
    category: str | None = None
    dependencies: list[str] | None = None
    cost_per_call: float | None = 0.0
    description: str | None = None
    config_schema: dict | None = None


class ToolUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    status: str | None = None
    dependencies: list[str] | None = None
    cost_per_call: float | None = None
    description: str | None = None
    config_schema: dict | None = None


@router.get("/")
async def list_tools(
    category: str | None = None,
    status: str = "active",
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    if not db.client:
        raise HTTPException(status_code=503, detail="Database not configured")
    query = await db.service_client.table("tools_registry").select("*").eq("status", status)
    if category:
        query = query.eq("category", category)
    res = query.range(offset, offset + limit - 1).execute()
    return {"items": res.data or [], "total": len(res.data or [])}


@router.post("/")
async def create_tool(payload: ToolCreate):
    if not db.client:
        raise HTTPException(status_code=503, detail="Database not configured")
    data = payload.dict()
    res = await db.service_client.table("tools_registry").insert(data).execute()
    return {"status": "success", "tool": res.data[0] if res.data else data}


@router.patch("/{tool_id}")
async def update_tool(tool_id: str, payload: ToolUpdate):
    if not db.client:
        raise HTTPException(status_code=503, detail="Database not configured")
    data = payload.dict(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = await db.service_client.table("tools_registry").update(data).eq("id", tool_id).execute()
    return {"status": "success", "tool": res.data[0] if res.data else None}


@router.delete("/{tool_id}")
async def delete_tool(tool_id: str):
    if not db.client:
        raise HTTPException(status_code=503, detail="Database not configured")
    await (
        db.service_client.table("tools_registry")
        .update({"status": "archived"})
        .eq("id", tool_id)
        .execute()
    )
    return {"status": "success", "message": "Tool archived"}
