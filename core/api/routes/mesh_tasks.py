"""Mesh Task Queue REST API — MESH-6, issue #926 (P0-critical).

বাংলা সারসংক্ষেপ:
------------------
Tower-native Task Queue-র REST surface (/api/v1/mesh/tasks)। Core logic সব
backend/core/task_router.py-তে — এখানে কেবল পাতলা FastAPI আবরণ:
- POST /api/v1/mesh/tasks                    — submit
- GET  /api/v1/mesh/tasks?task_status=       — snapshot + filter
- GET  /api/v1/mesh/tasks/queue/stats        — per-status counts
- GET  /api/v1/mesh/tasks/{task_id}          — detail
- POST /api/v1/mesh/tasks/{task_id}/claim    — CAS atomic claim ('any' = best match)
- POST /api/v1/mesh/tasks/{task_id}/lease    — lease renewal (leased-by check)
- POST /api/v1/mesh/tasks/{task_id}/complete — ফলাফল সহ সমাপ্তি
- POST /api/v1/mesh/tasks/{task_id}/fail     — ব্যর্থতা → retry/failed (Zero Zombie)
- POST /api/v1/mesh/tasks/{task_id}/cancel   — operator cancel
- POST /api/v1/mesh/tasks/reap               — expired lease re-queue (failover)

সম্পর্কিত:
- Master plan: docs/plans/MULTI_AGENT_MESH_MASTER_PLAN.md (§১, §৪.3, §৬ MESH-6)
- Issue: #926 (P0-critical) · Depends on: backend/core/task_router.py
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.task_router import (
    VALID_TASK_TYPES,
    ClaimedTask,
    TaskRecord,
    TaskRouter,
    get_task_router,
)

router = APIRouter(
    prefix="/api/v1/mesh/tasks",
    tags=["mesh-tasks"],
    # বাংলা: presence-এর মতোই pre-auth — task submit/claim প্রথম কল হতে পারে।
    # Per-task-type বিপজ্জনকতা HITL gate (MESH-4) এ যাচাই হবে; এখানে কেবল
    # queue state পরিচালিত হয়, privileged resource স্পর্শ করা হয় না।
)


# ── Request Models (tasks) ───────────────────────────────────────────────────
class TaskSubmitRequest(BaseModel):
    """POST /api/v1/mesh/tasks — নতুন task জমা দেওয়ার body।"""

    task_type: str = Field(..., description=f"One of {sorted(VALID_TASK_TYPES)}")
    title: str = Field(..., min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    target_role: str | None = Field(default=None, description="planner|coder|tester|gate|observer")
    priority: int = Field(default=5, ge=0, le=9, description="0 = সর্বোচ্চ অগ্রাধিকার")
    max_attempts: int = Field(default=3, ge=1, le=10)


class TaskClaimRequest(BaseModel):
    """POST /api/v1/mesh/tasks/{task_id}/claim — node নিজের জন্য claim করতে পারে,
    অথবা general claim endpoint (task_id='any') দিয়ে উপযুক্ত task নিতে পারে।"""

    node_id: str = Field(..., min_length=1, max_length=128)
    role: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    lease_seconds: int | None = Field(default=None, ge=1)


class TaskLeaseRequest(BaseModel):
    """POST /api/v1/mesh/tasks/{task_id}/lease — lease renewal body।"""

    node_id: str = Field(..., min_length=1, max_length=128)
    lease_seconds: int | None = Field(default=None, ge=1)


class TaskCompleteRequest(BaseModel):
    """POST /api/v1/mesh/tasks/{task_id}/complete — ফলাফল সহ সমাপ্তি।"""

    node_id: str = Field(..., min_length=1, max_length=128)
    result: dict[str, Any] = Field(default_factory=dict)


class TaskFailRequest(BaseModel):
    """POST /api/v1/mesh/tasks/{task_id}/fail — ত্রুটি সহ ব্যর্থতা (retry সিদ্ধান্ত router নেবে)।"""

    node_id: str = Field(..., min_length=1, max_length=128)
    error: str = Field(..., min_length=1, max_length=2000)


class TaskListResponse(BaseModel):
    """GET /api/v1/mesh/tasks — queue snapshot envelope।"""

    tasks: list[TaskRecord]
    count: int
    stats: dict[str, int]


# ── Endpoints (tasks) ────────────────────────────────────────────────────────
@router.post(
    "",
    response_model=TaskRecord,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new mesh task (MESH-6)",
)
async def submit_task(
    payload: TaskSubmitRequest,
    router: TaskRouter = Depends(get_task_router),
) -> TaskRecord:
    """নতুন task queue-তে জমা দাও — Telegram /task (MESH-4) ও MCP tools এটাই কল করবে।"""
    try:
        record = await router.submit_task(
            task_type=payload.task_type,
            title=payload.title,
            payload=payload.payload,
            required_capabilities=payload.required_capabilities,
            target_role=payload.target_role,
            priority=payload.priority,
            max_attempts=payload.max_attempts,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return record


@router.get(
    "",
    response_model=TaskListResponse,
    status_code=status.HTTP_200_OK,
    summary="Queue snapshot with optional status filter",
)
async def list_tasks(
    task_status: str | None = None,
    router: TaskRouter = Depends(get_task_router),
) -> TaskListResponse:
    """Queue-র বর্তমান state — MESH-2 dashboard ও Tower monitoring এটা পড়ে।"""
    try:
        tasks = await router.list_tasks(status=task_status)
        stats = await router.queue_stats()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return TaskListResponse(tasks=tasks, count=len(tasks), stats=stats)


@router.get(
    "/queue/stats",
    response_model=dict[str, int],
    status_code=status.HTTP_200_OK,
    summary="Per-status task counts (queue visibility)",
)
async def queue_stats(router: TaskRouter = Depends(get_task_router)) -> dict[str, int]:
    """কোন status-এ কতগুলি task — এক নজরে queue depth।"""
    return await router.queue_stats()


@router.get(
    "/{task_id}",
    response_model=TaskRecord,
    status_code=status.HTTP_200_OK,
    summary="Single task detail",
)
async def get_task(task_id: str, router: TaskRouter = Depends(get_task_router)) -> TaskRecord:
    """একটি task-এর পূর্ণ state (lease info সহ) — 404 যদি না থাকে।"""
    record = await router.get_task(task_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task_id {task_id!r} not found",
        )
    return record


@router.post(
    "/{task_id}/claim",
    response_model=ClaimedTask,
    status_code=status.HTTP_200_OK,
    summary="CAS atomic claim (task_id='any' → best matching pending task)",
)
async def claim_task(
    task_id: str,
    payload: TaskClaimRequest,
    router: TaskRouter = Depends(get_task_router),
) -> ClaimedTask:
    """Atomic claim — দুই agent একই task পাবে না (asyncio.Lock CAS)।

    task_id='any' দিলে node-এর role/capabilities মেলানো সবচেয়ে উপযুক্ত pending
    task দেওয়া হয়। কোনো task মেলে না হলে 204 (no content) — caller idle থাকবে।
    """
    try:
        if task_id == "any":
            got = await router.claim_task(
                node_id=payload.node_id,
                role=payload.role,
                capabilities=payload.capabilities,
                lease_seconds=payload.lease_seconds,
            )
            if got is None:
                # বাংলা: 204 = "কিছু নেই, idle থাকো" — daemon-এর জন্য স্বাভাবিক path।
                return Response(status_code=status.HTTP_204_NO_CONTENT)
            return ClaimedTask(**got.model_dump())
        # নির্দিষ্ট task claim — claim_task internal "best match" ব্যবহার করে না;
        # এখানে direct probe দরকার: task pending আছে কিনা দেখে claim করা হয়।
        record = await router.get_task(task_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"task_id {task_id!r} not found",
            )
        got = await router._claim_specific(  # noqa: SLF001 — route is part of the module contract
            task_id,
            node_id=payload.node_id,
            lease_seconds=payload.lease_seconds,
        )
        if got is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"task {task_id} is not claimable (status={record.status})",
            )
        return ClaimedTask(**got.model_dump())
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{task_id}/lease",
    response_model=TaskRecord,
    status_code=status.HTTP_200_OK,
    summary="Renew lease TTL (leased-by node only)",
)
async def renew_lease(
    task_id: str,
    payload: TaskLeaseRequest,
    router: TaskRouter = Depends(get_task_router),
) -> TaskRecord:
    """Lease TTL বাড়াও — ভুল node পাঠালে 403, task না থাকলে 404।"""
    try:
        return await router.renew_lease(
            task_id, node_id=payload.node_id, lease_seconds=payload.lease_seconds
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/{task_id}/complete",
    response_model=TaskRecord,
    status_code=status.HTTP_200_OK,
    summary="Mark task done with result (leased-by node only)",
)
async def complete_task(
    task_id: str,
    payload: TaskCompleteRequest,
    router: TaskRouter = Depends(get_task_router),
) -> TaskRecord:
    """সফল সমাপ্তি — SupremeAI Core এই result দেখে audit করবে (MESH flow step 6)।"""
    try:
        return await router.complete_task(task_id, node_id=payload.node_id, result=payload.result)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/{task_id}/fail",
    response_model=TaskRecord,
    status_code=status.HTTP_200_OK,
    summary="Report task failure → retry or permanent-fail (Zero Zombie)",
)
async def fail_task(
    task_id: str,
    payload: TaskFailRequest,
    router: TaskRouter = Depends(get_task_router),
) -> TaskRecord:
    """ব্যর্থতা রিপোর্ট — attempts < max_attempts হলে আবার pending, নাহলে failed।"""
    try:
        return await router.fail_task(task_id, node_id=payload.node_id, error=payload.error)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


@router.post(
    "/{task_id}/cancel",
    response_model=TaskRecord,
    status_code=status.HTTP_200_OK,
    summary="Cancel a pending/leased task (operator action)",
)
async def cancel_task(task_id: str, router: TaskRouter = Depends(get_task_router)) -> TaskRecord:
    """Operator cancel — terminal state এ গেলে 422।"""
    try:
        return await router.cancel_task(task_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post(
    "/reap",
    response_model=dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Reap expired leases → requeue/fail (failover trigger)",
)
async def reap_expired(router: TaskRouter = Depends(get_task_router)) -> dict[str, Any]:
    """মেয়াদোত্তীর্ণ lease-এর সব task re-queue — node মরে গেলে এটাই failover পথ।"""
    reaped = await router.reap_expired_leases()
    return {"reaped": reaped, "count": len(reaped)}


__all__ = [
    "TaskClaimRequest",
    "TaskCompleteRequest",
    "TaskFailRequest",
    "TaskLeaseRequest",
    "TaskListResponse",
    "TaskSubmitRequest",
    "router",
]
