"""Ecosystem user-facing routes — Phase 5, 12, 14 (ROADMAP §22, §36, §45)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from adaptive_engine.correlation import new_correlation_context
from ecosystem import (
    Capability,
    CapabilityLifecycleState,
    ProviderKind,
    ResourceRecord,
    ResourceState,
    TaskOwner,
    TaskState,
    get_capability_registry,
    get_deployment_tracker,
    get_health_aggregator,
    get_mcp_skeleton,
    get_resource_registry,
    get_task_engine,
)

router = APIRouter(prefix="/api/v1/ecosystem", tags=["ecosystem"])


class CapabilitySearchRequest(BaseModel):
    requirement: str
    signature_hint: str | None = None
    category_hint: str | None = None
    limit: int = 10


@router.get("/capabilities")
def list_capabilities(
    state: str | None = None, category: str | None = None, limit: int = Query(200, le=500)
) -> list[dict]:
    return [
        c.model_dump()
        for c in get_capability_registry().list(
            state=CapabilityLifecycleState(state) if state else None, category=category, limit=limit
        )
    ]


@router.post("/capabilities/search")
def search_capabilities(req: CapabilitySearchRequest) -> dict:
    caps = get_capability_registry().search(
        req.requirement,
        signature_hint=req.signature_hint,
        category_hint=req.category_hint,
        limit=req.limit,
    )
    return {
        "requirement": req.requirement,
        "candidates": [c.model_dump() for c in caps],
        "rule": "REUSE > ADAPT > EXTEND > CREATE",
        "gap_detected": len(caps) == 0,
    }


@router.get("/capabilities/{capability_id}")
def get_capability(capability_id: str) -> dict:
    c = get_capability_registry().get(capability_id)
    if not c:
        raise HTTPException(404, "not found")
    return c.model_dump()


class TaskSubmitRequest(BaseModel):
    goal: str
    owner: str = "USER"
    scope: str = "USER_WORKSPACE"
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    capability_requirements: list[dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "medium"
    tenant_id: str | None = None
    created_by: str = "user"


@router.post("/tasks")
def submit_task(req: TaskSubmitRequest) -> dict:
    new_correlation_context(user_id=req.created_by, tenant_id=req.tenant_id)
    try:
        owner = TaskOwner(req.owner)
    except ValueError:
        raise HTTPException(400, f"invalid owner: {req.owner}")
    t = get_task_engine().submit(
        goal=req.goal,
        owner=owner,
        scope=req.scope,
        created_by=req.created_by,
        tenant_id=req.tenant_id,
        success_criteria=req.success_criteria,
        capability_requirements=req.capability_requirements,
        risk_level=req.risk_level,
    )
    return t.model_dump()


@router.get("/tasks")
def list_tasks(
    state: str | None = None, owner: str | None = None, limit: int = Query(100, le=500)
) -> list[dict]:
    return [
        t.model_dump()
        for t in get_task_engine().list(
            state=TaskState(state) if state else None,
            owner=TaskOwner(owner) if owner else None,
            limit=limit,
        )
    ]


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    t = get_task_engine().get(task_id)
    if not t:
        raise HTTPException(404, "not found")
    return t.model_dump()


class TaskTransitionRequest(BaseModel):
    to_state: str
    patch: dict[str, Any] | None = None
    error: str | None = None
    actor: str = "system"


@router.post("/tasks/{task_id}/transition")
def transition_task(task_id: str, req: TaskTransitionRequest) -> dict:
    try:
        to = TaskState(req.to_state)
    except ValueError:
        raise HTTPException(400, f"invalid state: {req.to_state}")
    try:
        return (
            get_task_engine()
            .transition(task_id, to, actor=req.actor, patch=req.patch, error=req.error)
            .model_dump()
        )
    except Exception as e:
        raise HTTPException(409, str(e))


class TaskDeliverRequest(BaseModel):
    result: dict[str, Any]
    actor: str = "system"


@router.post("/tasks/{task_id}/deliver")
def deliver_task(task_id: str, req: TaskDeliverRequest) -> dict:
    return get_task_engine().deliver(task_id, req.result, actor=req.actor).model_dump()


@router.get("/resources")
def list_resources(
    provider: str | None = None,
    environment: str | None = None,
    state: str | None = None,
    limit: int = Query(200, le=500),
) -> list[dict]:
    return [
        r.model_dump()
        for r in get_resource_registry().list(
            provider=ProviderKind(provider) if provider else None,
            environment=environment,
            state=ResourceState(state) if state else None,
            limit=limit,
        )
    ]


class ResourceRegisterRequest(BaseModel):
    name: str
    provider: str
    type: str = "web_service"
    environment: str = "production"
    repository: str | None = None
    region: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider_config_ref: str | None = None
    owner: str = "system"
    tenant_id: str | None = None


@router.post("/resources")
def register_resource(req: ResourceRegisterRequest) -> dict:
    try:
        p = ProviderKind(req.provider)
    except ValueError:
        raise HTTPException(400, f"invalid provider: {req.provider}")
    r = ResourceRecord(
        name=req.name,
        provider=p,
        type=req.type,
        environment=req.environment,
        repository=req.repository,
        region=req.region,
        dependencies=req.dependencies,
        capabilities=req.capabilities,
        metadata=req.metadata,
        provider_config_ref=req.provider_config_ref,
        owner=req.owner,
        tenant_id=req.tenant_id,
    )
    return get_resource_registry().register(r).model_dump()


@router.get("/health")
def ecosystem_health() -> dict:
    agg = get_health_aggregator()
    return {
        "composite": str(agg.composite_status()),
        "resources": [h.model_dump() for h in agg.all_latest()],
        "top_memory": [h.model_dump() for h in agg.top_memory_consumers(5)],
    }


@router.get("/deployments")
def list_deployments(
    resource_id: str | None = None, commit_sha: str | None = None, limit: int = Query(50, le=200)
) -> list[dict]:
    dt = get_deployment_tracker()
    if commit_sha:
        return [d.model_dump() for d in dt.list_by_commit(commit_sha)]
    if resource_id:
        return [d.model_dump() for d in dt.list_by_resource(resource_id, limit=limit)]
    return []


@router.get("/deployments/trace/{commit_sha}")
def trace_commit(commit_sha: str) -> dict:
    return get_deployment_tracker().trace(commit_sha)


@router.get("/mcp/manifest")
def mcp_manifest() -> dict:
    return get_mcp_skeleton().manifest()


@router.post("/mcp/call")
async def mcp_call(operation: str, arguments: dict[str, Any] | None = None) -> dict:
    return await get_mcp_skeleton().call(operation, arguments=arguments or {})


__all__ = ["router"]
