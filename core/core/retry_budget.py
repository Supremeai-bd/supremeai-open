from __future__ import annotations

import asyncio
import os
import time


class RetryBudget:
    """
    বাংলা মন্তব্য: এপিআই রিকোয়েস্ট কোটা সুরক্ষায় টোকেন বাকেট অ্যালগরিদম ভিত্তিক রিট্রাই বাজেট ট্র্যাকার।
    """

    def __init__(self, max_tokens: int = 10, refill_rate_per_sec: float = 0.5) -> None:
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate_per_sec
        self.tokens = float(max_tokens)
        self.last_refill = time.monotonic()
        self.lock = asyncio.Lock()

    async def consume(self) -> bool:
        async with self.lock:
            from services.config_service import ConfigService

            # Fetch dynamic configs from cache/DB where possible
            max_tokens = await ConfigService.get_config(
                None, "retry_budget_max_tokens", self.max_tokens
            )
            refill_rate = await ConfigService.get_config(
                None, "retry_budget_refill_rate", self.refill_rate
            )

            self.max_tokens = max_tokens
            self.refill_rate = refill_rate

            now = time.monotonic()
            elapsed = now - self.last_refill
            # টোকেন রিফিল করা
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


# গ্লোবাল রিট্রাই বাজেট ইনস্ট্যান্স
from core.config import settings

global_retry_budget = RetryBudget(
    max_tokens=settings.retry_budget_max_tokens,
    refill_rate_per_sec=settings.retry_budget_refill_rate,
)
