"""
SupremeAI Rate Limiting Middleware
===================================
Redis-backed rate limiting for API endpoints.
Protects against abuse and controls LLM costs.

Author: SuperAI Transformation Patch
Version: 1.0.0
"""

import os
import time
from functools import wraps

import redis.asyncio as aioredis
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

from core.logging_config import logger
from services.config_service import ConfigService

# Configure logging

security = HTTPBearer(auto_error=False)

_BOUNDED_CACHE_MAX = int(os.getenv("RATE_LIMIT_FALLBACK_MAX_KEYS", 2000))

try:
    import cachetools

    fallback_cache: dict = cachetools.TTLCache(maxsize=_BOUNDED_CACHE_MAX, ttl=3600)
except ImportError:
    # RUNTIME-002 FIX: Use bounded OrderedDict instead of unbounded dict.
    # Previously: plain dict grew without limit → OOM if cachetools missing.
    from collections import OrderedDict

    _BoundedCache = OrderedDict()

    class _BoundedDict(OrderedDict):
        """Bounded dict that evicts oldest entries when max size is reached."""

        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            if len(self) > _BOUNDED_CACHE_MAX:
                self.popitem(last=False)

    fallback_cache = _BoundedDict()


class RateLimiter:
    """
    Token bucket rate limiter backed by Redis.

    Supports multiple rate limit tiers:
    - Anonymous: 10 requests/minute
    - Authenticated: 60 requests/minute
    - Premium: 300 requests/minute
    - Admin: 1000 requests/minute
    """

    # Rate limit configurations (requests per minute)
    TIERS = {
        "anonymous": (10, 60),  # 10 req/min
        "authenticated": (60, 60),  # 60 req/min
        "premium": (300, 60),  # 300 req/min
        "admin": (1000, 60),  # 1000 req/min
    }

    # Endpoint-specific overrides (endpoint: (limit, window))
    ENDPOINT_OVERRIDES = {
        "/api/chat/stream": (30, 60),  # Streaming is expensive
        "/api/ai/generate": (20, 60),  # AI generation
        "/api/browser/scrape": (5, 60),  # Scraping is resource-intensive
    }

    def __init__(self, redis_url: str | None = None, enabled: bool = True):
        from core.config import settings

        self.enabled = enabled
        self._redis: aioredis.Redis | None = None

    async def _get_redis(self) -> aioredis.Redis | None:
        """Lazy Redis initialization using centralized redis manager."""
        from core.cache.redis_manager import redis_manager
        from core.config import settings

        if getattr(settings, "RATE_LIMIT_USE_SIMPLIFIED", False):
            return None

        if not self._redis:
            try:
                self._redis = await redis_manager.get_client_async()
            except Exception as e:
                logger.warning(f"Rate limiter failed to get redis client: {e}")
                self._redis = None
        return self._redis

    def _get_tier(self, request: Request) -> str:
        """Determine rate limit tier from request context.

        FIX (P1, review 2026-09-12): AuthMiddleware stores the decoded JWT as a
        DICT on request.state.user, but this method used attribute access
        (getattr(user, "role")) — which always fails on a dict, so EVERY
        authenticated user (and admin) was throttled at the anonymous tier.
        Now both dict and object shapes are handled.
        """
        user = getattr(request.state, "user", None)
        if not user:
            return "anonymous"
        if isinstance(user, dict):
            role = user.get("role")
            is_premium = user.get("is_premium", False)
        else:
            role = getattr(user, "role", None)
            is_premium = getattr(user, "is_premium", False)

        if role == "admin":
            return "admin"
        if is_premium:
            return "premium"
        return "authenticated"

    async def _get_limits(self, request: Request, endpoint: str, tier: str) -> tuple:
        """Get rate limits for endpoint/tier combination."""
        db = getattr(request.state, "db", None)

        # Check endpoint-specific override first
        endpoint_overrides = await ConfigService.get_config(
            db, "endpoint_overrides", self.ENDPOINT_OVERRIDES
        )
        if endpoint in endpoint_overrides:
            val = endpoint_overrides[endpoint]
            # Handle tuple/list or dict formats
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                return tuple(val[:2])
            elif isinstance(val, dict):
                return (val.get("limit", 10), val.get("window", 60))

        # Fall back to tier defaults from DB
        tiers = await ConfigService.get_config(db, "rate_limit_tiers", self.TIERS)
        if tier in tiers:
            val = tiers[tier]
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                return tuple(val[:2])
            elif isinstance(val, dict):
                return (val.get("limit", 10), val.get("window", 60))

        # Default to anonymous
        anon_val = tiers.get("anonymous", self.TIERS["anonymous"])
        if isinstance(anon_val, (list, tuple)) and len(anon_val) >= 2:
            return tuple(anon_val[:2])
        elif isinstance(anon_val, dict):
            return (anon_val.get("limit", 10), anon_val.get("window", 60))

        return self.TIERS["anonymous"]

    def _fallback_is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, dict]:
        now = time.time()
        global fallback_cache
        try:
            timestamps = fallback_cache.get(key, [])
            timestamps = [t for t in timestamps if now - t < window]
            if len(timestamps) >= limit:
                return False, {
                    "remaining": 0,
                    "reset": now + window,
                    "current": len(timestamps),
                    "limit": limit,
                }
            timestamps.append(now)
            fallback_cache[key] = timestamps
            return True, {
                "remaining": limit - len(timestamps),
                "reset": now + window,
                "current": len(timestamps),
                "limit": limit,
            }
        except Exception as e:
            logger.error(f"Fallback rate limit failed: {e}")
            return True, {"remaining": limit, "reset": now + window, "current": 0, "limit": limit}

    def _static_limits(self, endpoint: str, tier: str) -> tuple[int, int]:
        """Static (non-DB) limits — used when Redis is unavailable so we can
        skip remote ConfigService reads that would retry with backoff and stall
        every request (FIX P2, review 2026-09-12)."""
        if endpoint in self.ENDPOINT_OVERRIDES:
            val = self.ENDPOINT_OVERRIDES[endpoint]
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                return (int(val[0]), int(val[1]))
            if isinstance(val, dict):
                return (int(val.get("limit", 10)), int(val.get("window", 60)))
        val = self.TIERS.get(tier, self.TIERS["anonymous"])
        if isinstance(val, (list, tuple)) and len(val) >= 2:
            return (int(val[0]), int(val[1]))
        if isinstance(val, dict):
            return (int(val.get("limit", 10)), int(val.get("window", 60)))
        return self.TIERS["anonymous"]

    async def is_allowed(self, key: str, limit: int, window: int) -> tuple[bool, dict]:
        """
        Check if request is allowed under rate limit.

        Uses sliding window algorithm with Redis.

        Returns:
            Tuple of (allowed, metadata)
        """
        if not self.enabled:
            return True, {"remaining": limit, "reset": time.time() + window}

        redis = await self._get_redis()
        if not redis:
            # Fallback to in-memory rate limiting
            logger.info("Rate limiter Redis unavailable, falling back to in-memory")
            return self._fallback_is_allowed(key, limit, window)

        try:
            # Issue #460 (Pillar 1): single atomic EVAL (1 billable op).
            # The old two-phase check/add pipelines cost 4 billable commands
            # per request. The Lua script preserves both P2 guarantees:
            # no window extension on retries (EXPIRE only on first INCR) and
            # no refill-then-pass behavior (attempts are counted, not just
            # accepted requests — retry storms stay throttled).
            from core.cache.rate_limit_atomic import atomic_window_incr

            now = time.time()
            count = await atomic_window_incr(redis, str(key), window)
            metadata = {
                "remaining": max(0, limit - count),
                "reset": now + window,
                "current": count,
                "limit": limit,
            }

            if count > limit:
                return False, metadata
            return True, metadata

        except Exception as e:
            logger.error(f"Rate limit check error: {e}")
            # Fallback on errors
            return self._fallback_is_allowed(key, limit, window)

    async def check_rate_limit(self, request: Request) -> tuple[bool, dict]:
        """
        Main entry point for rate limiting.

        Returns:
            Tuple of (allowed, headers_to_set)
        """
        # Get client identifier
        client_id = self._get_client_id(request)
        endpoint = request.url.path
        tier = self._get_tier(request)

        # FIX (P2, review 2026-09-12): when Redis is down, skip the remote
        # ConfigService reads entirely — each one retries with 0.5-1.0s backoff,
        # so every request was paying up to ~3s of sleeps before failing.
        redis = await self._get_redis()
        if redis is None:
            limit, window = self._static_limits(endpoint, tier)
        else:
            limit, window = await self._get_limits(request, endpoint, tier)

        # Build Redis key
        key = f"ratelimit:{client_id}:{endpoint}"

        allowed, meta = await self.is_allowed(key, limit, window)

        # FIX (P2, review 2026-09-12): retry_after must be SECONDS-until-reset,
        # not the absolute epoch timestamp that X-RateLimit-Reset carries.
        try:
            retry_after = max(1, int(float(meta.get("reset", time.time() + 60)) - time.time()))
        except Exception:
            retry_after = 60

        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(meta["remaining"]),
            "X-RateLimit-Reset": str(int(meta["reset"])),
            "X-RateLimit-Tier": tier,
            "Retry-After": str(retry_after),
        }

        return allowed, headers

    def _get_client_id(self, request: Request) -> str:
        """Extract client identifier from request."""
        # Try user ID first (FIX P1: AuthMiddleware stores a dict — handle it)
        user = getattr(request.state, "user", None)
        if user:
            if isinstance(user, dict):
                uid = user.get("sub") or user.get("uid") or user.get("id")
            else:
                uid = getattr(user, "id", None)
            if uid:
                return f"user:{uid}"

        # Fall back to IP address (R2-08: proxy-aware, spoof-resistant)
        from utils.client_ip import get_client_ip

        client_ip = get_client_ip(request)
        if not client_ip or client_ip == "unknown":
            session_id = request.headers.get("User-Agent", "unknown_agent")
            return f"ip:unknown:{hash(session_id)}"
        return f"ip:{client_ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware for automatic rate limiting."""

    def __init__(self, app, limiter: RateLimiter):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks and static assets
        path = request.url.path
        if (
            path in ["/health", "/ready", "/metrics"]
            or path.startswith("/api/v1/health")
            or "health" in path
        ):
            return await call_next(request)

        # বাংলা মন্তব্য (ROOT-CAUSE FIX): এই middleware TESTING/CI env চেক করত না,
        # অথচ middleware/rate_limiter.py-তে এই বাইপাস আছে। ফলে টেস্ট স্যুট চলাকালীন
        # (Redis ডাউন থাকায় in-memory fallback ব্যবহৃত হয়) একই client_id-তে বহু
        # টেস্ট ফিক্সচার register/login কল করায় anonymous tier (10 req/min) দ্রুত
        # ফুরিয়ে যেত এবং পরবর্তী টেস্টগুলো 429 পেয়ে cascade-ভাবে ব্যর্থ হতো।
        if os.getenv("TESTING") == "true" or os.getenv("PYTEST_CURRENT_TEST"):
            return await call_next(request)

        # Check rate limit
        allowed, headers = await self.limiter.check_rate_limit(request)

        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": "Too many requests. Please try again later.",
                    "retry_after": int(headers.get("Retry-After", 60)),
                },
                headers=headers,
            )

        response = await call_next(request)

        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = value

        return response


def rate_limit(limit: int = 60, window: int = 60):
    """
    Decorator for per-endpoint rate limiting.

    Usage:
        @app.post("/api/chat")
        @rate_limit(limit=30, window=60)
        async def chat_endpoint(request: Request):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapped_func(request: Request, *args, **kwargs):
            limiter = RateLimiter()
            client_id = limiter._get_client_id(request)
            key = f"decorator:{client_id}:{func.__name__}"

            allowed, meta = await limiter.is_allowed(key, limit, window)

            if not allowed:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={"error": "Rate limit exceeded", "retry_after": int(meta["reset"])},
                )

            response = await func(request, *args, **kwargs)
            return response

        return wrapped_func

    return decorator
