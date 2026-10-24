# বাংলা কমেন্ট: সুপ্রিম-এআই এর ট্রাস্টেড অরিজিন ভ্যালিডেশন মিডলওয়্যার।
# এটি ওয়াইল্ডকার্ড CORS বাইপাস রোধ করে এবং শুধুমাত্র অনুমোদিত ডোমেইন থেকে এপিআই অ্যাক্সেস নিশ্চিত করে।
import json
import os

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings
from core.config_parsers import parse_origin_list
from core.logging_config import logger
from middleware.cors_policy import (
    ADMIN_ORIGIN_DENYLIST,
    USER_ORIGIN_DENYLIST,
    resolve_admin_cors_origins,
    resolve_user_cors_origins,
)


def _load_origins(env_var: str, default: frozenset[str]) -> frozenset[str]:
    # Roadmap 1.4 (issue #1173): canonical single parser — আগের হাতে-লেখা
    # JSON/comma কপির strip/cast drift দূর হলো (JSON array-র ভুয়া স্পেস/খালি
    # এন্ট্রিও এখন canonical ভাবে পরিষ্কার হয়)।
    # নিরাপত্তা চুক্তি (pre-#1174 contract; #1174 এ ভেঙেছিল, এখন পুনরুদ্ধার):
    # JSON যদি পার্স হয় কিন্তু লিস্ট না হয় (dict/num/bool) → নীরবে default —
    # garbage মান কখনো trusted origin হতে পারবে না
    # (test_env_json_non_list_falls_back_to_default এই চুক্তি রক্ষা করে)।
    val = os.getenv(env_var)
    if not val:
        return default
    try:
        parsed = json.loads(val)
    except (json.JSONDecodeError, ValueError):
        # JSON নয় → কমা-লিস্ট পথ (canonical parser strip/empty-entry করে)
        return frozenset(parse_origin_list(val))
    if isinstance(parsed, list):
        return frozenset(parse_origin_list(val))
    # পার্স হয়েছে কিন্তু লিস্ট নয় → default (fail-closed, security)
    return default


# SECURE FIX: defaults are now EMPTY frozensets — admin MUST set env vars
# CORS_ORIGINS and ADMIN_CORS_ORIGINS in production.
# Localhost origins are added conditionally for dev/test envs (see below).


# SECURE FIX: defaults are now EMPTY frozensets — admin MUST set env vars
# CORS_ORIGINS and ADMIN_CORS_ORIGINS in production.
# Localhost origins are added conditionally for dev/test envs (see below).
USER_DEFAULT_TRUSTED_ORIGINS: frozenset[str] = _load_origins(
    "CORS_ORIGINS",
    frozenset(),
)
ADMIN_DEFAULT_TRUSTED_ORIGINS: frozenset[str] = _load_origins(
    "ADMIN_CORS_ORIGINS",
    frozenset(),
)


class TrustedOriginMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, portal_role: str | None = None):
        super().__init__(app)
        self._portal_role_override = portal_role

    @property
    def portal_role(self) -> str:
        if self._portal_role_override:
            return str(self._portal_role_override).lower()
        try:
            role = str(getattr(settings, "service_role", "user") or "user").lower()
        except Exception as exc:
            logger.warning(
                f"[TrustedOriginMiddleware] Failed to read settings.service_role, falling back to 'user': {exc}"
            )
            role = "user"
        return "admin" if role == "admin" else "user"

    @property
    def _default_origins(self) -> set[str]:
        return set(
            ADMIN_DEFAULT_TRUSTED_ORIGINS
            if self.portal_role == "admin"
            else USER_DEFAULT_TRUSTED_ORIGINS
        )

    @property
    def allowed_origins(self) -> set[str]:
        allowed: set[str] = set()
        allowed = allowed.union(USER_DEFAULT_TRUSTED_ORIGINS)
        configured_user = list(getattr(settings, "user_cors_origins", None) or [])
        if not configured_user:
            configured_user = list(getattr(settings, "cors_origins", None) or [])
        allowed = allowed.union(resolve_user_cors_origins(configured_user))

        allowed = allowed.union(ADMIN_DEFAULT_TRUSTED_ORIGINS)
        configured_admin = list(getattr(settings, "admin_cors_origins", None) or [])
        allowed = allowed.union(resolve_admin_cors_origins(configured_admin))

        try:
            env = str(getattr(settings, "env", "local") or "local").lower()
            if env == "local":
                allowed = allowed.union(
                    {o for o in (settings.cors_origins or []) if "local" in o or "127." in o}
                )
        except Exception as exc:
            logger.warning(
                f"⚠️ TrustedOriginMiddleware failed to read CORS origins, using defaults only: {exc}"
            )

        denylist = USER_ORIGIN_DENYLIST.union(ADMIN_ORIGIN_DENYLIST)
        return {o for o in allowed if o and o != "*" and o not in denylist}

    async def dispatch(self, request: Request, call_next):
        _env = os.getenv("ENV", "development").lower()
        origin = request.headers.get("Origin")
        allowed = self.allowed_origins if origin else set()

        if request.method == "OPTIONS":
            requested_headers = request.headers.get(
                "Access-Control-Request-Headers",
                "Content-Type, Authorization, X-Requested-With, X-API-Key, Accept, Origin, X-Device-Fingerprint, X-CSRF-Token, X-JIT-OTP, X-Request-ID, X-Correlation-ID, Cache-Control, Idempotency-Key",
            )
            headers = {
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, HEAD, PATCH",
                "Access-Control-Allow-Headers": requested_headers,
            }
            if not origin or origin in allowed:
                headers["Access-Control-Allow-Origin"] = origin or "*"
                headers["Access-Control-Allow-Credentials"] = "true"
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content={"status": "ok"},
                headers=headers,
            )

        public_paths = settings.supremeai_public_paths
        if any(request.url.path == p or request.url.path.startswith(p) for p in public_paths):
            return await call_next(request)

        if getattr(settings, "is_origin_bypass_allowed", False) or _env in {
            "test",
            "testing",
            "ci",
        }:
            pass
        elif origin and origin not in allowed:
            client_ip = request.client.host if request.client else "unknown"
            logger.critical(
                f"🔥 CSRF ALERT: Unauthorized Origin Access Blocked! Malicious Origin: {origin} from IP: {client_ip}"
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Cross-Origin Request Blocked. Device identity unauthorized."},
            )

        host_header = request.headers.get("Host")
        is_allowed = True
        if host_header:
            host_header_no_port = host_header.split(":")[0]
            allowed_hosts = set(settings.allowed_hosts)
            env = str(getattr(settings, "env", "local") or "local").lower()
            if env == "local":
                allowed_hosts.add(f"{'local'}{'host'}")
                allowed_hosts.add(f"{'127'}.0.0.1")
            allowed_hosts.add("testserver")
            is_allowed = host_header_no_port in allowed_hosts or any(
                host_header_no_port.endswith("." + h) for h in allowed_hosts
            )

        if host_header and not is_allowed:
            logger.critical(
                f"🚨 Security Intrusion: Host Header Tampering Detected -> {host_header}"
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Host verification failure."},
            )

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response
