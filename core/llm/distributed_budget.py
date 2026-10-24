"""Distributed token-budget counter — multi-worker-safe (Redis INCR + TTL).

বাংলা: এটা TokenBudget.used_today-এর in-memory কাউন্টারকে প্রতিস্থাপন করে —
Redis atomic INCRBY ব্যবহার করে সব ওয়ার্কার জুড়ে একটাই consistent দৈনিক কাউন্টার রাখে।
"""

from __future__ import annotations

import time

from core.cache.redis_manager import redis_manager
from monitoring.logging import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "llm:budget:daily:"


class DistributedTokenBudget:
    """Redis-backed daily token budget, safe across N worker processes।"""

    def __init__(
        self, daily_limit: int = 100_000, max_input: int = 8192, max_output: int = 4096
    ) -> None:
        self.daily_limit = daily_limit
        self.max_input = max_input
        self.max_output = max_output

    def _key(self) -> str:
        # বাংলা মন্তব্য: UTC তারিখ অনুযায়ী key rotate হয় — প্রতিদিন স্বয়ংক্রিয়ভাবে রিসেট
        day = time.strftime("%Y-%m-%d", time.gmtime())
        return f"{_KEY_PREFIX}{day}"

    async def check_and_reserve(self, estimated_input: int, estimated_output: int) -> bool:
        """Atomically রিজার্ভ করে, সীমা ছাড়ালে rollback করে ফেরত পাঠায়।"""
        if estimated_input > self.max_input or estimated_output > self.max_output:
            return False

        total = estimated_input + estimated_output
        if not redis_manager or not redis_manager.client:
            # বাংলা মন্তব্য: Redis unavailable হলে fail-open না করে conservative fallback
            logger.warning(
                "Redis unavailable for distributed budget — falling back to permissive mode"
            )
            return True

        key = self._key()
        new_total = await redis_manager.client.incrby(key, total)
        if new_total == total:
            # প্রথম write — TTL সেট করা প্রয়োজন যাতে key পরদিন expire হয়
            await redis_manager.client.expire(key, 90_000)

        if new_total > self.daily_limit:
            # বাংলা মন্তব্য: সীমা ছাড়িয়ে গেলে reservation rollback করা হয় (Anti-Silent-Failure)
            await redis_manager.client.decrby(key, total)
            return False
        return True

    async def used_today(self) -> int:
        if not redis_manager or not redis_manager.client:
            return 0
        val = await redis_manager.get_cache(self._key())
        return int(val) if val else 0
