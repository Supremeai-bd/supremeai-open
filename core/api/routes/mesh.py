"""Mesh presence + task dispatch REST API — MESH-1 (#939) + MESH-6 (#926).

বাংলা সারসংক্ষেপ:
------------------
SupremeAI Distributed Multi-Agent Mesh-এর control-plane endpoints:

presence (MESH-1):
- POST   /api/v1/nodes/heartbeat       — একটি agent তার heartbeat পাঠায়
- GET    /api/v1/nodes                  — সব active node-এর তালিকা (MESH-2 dashboard পড়ে)
- GET    /api/v1/nodes/{node_id}        — একটি node-এর বিস্তারিত record
- PATCH  /api/v1/nodes/{node_id}        — node-এর role পরিবর্তন (MESH-2 dropdown)

task queue (MESH-6):
- POST   /api/v1/mesh/tasks                  — নতুন task submit (Telegram /task, MCP tools এটাই কল করে)
- GET    /api/v1/mesh/tasks?status=          — queue snapshot + filter
- GET    /api/v1/mesh/tasks/{task_id}        — task detail
- POST   /api/v1/mesh/tasks/{task_id}/claim   — CAS atomic claim (node capabilities অনুযায়ী)
- POST   /api/v1/mesh/tasks/{task_id}/lease   — lease renewal (heartbeat continuation)
- POST   /api/v1/mesh/tasks/{task_id}/complete — সফল সমাপ্তি (leased-by check সহ)
- POST   /api/v1/mesh/tasks/{task_id}/fail    — ব্যর্থতা → retry/failed (Zero Zombie)
- POST   /api/v1/mesh/tasks/{task_id}/cancel  — operator cancel
- POST   /api/v1/mesh/tasks/reap              — expired lease re-queue (failover trigger)
- GET    /api/v1/mesh/tasks/queue/stats       — per-status count (visibility)

heartbeat-এ auto-dispatch: node heartbeat দিলে Tower স্বয়ংক্রিয়ভাবে তার capabilities
মেলানো pending task claim করে response-এর assigned_tasks-এ পাঠায় — এটাই
supreme-node daemon (MESH-3)-এর প্রত্যাশিত contract। Node ১০ মিনিট heartbeat না
দিলে reap_expired_leases সব lease ছেঁড়ে দেয় — অন্য node/cloud failover করতে পারে।

conventions:
- FastAPI APIRouter + Pydantic v2 models (match existing routes যেমন health.py)
- prefix=/api/v1 (routers.py থেকে mount করা হয়, এখানে prefix দেওয়া নেই)
- process-wide PresenceRegistry + TaskRouter singleton ব্যবহার করে
- কোনো fake/mock নেই — সব endpoint আসল registry/router-এ লেখে/পড়ে

সম্পর্কিত:
- Master plan: docs/plans/MULTI_AGENT_MESH_MASTER_PLAN.md (§১, §৪.3, §৬)
- Issues: #939 (MESH-1), #926 (MESH-6, P0)
- Depends on: backend/core/presence_registry.py, backend/core/task_router.py
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from core.logging_config import logger
from core.presence_registry import (
    DEFAULT_STALE_AFTER_SECONDS,
    VALID_NODE_TYPES,
    VALID_ROLES,
    HeartbeatResult,
    NodeLoad,
    NodeRecord,
    PresenceRegistry,
    get_presence_registry,
)
from core.task_router import ClaimedTask, TaskRouter, get_task_router

router = APIRouter(
    prefix="/api/v1/nodes",
    tags=["mesh-presence"],
    # বাংলা: এই endpoints public mesh presence প্রদান করে। Auth যোগ করা হয়নি
    # কারণ (১) heartbeat একটি agent-এর প্রথম কল হতে পারে — pre-auth; (২) কেবল
    # presence state পড়ে/লেখে, কোনো privileged resource স্পর্শ করে না। একটি
    # follow-up issue আলাদা auth যোগ করবে (MESH-3 local daemon-এর সাথে)।
)


# ── Request Models ───────────────────────────────────────────────────────────
class HeartbeatRequest(BaseModel):
    """POST /api/v1/nodes/heartbeat — request body schema (issue #939 spec-এর সাথে মিল)।"""

    node_id: str = Field(..., min_length=1, max_length=128, description="Unique node identifier")
    node_type: str = Field(..., description=f"One of {sorted(VALID_NODE_TYPES)}")
    role: str = Field(..., description=f"One of {sorted(VALID_ROLES)}")
    capabilities: list[str] = Field(default_factory=list)
    timestamp: str | None = Field(
        default=None,
        description="Client-provided ISO 8601 timestamp (optional; server uses its own clock for lease calc)",
    )
    load: NodeLoad | None = Field(default=None, description="System load snapshot")
    # বাংলা: None মানে "caller omitted করেছে" — registry তখন আগের record-এর
    # assigned_tasks বজায় রাখে (lease continuation contract)। খালি list পাঠালে
    # সেটাই override হবে (caller স্পষ্টভাবে পরিষ্কার করতে চাইলে)।
    assigned_tasks: list[str] | None = Field(
        default=None,
        description="Omit to preserve existing tasks (lease continuation); empty list clears.",
    )
    metadata: dict[str, Any] | None = Field(
        default=None,
        description="Omit to preserve existing metadata; explicit dict replaces.",
    )


class RoleUpdateRequest(BaseModel):
    """PATCH /api/v1/nodes/{node_id} — role update body (MESH-2 dashboard-এর জন্য)।"""

    role: str = Field(..., description=f"One of {sorted(VALID_ROLES)}")


# ── Response Models ───────────────────────────────────────────────────────────
class NodeListResponse(BaseModel):
    """GET /api/v1/nodes — list of active nodes wrapped in metadata envelope।"""

    nodes: list[NodeRecord]
    count: int
    stale_after_seconds: int


class NodeDetailResponse(BaseModel):
    """GET /api/v1/nodes/{node_id} — single node detail (or 404 if unknown)।"""

    node: NodeRecord


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.post(
    "/heartbeat",
    response_model=HeartbeatResult,
    status_code=status.HTTP_200_OK,
    summary="Register a mesh node heartbeat",
)
async def post_node_heartbeat(
    payload: HeartbeatRequest,
    registry: PresenceRegistry = Depends(get_presence_registry),
    task_router: TaskRouter = Depends(get_task_router),
) -> HeartbeatResult:
    """একটি agent তার heartbeat পাঠায় — registry-তে presence ও lease refresh হয়।

    প্রতিটি heartbeat একটি lease প্রদান করে যা ডিফল্টভাবে ১০ মিনিট পর মেয়াদোত্তীর্ণ হয়।
    পরবর্তী heartbeat এলে lease আবার refresh হয়। Lease মেয়াদোত্তীর্ণ হলেও record
    সরানো হয় না — শুধু `lease_active=false` চিহ্নিত করা হয়।

    Invalid `node_type` বা `role` হলে 422 + detailed error ফেরত আসে।
    """
    try:
        result = await registry.register_heartbeat(
            node_id=payload.node_id,
            node_type=payload.node_type,
            role=payload.role,
            capabilities=payload.capabilities,
            load=payload.load,
            assigned_tasks=payload.assigned_tasks,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        # Pydantic-style validation error — 422 is correct contract.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001 — surface any unexpected registry error
        logger.error("mesh.post_node_heartbeat: registry failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="presence registry unavailable",
        ) from exc

    # ── MESH-6 auto-dispatch (Zero Zombie Tasks) ─────────────────────────
    # বাংলা: প্রতি heartbeat-এ (১) মেয়াদোত্তীর্ণ lease re-queue হয় — node ১০
    # মিনিট চুপ থাকলে তার task অন্য node/cloud পায়; (২) এই node-এর capabilities
    # মেলানো pending task claim করে response-এ assigned_tasks হিসেবে যায়।
    # Dispatch ব্যর্থ হলে heartbeat এখনো 200 ফেরত দেয় (presence আর queue আলাদা
    # ব্যর্থতা ডোমেইন — Self-Healing directive)।
    try:
        await task_router.reap_expired_leases()
        claimed: list[ClaimedTask] = []
        while len(claimed) < task_router._max_active_per_node:  # noqa: SLF001 — same package contract
            got = await task_router.claim_task(
                node_id=payload.node_id,
                role=payload.role,
                capabilities=payload.capabilities,
            )
            if got is None:
                break
            claimed.append(got)
        if claimed:
            existing = list(result.assigned_tasks or [])
            existing.extend(t.task_id for t in claimed)
            result.assigned_tasks = existing
            logger.info(
                "mesh.heartbeat: auto-dispatched %d task(s) to %s",
                len(claimed),
                payload.node_id,
            )
    except Exception as exc:  # noqa: BLE001 — dispatch failure never breaks presence
        logger.warning(
            "mesh.post_node_heartbeat: task auto-dispatch failed (presence intact): %s",
            exc,
        )
    return result


@router.get(
    "",
    response_model=NodeListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all active mesh nodes",
)
async def list_active_nodes(
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
    registry: PresenceRegistry = Depends(get_presence_registry),
) -> NodeListResponse:
    """সব active (non-stale) mesh nodes — MESH-2 dashboard এই endpoint কল করে।

    বাংলা: ডিফল্টভাবে last_seen থেকে ৬০০ সেকেন্ড (১০ মিনিট) পুরোনো node
    stale হিসেবে গণ্য হয় এবং এই তালিকায় থাকবে না। `stale_after_seconds`
    query param দিয়ে caller-নির্দিষ্ট threshold যোগ করা যায় (min ১ সেকেন্ড)।
    """
    if stale_after_seconds < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="stale_after_seconds must be >= 1",
        )
    nodes = await registry.list_active_nodes(stale_after_seconds=stale_after_seconds)
    return NodeListResponse(
        nodes=nodes,
        count=len(nodes),
        stale_after_seconds=stale_after_seconds,
    )


@router.get(
    "/{node_id}",
    response_model=NodeDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a single mesh node detail",
)
async def get_node_detail(
    node_id: str,
    registry: PresenceRegistry = Depends(get_presence_registry),
) -> NodeDetailResponse:
    """একটি নির্দিষ্ট node-এর presence record দেখাও (stale হলেও ফেরত দেয়)।

    বাংলা: node_id পাওয়া না গেলে 404। পাওয়া গেলে lease state সহ full record ফেরত দেয়।
    """
    record = await registry.get_node(node_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"node_id {node_id!r} not registered",
        )
    return NodeDetailResponse(node=record)


@router.patch(
    "/{node_id}",
    response_model=NodeDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a mesh node's role (MESH-2 dashboard dropdown)",
)
async def patch_node_role(
    node_id: str,
    payload: RoleUpdateRequest,
    registry: PresenceRegistry = Depends(get_presence_registry),
) -> NodeDetailResponse:
    """Node-এর role পরিবর্তন করো — MESH-2 dashboard-এর Planner/Coder/Tester/Gate
    dropdown এই endpoint কল করবে।

    বাংলা: invalid role হলে 422, unknown node_id হলে 404।
    """
    try:
        updated = await registry.set_role(node_id, payload.role)
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
    return NodeDetailResponse(node=updated)


__all__ = [
    "HeartbeatRequest",
    "NodeDetailResponse",
    "NodeListResponse",
    "RoleUpdateRequest",
    "router",
]
