"""Agent Registry REST API — multi-AI governance Phase 1 (issue #1150).

বাংলা সারসংক্ষেপ:
------------------
রেজিস্ট্রি-র পাতলা FastAPI আবরণ:
- GET    /api/v1/agents          — তালিকা (পড়া নিরীহ — pre-auth ঠিক আছে)
- GET    /api/v1/agents/{id}     — একজনের বিবরণ
- POST   /api/v1/agents          — Admin upsert (role + provider assignment)
- DELETE /api/v1/agents/{id}     — Admin remove

লেখা পথে কঠোর admin auth (`get_project_admin`) — Phase-1 acceptance নীতি।
Safety boundary: PR + CI; এই API মূল সংজ্ঞা রাখে, কোনো orchestration নয়।
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api.dependencies import get_project_admin
from core.agent_registry import AgentRecord, AgentRegistry, get_agent_registry

router = APIRouter(prefix="/api/v1/agents", tags=["agent-registry"])


class AgentUpsertRequest(BaseModel):
    """POST /api/v1/agents body — পুরো AgentRecord।"""

    id: str
    role: str
    provider: str
    workspace_branch: str
    active: bool = True
    notes: str = ""


class OwnershipRequest(BaseModel):
    """POST /api/v1/agents/{id}/ownership body — task মালিকানা রেকর্ড তৈরি।"""

    task_id: str
    expected_scope: str
    status: str = "assigned"
    branch: str | None = None


@router.get("", response_model=list[AgentRecord], summary="List registered agents")
async def list_agents(active_only: bool = False) -> list[AgentRecord]:
    """সব agent-এর role + provider — dashboard dropdown এটা পড়বে।"""
    return get_agent_registry().list_agents(active_only=active_only)


@router.get("/{agent_id}", response_model=AgentRecord, summary="Single agent record")
async def get_agent(agent_id: str) -> AgentRecord:
    record = get_agent_registry().get(agent_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown agent {agent_id!r}"
        )
    return record


@router.post(
    "",
    response_model=AgentRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Admin: define/upsert an agent (role + AI provider)",
)
async def upsert_agent(
    payload: AgentUpsertRequest,
    _admin: dict = Depends(get_project_admin),
) -> AgentRecord:
    """Admin সংজ্ঞা — #1150 Phase-1 §1। খারাপ ইনপুট → 422।"""
    try:
        record = AgentRecord.model_validate(payload.model_dump())
        return get_agent_registry().upsert(record)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/{agent_id}/ownership",
    response_model=dict[str, Any],
    summary="Assign task ownership to an agent (task_id + scope + branch)",
)
async def assign_ownership(
    agent_id: str,
    payload: OwnershipRequest,
    _admin: dict = Depends(get_project_admin),
) -> dict[str, Any]:
    """#1150 Phase-1 §2 — task মালিকানা রেকর্ড; অজানা agent → 404/422।"""
    try:
        return get_agent_registry().ownership_record(
            agent_id,
            payload.task_id,
            payload.expected_scope,
            status=payload.status,
            branch=payload.branch,
        )
    except ValueError as exc:
        code = (
            status.HTTP_404_NOT_FOUND
            if "unknown agent" in str(exc)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Admin: remove an agent",
)
async def remove_agent(agent_id: str, _admin: dict = Depends(get_project_admin)) -> None:
    """204 মানে body নিষেধ — শুধু raise/return None (FastAPI চুক্তি)।"""
    removed = get_agent_registry().remove(agent_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown agent {agent_id!r}"
        )
    return None


__all__ = ["router"]
