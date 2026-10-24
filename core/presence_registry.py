"""Tower presence registry — multi-agent mesh foundation layer (MESH-1, issue #939).

বাংলা সারসংক্ষেপ:
------------------
SupremeAI Distributed Multi-Agent Mesh-এর ভিত্তি — সব connected agents
(PC-1, PC-2, Bolt, Lovable, Gemini Web ইত্যাদি) তাদের heartbeat পাঠালে এই
registry-তে live presence রেকর্ড হিসেবে জমা হয়। প্রতিটি heartbeat
`last_seen` timestamp আপডেট করে; ১০ মিনিট (ডিফল্ট) ধরে কোনো heartbeat না
এলে সেই node-কে stale হিসেবে চিহ্নিত করা হয় এবং তার lease release করা হয়।

আর্কিটেকচার:
- In-memory dict হলো primary store (সবসময় available, কোনো external dep নেই)।
- Optional Redis backing যোগ করা যায় — multi-instance ডিপ্লয়মেন্টে
  একই presence state সব FastAPI worker share করতে পারে। Redis unavailable
  হলে registry নীরবে in-memory fallback করে (Self-Healing directive)।
- Thread-safe — সব mutating method `asyncio.Lock` দিয়ে সুরক্ষিত।
- কোনো fake/mock নেই — সব method আসল data তে কাজ করে।

সম্পর্কিত:
- Master plan: docs/plans/MULTI_AGENT_MESH_MASTER_PLAN.md (Section 6, MESH-1)
- Issue: #939 (P1-high, Phase A)
- Blocks: MESH-3 (local daemon এই endpoint কল করে), MESH-2 (dashboard node list পড়ে)
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
# ডিফল্ট stale threshold — ১০ মিনিট (issue spec অনুযায়ী)।
DEFAULT_STALE_AFTER_SECONDS: int = 600
# প্রতিটি heartbeat-এর জন্য lease window — পরবর্তী heartbeat এলে আপডেট হয়।
DEFAULT_LEASE_SECONDS: int = 600

# Redis hash key — সব node record একই hash-এ থাকে, O(1) per-node read।
REDIS_HASH_KEY: str = "supremeai:mesh:presence:nodes"

# Valid enum values — invalid মান হলে ValueError ছুঁড়ে (fail-closed)।
VALID_NODE_TYPES: frozenset[str] = frozenset(
    {"local_pc", "cloud_agent", "web_ai", "edge_device", "external_mcp"}
)
VALID_ROLES: frozenset[str] = frozenset({"planner", "coder", "tester", "gate", "observer"})


# ── Pydantic Models ──────────────────────────────────────────────────────────
class NodeLoad(BaseModel):
    """Agent-এর বর্তমান system load — agent router-এর জন্য গুরুত্বপূর্ণ।"""

    cpu: float | None = Field(default=None, ge=0.0, le=100.0, description="CPU usage percent")
    mem: float | None = Field(default=None, ge=0.0, le=100.0, description="Memory usage percent")
    active_tasks: int | None = Field(default=None, ge=0, description="In-flight task count")
    extra: dict[str, Any] = Field(default_factory=dict, description="Forward-compat extras")


class NodeRecord(BaseModel):
    """নোডের presence ও lease state। একই model in-memory ও Redis উভয় ক্ষেত্রে ব্যবহৃত হয়।"""

    node_id: str
    node_type: str
    role: str
    capabilities: list[str] = Field(default_factory=list)
    load: NodeLoad | None = None
    last_seen: str  # ISO 8601 UTC
    last_seen_epoch: float
    lease_expires_at: str  # ISO 8601 UTC
    lease_active: bool
    assigned_tasks: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HeartbeatResult(BaseModel):
    """Heartbeat POST এর প্রতিক্রিয়া — issue spec-এর lease info block-এর সাথে মিল।"""

    status: str  # "ok" | "rejected"
    node_id: str
    lease_active: bool
    lease_expires_at: str
    assigned_tasks: list[str] = Field(default_factory=list)
    last_seen: str


# ── Registry ─────────────────────────────────────────────────────────────────
class PresenceRegistry:
    """Single source of truth for live mesh presence + lease lifecycle.

    বাংলা:
    - সব method `async` — কোনো blocking I/O নেই।
    - In-memory dict primary; optional Redis backing (multi-instance sync)।
    - Redis write ব্যর্থ হলে in-memory state ঠিক থাকে (fail-open for reads,
      fail-soft for writes)।
    - Stale node গুলো `release_stale_leases` দিয়ে পরিষ্কার করা যায় — সেই সাথে
      `list_active_nodes`-ও স্বয়ংক্রিয়ভাবে stale গুলো filter করে।
    """

    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
    ) -> None:
        # In-memory primary store: node_id → NodeRecord
        self._nodes: dict[str, NodeRecord] = {}
        # asyncio.Lock — single event loop-এ thread-safe।
        self._lock = asyncio.Lock()
        # Optional Redis backing — pass a redis.asyncio.Redis client
        # (or any duck-typed object exposing hset/hget/hdel/hgetall).
        self._redis = redis_client
        self._stale_after_seconds = stale_after_seconds
        self._lease_seconds = lease_seconds

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _now_epoch() -> float:
        return time.time()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    def _is_stale(self, record: NodeRecord, *, stale_after_seconds: int) -> bool:
        age = self._now_epoch() - record.last_seen_epoch
        return age > stale_after_seconds

    @staticmethod
    def _validate_node_type(node_type: str) -> None:
        if node_type not in VALID_NODE_TYPES:
            raise ValueError(
                f"invalid node_type {node_type!r}; expected one of {sorted(VALID_NODE_TYPES)}"
            )

    @staticmethod
    def _validate_role(role: str) -> None:
        if role not in VALID_ROLES:
            raise ValueError(f"invalid role {role!r}; expected one of {sorted(VALID_ROLES)}")

    async def _redis_persist(self, record: NodeRecord) -> None:
        """Best-effort Redis write — Redis unavailable হলে নীরবে skip।"""
        if self._redis is None:
            return
        try:
            payload = record.model_dump_json()
            await self._redis.hset(REDIS_HASH_KEY, record.node_id, payload)
        except Exception as exc:  # noqa: BLE001 — Redis is best-effort
            logger.warning(
                "presence_registry: redis persist failed (in-memory intact): %s",
                exc,
            )

    async def _redis_delete(self, node_id: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.hdel(REDIS_HASH_KEY, node_id)
        except Exception as exc:  # noqa: BLE001 — Redis is best-effort
            logger.warning(
                "presence_registry: redis delete failed (in-memory intact): %s",
                exc,
            )

    # ── public API ───────────────────────────────────────────────────────────
    async def register_heartbeat(
        self,
        node_id: str,
        node_type: str,
        role: str,
        capabilities: list[str] | None = None,
        load: NodeLoad | dict[str, Any] | None = None,
        assigned_tasks: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> HeartbeatResult:
        """নতুন heartbeat register করুন অথবা existing record refresh করুন।

        প্রতি heartbeat-এ `last_seen` ও `lease_expires_at` আপডেট হয়।
        নতুন node হলে তৈরি হয়; পুরোনো হলে role/capabilities/load সব refresh হয়।
        Invalid `node_type` বা `role` হলে ValueError ছুঁড়ে (fail-closed contract)।
        """
        if not node_id or not node_id.strip():
            raise ValueError("node_id must be a non-empty string")
        self._validate_node_type(node_type)
        self._validate_role(role)

        # load যদি dict আসে, NodeLoad-এ রূপান্তর করো (forward-compat for clients)।
        if isinstance(load, dict):
            load = NodeLoad(**load)
        elif load is None:
            load = NodeLoad()

        now_epoch = self._now_epoch()
        now_iso = self._now_iso()
        lease_expires_iso = datetime.fromtimestamp(
            now_epoch + self._lease_seconds, tz=UTC
        ).isoformat()

        # Preserve assigned_tasks / metadata of existing record যাতে lease রিফ্রেশে
        # অর্পিত কাজ হারিয়ে না যায় (lease continuation contract)।
        existing = self._nodes.get(node_id)
        preserved_tasks = (
            assigned_tasks
            if assigned_tasks is not None
            else (existing.assigned_tasks if existing else [])
        )
        preserved_metadata = (
            metadata if metadata is not None else (existing.metadata if existing else {})
        )

        record = NodeRecord(
            node_id=node_id,
            node_type=node_type,
            role=role,
            capabilities=list(capabilities or []),
            load=load,
            last_seen=now_iso,
            last_seen_epoch=now_epoch,
            lease_expires_at=lease_expires_iso,
            lease_active=True,
            assigned_tasks=list(preserved_tasks),
            metadata=dict(preserved_metadata),
        )

        async with self._lock:
            self._nodes[node_id] = record
            await self._redis_persist(record)

        logger.debug(
            "presence_registry: heartbeat registered node_id=%s role=%s type=%s",
            node_id,
            role,
            node_type,
        )

        return HeartbeatResult(
            status="ok",
            node_id=node_id,
            lease_active=True,
            lease_expires_at=lease_expires_iso,
            assigned_tasks=record.assigned_tasks,
            last_seen=now_iso,
        )

    async def get_node(self, node_id: str) -> NodeRecord | None:
        """একটি node-এর record ফেরত দাও (stale হলেও ফেরত দেয়; caller filter করবে)।"""
        async with self._lock:
            return self._nodes.get(node_id)

    async def list_active_nodes(
        self, stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS
    ) -> list[NodeRecord]:
        """শুধু active (non-stale) nodes-এর তালিকা — MESH-2 dashboard এটা পড়ে।

        Stale nodes ফিল্টার হয়ে যায় কিন্তু registry থেকে মুছে ফেলা হয় না
        (caller চাইলে `release_stale_leases` দিয়ে পরিষ্কার করতে পারে)।
        """
        async with self._lock:
            return [
                record
                for record in self._nodes.values()
                if not self._is_stale(record, stale_after_seconds=stale_after_seconds)
            ]

    async def set_role(self, node_id: str, role: str) -> NodeRecord:
        """Node-এর role পরিবর্তন করো (PATCH endpoint-এর জন্য; MESH-2 dashboard-এর
        Planner/Coder/Tester/Gate dropdown এটা কল করবে)।

        Unknown node_id হলে KeyError ছুঁড়ে। Invalid role হলে ValueError।
        """
        self._validate_role(role)
        async with self._lock:
            record = self._nodes.get(node_id)
            if record is None:
                raise KeyError(f"node_id {node_id!r} not registered")
            # Pydantic v2: create updated copy (immutable record stays pure)।
            updated = record.model_copy(update={"role": role})
            self._nodes[node_id] = updated
            await self._redis_persist(updated)
        logger.info("presence_registry: role changed node_id=%s new_role=%s", node_id, role)
        return updated

    async def release_stale_leases(
        self, stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS
    ) -> list[str]:
        """Stale সব node-এর lease release করো (assigned_tasks মুছে দাও, lease_active=False)।

        Returns the list of node_ids whose leases were released।
        MESH-2 dashboard বা একটি periodic sweeper এটা কল করতে পারে।
        """
        released: list[str] = []
        async with self._lock:
            for node_id, record in list(self._nodes.items()):
                if not self._is_stale(record, stale_after_seconds=stale_after_seconds):
                    continue
                # lease release: assigned_tasks মুছে দাও, lease_active=False।
                # Record পুরোপুরি মুছছি না যাতে get_node দিয়ে "last_seen"
                # এখনো দেখা যায় (audit ও observability-র জন্য)।
                released_record = record.model_copy(
                    update={
                        "lease_active": False,
                        "assigned_tasks": [],
                    }
                )
                self._nodes[node_id] = released_record
                await self._redis_persist(released_record)
                released.append(node_id)
        if released:
            logger.info(
                "presence_registry: released %d stale leases (ids=%s)",
                len(released),
                released,
            )
        return released

    async def remove_node(self, node_id: str) -> bool:
        """Node-কে সম্পূর্ণ registry থেকে সরাও (admin/manual cleanup)।
        Returns True if a record was actually removed।"""
        async with self._lock:
            existed = self._nodes.pop(node_id, None) is not None
            if existed:
                await self._redis_delete(node_id)
        return existed

    async def count(self) -> int:
        """Registry-তে মোট কতগুলো node record আছে (stale সহ)।"""
        async with self._lock:
            return len(self._nodes)


# ── Module-level singleton (process-wide) ───────────────────────────────────
# একই process-এ সব route handler ও test একই instance দেখে —
# fastapi.Depends(get_presence_registry) এটাই ফেরত দেয়।
_registry_singleton: PresenceRegistry | None = None
_singleton_lock = asyncio.Lock()


async def get_presence_registry() -> PresenceRegistry:
    """FastAPI dependency — process-wide singleton registry ফেরত দেয়।

    বাংলা: প্রথম কলেই lazy-init হয়। Redis backing চালু করতে চাইলে
    PRESENCE_REDIS_BACKING=true env var সেট করতে হবে — তখন SecureRedisManager
    থেকে client নেওয়া হয় (Redis unavailable হলে নীরবে in-memory তে fallback)।
    """
    global _registry_singleton
    if _registry_singleton is not None:
        return _registry_singleton
    async with _singleton_lock:
        if _registry_singleton is None:
            redis_client = await _maybe_get_redis_client()
            _registry_singleton = PresenceRegistry(redis_client=redis_client)
    return _registry_singleton


async def _maybe_get_redis_client() -> Any | None:
    """Optional Redis backing — সব error-এ নীরবে None (in-memory fallback)।"""
    try:
        import os

        if os.getenv("PRESENCE_REDIS_BACKING", "false").strip().lower() != "true":
            return None
        from core.cache.redis_manager import redis_manager

        client = await redis_manager.get_client_async()
        # duck-typed sanity check — hset/hget/hdel/hgetall থাকা দরকার।
        for attr in ("hset", "hget", "hdel", "hgetall"):
            if not hasattr(client, attr):
                logger.warning(
                    "presence_registry: redis client missing %s — falling back to in-memory",
                    attr,
                )
                return None
        return client
    except Exception as exc:  # noqa: BLE001 — backing init must never break boot
        logger.info(
            "presence_registry: redis backing disabled (%s) — using in-memory only",
            exc,
        )
        return None


def reset_presence_registry_for_tests() -> None:
    """Test helper — singleton রিসেট করে (test isolation-এর জন্য)।

    বাংলা: শুধু test থেকে কল করা হয়; production কোড কখনো কল করবে না।
    """
    global _registry_singleton
    _registry_singleton = None


__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_STALE_AFTER_SECONDS",
    "HeartbeatResult",
    "NodeLoad",
    "NodeRecord",
    "PresenceRegistry",
    "REDIS_HASH_KEY",
    "VALID_NODE_TYPES",
    "VALID_ROLES",
    "get_presence_registry",
    "reset_presence_registry_for_tests",
]
