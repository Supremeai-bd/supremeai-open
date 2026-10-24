"""gateway/service/redis_rate_limit.py — Optional Redis-backed distributed limiter (Way 14).

বাংলা: Upstash/Redis ভিত্তিক distributed sliding-window rate limiter — একাধিক
gateway replica একই counter শেয়ার করতে পারে। Redis না থাকলে fail-open হয়ে
existing in-process `gateway.rate_limit.SlidingWindowLimiter`-এর কাছে সিদ্ধান্ত দেয়।

Why (plan Way 14, "Redis-backed sliding window"):
- The existing `gateway/rate_limit.py` limiter (issue #336 AC2) is per-process:
  correct on one replica, but N replicas = N independent budgets. This module
  adds an OPTIONAL distributed layer returning the SAME `RateDecision` shape —
  callers swap without any response-shape change (P3).

Contract (mirrors gateway.rate_limit exactly):
- `RedisSlidingWindowLimiter(window_s, max_requests).check(key)` -> RateDecision
  (the canonical dataclass; no duplicate decision type).
- Redis unavailable / misconfigured / hiccup → delegates to a managed
  `SlidingWindowLimiter` fallback and sets `self.degraded = True` (visible in
  telemetry); NEVER raises, NEVER blocks the request path.
- Lua-free: INCR + EXPIRE pipeline on a per-window key — window-atomic,
  works on Upstash REST-compatible Redis without EVAL permissions.
- Zero new hard deps: `redis` imported lazily; absent dep = always fallback.

Env:
- RATE_LIMIT_REDIS_URL    e.g. rediss://default:<pw>@<host>:6379 (Upstash-compatible)
- RATE_LIMIT_REDIS_PREFIX key prefix (default "rl")
- RATE_LIMIT_DISTRIBUTED=0 disables the distributed layer entirely.

Local test:
    pytest tests/test_redis_rate_limit.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from ..rate_limit import RateDecision, SlidingWindowLimiter
from ..config import utc_ts  # canonical int-epoch clock — keep decisions shape-identical (P3)

try:  # optional dep — gateway/requirements.txt intentionally stays redis-free
    from redis import asyncio as aioredis  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - redis not installed
    aioredis = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


def _env_flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in {"0", "false", "no", "off"}


class RedisSlidingWindowLimiter:
    """Distributed per-window limiter with in-process fail-open fallback.

    বাংলা: প্রতি উইন্ডোতে INCR+EXPIRE — মাল্টি-রেপ্লিকার কমন বাজেট;
    Redis ডাউন হলে ইন-প্রসেস fallback, রিকোয়েস্ট কখনো ব্লক হয় না।
    """

    def __init__(
        self,
        window_s: int,
        max_requests: int,
        *,
        redis_url: str | None = None,
        prefix: str | None = None,
        max_keys: int = 10_000,
        clock: Any = None,
    ) -> None:
        if window_s <= 0 or max_requests <= 0:
            raise ValueError("window_s and max_requests must be positive (fail-closed)")
        self.window_s = window_s
        self.max_requests = max_requests
        self._url = (redis_url or os.getenv("RATE_LIMIT_REDIS_URL", "")).strip()
        self._prefix = (prefix or os.getenv("RATE_LIMIT_REDIS_PREFIX") or "rl").strip(":")
        self._enabled = _env_flag("RATE_LIMIT_DISTRIBUTED") and bool(self._url)
        self._redis: Any | None = None
        self._redis_lock = asyncio.Lock()
        self._connect_tried = False
        self.degraded = False  # telemetry: True => served by in-process fallback
        self._fallback = SlidingWindowLimiter(
            window_s, max_requests, max_keys=max_keys, clock=clock or utc_ts
        )

    # ------------------------------------------------------------------ redis
    async def _client(self) -> Any | None:
        """Lazily build (and cache) the redis client; None when unavailable."""
        if not self._enabled or aioredis is None:
            return None
        if self._redis is not None or self._connect_tried:
            return self._redis
        async with self._redis_lock:
            if self._redis is None and not self._connect_tried:
                self._connect_tried = True
                try:
                    client = aioredis.from_url(
                        self._url,
                        socket_connect_timeout=0.5,
                        socket_timeout=0.5,
                        health_check_interval=30,
                    )
                    await client.ping()
                    self._redis = client
                    logger.info("redis_rate_limit: distributed limiter online")
                except Exception as exc:  # bad URL / auth / network
                    logger.warning(
                        "redis_rate_limit: redis unavailable (%s) — using in-process fallback",
                        exc.__class__.__name__,
                    )
                    self._redis = None
                    self._enabled = False
                    self.degraded = True
        return self._redis

    # ----------------------------------------------------------------- public
    async def check(self, key: str) -> RateDecision:
        """Distributed sliding-window decision; falls back in-process on any fault.

        বাংলা: ডিস্ট্রিবিউটেড কাউন্টার সিদ্ধান্ত; ব্যর্থ হলে ইন-প্রসেস fallback।
        """
        client = await self._client()
        if client is None:
            # No distributed layer active (disabled / no URL / connect failed):
            # serving from the in-process fallback — mark degraded for telemetry.
            self.degraded = True
            return await self._fallback.check(key)

        now = time.time()
        window_id = int(now // self.window_s)
        rkey = f"{self._prefix}:{self.window_s}:{self.max_requests}:{key}:{window_id}"
        try:
            pipe = client.pipeline()
            pipe.incr(rkey)
            pipe.expire(rkey, self.window_s + 1)  # +1s: survive boundary skew
            count, _ = await pipe.execute()
            count = int(count)
        except Exception as exc:
            # Redis hiccup mid-request → degrade once, keep serving (fail-open).
            logger.warning(
                "redis_rate_limit: INCR failed (%s) — degrading to in-process", exc
            )
            self._redis = None
            self._enabled = False
            self.degraded = True
            return await self._fallback.check(key)

        reset_epoch = int((window_id + 1) * self.window_s)
        remaining = max(0, self.max_requests - count)
        allowed = count <= self.max_requests
        retry_after = max(1, reset_epoch - int(now)) if not allowed else None
        return RateDecision(
            allowed=allowed,
            remaining=remaining,
            reset_epoch=reset_epoch,
            retry_after_s=retry_after,
        )

    async def aclose(self) -> None:
        """Close the redis connection (tests / shutdown)."""
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None
