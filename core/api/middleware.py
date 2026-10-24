# backend/api/middleware.py
"""API-level middleware for SupremeAI.

Provides:
- SupremeContextMiddleware: Correlation ID injection with ErrorEventBus integration.
- RequestIdMiddleware: Inject X-Request-ID into every response for distributed tracing.
- TenantExtractionMiddleware: attaches verified JWT tenant context to request.state.
- ResponseStandardizationMiddleware: ensures all non-JSON responses follow the standard envelope.
- ChaosInjectorMiddleware: Enterprise Fault Injection & Chaos Engine for local testing.
- IdempotencyMiddleware: Redis-based distributed idempotency for POST paths.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import random
import time
import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus


class SupremeContextMiddleware(BaseHTTPMiddleware):
    """Injects Correlation ID for end-to-end observability and handles global failures."""

    @with_error_bus("dispatch")
    async def dispatch(self, request: Request, call_next):
        # Issue #685 (Domain 15): accept the standard ``X-Request-ID`` header
        # (sent by the canonical frontend apiClient) as a fallback so the id
        # contextualized into every log line below is the SAME id the client
        # generated — not a second, unrelated UUID. Precedence:
        # X-Correlation-ID → X-Request-ID → fresh UUID (mirrored in
        # core/request_context.py and RequestIdMiddleware).
        correlation_id = (
            request.headers.get("X-Correlation-ID")
            or request.headers.get("X-Request-ID")
            or str(uuid.uuid4())
        )
        request.state.correlation_id = correlation_id
        start_time = time.time()

        with logger.contextualize(correlation_id=correlation_id):
            try:
                response = await call_next(request)

                response.headers["X-Correlation-ID"] = correlation_id
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "DENY"
                response.headers["Strict-Transport-Security"] = (
                    "max-age=31536000; includeSubDomains"
                )
                response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

                process_time = time.time() - start_time
                response.headers["X-Process-Time"] = f"{process_time:.4f}"

                return response

            except Exception as exc:
                error_event_bus.emit(
                    ErrorEvent(
                        module="GlobalMiddleware",
                        error_type="REQUEST_FAILURE",
                        message=str(exc)[:500],
                        severity="ERROR",
                        context={
                            "method": request.method,
                            "url": str(request.url),
                            "correlation_id": correlation_id,
                        },
                        structured_context=ErrorContext(
                            module="api.middleware",
                            request_id=correlation_id,
                            env=settings.env,
                        ),
                    )
                )
                raise


class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce the readable-cookie/header double-submit CSRF contract.

    Bearer-token clients remain compatible because CSRF is only required when
    authentication is supplied by the httpOnly access-token cookie.
    """

    SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
    BOOTSTRAP_PATHS = {
        "/auth/login",
        "/auth/register",
        "/auth/refresh",
        "/auth/logout",
    }
    SIGNED_WEBHOOK_PREFIXES = ("/webhooks/", "/api/v1/webhooks/", "/cdc/")

    async def dispatch(self, request: Request, call_next):
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        if path in self.BOOTSTRAP_PATHS or path.startswith(self.SIGNED_WEBHOOK_PREFIXES):
            return await call_next(request)

        # Authorization-header requests are protected by the bearer token and
        # do not expose a browser cookie attack surface.
        if request.headers.get("Authorization"):
            return await call_next(request)

        access_cookie = request.cookies.get("supreme_access_token")
        if access_cookie:
            cookie_token = request.cookies.get("supreme_csrf_token")
            header_token = request.headers.get("X-CSRF-Token")
            if (
                not cookie_token
                or not header_token
                or not hmac.compare_digest(cookie_token, header_token)
            ):
                correlation_id = getattr(request.state, "correlation_id", str(uuid.uuid4()))
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": "CSRF validation failed",
                        "correlation_id": correlation_id,
                    },
                    headers={"X-Correlation-ID": correlation_id},
                )

        return await call_next(request)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID into every response for distributed tracing."""

    async def dispatch(self, request: Request, call_next):
        # Issue #685 (Domain 15): single-ID guarantee. SupremeContextMiddleware
        # runs OUTSIDE this middleware and has already resolved the request's
        # correlation id (X-Correlation-ID → X-Request-ID → fresh UUID), so
        # reuse it when the client did not send X-Request-ID itself. Result:
        # X-Request-ID and X-Correlation-ID response headers always carry ONE
        # id per request, matching the id in the structured logs.
        request_id = (
            request.headers.get("X-Request-ID")
            or getattr(request.state, "correlation_id", None)
            or str(uuid.uuid4())
        )
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class TenantExtractionMiddleware(BaseHTTPMiddleware):
    """Attach tenant_id to request.state from verified JWT claims only."""

    async def dispatch(self, request: Request, call_next):
        user = getattr(request.state, "user", None)
        request.state.tenant_id = (user or {}).get("tenant_id") or (user or {}).get("org_id")
        return await call_next(request)


class ResponseStandardizationMiddleware(BaseHTTPMiddleware):
    """Wrap non-JSON error responses into the standard API error envelope."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if (
            response.status_code >= 400
            and response.headers.get("content-type") != "application/json"
        ):
            description = getattr(response, "description", "Unknown error")
            body_content = ""
            if hasattr(response, "body") and getattr(response, "body", b""):
                body_content = response.body.decode()
            body = {"error": {"title": description, "detail": body_content}}
            standardized = JSONResponse(status_code=response.status_code, content=body)
            for key, value in response.headers.items():
                if key.lower() not in (
                    "content-type",
                    "content-length",
                    "content-encoding",
                    "transfer-encoding",
                ):
                    standardized.headers[key] = value
            return standardized
        return response


