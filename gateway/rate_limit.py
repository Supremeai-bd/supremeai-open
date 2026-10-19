"""SupremeAI Gateway — keyed sliding-window rate limiter (issue #336 AC2).

Per-key (X-SupremeAI-Key identity, IP fallback) sliding window with the
standardized header contract::

    X-RateLimit-Limit: <max_requests>
    X-RateLimit-Remaining: <n>
    X-RateLimit-Reset: <unix epoch seconds when the window frees>

On rejection the response carries ``Retry-After`` (MCP_CONNECT §4 etiquette:
"Wait Retry-After seconds; retry with backoff. Never hot-loop.").

Thread-safe via a single asyncio lock; per-key memory is bounded (oldest
windows evicted beyond ``max_keys`` — a key cannot OOM the gateway).
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass

from .config import utc_ts


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    remaining: int
    reset_epoch: int
    retry_after_s: int | None = None


class SlidingWindowLimiter:
    """asyncio-safe sliding window; deterministic under a injected clock."""

    def __init__(
        self,
        window_s: int,
        max_requests: int,
        *,
        max_keys: int = 10_000,
        clock: callable = utc_ts,
    ):
        if window_s <= 0 or max_requests <= 0:
            raise ValueError("window_s and max_requests must be positive (fail-closed)")
        self.window_s = window_s
        self.max_requests = max_requests
        self.max_keys = max_keys
        self._clock = clock
        self._hits: dict[str, deque[int]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> RateDecision:
        async with self._lock:
            now = self._clock()
            cutoff = now - self.window_s
            if key not in self._hits and len(self._hits) >= self.max_keys:
                # Bound memory: evict the oldest key (deterministic FIFO).
                oldest = next(iter(self._hits))
                del self._hits[oldest]
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.max_requests:
                retry_after = max(1, (hits[0] + self.window_s) - now)
                return RateDecision(
                    allowed=False,
                    remaining=0,
                    reset_epoch=hits[0] + self.window_s,
                    retry_after_s=retry_after,
                )
            hits.append(now)
            reset_epoch = (hits[0] + self.window_s) if hits else now + self.window_s
            return RateDecision(
                allowed=True,
                remaining=self.max_requests - len(hits),
                reset_epoch=reset_epoch,
            )
