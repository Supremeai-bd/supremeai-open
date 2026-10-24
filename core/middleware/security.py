"""
SuperAI Security Middleware
============================
Security headers, request validation, and attack prevention.

Author: SuperAI Transformation Patch
Version: 1.0.0
"""

import asyncio
import os
import re
import sys
import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from core.config import settings
from core.logging_config import logger

# Configure logging


# Security header configuration
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        # SEC-HARDEN P9: 'unsafe-inline' removed from script-src. Inline execution
        # stays enabled ONLY where a per-route CSP explicitly needs it (mermaid /
        # react artifact previews set their own headers); every other HTML surface
        # (including raw user-uploaded artifact HTML) now inherits a strict policy,
        # which directly mitigates stored/reflected XSS.
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://*.supabase.co wss://*.supabase.co; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-src 'self' https: http:;"
    ),
}

# Patterns for SQL injection detection
SQL_INJECTION_PATTERNS = [
    r"(\%27)|(\')|(\-\-)|(\%23)|(#)",  # Basic SQL meta-characters
    r"((\%3D)|(=))[^\n]*((\%27)|(\')|(\-\-)|(\%3B)|(;))",  # SQL injection basics
    r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))",  # SQL 'OR' injection
    r"((\%27)|(\'))union",  # UNION injection
    r"exec(\s|\+)+(s|x)p\w+",  # SQL Server exec
]

# XSS detection patterns
XSS_PATTERNS = [
    r"<script[^>]*>.*?</script>",
    r"javascript\s*:",
    r"on\w+\s*=",
    r"<iframe",
    r"<object",
    r"<embed",
]