class ChaosInjectorMiddleware(BaseHTTPMiddleware):
    """Enterprise Fault Injection & Chaos Engine.
    Simulates real-world network degradation, packet loss, and latency spikes.
    Active ONLY when LOCAL_CHAOS_MODE=true.
    """

    def __init__(self, app):
        super().__init__(app)
        self.chaos_enabled = (
            os.getenv("LOCAL_CHAOS_MODE", "false").lower() == "true"
            and settings.env.lower() != "production"
        )
        self.packet_drop_rate = float(os.getenv("CHAOS_PACKET_DROP_RATE", "0.20"))
        self.max_latency_spike = float(os.getenv("CHAOS_MAX_LATENCY_SPIKE", "3.5"))
        self.latency_spike_chance = float(os.getenv("CHAOS_LATENCY_SPIKE_CHANCE", "0.30"))

    async def dispatch(self, request: Request, call_next):
        if not self.chaos_enabled:
            return await call_next(request)

        if random.random() < self.latency_spike_chance:
            delay = random.uniform(0.5, self.max_latency_spike)
            logger.warning(
                f"[CHAOS ENGINE] Injecting artificial network lag: {delay:.2f}s on {request.url.path}"
            )
            await asyncio.sleep(delay)

        if random.random() < self.packet_drop_rate:
            logger.critical(
                f"[CHAOS ENGINE] Simulated Packet Drop! Severing connection for {request.url.path}"
            )
            return JSONResponse(
                status_code=504,
                content={
                    "title": "Gateway Timeout (Chaos Simulated)",
                    "detail": "Upstream connection dropped due to artificial network degradation.",
                    "instance": request.url.path,
                },
            )

        return await call_next(request)


class GlobalRateLimiterMiddleware(BaseHTTPMiddleware):
    """Redis-based distributed sliding window rate limiter."""

    def __init__(self, app, limit: int = 100, window: int = 60):
        super().__init__(app)
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next):
        # Test harness already disables the lower-level limiter via RATE_LIMIT_ENABLED.
        # Keep this global gate aligned with that same switch so endpoint tests do not
        # become order-dependent or consume a shared Redis window.
        if (
            os.getenv("TESTING", "false").lower() == "true"
            or os.getenv("PYTEST_CURRENT_TEST")
            or os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "false"
            or str(getattr(settings, "env", "")).lower() == "test"
        ):
            return await call_next(request)

        if request.url.path.startswith(("/docs", "/redoc", "/api/v1/health", "/api/health")):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        from middleware.rate_limiter import AsyncRateLimiter

        limiter = AsyncRateLimiter()
        is_allowed = await limiter.acquire(
            f"global_ip:{client_ip}", limit=self.limit, window=self.window
        )

        if not is_allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "title": "Too Many Requests",
                        "detail": "Rate limit exceeded. Please try again later.",
                    }
                },
                headers={"Retry-After": str(self.window)},
            )

        return await call_next(request)


