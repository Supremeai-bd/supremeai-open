"""Tower agent mailbox — direct + topic/role pub-sub messaging (MESH gap-3, issue #927).

বাংলা সারসংক্ষেপ:
------------------
MESH-1 (`presence_registry.py`) কে অনলাইনে আছে এবং MESH-6 (`task_router.py`)
"কী কাজ" বিতরণ করে — কিন্তু agent-রা একে অপরকে **কী কথা বলবে** তার কোনো
direct channel ছিল না। আগে একমাত্র পথ ছিল memory sidecar-এর shared blackboard
(write-only "চিৎকার") — প্রতিপক্ষ কখন পড়বে তার কোনো guarantee নেই।

এই module সেই gap পূরণ করে: একটি Tower-native Agent Mailbox —
- **direct message**: A → B (আলাদা mailbox)।
- **role/topic broadcast**: `to_agent="*"` + `to_role`/`topic` — pull-based pub/sub
  (client `inbox` poll করে; কোনো always-on subscriber process লাগে না)।
- **reply_to threading**: orchestrator-এর পাঠানো context-এর উত্তর subagent
  একই thread-এ ফেরত দিতে পারে।
- **delivery guarantee**: per-message `ack` (unacked বার্তা TTL পর্যন্ত থাকে)।
- **TTL**: ডিফল্ট ২৪ ঘণ্টা; মেয়াদোত্তীর্ণ বার্তা `purge_expired()`-এ মুছে যায়।
- **Tenant isolation**: প্রতিটি operation tenant-scoped; cross-tenant ack → 403।

আর্কিটেকচার (presence_registry/task_router-এর হুবহু Gold-Standard অনুসরণ):
- In-memory dict primary store (সবসময় available, external dep নেই)।
- Optional Redis backing — multi-instance deployment-এ state share করার জন্য
  (`MESH_MAILBOX_REDIS_BACKING=true`)। Redis unavailable হলে নীরবে in-memory।
- Thread-safe — সব mutating method `asyncio.Lock` দিয়ে সুরক্ষিত।
- কোনো fake/mock নেই — সব method আসল data-তে কাজ করে।
- Audit: প্রতিটি send/ack structured `mesh_mailbox_audit` log + optional hook-এ
  যায় (gap-4 spam/abuse traceability)।

সম্পর্কিত:
- Roadmap issue: #927 (P1-high, MCP Tower gap-3)
- Master plan: docs/plans/MULTI_AGENT_MESH_MASTER_PLAN.md
- Docs: docs/master_docs/INTEG-01-MCP_INTEGRATION_HANDBOOK.md (delegation protocol)
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
# ডিফল্ট TTL — ২৪ ঘণ্টা (roadmap issue #927 spec)।
DEFAULT_TTL_SECONDS: int = 86_400
# সর্বোচ্চ TTL — ৭ দিন (unbounded retention নিষিদ্ধ; free-tier memory রক্ষা)।
MAX_TTL_SECONDS: int = 7 * 86_400
# Broadcast target — সব agent-কে পাঠাতে `to_agent="*"`।
BROADCAST_TARGET: str = "*"
# সর্বোচ্চ body footprint — free-tier memory রক্ষা (SwarmPubSub 256KB cap-এর সাথে সামঞ্জস্যপূর্ণ)।
MAX_BODY_BYTES: int = 256 * 1024
# Inbox pagination bounds।
DEFAULT_INBOX_LIMIT: int = 50
MAX_INBOX_LIMIT: int = 200
# Valid mesh roles — presence_registry.VALID_ROLES-এর সাথে ১:১।
VALID_ROLES: frozenset[str] = frozenset({"planner", "coder", "tester", "gate", "observer"})
# Default tenant — mesh endpoints pre-auth (presence/tasks-এর মতোই), tenant header না এলে এটাই।
DEFAULT_TENANT_ID: str = "default"

# Redis hash keys — best-effort backing।
REDIS_HASH_KEY: str = "supremeai:mesh:mailbox:messages"
REDIS_SUBS_KEY: str = "supremeai:mesh:mailbox:subscriptions"

# Audit hook type — caller-provided sink (gap-4)। Default = structured log.
AuditHook = Callable[[dict[str, Any]], Awaitable[None]]


def _now_epoch() -> float:
    return time.time()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _epoch_to_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()


# ── Pydantic Models ──────────────────────────────────────────────────────────
class MailboxMessage(BaseModel):
    """একটি agent-to-agent বার্তার পূর্ণ envelope (issue #927 message schema)।"""

    message_id: str
    tenant_id: str
    from_agent: str
    # নির্দিষ্ট recipient id, অথবা BROADCAST_TARGET ("*")।
    to_agent: str
    # role-targeted broadcast (optional) — "planner"/"coder"/... শুধু সেই role পড়বে।
    to_role: str | None = None
    # topic-based routing (optional) — subscribers ছাড়া কেউ পাবে না (direct ব্যতীত)।
    topic: str | None = None
    body: dict[str, Any] = Field(default_factory=dict)
    # reply_to — যে বার্তার উত্তর, তার message_id (threading)।
    reply_to: str | None = None
    created_at: str  # ISO 8601 UTC
    created_at_epoch: float
    expires_at: str  # ISO 8601 UTC
    expires_at_epoch: float
    acked: bool = False
    acked_at: str | None = None
    acked_by: str | None = None


class SendResult(BaseModel):
    """Send-এর প্রতিক্রিয়া — client পরের ধাপে reply_to হিসেবে message_id ব্যবহার করে।"""

    status: str  # "ok"
    message: MailboxMessage


class InboxResult(BaseModel):
    """Inbox poll-এর প্রতিক্রিয়া।"""

    agent_id: str
    tenant_id: str
    count: int
    messages: list[MailboxMessage] = Field(default_factory=list)


class SubscriptionResult(BaseModel):
    """topic_subscribe-এর প্রতিক্রিয়া — agent-এর সম্পূর্ণ subscription list।"""

    status: str  # "ok"
    agent_id: str
    tenant_id: str
    topics: list[str] = Field(default_factory=list)


# ── Mailbox ──────────────────────────────────────────────────────────────────
class AgentMailbox:
    """Tower-native agent mailbox — direct + pub/sub messaging with TTL ও tenancy.

    বাংলা:
    - সব method `async`; `asyncio.Lock` দিয়ে একই event-loop-এ atomic।
    - In-memory dict primary; optional Redis backing (multi-instance sync)।
    - Redis ব্যর্থ হলে in-memory state অটুট (presence_registry-র মতো fail-soft)।
    """

    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        default_ttl_seconds: int = DEFAULT_TTL_SECONDS,
        audit_hook: AuditHook | None = None,
    ) -> None:
        # message_id → MailboxMessage (primary store)।
        self._messages: dict[str, MailboxMessage] = {}
        # f"{tenant_id}:{agent_id}" → subscribed topics।
        self._subscriptions: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()
        self._redis = redis_client
        self._default_ttl_seconds = default_ttl_seconds
        self._audit_hook = audit_hook

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _subs_key(tenant_id: str, agent_id: str) -> str:
        return f"{tenant_id}:{agent_id}"

    def _is_expired(self, message: MailboxMessage, now_epoch: float | None = None) -> bool:
        return (now_epoch if now_epoch is not None else _now_epoch()) >= message.expires_at_epoch

    def _purge_expired_locked(self) -> int:
        """Caller অবশ্যই self._lock ধরে রাখবে। মেয়াদোত্তীর্ণ বার্তা মুছে দেয়।"""
        now = _now_epoch()
        expired = [mid for mid, msg in self._messages.items() if self._is_expired(msg, now)]
        for mid in expired:
            self._messages.pop(mid, None)
        return len(expired)

    @staticmethod
    def _validate_role(role: str) -> None:
        if role not in VALID_ROLES:
            raise ValueError(f"invalid role {role!r}; expected one of {sorted(VALID_ROLES)}")

    @staticmethod
    def _validate_ttl(ttl_seconds: int | None, default: int) -> int:
        ttl = default if ttl_seconds is None else int(ttl_seconds)
        if ttl < 1:
            raise ValueError("ttl_seconds must be >= 1")
        if ttl > MAX_TTL_SECONDS:
            raise ValueError(f"ttl_seconds must be <= {MAX_TTL_SECONDS}")
        return ttl

    @staticmethod
    def _validate_body(body: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(body or {})
        try:
            size = len(json.dumps(payload, default=str).encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"body is not JSON-serializable: {exc}") from exc
        if size > MAX_BODY_BYTES:
            raise ValueError(f"body exceeds {MAX_BODY_BYTES} bytes ({size})")
        return payload

    def _visibility_ok(
        self,
        message: MailboxMessage,
        *,
        agent_id: str,
        role: str | None,
        topics: set[str],
    ) -> bool:
        """একটি বার্তা নির্দিষ্ট agent-এর জন্য দৃশ্যমান কি না।

        বাংলা: direct বার্তা সবসময় দৃশ্যমান (subscription লাগে না)। Broadcast
        (`to_agent="*"`) ক্ষেত্রে role-match ও topic-subscription দুটোই gate।
        """
        if message.to_agent == agent_id:
            return True  # direct
        if message.to_agent != BROADCAST_TARGET:
            return False
        if message.to_role is not None and message.to_role != role:
            return False
        if message.topic is not None and message.topic not in topics:
            return False
        return True

    async def _redis_persist(self, message: MailboxMessage) -> None:
        """Best-effort Redis write — Redis unavailable হলে নীরবে skip।"""
        if self._redis is None:
            return
        try:
            await self._redis.hset(REDIS_HASH_KEY, message.message_id, message.model_dump_json())
        except Exception as exc:  # noqa: BLE001 — Redis is best-effort
            logger.warning(f"agent_mailbox: redis persist failed (in-memory intact): {exc}")

    async def _redis_delete(self, message_id: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.hdel(REDIS_HASH_KEY, message_id)
        except Exception as exc:  # noqa: BLE001 — Redis is best-effort
            logger.warning(f"agent_mailbox: redis delete failed (in-memory intact): {exc}")

    async def _redis_persist_subs(self, tenant_id: str, agent_id: str, topics: set[str]) -> None:
        if self._redis is None:
            return
        try:
            payload = json.dumps(sorted(topics))
            await self._redis.hset(REDIS_SUBS_KEY, self._subs_key(tenant_id, agent_id), payload)
        except Exception as exc:  # noqa: BLE001 — Redis is best-effort
            logger.warning(f"agent_mailbox: redis subs persist failed (in-memory intact): {exc}")

    async def _audit(self, event: str, **fields: Any) -> None:
        """Structured audit trail — spam/abuse traceable (roadmap gap-4)।

        বাংলা: কখনো raise করে না; audit sink ব্যর্থ হলেও messaging অটুট থাকে।
        """
        payload: dict[str, Any] = {"event": event, "occurred_at": _now_iso(), **fields}
        logger.info(f"mesh_mailbox_audit: {json.dumps(payload, default=str)}")
        if self._audit_hook is not None:
            try:
                await self._audit_hook(payload)
            except Exception as exc:  # noqa: BLE001 — audit must never break delivery
                logger.warning(f"agent_mailbox: audit hook failed (message intact): {exc}")

    # ── public API ───────────────────────────────────────────────────────────
    async def send(
        self,
        *,
        from_agent: str,
        to_agent: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        to_role: str | None = None,
        topic: str | None = None,
        body: dict[str, Any] | None = None,
        reply_to: str | None = None,
        ttl_seconds: int | None = None,
    ) -> MailboxMessage:
        """একটি বার্তা পাঠাও — direct (`to_agent=<id>`) বা broadcast (`to_agent="*"`)।

        Raises:
            ValueError: খালি from/to, invalid role, TTL range, body size,
                অথবা unknown/cross-tenant `reply_to`।
        """
        from_agent = (from_agent or "").strip()
        to_agent = (to_agent or "").strip()
        if not from_agent:
            raise ValueError("from_agent must be non-empty")
        if not to_agent:
            raise ValueError("to_agent must be non-empty")
        if to_role is not None:
            self._validate_role(to_role)
        topic_clean = topic.strip() if topic and topic.strip() else None
        ttl = self._validate_ttl(ttl_seconds, self._default_ttl_seconds)
        payload = self._validate_body(body)

        now = _now_epoch()
        message = MailboxMessage(
            message_id=f"msg-{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            from_agent=from_agent,
            to_agent=to_agent,
            to_role=to_role,
            topic=topic_clean,
            body=payload,
            reply_to=reply_to,
            created_at=_now_iso(),
            created_at_epoch=now,
            expires_at=_epoch_to_iso(now + ttl),
            expires_at_epoch=now + ttl,
        )

        async with self._lock:
            if reply_to is not None:
                parent = self._messages.get(reply_to)
                if parent is None:
                    raise ValueError(f"reply_to {reply_to!r} not found")
                if parent.tenant_id != tenant_id:
                    # cross-tenant threading সম্পূর্ণ নিষিদ্ধ
                    raise ValueError("reply_to crosses tenant boundary")
            self._messages[message.message_id] = message
            await self._redis_persist(message)

        await self._audit(
            "message_sent",
            message_id=message.message_id,
            tenant_id=tenant_id,
            from_agent=from_agent,
            to_agent=to_agent,
            to_role=to_role,
            topic=topic_clean,
            reply_to=reply_to,
        )
        logger.debug(
            "agent_mailbox: sent "
            f"message_id={message.message_id} from={from_agent} to={to_agent} "
            f"role={to_role} topic={topic_clean}"
        )
        return message

    async def inbox(
        self,
        *,
        agent_id: str,
        tenant_id: str = DEFAULT_TENANT_ID,
        role: str | None = None,
        unread_only: bool = False,
        limit: int = DEFAULT_INBOX_LIMIT,
    ) -> list[MailboxMessage]:
        """একটি agent-এর জন্য দৃশ্যমান বার্তা — direct + subscribed/role broadcast।

        বাংলা: pull-based pub/sub — client নিয়মিত `inbox` poll করে। `unread_only`
        দিলে acked বার্তা বাদ পড়ে; `limit` সর্বোচ্চ MAX_INBOX_LIMIT।
        """
        effective_limit = max(1, min(int(limit), MAX_INBOX_LIMIT))
        async with self._lock:
            self._purge_expired_locked()
            topics = set(self._subscriptions.get(self._subs_key(tenant_id, agent_id), set()))
            visible = [
                msg
                for msg in self._messages.values()
                if msg.tenant_id == tenant_id
                and self._visibility_ok(msg, agent_id=agent_id, role=role, topics=topics)
                and not (unread_only and msg.acked)
            ]
        visible.sort(key=lambda m: (m.created_at_epoch, m.message_id))
        return visible[:effective_limit]

    async def ack(
        self,
        *,
        message_id: str,
        agent_id: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> MailboxMessage:
        """একটি বার্তা acknowledged হিসেবে চিহ্নিত করো (idempotent)।

        Raises:
            KeyError: message_id অজানা/মেয়াদোত্তীর্ণ।
            PermissionError: cross-tenant access, অথবা direct বার্তা ভিন্ন agent ack করছে।
        """
        async with self._lock:
            self._purge_expired_locked()
            message = self._messages.get(message_id)
            if message is None:
                raise KeyError(f"message_id {message_id!r} not found")
            if message.tenant_id != tenant_id:
                raise PermissionError("cross-tenant ack denied")
            # direct বার্তা শুধু প্রকৃত recipient ack করতে পারে (broadcast সবাই পারে)।
            if message.to_agent not in (BROADCAST_TARGET, agent_id):
                raise PermissionError(f"agent {agent_id!r} is not the recipient of {message_id!r}")
            if message.acked:
                return message
            updated = message.model_copy(
                update={"acked": True, "acked_at": _now_iso(), "acked_by": agent_id}
            )
            self._messages[message_id] = updated
            await self._redis_persist(updated)

        await self._audit(
            "message_acked",
            message_id=message_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            from_agent=updated.from_agent,
            to_agent=updated.to_agent,
        )
        return updated

    async def subscribe(
        self,
        *,
        agent_id: str,
        topics: list[str],
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> list[str]:
        """Agent-কে এক বা একাধিক topic-এ subscribe করাও (idempotent union)।"""
        cleaned = sorted({t.strip() for t in topics if t and t.strip()})
        if not cleaned:
            raise ValueError("topics must contain at least one non-empty topic")
        key = self._subs_key(tenant_id, agent_id)
        async with self._lock:
            existing = self._subscriptions.setdefault(key, set())
            existing.update(cleaned)
            snapshot = set(existing)
            await self._redis_persist_subs(tenant_id, agent_id, snapshot)
        await self._audit(
            "topic_subscribed",
            tenant_id=tenant_id,
            agent_id=agent_id,
            topics=cleaned,
        )
        return sorted(snapshot)

    async def subscriptions(
        self,
        *,
        agent_id: str,
        tenant_id: str = DEFAULT_TENANT_ID,
    ) -> list[str]:
        """একটি agent-এর বর্তমান subscription তালিকা।"""
        async with self._lock:
            return sorted(self._subscriptions.get(self._subs_key(tenant_id, agent_id), set()))

    async def purge_expired(self) -> int:
        """মেয়াদোত্তীর্ণ সব বার্তা মুছে দাও; কতগুলো মুছলো তা ফেরত দাও।"""
        async with self._lock:
            removed = self._purge_expired_locked()
        if removed:
            logger.info("agent_mailbox: purged %d expired message(s)", removed)
        return removed

    async def count(self, tenant_id: str | None = None) -> int:
        """মোট বার্তা সংখ্যা (ঐচ্ছিকভাবে নির্দিষ্ট tenant-এর জন্য)।"""
        async with self._lock:
            self._purge_expired_locked()
            if tenant_id is None:
                return len(self._messages)
            return sum(1 for m in self._messages.values() if m.tenant_id == tenant_id)

    async def stats(self, tenant_id: str | None = None) -> dict[str, Any]:
        """Visibility — per-tenant message/ack/subscription count।"""
        async with self._lock:
            self._purge_expired_locked()
            messages = [
                m for m in self._messages.values() if tenant_id is None or m.tenant_id == tenant_id
            ]
            tenants: dict[str, int] = {}
            for msg in messages:
                tenants[msg.tenant_id] = tenants.get(msg.tenant_id, 0) + 1
            return {
                "total_messages": len(messages),
                "unacked_messages": sum(1 for m in messages if not m.acked),
                "subscription_keys": len(self._subscriptions),
                "per_tenant": tenants,
            }


# ── Singleton ─────────────────────────────────────────────────────────────────
# fastapi.Depends(get_agent_mailbox) এটাই ফেরত দেয়।
_mailbox_singleton: AgentMailbox | None = None
_singleton_lock = asyncio.Lock()


async def get_agent_mailbox() -> AgentMailbox:
    """Process-wide AgentMailbox singleton — mesh_mailbox routes এটা Depends করে।

    বাংলা: Redis backing opt-in — `MESH_MAILBOX_REDIS_BACKING=true` সেট করলে
    SecureRedisManager থেকে client নেওয়া হয় (unavailable হলে in-memory fallback)।
    """
    global _mailbox_singleton
    if _mailbox_singleton is not None:
        return _mailbox_singleton
    async with _singleton_lock:
        if _mailbox_singleton is None:
            redis_client = await _maybe_get_redis_client()
            _mailbox_singleton = AgentMailbox(redis_client=redis_client)
    return _mailbox_singleton


async def _maybe_get_redis_client() -> Any | None:
    """Optional Redis backing — সব error-এ নীরবে None (in-memory fallback)।"""
    try:
        import os

        if os.getenv("MESH_MAILBOX_REDIS_BACKING", "false").strip().lower() != "true":
            return None
        from core.cache.redis_manager import redis_manager

        client = await redis_manager.get_client_async()
        # duck-typed sanity check — hset/hdel থাকা দরকার।
        for attr in ("hset", "hdel"):
            if not hasattr(client, attr):
                logger.warning(
                    f"agent_mailbox: redis client missing {attr} — falling back to in-memory"
                )
                return None
        return client
    except Exception as exc:  # noqa: BLE001 — backing init must never break boot
        logger.info(f"agent_mailbox: redis backing disabled ({exc}) — using in-memory only")
        return None


def reset_agent_mailbox_for_tests() -> None:
    """Test helper — singleton রিসেট করে (test isolation-এর জন্য)।"""
    global _mailbox_singleton
    _mailbox_singleton = None


__all__ = [
    "BROADCAST_TARGET",
    "DEFAULT_INBOX_LIMIT",
    "DEFAULT_TENANT_ID",
    "DEFAULT_TTL_SECONDS",
    "MAX_BODY_BYTES",
    "MAX_INBOX_LIMIT",
    "MAX_TTL_SECONDS",
    "REDIS_HASH_KEY",
    "REDIS_SUBS_KEY",
    "VALID_ROLES",
    "AgentMailbox",
    "InboxResult",
    "MailboxMessage",
    "SendResult",
    "SubscriptionResult",
    "get_agent_mailbox",
    "reset_agent_mailbox_for_tests",
]
