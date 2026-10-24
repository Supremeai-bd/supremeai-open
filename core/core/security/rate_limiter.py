"""Rate Limiter — DEPRECATION SHIM (Wave 3.1, issue #1257).

This file remains as a deprecation shim per the no-file-delete doctrine
(WAVE_MASTER_PLAN §10 rule 4 / security policy SG-01).

Canonical rate limiting logic lives in :mod:`middleware.rate_limiter`.
"""

from __future__ import annotations

import time
from typing import Literal

from core.cache.redis_manager import redis_manager
from core.config import settings
from core.errors.error_bus import with_error_bus
from core.logging_config import logger


class RateLimitExceededError(Exception):
    """Raised when rate limit is exceeded."""

    pass


class SlidingWindowRateLimiter:
    """Sliding window rate limiter using Redis ZSET with atomic Lua script operations.

    .. deprecated:: 2.5
        Use :class:`middleware.rate_limiter.RateLimiter` or canonical middleware instead.
    """

    def __init__(self):
        self.lua_script = """
        local key = KEYS[1]
        local window_size = tonumber(ARGV[1])
        local limit = tonumber(ARGV[2])
        local current_time = tonumber(ARGV[3])

        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, 0, current_time - window_size)

        -- Get current count
        local current_count = redis.call('ZCARD', key)

        -- Check if limit would be exceeded
        if current_count >= limit then
            return {0, redis.call('ZSCORE', key, current_time - window_size + 1)}
        end

        -- Add current request
        redis.call('ZADD', key, current_time, current_time .. '_' .. ARGV[4])

        -- Set expiration to ensure cleanup
        redis.call('EXPIRE', key, window_size)

        -- Return 1 for success, 0 for failure
        return {1, current_count + 1}
        """
        self.script_sha = None

    @with_error_bus("_load_script")
    async def _load_script(self, client):
        if self.script_sha is None:
            try:
                self.script_sha = await client.script_load(self.lua_script)
            except Exception:
                self.script_sha = None
                logger.debug("SCRIPT LOAD failed, will fallback to EVAL")

    async def is_allowed(
        self,
        identifier: str,
        limit: int,
        window_size: int,
        limit_type: Literal["ip", "user", "endpoint"] = "ip",
    ) -> tuple[bool, int, int]:
        client = await redis_manager.get_client_async()
        if not client:
            if settings.env in ["production", "staging"]:
                logger.warning(
                    f"Redis unavailable, denying request for {identifier} in {limit_type} rate limiter"
                )
                return False, 0, 0
            else:
                logger.warning(
                    f"Redis unavailable, allowing request for {identifier} in {limit_type} rate limiter (non-production)"
                )
                return True, 0, limit

        try:
            key = f"rate_limit:{limit_type}:{identifier}"
            await self._load_script(client)
            current_time = int(time.time())
            request_id = f"{current_time}_{hash(identifier) % 1000000}"

            if self.script_sha:
                result = await client.evalsha(
                    self.script_sha,
                    1,
                    key,
                    window_size,
                    limit,
                    current_time,
                    request_id,
                )
            else:
                result = await client.eval(
                    self.lua_script,
                    1,
                    key,
                    window_size,
                    limit,
                    current_time,
                    request_id,
                )

            is_allowed_flag, current_count = result[0], result[1]
            remaining = max(0, limit - current_count)
            return bool(is_allowed_flag), current_count, remaining
        except Exception as e:
            logger.error(f"Rate limiter error for {identifier}: {e}")
            if settings.env in ["production", "staging"]:
                return False, 0, 0
            else:
                return True, 0, limit

    async def get_reset_time(
        self,
        identifier: str,
        window_size: int,
        limit_type: Literal["ip", "user", "endpoint"] = "ip",
    ) -> int:
        client = await redis_manager.get_client_async()
        if not client:
            return int(time.time()) + window_size

        try:
            key = f"rate_limit:{limit_type}:{identifier}"
            current_time = int(time.time())
            oldest_req = await client.zrange(key, 0, 0, withscores=True)
            if oldest_req:
                oldest_timestamp = int(oldest_req[0][1].split("_")[0])
                reset_time = oldest_timestamp + window_size
            else:
                reset_time = current_time
            return reset_time
        except Exception as e:
            logger.error(f"Error getting reset time for {identifier}: {e}")
            return int(time.time()) + window_size


rate_limiter = SlidingWindowRateLimiter()

__all__ = ["RateLimitExceededError", "SlidingWindowRateLimiter", "rate_limiter"]
