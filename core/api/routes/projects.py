"""Project Spaces CRUD — ERR-B01 fix (canonical defect register 2026-09-15).

বাংলা: `/projects` পেজটি আগে স্ট্যাটিক মার্কেটিং কার্ড ছিল — "Create a project
space" বাটন কিছুই করত না (ERR-B01)। এই রাউটার real, DB-backed Project Space
CRUD দেয়: create / list / rename / delete, ownership-enforced।

Pattern: `api.routes.plugins` — canonical `get_current_user_token` dependency,
`get_db_session` AsyncSession, user identity JWT payload ('sub') থেকে।
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_token
from database.session import get_db_session
from models.project import Project

router = APIRouter(prefix="/api/v1/projects", tags=["Project Spaces"])


async def _current_user_id(payload: dict = Depends(get_current_user_token)) -> str:
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Invalid token structure")
    return str(sub)


# ---------- Schemas ----------


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class ProjectOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None


def _serialize(project: Project) -> dict:
    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description or "",
        "status": project.status,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


async def _get_owned_project(project_id: str, owner_id: str, db: AsyncSession) -> Project:
    """Fetch a project enforcing ownership — 404 (not 403) to avoid id probing."""
    project = await db.get(Project, project_id)
    if project is None or project.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ---------- Routes ----------


@router.post("", status_code=201)
async def create_project(
    payload: ProjectCreate,
    user_id: str = Depends(_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new Project Space owned by the current user."""
    project = Project(
        owner_id=user_id,
        name=payload.name.strip(),
        description=payload.description,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return {"status": "success", "project": _serialize(project)}


@router.get("")
async def list_projects(
    user_id: str = Depends(_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """List the current user's Project Spaces (newest first)."""
    result = await db.execute(
        select(Project)
        .where(Project.owner_id == user_id, Project.status == "active")
        .order_by(Project.created_at.desc())
    )
    items = [_serialize(p) for p in result.scalars().all()]
    return {"items": items, "total": len(items)}


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    user_id: str = Depends(_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Rename / re-describe a Project Space (owner only)."""
    project = await _get_owned_project(project_id, user_id, db)
    if payload.name is not None:
        project.name = payload.name.strip()
    if payload.description is not None:
        project.description = payload.description
    await db.commit()
    await db.refresh(project)
    return {"status": "success", "project": _serialize(project)}


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    user_id: str = Depends(_current_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    """Permanently delete a Project Space (owner only)."""
    project = await _get_owned_project(project_id, user_id, db)
    await db.delete(project)
    await db.commit()
    return {"status": "success", "message": "Project deleted"}
