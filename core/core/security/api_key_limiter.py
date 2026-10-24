"""Per-API-Key Rate Limiting using sliding window counter.

বাংলা মন্তব্য: একক API key দিয়ে যেন কেউ পুরো সিস্টেম abuse করতে না পারে, সেজন্য প্রতি কি (Key) ভিত্তিক ডিস্ট্রিবিউটেড রেট লিমিটিং।
"""

import hashlib
import threading
import time
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.logging_config import logger

API_KEY_LIMIT_PREFIX = "apikey:rate:"
DEFAULT_MAX_REQUESTS_PER_MINUTE = 60

# Issue #1703: Redis-down degraded-mode guard — per-process sliding minute
# window যাতে API-key rate limit কখনো সম্পূর্ণ অচল না হয়।
_FALLBACK_WINDOW = 60.0
_FALLBACK_HITS: dict[str, list[float]] = {}
_FALLBACK_LOCK = threading.Lock()


def _fallback_allow(api_key_hash: str, max_requests: int) -> bool:
    """In-memory per-key minute-window check (issue #1703 degraded mode)."""
    now = time.time()
    key = api_key_hash[:16]
    with _FALLBACK_LOCK:
        if len(_FALLBACK_HITS) > 50_000:
            # opportunistic prune of stale windows
            for k in [
                k for k, ts in _FALLBACK_HITS.items() if not ts or ts[-1] < now - _FALLBACK_WINDOW
            ]:
                _FALLBACK_HITS.pop(k, None)
        window = [ts for ts in _FALLBACK_HITS.get(key, []) if ts > now - _FALLBACK_WINDOW]
        window.append(now)
        _FALLBACK_HITS[key] = window
        return len(window) <= max_requests


async def enforce_api_key_rate_limit(
    api_key_hash: str, max_requests: int = DEFAULT_MAX_REQUESTS_PER_MINUTE
) -> None:
    """Enforce rate limits per API Key hash using atomic Redis counters."""
    from core.cache.redis_manager import redis_manager

    if not redis_manager or not getattr(redis_manager, "client", None):
        # Issue #1703: fail-open বাদ — in-memory fallback window প্রয়োগ হয়।
        if not _fallback_allow(api_key_hash, max_requests):
            logger.critical(
                "API key rate limit exceeded (in-memory fallback, Redis unavailable) "
                f"for key hash prefix {api_key_hash[:8]}"
            )
            raise HTTPException(status_code=429, detail="API key rate limit exceeded")
        return

    current_minute = int(time.time() / 60)
    window_key = f"{API_KEY_LIMIT_PREFIX}{api_key_hash[:16]}:{current_minute}"

    try:
        # Issue #460: single atomic EVAL (1 billable op) instead of the
        # INCR+EXPIRE 2-command pipeline.
        # Issue #1703: raise_on_failure=True — atomic_window_incr-এর
        # "error-এ 0 রিটার্ন" fail-open contract এখানে গ্রহণযোগ্য নয়;
        # exception ছড়িয়ে নিচের in-memory fallback window-এ যাওয়া হয়।
        from core.cache.rate_limit_atomic import atomic_window_incr

        current_count = await atomic_window_incr(
            redis_manager.client, window_key, 120, raise_on_failure=True
        )

        if current_count > max_requests:
            logger.warning(
                f"🚨 API key rate limit exceeded for key hash prefix {api_key_hash[:8]}: ({current_count} hits)"
            )
            raise HTTPException(status_code=429, detail="API key rate limit exceeded")
    except HTTPException:
        raise
    except Exception as exc:
        # Issue #1703: unexpected Redis error-তেও fallback window প্রয়োগ হয়।
        logger.warning(
            f"⚠️ API Key rate limiter error: {exc}. Using in-memory fallback window (issue #1703)."
        )
        if not _fallback_allow(api_key_hash, max_requests):
            raise HTTPException(status_code=429, detail="API key rate limit exceeded") from exc


