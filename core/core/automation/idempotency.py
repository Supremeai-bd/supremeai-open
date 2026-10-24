import os
import time
from collections import OrderedDict
from typing import Optional, Protocol

from core.logging_config import logger

from .models import AutomationResult, AutomationStatus


class IdempotencyStore(Protocol):
    async def get(self, key: str) -> AutomationResult | None: ...
    async def set(self, key: str, result: AutomationResult) -> None: ...
    async def clear(self) -> None: ...
    async def size(self) -> int: ...


class InMemoryIdempotencyStore(IdempotencyStore):
    """Bounded LRU cache with TTL for idempotent dispatch results."""

    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        self._cache: OrderedDict[str, tuple[AutomationResult, float]] = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl

    async def get(self, key: str) -> AutomationResult | None:
        """key থাকলে ও TTL-এর মধ্যে হলে result ফেরত দেয়, নাহলে None।"""
        entry = self._cache.get(key)
        if entry is None:
            return None
        result, ts = entry
        if time.time() - ts > self._ttl:
            # expired — remove
            self._cache.pop(key, None)
            return None
        # LRU: move to end (most recently used)
        self._cache.move_to_end(key)
        return result

    async def set(self, key: str, result: AutomationResult) -> None:
        """key → result সংরক্ষণ। max_size exceed হলে LRU eviction।"""
        self._cache[key] = (result, time.time())
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)  # evict oldest

    async def clear(self) -> None:
        self._cache.clear()

    async def size(self) -> int:
        return len(self._cache)


class RedisIdempotencyStore(IdempotencyStore):
    """Redis-backed idempotency store for distributed correctness."""

    def __init__(self, redis_client, ttl: int = 3600, prefix: str = "idemp:"):
        self._redis = redis_client
        self._ttl = ttl
        self._prefix = prefix

    def _make_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> AutomationResult | None:
        try:
            data = await self._redis.get(self._make_key(key))
            if data:
                return AutomationResult.model_validate_json(data)
        except Exception as e:
            logger.warning(f"RedisIdempotencyStore get failed for {key}: {e}")
        return None

    async def set(self, key: str, result: AutomationResult) -> None:
        try:
            await self._redis.set(self._make_key(key), result.model_dump_json(), ex=self._ttl)
        except Exception as e:
            logger.warning(f"RedisIdempotencyStore set failed for {key}: {e}")

    async def clear(self) -> None:
        try:
            # Note: This is an expensive operation and mostly for tests/admin.
            # Using scan_iter to safely delete keys by prefix.
            keys = [k async for k in self._redis.scan_iter(match=f"{self._prefix}*")]
            if keys:
                await self._redis.delete(*keys)
        except Exception as e:
            logger.warning(f"RedisIdempotencyStore clear failed: {e}")

    async def size(self) -> int:
        try:
            # Not exact in cluster mode, but close enough for observability
            keys = [k async for k in self._redis.scan_iter(match=f"{self._prefix}*")]
            return len(keys)
        except Exception as e:
            logger.warning(f"RedisIdempotencyStore size failed: {e}")
            return 0


def create_idempotency_store() -> IdempotencyStore:
    """Factory to create appropriate idempotency store based on environment."""
    redis_url = os.getenv("REDIS_URL") or os.getenv("UPSTASH_REDIS_URL")
    if redis_url:
        try:
            import redis.asyncio as redis_async

            client = redis_async.from_url(redis_url, socket_connect_timeout=3, socket_timeout=3)
            logger.info("Using RedisIdempotencyStore for distributed idempotency.")
            return RedisIdempotencyStore(client)
        except Exception as e:
            logger.warning(
                f"Failed to connect to Redis for idempotency ({e}). Falling back to InMemoryIdempotencyStore."
            )

    logger.info("Using InMemoryIdempotencyStore for idempotency (single-process only).")
    return InMemoryIdempotencyStore()
