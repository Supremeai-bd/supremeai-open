from __future__ import annotations

import os
import time

from core.cache.redis_manager import redis_manager
from core.config import settings
from core.logging_config import logger

# Issue #437 (log-storm dampener): under provider quota exhaustion every request
# used to log a fallback warning (42–51% of all boot log lines during the
# Upstash incident). Warn at most once per 5 minutes per process instead.
_FALLBACK_WARN_INTERVAL = 300.0
_last_fallback_warn: float = 0.0


def _warn_fallback_throttled(message: str) -> None:
    global _last_fallback_warn
    now = time.monotonic()
    if now - _last_fallback_warn >= _FALLBACK_WARN_INTERVAL:
        _last_fallback_warn = now
        logger.warning(message)


class InMemoryFallbackLimiter:
    """Sliding-window rate limiter scoped per API key prefix as a fallback when Redis is down."""

    # Audit B-11 fix (2026-09-17): keys of clients that stop calling were
    # never deleted (only the CURRENT key got pruned) — slow growth during
    # Redis outages. A bounded sweep now evicts expired keys once the map
    # grows past the cap.
    _MAX_KEYS = 1000

    def __init__(self, burst: int = 20, window: float = 60.0) -> None:
        self.burst = burst
        self.window = window
        self._hits: dict[str, list[float]] = {}

    def _sweep_expired(self, now: float) -> None:
        if len(self._hits) <= self._MAX_KEYS:
            return
        expired = [k for k, ts in self._hits.items() if not ts or now - ts[-1] >= self.window]
        for k in expired:
            self._hits.pop(k, None)

    def _cleanup(self, key: str, now: float) -> None:
        # বাংলা মন্তব্ব্য: মেমোরি লিক এড়াতে যদি কোনো কী-তে নতুন কোনো হিট না থাকে, তবে ডিকশনারি থেকে কী-টি ডিলিট করা হচ্ছে।
        if key in self._hits:
            self._hits[key] = [t for t in self._hits[key] if now - t < self.window]
            if not self._hits[key]:
                del self._hits[key]

    def is_allowed(self, key: str, limit: int = 6) -> bool:
        now = time.time()
        self._cleanup(key, now)
        self._sweep_expired(now)
        hits = self._hits.setdefault(key, [])
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

local clear_before = now - window
redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)
local current_requests = redis.call('ZCARD', key)

if current_requests < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window))
    return {1, current_requests + 1}
else
    return {0, current_requests}
end
"""


class AsyncRateLimiter:
    """
    Async Redis rate limiter using centralized redis_manager.
    Pipeline reduces network round-trips.
    Includes an in-memory fallback (Pre-Deletion Safety Check).

    বাংলা: কেন্দ্রীয় redis_manager ব্যবহার করে — আলাদা Redis connection তৈরি করে না।
    Zero-Cost, ফ্রি-টিয়ার Upstash Redis এর সাথে সামঞ্জস্যপূর্ণ।
    """

    def __init__(self) -> None:
        self._rate_limit_enabled: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() in {
            "true",
            "1",
            "yes",
        }

        # Initialize fallback limiter
        self._fallback_limiter = InMemoryFallbackLimiter()

        # Enhanced rate limiting tiers
        # M13 P-B (zero-hardcode): tier-সীমা এখন config-চালিত — ডিফল্ট অপরিবর্তিত
        # (free 60 / pro 600 / premium 1200 / enterprise 6000 প্রতি window)।
        self._tier_limits = {
            "free": {
                "requests": settings.rate_limit_tier_free,
                "window": settings.rate_limit_tier_window_seconds,
            },
            "pro": {
                "requests": settings.rate_limit_tier_pro,
                "window": settings.rate_limit_tier_window_seconds,
            },
            "premium": {
                "requests": settings.rate_limit_tier_premium,
                "window": settings.rate_limit_tier_window_seconds,
            },
            "enterprise": {
                "requests": settings.rate_limit_tier_enterprise,
                "window": settings.rate_limit_tier_window_seconds,
            },
        }

    async def _get_redis(self):
        """Helper for test mock compatibility."""
        return await redis_manager.get_client_async()

    async def close(self) -> None:
        """No-op: this limiter does not own a Redis connection.

        It shares the centralized `redis_manager` connection, which has its
        own lifecycle. This method exists for interface completeness so
        callers can treat AsyncRateLimiter symmetrically with other
        resources that need explicit shutdown.
        """
        return None

    async def acquire(self, key: str, limit: int | None = None, window: int | None = None) -> bool:
        """Redis-based sliding window rate limiting with fail-closed behavior.

        Issue #460 optimization: Uses atomic single-op Lua script on Upstash Redis,
        reducing command quota usage by 75% compared to multi-command pipelines.

        বাংলা মন্তব্ব্য: Redis-ভিত্তিক sliding window রেট লিমিটিং।
        """
        if not self._rate_limit_enabled or os.getenv("TESTING") == "true":
            return True

        # M13 P-B: ডিফল্ট limit/window এখন config-চালিত (ডিফল্ট অপরিবর্তিত 100/60)।
        limit = limit or settings.rate_limit_default_limit
        window = window or settings.rate_limit_default_window

        try:
            client = await self._get_redis()
            if client is None:
                _warn_fallback_throttled(
                    f"Rate limiter Redis unavailable — in-memory sliding window fallback active "
                    f"(per-instance, NOT aggregate-safe). Last key: {key}."
                )
                return self._fallback_limiter.is_allowed(key, limit)

            now = time.time()
            import secrets

            member = f"{now}_{secrets.token_hex(4)}"
            zset_key = f"rate_limit:{key}"

            # 1. Primary path: Atomic Lua Script (Issue #460 - Upstash quota optimization: 1 op vs 4 ops)
            if hasattr(client, "eval"):
                try:
                    res = await client.eval(
                        _SLIDING_WINDOW_LUA,
                        1,
                        zset_key,
                        str(now),
                        str(window),
                        str(limit),
                        member,
                    )
                    if isinstance(res, (list, tuple)) and len(res) >= 2:
                        is_allowed = bool(res[0])
                        count = int(res[1])
                        if count > limit * 0.8:
                            logger.warning(f"Rate limit approaching for {key}: {count}/{limit}")
                        return is_allowed
                except (AttributeError, TypeError) as exc:
                    logger.debug("Redis eval not supported (%s); falling back to pipeline", exc)

            # 2. Fallback path: Pipeline execution
            pipe = client.pipeline()
            pipe.zadd(zset_key, {member: now})
            pipe.zremrangebyscore(zset_key, 0, now - window)
            pipe.zcard(zset_key)
            pipe.expire(zset_key, window)

            results = await pipe.execute()
            count = results[2]  # result of zcard
            is_allowed = count <= limit

            # Log near-limit cases for monitoring (M13 P-B: ratio config-চালিত)
            if count > limit * settings.rate_limit_warn_ratio:
                logger.warning(f"Rate limit approaching for {key}: {count}/{limit}")

            return is_allowed
        except Exception as e:
            redis_manager.report_failure(e)
            _warn_fallback_throttled(
                f"Rate limiter Redis operation failed ({e}) — in-memory sliding window fallback "
                f"active (per-instance, NOT aggregate-safe). Last key: {key}."
            )
            return self._fallback_limiter.is_allowed(key, limit)