class APIKeyLimiter:
    """Per-API-key rate limiter facade.

    বাংলা: একক API key-ভিত্তিক rate limiter-এর class-based facade।
    Issue #895: test contract (`backend/tests/core/test_security_and_intelligence_contracts.py`)
    একটি `APIKeyLimiter` class expect করে। এই class বিদ্যমান
    `enforce_api_key_rate_limit()` async function-এর চারপাশে thin wrapper — কোনো
    নতুন behavior নয়, শুধু class-based API surface যাতে callers/test contract
    match করে।

    Usage::

        limiter = APIKeyLimiter(max_requests=120)
        await limiter.enforce(api_key_hash)
    """

    def __init__(self, max_requests: int = DEFAULT_MAX_REQUESTS_PER_MINUTE) -> None:
        self.max_requests = max_requests

    async def enforce(self, api_key_hash: str) -> None:
        """Enforce the per-key rate limit (delegates to module-level function)."""
        await enforce_api_key_rate_limit(api_key_hash, max_requests=self.max_requests)

    # Allow `APIKeyLimiter(...)(api_key_hash)` shorthand too.
    async def __call__(self, api_key_hash: str) -> None:
        await self.enforce(api_key_hash)


# Module-level convenience singleton (default 60 req/min ceiling).
api_key_limiter = APIKeyLimiter()


class APIKeyLimiterMiddleware(BaseHTTPMiddleware):
    """ASGI middleware wrapper for per-API-key rate limiting.

    বাংলা: Issue #898 — `security_pipeline.py` পূর্বে `APIKeyLimiter` class কে
    middleware হিসেবে `app.add_middleware()` দিয়ে register করতে চেয়েছিল, কিন্তু
    সেটি ASGI middleware protocol follow করে না → চুপচাপ skip হতো। এই class টি
    `BaseHTTPMiddleware` subclass করে আসল ASGI middleware হিসেবে behave করে।

    Behavior:
        - প্রতিটি request থেকে API key extract করে (`x-api-key` header অথবা
          `Authorization: Bearer <key>`)।
        - Key কে SHA-256 hash করে (privacy: raw key কখনো log/store করে না)।
        - `enforce_api_key_rate_limit()` call করে per-key rate limit enforce করে।
        - Rate limit পার হলে `call_next` এ যায়; অতিক্রম হলে 429 response।
        - Rate limit check নিজে exception ছাড়ালে fail-open করে (resilience — যাতে
          Redis down থাকলেও API available থাকে)।
    """

    def __init__(
        self,
        app: Any,
        max_requests: int = DEFAULT_MAX_REQUESTS_PER_MINUTE,
    ) -> None:
        super().__init__(app)
        self.max_requests = max_requests

    @staticmethod
    def _extract_api_key(request: Request) -> str | None:
        """`x-api-key` header অথবা `Authorization: Bearer <key>` থেকে API key নেয়।"""
        api_key = request.headers.get("x-api-key")
        if api_key:
            return api_key
        auth_header = request.headers.get("authorization") or ""
        if auth_header.lower().startswith("bearer "):
            token = auth_header[7:].strip()
            if token:
                return token
        return None

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        api_key = self._extract_api_key(request)
        if api_key:
            # Privacy: hash করে পাঠানো হয় — raw key কখনো log/store নয়।
            api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
            try:
                await enforce_api_key_rate_limit(api_key_hash, max_requests=self.max_requests)
            except HTTPException as exc:
                # 429 propagation — rate limit exceeded response।
                if exc.status_code == 429:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": exc.detail},
                        headers={"Retry-After": "60"},
                    )
                raise
            except Exception as exc:
                # Fail-open: rate limiter itself exception ছাড়ালেও request চলবে।
                logger.warning(
                    f"[APIKeyLimiterMiddleware] Rate limit check failed (fail-open): {exc}"
                )
        return await call_next(request)