IDEMPOTENCY_TTL_SECONDS = 120
IDEMPOTENCY_PATHS = (
    "/api/task",
    "/api/github",
    "/api/auth/callback",
    "/api/pr",
    "/api/agent",
)


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Redis-based distributed idempotency for POST paths."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method != "POST" or not any(path.startswith(p) for p in IDEMPOTENCY_PATHS):
            return await call_next(request)

        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Bad Request: 'Idempotency-Key' header is required for mutating operations.",
                    "hint": "Provide a unique UUID as 'Idempotency-Key' header.",
                },
            )

        # FIX (#897, P1 security): পূর্বে এই import `try/except ImportError`-এ
        # fail-open ছিল — যার কারণে cache_response_and_release_lock missing থাকলেও
        # সম্পূর্ণ idempotency middleware silent no-op হয়ে যেত। Security middleware
        # silent skip করবে না — import error হলে fail-loud log + explicit metric
        # (non-blocking raise নয় কারণ এটি request-path মিডলওয়্যার)।
        from core.cache.redis_manager import (
            acquire_idempotency_lock,
            cache_response_and_release_lock,
            redis_manager,
            release_idempotency_lock,
        )

        # FIX (P1, review 2026-09-12): compute the scoped key before any Redis
        # usage so the lock path below is user-scoped too.
        principal = "anon"
        user = getattr(request.state, "user", None)
        if user:
            if isinstance(user, dict):
                principal = str(user.get("sub") or user.get("uid") or user.get("id") or "anon")
            else:
                principal = str(getattr(user, "id", None) or "anon")
        scoped_key = f"{principal}:{idempotency_key}"

        if redis_manager.client is not None:
            try:
                # FIX (P1, review 2026-09-12): scope the idempotency key per
                # authenticated principal. The cache was previously keyed ONLY by
                # the client-supplied Idempotency-Key header, so ANY user holding
                # the same key could replay another user's cached response
                # (cross-tenant data leak). Auth now runs before this middleware
                # (see app_builder reorder), so request.state.user is available.
                cached_key = f"idempotency:response:{scoped_key}"
                cached = await redis_manager.client.get(cached_key)
                if cached:
                    logger.info(
                        f"Idempotency Hit: serving cached response for key {idempotency_key}"
                    )
                    cached_data = json.loads(cached)
                    return JSONResponse(
                        status_code=cached_data.get("status_code", 200),
                        content=cached_data.get("body", {}),
                        headers={"X-Cache-Lookup": "HIT - Idempotency Lock"},
                    )
            except Exception as e:
                logger.warning(f"[Idempotency] Cache read failed — continuing: {e}")

        acquired = await acquire_idempotency_lock(scoped_key, IDEMPOTENCY_TTL_SECONDS)
        if not acquired:
            logger.warning(f"Idempotency Block: {idempotency_key} is already being processed.")
            raise HTTPException(
                status_code=409,
                detail="Conflict: Request is already being processed. Duplicate execution blocked.",
            )

        try:
            response = await call_next(request)

            if 200 <= response.status_code < 300 and redis_manager.client is not None:
                body_bytes = b""
                if hasattr(response, "body_iterator"):
                    try:
                        response_body = [section async for section in response.body_iterator]
                        body_bytes = b"".join(response_body)
                    except (RuntimeError, StopAsyncIteration) as stream_err:
                        logger.warning(
                            f"[Idempotency] Body iterator exhausted or failed: {stream_err}"
                        )
                        body_bytes = b"{}"
                elif hasattr(response, "body"):
                    body_bytes = response.body if response.body is not None else b"{}"
                else:
                    body_bytes = b"{}"

                if hasattr(response, "body_iterator"):
                    from starlette.responses import Response as StarletteResponse

                    response = StarletteResponse(
                        content=body_bytes,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type,
                    )

                try:
                    body_str = body_bytes.decode("utf-8")
                    cache_data = json.dumps({"status_code": 200, "body": json.loads(body_str)})
                    await cache_response_and_release_lock(
                        scoped_key, cache_data, IDEMPOTENCY_TTL_SECONDS * 5
                    )
                except (json.JSONDecodeError, UnicodeDecodeError) as parse_err:
                    logger.warning(
                        f"[Idempotency] Response body not JSON-serializable (non-blocking): {parse_err}"
                    )
                    await release_idempotency_lock(scoped_key)
                except Exception as cache_err:
                    logger.warning(
                        f"[Idempotency] Response caching failed (non-blocking): {cache_err}"
                    )
                    await release_idempotency_lock(scoped_key)
            else:
                await release_idempotency_lock(scoped_key)

            return response

        except Exception as e:
            await release_idempotency_lock(scoped_key)
            logger.error(f"Execution failed inside Idempotency block: {e!s}")
            raise


__all__ = [
    "ChaosInjectorMiddleware",
    "IdempotencyMiddleware",
    "RequestIdMiddleware",
    "ResponseStandardizationMiddleware",
    "SupremeContextMiddleware",
    "TenantExtractionMiddleware",
]
