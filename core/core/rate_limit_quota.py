"""Daily Quota Limiter — Sliding window daily usage limiter.

Tracks and enforces daily usage quotas per user to prevent abuse
and control LLM costs over a 24-hour period.
"""

from __future__ import annotations

import threading
import time

import redis.asyncio as aioredis

from core.logging_config import logger


class DailyQuotaLimiter:
    """
    Tracks and enforces daily usage quotas per user to prevent abuse
    and control LLM costs over a 24-hour period.
    """

    def __init__(self, redis_url: str | None = None):
        from core.config import settings

        self.redis_url = redis_url or getattr(settings, "redis_url", None)
        self._redis = None
        self.DAILY_LIMITS = {
            "anonymous": 50,
            "authenticated": 500,
            "premium": 5000,
            "admin": 999999,
        }
        # Issue #1703: Redis-down degraded-mode guard — per-process daily
        # counters যাতে quota কখনো অসীম না হয় (আগে নীরব fail-open)।
        self._fallback_lock = threading.Lock()
        self._fallback_counts: dict[str, int] = {}

    def _fallback_check(self, user_id: str, limit: int) -> bool:
        """In-memory fallback quota check (issue #1703).

        Redis অনুপলব্ধ হলে per-process daily কাউন্টারে একই লিমিট প্রয়োগ
        হয় — multi-instance ডিপ্লয়ে এটি per-instance সীমা (দুর্বল কিন্তু
        অসীম নয়); single-instance ডিপ্লয়ে সম্পূর্ণ সঠিক।
        """
        key = f"{user_id}:{time.strftime('%Y-%m-%d')}"
        with self._fallback_lock:
            if len(self._fallback_counts) > 50_000:
                today = time.strftime("%Y-%m-%d")
                self._fallback_counts = {
                    k: v for k, v in self._fallback_counts.items() if k.endswith(f":{today}")
                }
            current = self._fallback_counts.get(key, 0) + 1
            self._fallback_counts[key] = current
        return current <= limit

    async def get_redis(self):
        if not self._redis:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def check_daily_quota(self, user_id: str, tier: str) -> bool:
        """
        Check if the user has exceeded their daily quota.
        Increments the counter and returns True if allowed, False if exceeded.
        """
        limit = self.DAILY_LIMITS.get(tier, self.DAILY_LIMITS["anonymous"])

        try:
            redis = await self.get_redis()

            # Use current date as part of the key
            today = time.strftime("%Y-%m-%d")
            key = f"daily_quota:{user_id}:{today}"

            current = await redis.incr(key)
            if current == 1:
                # First request of the day, set expiration to 24 hours (86400 seconds)
                await redis.expire(key, 86400)

            if current > limit:
                logger.warning(f"User {user_id} exceeded daily quota of {limit} for tier {tier}")
                return False

            return True
        except Exception as e:
            # Issue #1703: নীরব fail-open বাদ — Redis ডাউন হলে per-process
            # in-memory fallback guard-এ একই দৈনিক লিমিট প্রয়োগ হয়। Unlimited
            # spend আর সম্ভব নয়, আবার সম্পূর্ণ deny-outage-ও নয়।
            logger.critical(
                f"Daily quota check UNAVAILABLE (Redis unreachable) for "
                f"{user_id} — using in-memory fallback quota (issue #1703): "
                f"{type(e).__name__}: {e}"
            )
            return self._fallback_check(user_id, limit)
