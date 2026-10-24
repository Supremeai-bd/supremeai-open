"""Mesh Agent Mailbox REST API — MESH gap-3, issue #927 (P1-high).

বাংলা সারসংক্ষেপ:
------------------
Tower-native agent-to-agent messaging-এর REST surface (/api/v1/mesh/*)। Core
logic সব backend/core/agent_mailbox.py-তে — এখানে কেবল পাতলা FastAPI আবরণ:

- POST /api/v1/mesh/messages                    — agent_send (direct / role / topic broadcast)
- GET  /api/v1/mesh/messages/inbox              — agent_inbox (pull-based pub/sub + unread filter)
- POST /api/v1/mesh/messages/{message_id}/ack   — agent_ack (delivery acknowledgement)
- POST /api/v1/mesh/subscriptions                — topic_subscribe (agent → topics)
- GET  /api/v1/mesh/subscriptions                — agent-এর current subscriptions
- GET  /api/v1/mesh/messages/stats               — visibility (per-tenant count)
- POST /api/v1/mesh/messages/purge               — TTL-expired বার্তা পরিষ্কার

Tenant isolation:
- প্রতিটি request-এ tenant নির্ধারিত হয় `x-tenant-id` header (MCP Control Tower
  convention) অথবা body/query `tenant_id` থেকে; না থাকলে DEFAULT_TENANT_ID।
- Header ও payload দ্বন্দ্ব করলে → 403 (cross-tenant spoof প্রতিরোধ)।
- Cross-tenant ack → 403; ভিন্ন tenant-এর inbox সম্পূর্ণ partition করা।

conventions:
- FastAPI APIRouter + Pydantic v2 (mesh.py / mesh_tasks.py-র হুবহু ধাঁচ)।
- prefix=/api/v1/mesh — routers.py থেকে mount (registry prefix "")।
- process-wide AgentMailbox singleton (get_agent_mailbox dependency)।

সম্পর্কিত:
- Roadmap issue: #927 · Core: backend/core/agent_mailbox.py
- Docs: docs/master_docs/INTEG-01-MCP_INTEGRATION_HANDBOOK.md (delegation protocol)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from core.agent_mailbox import (
    DEFAULT_INBOX_LIMIT,
    DEFAULT_TENANT_ID,
    MAX_INBOX_LIMIT,
    MAX_TTL_SECONDS,
    AgentMailbox,
    InboxResult,
    MailboxMessage,
    SendResult,
    SubscriptionResult,
    get_agent_mailbox,
)

router = APIRouter(
    prefix="/api/v1/mesh",
    tags=["mesh-mailbox"],
    # বাংলা: presence/tasks-এর মতোই pre-auth — একটি fresh agent-এর প্রথম কল হতে
    # পারে; শুধু mailbox state পরিচালিত হয়, privileged resource স্পর্শ হয় না।
    # Tenant boundary header/payload থেকে এনফোর্স করা (cross-tenant → 403)।
)


# ── Request Models ───────────────────────────────────────────────────────────
class MessageSendRequest(BaseModel):
    """POST /api/v1/mesh/messages — agent_send এর body।"""

    from_agent: str = Field(..., min_length=1, max_length=128)
    to_agent: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description='Specific agent id, or "*" for a tenant-wide broadcast',
    )
    to_role: str | None = Field(default=None, description="planner|coder|tester|gate|observer")
    topic: str | None = Field(default=None, max_length=128)
    body: dict[str, Any] = Field(default_factory=dict)
    reply_to: str | None = Field(default=None, max_length=128)
    ttl_seconds: int | None = Field(default=None, ge=1, le=MAX_TTL_SECONDS)
    tenant_id: str | None = Field(default=None, max_length=128)


class MessageAckRequest(BaseModel):
    """POST /api/v1/mesh/messages/{message_id}/ack — agent_ack এর body।"""

    agent_id: str = Field(..., min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=128)


class SubscriptionRequest(BaseModel):
    """POST /api/v1/mesh/subscriptions — topic_subscribe এর body।"""

    agent_id: str = Field(..., min_length=1, max_length=128)
    topics: list[str] = Field(..., min_length=1, max_length=32)
    tenant_id: str | None = Field(default=None, max_length=128)


# ── Helpers ──────────────────────────────────────────────────────────────────
def _resolve_tenant_id(header_tenant: str | None, explicit_tenant: str | None) -> str:
    """Header ও payload থেকে tenant নির্ধারণ — দ্বন্দ্ব হলে 403 (fail-closed)।

    বাংলা: MCP Control Tower `x-tenant-id` header পাঠায়; CLI/daemon চাইলে
    payload-এ `tenant_id` দিতে পারে। দুটোই থাকলে অবশ্যই মিলতে হবে।
    """
    header_clean = (header_tenant or "").strip()
    explicit_clean = (explicit_tenant or "").strip()
    if header_clean and explicit_clean and header_clean != explicit_clean:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant mismatch: x-tenant-id header and payload tenant_id differ",
        )
    return header_clean or explicit_clean or DEFAULT_TENANT_ID


def _map_error(exc: Exception) -> HTTPException:
    """Core-এর ValueError/PermissionError/KeyError → সঠিক HTTP status (fail-closed)।"""
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, KeyError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    raise exc


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.post(
    "/messages",
    response_model=SendResult,
    status_code=status.HTTP_201_CREATED,
    summary="Send a direct or broadcast message to another agent",
)
async def mesh_send_message(
    payload: MessageSendRequest,
    x_tenant_id: str | None = Header(default=None),
    mailbox: AgentMailbox = Depends(get_agent_mailbox),
) -> SendResult:
    """একটি বার্তা পাঠাও — `to_agent` = ঠিকানা, `"*"` = broadcast, `topic` = pub/sub।"""
    tenant_id = _resolve_tenant_id(x_tenant_id, payload.tenant_id)
    try:
        message = await mailbox.send(
            from_agent=payload.from_agent,
            to_agent=payload.to_agent,
            tenant_id=tenant_id,
            to_role=payload.to_role,
            topic=payload.topic,
            body=payload.body,
            reply_to=payload.reply_to,
            ttl_seconds=payload.ttl_seconds,
        )
    except (ValueError, PermissionError) as exc:
        raise _map_error(exc) from exc
    return SendResult(status="ok", message=message)


@router.get(
    "/messages/inbox",
    response_model=InboxResult,
    summary="Poll an agent inbox (pull-based pub/sub)",
)
async def mesh_message_inbox(
    agent_id: str = Query(..., min_length=1, max_length=128, description="Target agent id"),
    role: str | None = Query(default=None, description="Role gate for broadcast visibility"),
    unread_only: bool = Query(default=False, description="Exclude already-acked messages"),
    limit: int = Query(default=DEFAULT_INBOX_LIMIT, ge=1, le=MAX_INBOX_LIMIT),
    tenant_id: str | None = Query(default=None, max_length=128),
    x_tenant_id: str | None = Header(default=None),
    mailbox: AgentMailbox = Depends(get_agent_mailbox),
) -> InboxResult:
    """দৃশ্যমান বার্তা পড়ো — direct + subscribed/role broadcast, TTL purge সহ।"""
    resolved = _resolve_tenant_id(x_tenant_id, tenant_id)
    try:
        messages = await mailbox.inbox(
            agent_id=agent_id,
            tenant_id=resolved,
            role=role,
            unread_only=unread_only,
            limit=limit,
        )
    except ValueError as exc:
        raise _map_error(exc) from exc
    return InboxResult(
        agent_id=agent_id, tenant_id=resolved, count=len(messages), messages=messages
    )


@router.post(
    "/messages/{message_id}/ack",
    response_model=MailboxMessage,
    summary="Acknowledge receipt of a message (idempotent)",
)
async def mesh_ack_message(
    message_id: str,
    payload: MessageAckRequest,
    x_tenant_id: str | None = Header(default=None),
    mailbox: AgentMailbox = Depends(get_agent_mailbox),
) -> MailboxMessage:
    """বার্তা ack করো — cross-tenant/bad recipient → 403, অজানা id → 404।"""
    tenant_id = _resolve_tenant_id(x_tenant_id, payload.tenant_id)
    try:
        message = await mailbox.ack(
            message_id=message_id,
            agent_id=payload.agent_id,
            tenant_id=tenant_id,
        )
    except (ValueError, PermissionError, KeyError) as exc:
        raise _map_error(exc) from exc
    return message


@router.post(
    "/subscriptions",
    response_model=SubscriptionResult,
    summary="Subscribe an agent to one or more topics (pub/sub)",
)
async def mesh_subscribe_topics(
    payload: SubscriptionRequest,
    x_tenant_id: str | None = Header(default=None),
    mailbox: AgentMailbox = Depends(get_agent_mailbox),
) -> SubscriptionResult:
    """Topic-এ subscribe করো — পরবর্তী inbox poll-এ সেই topic-এর broadcast দৃশ্যমান।"""
    tenant_id = _resolve_tenant_id(x_tenant_id, payload.tenant_id)
    try:
        topics = await mailbox.subscribe(
            agent_id=payload.agent_id,
            topics=payload.topics,
            tenant_id=tenant_id,
        )
    except ValueError as exc:
        raise _map_error(exc) from exc
    return SubscriptionResult(
        status="ok", agent_id=payload.agent_id, tenant_id=tenant_id, topics=topics
    )


@router.get(
    "/subscriptions",
    response_model=SubscriptionResult,
    summary="List an agent's current topic subscriptions",
)
async def mesh_list_subscriptions(
    agent_id: str = Query(..., min_length=1, max_length=128),
    tenant_id: str | None = Query(default=None, max_length=128),
    x_tenant_id: str | None = Header(default=None),
    mailbox: AgentMailbox = Depends(get_agent_mailbox),
) -> SubscriptionResult:
    """একটি agent-এর বর্তমান subscription তালিকা (tenant-scoped)।"""
    resolved = _resolve_tenant_id(x_tenant_id, tenant_id)
    topics = await mailbox.subscriptions(agent_id=agent_id, tenant_id=resolved)
    return SubscriptionResult(status="ok", agent_id=agent_id, tenant_id=resolved, topics=topics)


@router.get("/messages/stats", summary="Mailbox visibility stats (per-tenant counts)")
async def mesh_message_stats(
    tenant_id: str | None = Query(default=None, max_length=128),
    x_tenant_id: str | None = Header(default=None),
    mailbox: AgentMailbox = Depends(get_agent_mailbox),
) -> dict[str, Any]:
    """মেসেজ/ack/subscription count — diagnostics ও gate-এর জন্য।"""
    resolved = _resolve_tenant_id(x_tenant_id, tenant_id)
    return await mailbox.stats(tenant_id=resolved)


@router.post("/messages/purge", summary="Purge TTL-expired messages")
async def mesh_purge_messages(
    mailbox: AgentMailbox = Depends(get_agent_mailbox),
) -> dict[str, Any]:
    """মেয়াদোত্তীর্ণ বার্তা মুছে দাও — TTL retention guarantee নিশ্চিত করে।"""
    purged = await mailbox.purge_expired()
    return {"status": "ok", "purged": purged}
