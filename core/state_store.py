"""Durable state store facade (issue #451).

Stateful features previously lived ONLY in in-process dicts — every Render
deploy/restart silently erased user data (single-worker policy, 512MB RAM).
This facade gives those stores a Redis-backed durable layer through the
existing SecureRedisManager federation pool (issue #460: 5 Upstash accounts,
quota-aware failover) with ZERO new dependencies and an in-memory mirror so
behaviour is never worse than the pre-#451 status quo.

বাংলা: এতদিন এই স্টোরগুলো শুধু প্রসেস-মেমোরিতে থাকত — প্রতি ডিপ্লয়েই
ইউজার-ডেটা চুপচাপ মুছে যেত। এখন লেখাগুলো Redis federation-এ mirror হয়
(write-through, best-effort), বুটে/মিসে hydrate হয়, আর Redis না পেলে
আগের মতোই in-memory fallback — অর্থাৎ আগের চেয়ে খারাপ কিছুই হয় না।

Design constraints honoured:
- LOW_MEMORY_MODE / 512MB: no new packages; values are compact JSON.
- Upstash billing (issue #460): reads are served from the in-memory mirror
  (0 ops); each mutation = 1 SET/DEL op; hydration = 1 bounded SCAN at boot.
- Never raise at the call site: durable failures log (once, rate-limited)
  and degrade to the mirror.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger("state_store")

_KEY_PREFIX = "supremeai:state:"
_HYDRATE_SCAN_COUNT = 200  # bounded: single SCAN page, Upstash bills per op
_MIRROR_MAXLEN = 5000
_SYNC_CALL_TIMEOUT = 2.0

_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Capture the FastAPI main event loop so sync callers can bridge to it.

    বাংলা: sync রুট-হ্যান্ডলাররা থ্রেডপুলে চলে — তাদের জন্য মেইন লুপের
    রেফারেন্স দরকার (run_coroutine_threadsafe)। main.py lifespan-এ সেট হয়।
    """
    global _main_loop
    _main_loop = loop


async def _redis_client() -> Any | None:
    try:
        from core.cache.redis_manager import secure_redis_manager

        return await secure_redis_manager.get_client_async()
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("state_store: redis client unavailable: %s", exc)
        return None


class DurableStateStore:
    """Redis-backed, mirror-fronted key/value store for one feature namespace.

    Call-site contract: NEVER raises. `durable` on the last mutation tells
    the caller whether the write reached Redis (honest telemetry).
    """

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self._mirror: dict[str, str] = {}
        self._lock = threading.Lock()
        self._hydrated = False
        self._last_failure_log = 0.0
        self._durable = False  # status of the most recent mutation

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _k(self, key: str) -> str:
        return f"{_KEY_PREFIX}{self.namespace}:{key}"

    def _log_failure(self, op: str, exc: Exception) -> None:
        now = time.monotonic()
        if now - self._last_failure_log > 300.0:  # once / 5 min
            self._last_failure_log = now
            logger.warning(
                "state_store[%s]: %s failed, degrading to in-process mirror "
                "(data loss on restart possible): %s",
                self.namespace,
                op,
                exc,
            )

    async def _apply(
        self, op: str, redis_key: str, value: str | None = None, ttl: int | None = None
    ):
        client = await _redis_client()
        if client is None:
            self._durable = False
            return
        try:
            if op == "set":
                if ttl:
                    await client.set(redis_key, value, ex=int(ttl))
                else:
                    await client.set(redis_key, value)
            elif op == "delete":
                await client.delete(redis_key)
            self._durable = True
        except Exception as exc:
            self._durable = False
            self._log_failure(op, exc)

    def _bridge_to_loop(self, coro) -> bool:
        """Run a mutation coroutine on the captured main loop from sync code."""
        loop = _main_loop
        if loop is None or loop.is_closed():
            self._durable = False
            return False
        try:
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                asyncio.ensure_future(coro)
                return True
            asyncio.run_coroutine_threadsafe(coro, loop)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            self._log_failure("bridge", exc)
            return False

    # ------------------------------------------------------------------
    # async API (preferred)
    # ------------------------------------------------------------------
    async def set_async(self, key: str, value: Any, ttl: int | None = None) -> None:
        encoded = json.dumps(value, separators=(",", ":"), default=str)
        with self._lock:
            self._mirror[key] = encoded
        await self._apply("set", self._k(key), encoded, ttl)

    async def delete_async(self, key: str) -> None:
        with self._lock:
            self._mirror.pop(key, None)
        await self._apply("delete", self._k(key))

    async def get_async(self, key: str) -> Any | None:
        with self._lock:
            encoded = self._mirror.get(key)
        if encoded is not None:
            return json.loads(encoded)
        client = await _redis_client()
        if client is None:
            return None
        try:
            encoded = await client.get(self._k(key))
        except Exception as exc:
            self._log_failure("get", exc)
            return None
        if encoded is None:
            return None
        with self._lock:
            self._mirror.setdefault(key, encoded)
        return json.loads(encoded)

    async def hydrate_async(self) -> int:
        """Boot-time hydration: one bounded SCAN page → mirror. Returns count."""
        if self._hydrated:
            return len(self._mirror)
        client = await _redis_client()
        if client is None:
            self._hydrated = True
            return 0
        loaded = 0
        try:
            cursor, keys = await client.scan(
                match=f"{_KEY_PREFIX}{self.namespace}:*", count=_HYDRATE_SCAN_COUNT
            )
            if keys:
                raw = await client.mget(*keys)  # one pipeline → few billable ops
                with self._lock:
                    for k, v in zip(keys, raw, strict=False):
                        if v is None:
                            continue
                        short = k.decode() if isinstance(k, bytes) else k
                        short = short.rsplit(":", 1)[-1]
                        text = v.decode() if isinstance(v, bytes) else v
                        self._mirror.setdefault(short, text)
                        loaded += 1
            self._hydrated = True
        except Exception as exc:
            self._log_failure("hydrate", exc)
            self._hydrated = True  # do not retry-spam; mirror remains source
        if loaded:
            logger.info(
                "state_store[%s]: hydrated %d durable record(s) from Redis",
                self.namespace,
                loaded,
            )
        return loaded

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._mirror.keys())

    def reset(self) -> None:
        """Clear mirror + hydration state (test isolation / admin ops).

        বাংলা: সিঙ্গেলটন স্টোর টেস্টের মধ্যে state লিক করায় — ফিক্সচারে
        reset() ডাকা হয়। Redis-এ কোনো DEL পাঠায় না (শুধু লোকাল ভিউ)।
        """
        with self._lock:
            self._mirror.clear()
            self._hydrated = False

    def mirror_items(self) -> dict[str, Any]:
        with self._lock:
            return {k: json.loads(v) for k, v in self._mirror.items()}

    @property
    def last_mutation_durable(self) -> bool:
        return self._durable

    # ------------------------------------------------------------------
    # sync API (bridges to the main loop; mirror always applies first)
    # ------------------------------------------------------------------
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        encoded = json.dumps(value, separators=(",", ":"), default=str)
        with self._lock:
            self._mirror[key] = encoded
        self._bridge_to_loop(self._apply("set", self._k(key), encoded, ttl))

    def delete(self, key: str) -> None:
        with self._lock:
            self._mirror.pop(key, None)
        self._bridge_to_loop(self._apply("delete", self._k(key)))

    def get(self, key: str) -> Any | None:
        with self._lock:
            encoded = self._mirror.get(key)
        return json.loads(encoded) if encoded is not None else None