# Additional Dangerous Patterns
DANGEROUS_PATTERNS = [
    r"\.\./",  # Path traversal
    r"\.\.\\",  # Path traversal, Windows backslash
    r"\$\{",  # Template injection
    # URL/Double-encoded traversal variants (SEC-HARDEN-2026-09): `\.\./` alone
    # cannot match hex-encoded ("%2e%2e%2f") or double-encoded ("%252e%252e%252f")
    # payloads, which is a standard WAF bypass. These patterns close that gap.
    r"%2e%2e%2f",  # URL-encoded "../"
    r"%2e%2e\\",  # URL-encoded "..\"
    r"%252e%252e%252f",  # Double-encoded "../"
    r"%252e%252e%255c",  # Double-encoded "..\"
    r"\.\.%2f",  # Mixed "./..%2f"
    r"\.\.%5c",  # Mixed "./..\ (encoded)"
    r"%2e%2e/",  # Mixed "../"
]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        # Add security headers
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value

        # Remove server signature
        del_response_header(response.headers, "Server")
        del_response_header(response.headers, "X-Powered-By")

        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Validate requests for common attack patterns.

    বাংলা (P1 — Redis-authoritative rate limiting policy):
    রেট লিমিটিং Redis-ভিত্তিক (centralized redis_manager) — সেটাই authority;
    মাল্টি-ইনস্ট্যান্স deployment-এ aggregate লিমিট একমাত্র Redis ধরে।
    Redis অনুপলব্ধ হলে per-instance in-memory sliding window শুধুমাত্র
    EMERGENCY fallback — এটা aggregate-safe নয় এবং WARNING লগে চিহ্নিত।
    আরও দেখুন docs/deployment/RATE_LIMITING.md
    """

    # Maximum request sizes (bytes)
    MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_QUERY_LENGTH = 2048
    MAX_HEADER_SIZE = 8192

    # Default Rate limiting per IP
    RATE_LIMIT = 100  # Requests per minute
    RATE_WINDOW = 60  # Seconds

    # Path-specific rate limits (critical paths)
    SIMPLE_RATE_LIMITS = {
        "/api/v1/auth/login": {"requests": 5, "window": 600},  # 5 per 10 min
        "/api/v1/auth/register": {"requests": 3, "window": 3600},  # 3 per hour
        "/api/v1/scraper/scrape": {"requests": 20, "window": 3600},  # 20 per hour
        "/api/v1/kaggle/submit": {"requests": 10, "window": 3600},  # 10 per hour
    }

    def __init__(self, app):
        super().__init__(app)
        # বাংলা: EMERGENCY fallback state — প্রতি ইনস্ট্যান্সে আলাদা (per-process)।
        self._request_log: dict[str, list[float]] = {}
        self._fallback_warned = False
        # Issue #437 (log-storm dampener): warn at most once per 5 minutes while
        # Redis is unavailable (quota exhaustion persisted for the whole month in
        # the Upstash incident and this middleware produced 42–51% of all log lines).
        self._last_fallback_warning = 0.0

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        client_ip = self._get_client_ip(request)

        # Check request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.MAX_BODY_SIZE:
            logger.warning(f"Oversized request from {client_ip}: {content_length} bytes")
            return Response(
                status_code=413,
                content=b'{"error": "Request entity too large"}',
                media_type="application/json",
            )

        # Check query string length
        if len(str(request.query_params)) > self.MAX_QUERY_LENGTH:
            return Response(
                status_code=414, content=b'{"error": "URI too long"}', media_type="application/json"
            )

        # Simple rate limiting (backup for Redis-based limiter)
        is_testing = (
            os.getenv("TESTING", "false").lower() == "true"
            or bool(os.getenv("PYTEST_CURRENT_TEST"))
            or os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "false"
        )
        if not is_testing:
            # Issue #460 dedup: APIKeyAuthMiddleware (outermost) already
            # evaluated this request's IP verdict at the same (limit, window)
            # — reuse it instead of double-billing a second Redis evaluation.
            eff_limit, eff_window = self._effective_limits(request.url.path)
            verdict = getattr(request.state, "rate_limit_ip_verdict", None)
            shared = (
                verdict is not None
                and verdict.get("limit") == eff_limit
                and verdict.get("window") == eff_window
            )
            if shared:
                allowed = verdict["allowed"]
            else:
                allowed = await self._check_rate_limit(client_ip, request.url.path)
                request.state.rate_limit_ip_verdict = {
                    "allowed": allowed,
                    "limit": eff_limit,
                    "window": eff_window,
                }
            if not allowed:
                return Response(
                    status_code=429,
                    content=b'{"error": "Too many requests"}',
                    media_type="application/json",
                )

        # Scan for SQL injection in query params
        query_string = str(request.query_params)
        if self._detect_sql_injection(query_string):
            logger.warning(f"SQL injection attempt from {client_ip}")
            return Response(
                status_code=400,
                content=b'{"error": "Invalid request"}',
                media_type="application/json",
            )

        # Scan for XSS in query params
        if self._detect_xss(query_string):
            logger.warning(f"XSS attempt from {client_ip}")
            return Response(
                status_code=400,
                content=b'{"error": "Invalid request"}',
                media_type="application/json",
            )

        # Scan for other dangerous patterns
        if self._detect_dangerous(query_string):
            logger.warning(f"Dangerous pattern attempt from {client_ip}")
            return Response(
                status_code=400,
                content=b'{"error": "Invalid request"}',
                media_type="application/json",
            )

        return await call_next(request)

    def _get_client_ip(self, request: Request) -> str:
        # R2-08: proxy-aware, spoof-resistant extraction (shared helper)
        from utils.client_ip import get_client_ip

        return get_client_ip(request)

    def _effective_limits(self, path: str) -> tuple[int, int]:
        """Resolve (limit, window) for a path — default or critical-path override."""
        for critical_path, config in self.SIMPLE_RATE_LIMITS.items():
            if path.startswith(critical_path):
                return int(config["requests"]), int(config["window"])
        return self.RATE_LIMIT, self.RATE_WINDOW

    async def _check_rate_limit(self, client_ip: str, path: str) -> bool:
        """Rate limit check — Redis-authoritative with emergency fallback.

        বাংলা: একক atomic EVAL (issue #460) — INCR+EXPIRE ১টি op-এ হয়, retry
        দিয়ে window বাড়ানো যায় না (self-amplifying 429 loop bug এড়াতে,
        core/rate_limit.py-এর P2 fix-এর সাথে consistent)।
        """
        # Determine applicable limits
        limit = self.RATE_LIMIT
        window = self.RATE_WINDOW

        for critical_path, config in self.SIMPLE_RATE_LIMITS.items():
            if path.startswith(critical_path):
                limit = config["requests"]
                window = config["window"]
                break

        # Use a combination of IP and path prefix for tracking critical paths
        # For general requests, just use IP to group them
        tracking_key = f"{client_ip}:{path}" if limit != self.RATE_LIMIT else client_ip

        # 1) Redis-authoritative path (aggregate-safe across instances)
        client = None
        try:
            # (#2098) Patch-proof + shadow-proof manager resolution.
            # বাংলা: `from core.cache.redis_manager import redis_manager` লিখলে
            # core/cache/__init__-এর same-name re-export shadow দিয়ে গিয়ে
            # package attribute-এ বসা REAL singleton instance পেয়ে যেতে পারে —
            # টেস্টের module-attr monkeypatch বাইপাস হয়ে যায় (CI-only 4×
            # "Event loop is closed" failure, issue #2098)। sys.modules-first
            # lookup সবসময় আসল module object-এর (patch-করা) attribute দেয়।
            # Production-এ দুই পথই একই singleton দেয় — behavior identical।
            rm_module = sys.modules.get("core.cache.redis_manager")
            if rm_module is None:
                from importlib import import_module

                rm_module = import_module("core.cache.redis_manager")
            redis_manager = rm_module.redis_manager

            client = await redis_manager.get_client_async()
        except Exception as exc:  # noqa: BLE001 — any redis failure falls back
            logger.debug(f"Security rate limiter Redis error: {exc}")

        if client is not None:
            try:
                # Issue #460 (Pillar 1): single atomic EVAL (1 billable op).
                # Old two-phase prune+count then add+expire = 4 billable
                # commands per request. EXPIRE only lands on the first INCR,
                # so retries can never extend the window (P2 guarantee kept).
                from core.cache.rate_limit_atomic import atomic_window_incr

                rl_key = f"security_rate_limit:{tracking_key}"
                count = await atomic_window_incr(client, rl_key, window)
                return count <= limit
            except Exception as exc:  # noqa: BLE001 — degrade to memory, never 500
                redis_manager.report_failure(exc)
                self._fallback_warned = True
                now_mono = time.monotonic()
                if now_mono - self._last_fallback_warning >= 300.0:
                    self._last_fallback_warning = now_mono
                    logger.warning(
                        f"Security rate limiter Redis failed ({exc}) — EMERGENCY in-memory "
                        "fallback active (per-instance, NOT aggregate-safe across instances)"
                    )

        # 2) EMERGENCY in-memory fallback (per-instance)
        # বাংলা: await বাধ্যতামূলক — না করলে coroutine অবজেক্ট truthy হয়ে
        # যাবে এবং fallback মোডে লিমিট আর enforce-ই হবে না।
        return await self._in_memory_rate_limit(tracking_key, limit, window)

    async def _in_memory_rate_limit(self, tracking_key: str, limit: int, window: int) -> bool:
        """EMERGENCY per-instance sliding window (NOT multi-instance safe).

        বাংলা: Redis না থাকলে এই ফলব্যাক চলে — শুধু এই প্রসেস/ইনস্ট্যান্সের
        ভেতরে সঠিক; ২+ ইনস্ট্যান্সে aggregate লিমিট বাইপাস হয়। তাই এটা
        single-instance deployment-এর emergency behavior হিসেবে documented।
        """
        now = time.time()

        # Prune old entries (keep at most 1 hour of history)
        self._request_log = {
            k: timestamps
            for k, timestamps in self._request_log.items()
            if any(ts > now - 3600 for ts in timestamps)
        }

        # Check current IP/Key
        if tracking_key not in self._request_log:
            self._request_log[tracking_key] = []

        recent_requests = [ts for ts in self._request_log[tracking_key] if ts > now - window]

        if len(recent_requests) >= limit:
            return False

        self._request_log[tracking_key] = recent_requests + [now]
        return True

    @staticmethod
    def _detect_sql_injection(input_string: str) -> bool:
        """Detect potential SQL injection attempts."""
        for pattern in SQL_INJECTION_PATTERNS:
            if re.search(pattern, input_string, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _detect_xss(input_string: str) -> bool:
        """Detect potential XSS attempts."""
        for pattern in XSS_PATTERNS:
            if re.search(pattern, input_string, re.IGNORECASE):
                return True
        return False

    @staticmethod
    def _detect_dangerous(input_string: str) -> bool:
        """Detect other dangerous patterns (Path traversal, Template injection)."""
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, input_string, re.IGNORECASE):
                return True
        return False


def del_response_header(headers, key: str):
    """Safely delete a response header."""
    try:
        del headers[key]
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")
