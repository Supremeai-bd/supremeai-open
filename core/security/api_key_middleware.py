"""API Key Authentication Middleware.

বাংলা: API কী অথেনটিকেশন মিডলওয়্যার — রেট লিমিটিং, রিভোকেশন চেক, এক্সপায়ারি ভ্যালিডেশন।
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.cache.redis_manager import redis_manager
from core.config import settings
from core.logging_config import logger
from core.resilience.circuit_breaker import CircuitBreaker
from core.security import API_KEY_PREFIX, hash_api_key, mask_api_key
from database.pgbouncer_pool import get_db_pool
from middleware.rate_limiter import AsyncRateLimiter
from models.api_key import record_api_key_usage
from utils.environment import is_test_environment


def _extract_client_ip(request: Request) -> str:
    """বাংলা: ক্লায়েন্টের আসল IP এক্সট্র্যাক্ট করে।

    শুধু request.client.host ব্যবহার করলে X-Forwarded-For স্পুফিং-এ প্রতারিত হওয়া যায়।
    নিরাপদ পদ্ধতি: settings.trusted_proxy_count পরিচিত প্রক্সি চেইন থাকলে শেষ
    প্রক্সি-এর আগের IP নেওয়া হয় (সবচেয়ে নির্ভরযোগ্য)। না থাকলে raw client.host।
    """
    raw_host = request.client.host if request.client else "unknown"
    if raw_host == "unknown":
        return "unknown"

    # বাংলা: trusted proxy chain কনফিগার করা থাকলেই XFF থেকে আসল IP নেওয়া হবে —
    # নাহলে যেকোনো ক্লায়েন্ট XFF স্পুফ করে rate limit বাইপাস করতে পারবে।
    trusted_proxy_count = int(getattr(settings, "trusted_proxy_count", 0) or 0)
    if trusted_proxy_count <= 0:
        return raw_host

    xff = request.headers.get("x-forwarded-for", "")
    if not xff:
        return raw_host

    # বাংলা: XFF ফরম্যাট: "client, proxy1, proxy2, ..."। শেষ trusted_proxy_count
    # সংখ্যক এন্ট্রি বাদ দিয়ে তার আগের IP টাই আসল ক্লায়েন্ট।
    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if len(parts) <= trusted_proxy_count:
        return raw_host
    return parts[-trusted_proxy_count - 1]


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validates API keys from the x-api-key header.

    Skips validation if:
    - No x-api-key header present
    - Key doesn't start with expected prefix
    - Running in test environment
    """

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.limiter = AsyncRateLimiter()
        self.prefix = API_KEY_PREFIX
        # Add circuit breaker for database operations
        self.db_circuit_breaker = CircuitBreaker(
            name="api_key_db_lookup", failure_threshold=3, recovery_timeout=30
        )

    async def _get_cached_api_key(self, key_hash: str) -> dict | None:
        """Fetch API key row from Redis cache or PostgreSQL with caching."""
        cache_key = f"apikey:{key_hash}"
        try:
            cached = await redis_manager.get_cache(cache_key)
            if cached:
                import json as _json

                return _json.loads(cached)
        except Exception as exc:
            logger.warning(f"Redis cache read failed for API key: {exc}")

        # Use circuit breaker for database operations
        try:
            # Execute database call through circuit breaker
            row = await self.db_circuit_breaker.acall(self._fetch_api_key_from_db, key_hash)
            if row:
                try:
                    import json as _json

                    await redis_manager.set_cache(cache_key, _json.dumps(dict(row)), ex_seconds=300)
                except Exception as exc:
                    logger.warning(f"Redis cache write failed for API key: {exc}")
                return dict(row)
        except Exception as exc:
            logger.error(f"Database operation failed for API key {mask_api_key(key_hash)}: {exc}")
            # Return None to indicate failure, but we'll handle it gracefully
            pass

        return None

    async def _fetch_api_key_from_db(self, key_hash: str):
        """Internal method to fetch API key from database."""
        pool = await get_db_pool()
        return await pool.fetchrow(
            "SELECT id, key_hash, revoked, rate_limit_rps, rate_limit_window, expires_at, scopes FROM api_keys WHERE key_hash = $1 LIMIT 1",
            key_hash,
        )

    async def dispatch(self, request: Request, call_next: Any) -> JSONResponse:
        # বাংলা মন্তব্য: public path-এ API key lookup DB call না করে সরাসরি skip করা হচ্ছে।
        # এটি health check, docs, auth endpoint-এ অযথা DB query এড়ায়।
        from core.config import settings as _settings

        path = request.url.path
        if any(path.startswith(p) for p in _settings.supremeai_public_paths):
            return await call_next(request)

        # IP-based sliding window rate limiter check
        # বাংলা: X-Forwarded-For স্পুফিং-সহনশীল IP এক্সট্র্যাকশন ব্যবহার করা হলো।
        client_ip = _extract_client_ip(request)
        # Issue #460 dedup: ONE IP evaluation per request across the whole
        # middleware stack. RequestValidationMiddleware reuses this verdict
        # whenever its effective (limit, window) matches, instead of every
        # request paying for two separate Redis rate-limit evaluations.
        verdict = getattr(request.state, "rate_limit_ip_verdict", None)
        if verdict is None:
            allowed = await self.limiter.acquire(f"ip:{client_ip}", limit=100, window=60)
            request.state.rate_limit_ip_verdict = {
                "allowed": allowed,
                "limit": 100,
                "window": 60,
            }
        else:
            allowed = verdict["allowed"]
        if not allowed:
            logger.warning(f"IP rate limit exceeded: {client_ip}")
            return JSONResponse(status_code=429, content={"detail": "IP rate limit exceeded"})

        api_key_header = request.headers.get("x-api-key")
        if not api_key_header or not api_key_header.startswith(self.prefix):
            return await call_next(request)

        if is_test_environment():
            request.state.api_key = {
                "id": "test",
                "masked": mask_api_key(api_key_header),
            }
            return await call_next(request)

        key_hash = hash_api_key(api_key_header)
        row = await self._get_cached_api_key(key_hash)
        if row is None:
            logger.warning(
                f"Invalid API key attempt or DB unavailable: {mask_api_key(api_key_header)}"
            )
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
        if row["revoked"]:
            logger.warning(f"Revoked API key used: {row['id']}")
            return JSONResponse(status_code=403, content={"detail": "API key has been revoked"})
        if row["expires_at"] and row["expires_at"] < int(time.time()):
            logger.warning(f"Expired API key used: {row['id']}")
            return JSONResponse(status_code=403, content={"detail": "API key has expired"})

        rps = int(row.get("rate_limit_rps") or 6)
        window = int(row.get("rate_limit_window") or 60)
        key_prefix = api_key_header[:12]

        try:
            is_allowed = await self.limiter.acquire(key_prefix, limit=rps, window=window)
        except RuntimeError as exc:
            logger.critical(f"Rate limiter failed: {exc}")
            return JSONResponse(
                status_code=503, content={"detail": "Rate limiting service unavailable"}
            )

        if not is_allowed:
            logger.warning(f"Rate limit hit for API key: {row['id']}")
            return JSONResponse(status_code=429, content={"detail": "API key rate limit exceeded"})

        request.state.api_key = {
            "id": row["id"],
            "masked": mask_api_key(api_key_header),
            "scopes": row.get("scopes", []),
        }

        # Non-critical: usage tracking failure should not block the request
        try:
            await record_api_key_usage(
                key_id=row["id"],
                endpoint=request.url.path,
                status_code=200,
                latency_ms=0.0,
                ip_address=str(request.client.host) if request.client else None,
            )
        except Exception:
            logger.opt(exception=True).warning(f"Failed to record API key usage for {row['id']}")

        logger.info(f"API key authenticated: {request.state.api_key['masked']}")
        return await call_next(request)