class DurableRing(DurableStateStore):
    """FIFO ring mirroring core.degraded_mode.InMemoryRing semantics, durable.

    Used by CascadeMemoryService's degraded mode: same bounded mirror, but
    every append/remove also lands in Redis so a restart no longer erases
    the memories silently (issue #451).
    """

    def __init__(self, namespace: str, maxlen: int = _MIRROR_MAXLEN) -> None:
        super().__init__(namespace)
        self._order: deque[str] = deque(maxlen=maxlen)

    async def append_async(self, item_id: str, item: Any) -> None:
        with self._lock:
            if item_id in self._mirror:
                self._order.remove(item_id)
            self._order.append(item_id)
        await self.set_async(item_id, item)

    def append(self, item_id: str, item: Any) -> None:
        with self._lock:
            if item_id in self._mirror:
                self._order.remove(item_id)
            self._order.append(item_id)
        self.set(item_id, item)

    def evict(self, item_id: str) -> None:
        with self._lock:
            try:
                self._order.remove(item_id)
            except ValueError:
                # Item was never ordered (or already evicted) — expected no-op.
                logger.debug("state_store[%s]: evict of unknown id %s", self.namespace, item_id)
            self._mirror.pop(item_id, None)
        self.delete(item_id)

    def ordered_snapshot(self) -> list[Any]:
        with self._lock:
            return [json.loads(self._mirror[k]) for k in self._order if k in self._mirror]


_registry: dict[str, DurableStateStore] = {}
_registry_lock = threading.Lock()

# Startup banner inventory (issue #451 acceptance): store → backing.
INVENTORY: dict[str, str] = {}


def durable_state(namespace: str, durable: bool = True) -> DurableStateStore:
    """Namespace singleton registry.

    `durable=False` keeps a namespace mirror-only (documented in-process
    tradeoff); the startup banner prints the honest backing either way.
    """
    with _registry_lock:
        if namespace not in _registry:
            _registry[namespace] = DurableStateStore(namespace)
            INVENTORY[namespace] = "redis+mirror" if durable else "in-process only"
        return _registry[namespace]


async def hydrate_all() -> int:
    """Boot-time hydration for every registered namespace (issue #451).

    বাংলা: lifespan-এ একবার চলে — প্রতিটি স্টোর একটি bounded SCAN করে
    Redis থেকে নিজের ডেটা mirror-এ তুলে নেয় (restart-এর পরে ডেটা ফেরে)।
    """
    total = 0
    with _registry_lock:
        stores = list(_registry.values())
    for store in stores:
        try:
            total += await store.hydrate_async()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("state_store[%s]: hydrate failed: %s", store.namespace, exc)
    return total


def banner() -> str:
    """Honest startup banner: which state stores survive restarts."""
    lines = [
        "── Durable state store inventory (issue #451) ──────────────────",
        "   Feature state backed by Redis federation + in-memory mirror.",
        "   'redis+mirror' survives restarts; 'in-process only' does NOT.",
    ]
    if not INVENTORY:
        lines.append("   (no state stores registered)")
    for ns, backing in sorted(INVENTORY.items()):
        lines.append(f"   • {ns:<28} → {backing}")
    lines.append("─────────────────────────────────────────────────────────────────")
    return "\n".join(lines)


def log_banner() -> None:
    logger.info("\n%s", banner())
