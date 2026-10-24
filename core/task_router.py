"""Tower Task Router & Lease Manager — multi-agent mesh control plane (MESH-6, issue #926).

বাংলা সারসংক্ষেপ:
------------------
SupremeAI Distributed Multi-Agent Mesh-এর প্রাণ — Tower-native Task Queue।
Agent-রা আর GitHub issue-কে task store হিসেবে ব্যবহার করে না; এখানে
CAS-style atomic claim, lease/heartbeat, "Zero Zombie Tasks" failover —
সব Tower-এর নিজস্ব মেমরিতে চলে (master plan §১ Task Router & Lease Manager,
§৪.3 Dynamic Lease & Failover)।

আর্কিটেকচার:
- In-memory dict primary store; optional Redis backing (multi-instance sync)।
  Redis write ব্যর্থ হলে in-memory state অক্ষত থাকে (fail-soft, presence_registry
  এর মতোই)।
- Atomicity: সব mutating method `asyncio.Lock` দিয়ে সুরক্ষিত — দুটি agent কখনো
  একই task claim করতে পারবে না (CAS guarantee)।
- Lease: claim করা task-এর TTL থাকে (ডিফল্ট ১০ মিনিট)। Heartbeat/renew এলে
  TTL বাড়ে; TTL শেষ হলে `reap_expired_leases()` task-টি আবার pending করে
  (max_attempts পার হলে failed) — zombie task অসম্ভব।
- Matching: node-এর role + capabilities দেখে task assign হয় — required
  capabilities ⊆ node capabilities হতে হবে, target_role দিলে সেটাও মিলতে হবে।
- কোনো fake/mock নেই — সব method আসল data তে কাজ করে।

সম্পর্কিত:
- Master plan: docs/plans/MULTI_AGENT_MESH_MASTER_PLAN.md (§১, §৪.3, §৬ MESH-6)
- Issue: #926 (P0-critical)
- Depends on: backend/core/presence_registry.py (MESH-1, #939)
- Blocks: MESH-4 (Telegram /task এই queue-তে submit করে), MESH-7 (webhook events)
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.logging_config import logger

# ── Constants ────────────────────────────────────────────────────────────────
# ডিফল্ট lease window — ১০ মিনিট (master plan §৪.3 অনুযায়ী)।
DEFAULT_LEASE_SECONDS: int = 600
# একটি node সর্বোচ্চ কতগুলো concurrent leased task রাখতে পারে।
DEFAULT_MAX_ACTIVE_PER_NODE: int = 2
# একটি task সর্বোচ্চ কতবার lease হয়ে ব্যর্থ/মেয়াদোত্তীর্ণ হতে পারে।
DEFAULT_MAX_ATTEMPTS: int = 3

REDIS_HASH_KEY: str = "supremeai:mesh:tasks"

VALID_TASK_TYPES: frozenset[str] = frozenset(
    {"bash", "pytest", "ollama", "git_push", "file_edit", "custom"}
)
VALID_TASK_STATUSES: frozenset[str] = frozenset(
    {"pending", "leased", "done", "failed", "cancelled"}
)


# ── Pydantic Models ──────────────────────────────────────────────────────────
class TaskRecord(BaseModel):
    """Queue-তে থাকা একটি task-এর পূর্ণ state। In-memory ও Redis উভয়তে এই model।"""

    task_id: str
    task_type: str = Field(..., description=f"One of {sorted(VALID_TASK_TYPES)}")
    title: str = Field(..., min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    required_capabilities: list[str] = Field(default_factory=list)
    target_role: str | None = Field(
        default=None,
        description="নির্দিষ্ট role (planner/coder/tester/gate) হলে শুধু সেই role claim করতে পারবে",
    )
    priority: int = Field(
        default=5, ge=0, le=9, description="বেশি priority = আগে claim হবে (0=সর্বোচ্চ)"
    )
    status: str = Field(default="pending", description=f"One of {sorted(VALID_TASK_STATUSES)}")
    created_at: str  # ISO 8601 UTC
    created_at_epoch: float
    updated_at: str  # ISO 8601 UTC
    lease_node_id: str | None = None
    lease_expires_at: str | None = None
    lease_expires_epoch: float | None = None
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=DEFAULT_MAX_ATTEMPTS, ge=1)
    result: dict[str, Any] | None = None
    error: str | None = None


class ClaimedTask(BaseModel):
    """claim_task সফল হলে node যা পায়।"""

    task_id: str
    task_type: str
    title: str
    payload: dict[str, Any]
    lease_expires_at: str
    timeout_hint_seconds: float | None = None


# ── Core Router ───────────────────────────────────────────────────────────────
class TaskRouter:
    """Tower-native task queue — CAS claim, lease, heartbeat renewal, failover।

    বাংলা:
    - `claim_task` একটি pending task-কে atomicভাবে lease করে — asyncio.Lock
      ধরা হয় বলে দুই agent একসাথে একই task পাবে না (CAS guarantee)।
    - `renew_lease` শুধু সেই node করতে পারে যার কাছে task-টা leased।
    - Lease মেয়াদোত্তীর্ণ হলে `reap_expired_leases()` task আবার pending করে
      (attempts < max_attempts হলে), নাহলে failed — Zero Zombie Tasks।
    """

    def __init__(
        self,
        *,
        redis_client: Any | None = None,
        lease_seconds: int = DEFAULT_LEASE_SECONDS,
        max_active_per_node: int = DEFAULT_MAX_ACTIVE_PER_NODE,
    ) -> None:
        # In-memory primary store: task_id → TaskRecord
        self._tasks: dict[str, TaskRecord] = {}
        # FIFO + priority ordering-এর জন্য claim-এর সময় sort করা হয় (N ছোট হওয়ায় যথেষ্ট)।
        self._lock = asyncio.Lock()
        self._redis = redis_client
        self._lease_seconds = lease_seconds
        self._max_active_per_node = max_active_per_node

    # ── helpers ──────────────────────────────────────────────────────────────
    @staticmethod
    def _now_epoch() -> float:
        return time.time()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _new_task_id() -> str:
        return f"task-{uuid.uuid4().hex[:12]}"

    def _is_expired(self, record: TaskRecord) -> bool:
        if record.status != "leased" or record.lease_expires_epoch is None:
            return False
        return self._now_epoch() > record.lease_expires_epoch

    def _capability_match(self, record: TaskRecord, capabilities: list[str]) -> bool:
        return set(record.required_capabilities).issubset(set(capabilities or []))

    async def _redis_persist(self, record: TaskRecord) -> None:
        """Best-effort Redis write — Redis unavailable হলে নীরবে skip।"""
        if self._redis is None:
            return
        try:
            await self._redis.hset(REDIS_HASH_KEY, record.task_id, record.model_dump_json())
        except Exception as exc:  # noqa: BLE001 — Redis is best-effort
            logger.warning("task_router: redis persist failed (in-memory intact): %s", exc)

    async def _redis_delete(self, task_id: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.hdel(REDIS_HASH_KEY, task_id)
        except Exception as exc:  # noqa: BLE001 — Redis is best-effort
            logger.warning("task_router: redis delete failed (in-memory intact): %s", exc)

    # ── public API ───────────────────────────────────────────────────────────
    async def submit_task(
        self,
        *,
        task_type: str,
        title: str,
        payload: dict[str, Any] | None = None,
        required_capabilities: list[str] | None = None,
        target_role: str | None = None,
        priority: int = 5,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> TaskRecord:
        """নতুন task queue-তে জমা দাও — status=pending, FIFO অনুযায়ী claim হবে।"""
        if task_type not in VALID_TASK_TYPES:
            raise ValueError(
                f"invalid task_type {task_type!r}; expected one of {sorted(VALID_TASK_TYPES)}"
            )
        if target_role is not None and target_role not in {
            "planner",
            "coder",
            "tester",
            "gate",
            "observer",
        }:
            raise ValueError(f"invalid target_role {target_role!r}")
        now_epoch = self._now_epoch()
        now_iso = self._now_iso()
        record = TaskRecord(
            task_id=self._new_task_id(),
            task_type=task_type,
            title=title,
            payload=payload or {},
            required_capabilities=required_capabilities or [],
            target_role=target_role,
            priority=priority,
            created_at=now_iso,
            created_at_epoch=now_epoch,
            updated_at=now_iso,
            max_attempts=max_attempts,
        )
        async with self._lock:
            self._tasks[record.task_id] = record
            await self._redis_persist(record)
        logger.info(
            "task_router: submitted %s (%s, priority=%d, caps=%s)",
            record.task_id,
            record.task_type,
            record.priority,
            record.required_capabilities,
        )
        return record

    async def claim_task(
        self,
        *,
        node_id: str,
        role: str | None = None,
        capabilities: list[str] | None = None,
        lease_seconds: int | None = None,
    ) -> ClaimedTask | None:
        """CAS atomic claim — সবচেয়ে উপযুক্ত pending task node-এর কাছে lease করা হয়।

        বাংলা: matching order — (১) priority ascending (0 সর্বোচ্চ),
        (২) FIFO (created_at_epoch ascending)। capabilities মিল না হলে task skip।
        Node-এর max_active_per_node অতিক্রম হলে None। উপযুক্ত task না পেলে None
        (caller idle থাকবে)।
        """
        lease_s = lease_seconds if lease_seconds is not None else self._lease_seconds
        if lease_s < 1:
            raise ValueError("lease_seconds must be >= 1")
        async with self._lock:
            await self._reap_expired_leases_locked()
            # node ইতিমধ্যে কতগুলো active task ধরে আছে?
            active = sum(
                1
                for t in self._tasks.values()
                if t.status == "leased" and t.lease_node_id == node_id
            )
            if active >= self._max_active_per_node:
                return None
            candidates = [
                t
                for t in self._tasks.values()
                if t.status == "pending"
                and self._capability_match(t, capabilities or [])
                and (t.target_role is None or t.target_role == role)
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda t: (t.priority, t.created_at_epoch))
            chosen = candidates[0]
            now_epoch = self._now_epoch()
            chosen.status = "leased"
            chosen.lease_node_id = node_id
            chosen.lease_expires_epoch = now_epoch + lease_s
            chosen.lease_expires_at = datetime.fromtimestamp(
                now_epoch + lease_s, tz=UTC
            ).isoformat()
            chosen.attempts += 1
            chosen.updated_at = self._now_iso()
            await self._redis_persist(chosen)
            logger.info(
                "task_router: %s claimed by %s (attempts=%d, lease=%ds)",
                chosen.task_id,
                node_id,
                chosen.attempts,
                lease_s,
            )
            return ClaimedTask(
                task_id=chosen.task_id,
                task_type=chosen.task_type,
                title=chosen.title,
                payload=chosen.payload,
                lease_expires_at=chosen.lease_expires_at or "",
                timeout_hint_seconds=float(lease_s),
            )

    async def _claim_specific(
        self,
        task_id: str,
        *,
        node_id: str,
        lease_seconds: int | None = None,
    ) -> ClaimedTask | None:
        """নির্দিষ্ট task_id claim — pending না হলে None (409 mapping route-এ হয়)।

        বাংলা: claim_task "best match" করে; এটি একটি নির্দিষ্ট task ধরে atomic
        lease করে। REST route (/tasks/{id}/claim) এটাই ব্যবহার করে।
        """
        lease_s = lease_seconds if lease_seconds is not None else self._lease_seconds
        if lease_s < 1:
            raise ValueError("lease_seconds must be >= 1")
        async with self._lock:
            await self._reap_expired_leases_locked()
            record = self._tasks.get(task_id)
            if record is None:
                raise KeyError(f"task_id {task_id!r} not found")
            if record.status != "pending":
                return None
            now_epoch = self._now_epoch()
            record.status = "leased"
            record.lease_node_id = node_id
            record.lease_expires_epoch = now_epoch + lease_s
            record.lease_expires_at = datetime.fromtimestamp(
                now_epoch + lease_s, tz=UTC
            ).isoformat()
            record.attempts += 1
            record.updated_at = self._now_iso()
            await self._redis_persist(record)
            logger.info(
                "task_router: %s claimed by %s (attempts=%d, lease=%ds)",
                record.task_id,
                node_id,
                record.attempts,
                lease_s,
            )
            return ClaimedTask(
                task_id=record.task_id,
                task_type=record.task_type,
                title=record.title,
                payload=record.payload,
                lease_expires_at=record.lease_expires_at or "",
                timeout_hint_seconds=float(lease_s),
            )

    async def renew_lease(
        self, task_id: str, *, node_id: str, lease_seconds: int | None = None
    ) -> TaskRecord:
        """Lease TTL বাড়াও — শুধু যে node-এর কাছে leased সে-ই করতে পারবে।"""
        lease_s = lease_seconds if lease_seconds is not None else self._lease_seconds
        if lease_s < 1:
            raise ValueError("lease_seconds must be >= 1")
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise KeyError(f"task_id {task_id!r} not found")
            if record.status != "leased" or record.lease_node_id != node_id:
                raise PermissionError(f"task {task_id} is not leased by node {node_id!r}")
            now_epoch = self._now_epoch()
            record.lease_expires_epoch = now_epoch + lease_s
            record.lease_expires_at = datetime.fromtimestamp(
                now_epoch + lease_s, tz=UTC
            ).isoformat()
            record.updated_at = self._now_iso()
            await self._redis_persist(record)
            return record

    async def complete_task(
        self, task_id: str, *, node_id: str, result: dict[str, Any] | None = None
    ) -> TaskRecord:
        """Task সফলভাবে শেষ — leased-by check সহ (শুধু দাবিদার node-ই complete করতে পারবে)।"""
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise KeyError(f"task_id {task_id!r} not found")
            if record.status != "leased" or record.lease_node_id != node_id:
                raise PermissionError(f"task {task_id} is not leased by node {node_id!r}")
            record.status = "done"
            record.result = result or {}
            record.error = None
            record.lease_node_id = None
            record.lease_expires_at = None
            record.lease_expires_epoch = None
            record.updated_at = self._now_iso()
            await self._redis_persist(record)
            logger.info("task_router: %s completed by %s", task_id, node_id)
            return record

    async def fail_task(self, task_id: str, *, node_id: str, error: str) -> TaskRecord:
        """Task ব্যর্থ — attempts < max_attempts হলে আবার pending (retry), নাহলে failed।"""
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise KeyError(f"task_id {task_id!r} not found")
            if record.status != "leased" or record.lease_node_id != node_id:
                raise PermissionError(f"task {task_id} is not leased by node {node_id!r}")
            record.error = error[:2000]
            record.updated_at = self._now_iso()
            if record.attempts >= record.max_attempts:
                record.status = "failed"
                record.lease_node_id = None
                record.lease_expires_at = None
                record.lease_expires_epoch = None
                logger.warning(
                    "task_router: %s failed permanently (attempts=%d): %s",
                    task_id,
                    record.attempts,
                    record.error,
                )
            else:
                record.status = "pending"
                record.lease_node_id = None
                record.lease_expires_at = None
                record.lease_expires_epoch = None
                logger.info(
                    "task_router: %s back to pending for retry (attempt %d/%d): %s",
                    task_id,
                    record.attempts,
                    record.max_attempts,
                    record.error,
                )
            await self._redis_persist(record)
            return record

    async def cancel_task(self, task_id: str) -> TaskRecord:
        """Pending বা leased task cancel করো (owner/operator action)।"""
        async with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                raise KeyError(f"task_id {task_id!r} not found")
            if record.status in ("done", "failed", "cancelled"):
                raise ValueError(f"task {task_id} already in terminal status {record.status!r}")
            record.status = "cancelled"
            record.lease_node_id = None
            record.lease_expires_at = None
            record.lease_expires_epoch = None
            record.updated_at = self._now_iso()
            await self._redis_persist(record)
            return record

    async def get_task(self, task_id: str) -> TaskRecord | None:
        """একটি task-এর বর্তমান state (lock ছাড়া read — pydantic immutable-ish snapshot)।"""
        async with self._lock:
            return self._tasks.get(task_id)

    async def list_tasks(self, *, status: str | None = None) -> list[TaskRecord]:
        """Queue snapshot — status filter সহ (created_at ascending)।"""
        if status is not None and status not in VALID_TASK_STATUSES:
            raise ValueError(
                f"invalid status {status!r}; expected one of {sorted(VALID_TASK_STATUSES)}"
            )
        async with self._lock:
            await self._reap_expired_leases_locked()
            tasks = [t for t in self._tasks.values() if status is None or t.status == status]
            return sorted(tasks, key=lambda t: (t.priority, t.created_at_epoch))

    async def queue_stats(self) -> dict[str, int]:
        """Queue visibility — dashboard/monitoring-এর জন্য per-status count।"""
        async with self._lock:
            await self._reap_expired_leases_locked()
            stats = {s: 0 for s in VALID_TASK_STATUSES}
            for t in self._tasks.values():
                stats[t.status] = stats.get(t.status, 0) + 1
            return stats

    async def active_task_count(self, node_id: str) -> int:
        """নির্দিষ্ট node-এর এখন কতগুলো leased task আছে।"""
        async with self._lock:
            return sum(
                1
                for t in self._tasks.values()
                if t.status == "leased" and t.lease_node_id == node_id
            )

    async def reap_expired_leases(self) -> list[str]:
        """মেয়াদোত্তীর্ণ lease-এর সব task আবার pending/failed করো — Zero Zombie Tasks।

        Returns: reaped task_id list (monitoring/log-এর জন্য)।
        """
        async with self._lock:
            return await self._reap_expired_leases_locked()

    async def _reap_expired_leases_locked(self) -> list[str]:
        """Caller অবশ্যই self._lock ধরে রাখবে (internal helper)।"""
        reaped: list[str] = []
        for record in self._tasks.values():
            if not self._is_expired(record):
                continue
            record.lease_node_id = None
            record.lease_expires_at = None
            record.lease_expires_epoch = None
            record.updated_at = self._now_iso()
            if record.attempts >= record.max_attempts:
                record.status = "failed"
                logger.warning(
                    "task_router: %s lease expired after max attempts — failed",
                    record.task_id,
                )
            else:
                record.status = "pending"
                logger.info(
                    "task_router: %s lease expired — requeued for failover (attempt %d/%d)",
                    record.task_id,
                    record.attempts,
                    record.max_attempts,
                )
            reaped.append(record.task_id)
            await self._redis_persist(record)
        return reaped


# ── Singleton ─────────────────────────────────────────────────────────────────
# fastapi.Depends(get_task_router) এটাই ফেরত দেয়।
_router_singleton: TaskRouter | None = None
_singleton_lock = asyncio.Lock()


async def get_task_router() -> TaskRouter:
    """Process-wide TaskRouter singleton — mesh.py routes এটা Depends করে।"""
    global _router_singleton
    if _router_singleton is None:
        async with _singleton_lock:
            if _router_singleton is None:
                # বাংলা: Redis client ঐচ্ছিক — পরে MESH infra যোগ হলে wire করা হবে।
                _router_singleton = TaskRouter()
    return _router_singleton


def reset_task_router_for_tests() -> None:
    """Test helper — singleton রিসেট করে (test isolation-এর জন্য)।

    বাংলা: শুধু test থেকে কল করা হয়; production কোড কখনো কল করবে না।
    """
    global _router_singleton
    _router_singleton = None


__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MAX_ACTIVE_PER_NODE",
    "DEFAULT_MAX_ATTEMPTS",
    "REDIS_HASH_KEY",
    "VALID_TASK_STATUSES",
    "VALID_TASK_TYPES",
    "ClaimedTask",
    "TaskRecord",
    "TaskRouter",
    "get_task_router",
    "reset_task_router_for_tests",
]
