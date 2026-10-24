from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import get_project_admin
from database.supabase_client import db

router = APIRouter(
    prefix="/repos",
    tags=["repos"],
    dependencies=[Depends(get_project_admin)],
)


class RepoCreate(BaseModel):
    id: str
    name: str
    url: str
    description: str = ""
    language: str = ""
    category: str | None = None
    priority: str | None = "medium"
    purpose: str | None = None
    install_command: str | None = None
    status: str | None = "active"
    metadata: dict | None = None


class RepoUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    description: str | None = None
    language: str | None = None
    category: str | None = None
    priority: str | None = None
    purpose: str | None = None
    install_command: str | None = None
    status: str | None = None
    metadata: dict | None = None


@router.get("/")
async def list_repos(
    category: str | None = None,
    priority: str | None = None,
    status: str = "active",
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    user: dict = Depends(get_project_admin),
):
    if not db.client:
        raise HTTPException(status_code=503, detail="Database not configured")
    query = (
        await db.client.table("github_repos")
        .select("*")
        .eq("status", status)
        .eq("tenant_id", user["tenant_id"])
    )
    if category:
        query = query.eq("category", category)
    if priority:
        query = query.eq("priority", priority)
    res = query.range(offset, offset + limit - 1).execute()
    return {"items": res.data or [], "total": len(res.data or [])}


@router.post("/")
async def create_repo(payload: RepoCreate, user: dict = Depends(get_project_admin)):
    if not db.client:
        raise HTTPException(status_code=503, detail="Database not configured")
    data = payload.dict(exclude_none=True)
    data["tenant_id"] = user["tenant_id"]
    res = await db.client.table("github_repos").insert(data).execute()
    return {"status": "success", "repo": res.data[0] if res.data else data}


@router.patch("/{repo_id}")
async def update_repo(repo_id: str, payload: RepoUpdate, user: dict = Depends(get_project_admin)):
    if not db.client:
        raise HTTPException(status_code=503, detail="Database not configured")
    data = payload.dict(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    res = (
        await db.client.table("github_repos")
        .update(data)
        .eq("id", repo_id)
        .eq("tenant_id", user["tenant_id"])
        .execute()
    )
    return {"status": "success", "repo": res.data[0] if res.data else None}


@router.delete("/{repo_id}")
async def delete_repo(repo_id: str, user: dict = Depends(get_project_admin)):
    if not db.client:
        raise HTTPException(status_code=503, detail="Database not configured")
    await (
        db.client.table("github_repos")
        .update({"status": "archived"})
        .eq("id", repo_id)
        .eq("tenant_id", user["tenant_id"])
        .execute()
    )
    return {"status": "success", "message": "Repo archived"}
