"""Authentication Middleware — JWT Auth token validation with fail-closed behavior.

বাংলা: অথেনটিকেশন মিডলওয়্যার — JWT বিয়ারার টোকেন ভ্যালিডেশন, Fail-Closed।
"""

from __future__ import annotations

import hmac
import json
from collections.abc import Awaitable, Callable
from typing import Any

import jwt
from jwt import ExpiredSignatureError
from jwt import PyJWTError as JWTError

from core.config import settings
from core.logging_config import logger
from utils.environment import is_test_environment

ASGIScope = dict[str, Any]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]
ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGIApp = Callable[[ASGIScope, ASGIReceive, ASGISend], Awaitable[None]]
Headers = list[tuple[bytes, bytes]]


def _get_bearer_token(headers: Headers) -> str | None:
    """Extract an Auth token from the ASGI headers list.

    বাংলা: ASGI হেডার থেকে Bearer টোকেন এক্সট্র্যাক্ট করে।
    """
    for key, value in headers:
        if key.lower() == b"authorization":
            raw = value.decode("utf-8", errors="replace")
            if raw.startswith("Bearer "):
                return raw[7:]
    return None


def _get_token_from_query(scope: ASGIScope) -> str | None:
    """Extract an Auth token from the query string for SSE/EventSource.

    EventSource (and <img>/<script>) cannot set an Authorization header, so
    SSE endpoints must accept the token via a query parameter:
        /api/dashboard/stream?token=<jwt>

    বাংলা: EventSource Authorization হেডার পাঠাতে পারে না, তাই SSE এন্ডপয়েন্টে
    টোকেন query parameter হিসাবে গ্রহণ করা হয়।

    SECURITY FIX (AUDIT-SEC-8, HIGH): query-string token সব পাথে গ্রহণ করলে
    JWT সার্ভার access log, reverse-proxy log, browser history ও Referer
    হেডারে লিক হয়। তাই এখন query token শুধুমাত্র SSE/স্ট্রিমিং পাথে
    (path-এ '/stream' থাকলে) গ্রহণ করা হবে — বাকি সব এন্ডপয়েন্টে
    Authorization header/httpOnly cookie ছাড়া কোনো টোকেন নয়।
    """
    path = (scope.get("path") or "").lower()
    if "/stream" not in path:
        return None
    qs = scope.get("query_string", b"")
    if not qs:
        return None
    try:
        query = qs.decode("utf-8", errors="replace")
    except Exception:
        return None
    for part in query.split("&"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        if key == "token" and value:
            from urllib.parse import unquote

            return unquote(value)
    return None


# JWT-COOKIE-MIGRATION (issue #1668, ধাপ ২/২): must stay in sync with
# api/routes/auth.py ACCESS_COOKIE_NAME / CSRF_COOKIE_NAME. The httpOnly
# access-token cookie set at login now counts as an auth source, so the
# frontend can stop persisting JS-readable tokens (XSS exfiltration path).
# বাংলা: login-এ সেট হওয়া httpOnly access-token cookie এখন অথেনটিকেশনের
# উৎস হিসেবে গ্রহণ করা হয় — Bearer header-এর পরে fallback হিসেবে।
ACCESS_COOKIE_NAME = "supreme_access_token"
CSRF_COOKIE_NAME = "supreme_csrf_token"
_CSRF_EXEMPT_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _parse_cookies(scope: ASGIScope) -> dict[str, str]:
    """Parse the Cookie header of an ASGI scope into a dict."""
    cookies: dict[str, str] = {}
    for key, value in scope.get("headers", []):
        if key.lower() == b"cookie":
            raw = value.decode("utf-8", errors="replace")
            for part in raw.split(";"):
                name, _, val = part.strip().partition("=")
                if name:
                    cookies[name] = val
    return cookies


def _get_cookie_token(scope: ASGIScope) -> str | None:
    """Extract the httpOnly access-token cookie set by /auth login/register.

    Priority order in AuthMiddleware.__call__: Authorization header →
    httpOnly cookie → (SSE-only) query param. The cookie is JS-unreadable,
    so this is the XSS-safe source the JWT-COOKIE-MIGRATION builds toward.
    """
    return _parse_cookies(scope).get(ACCESS_COOKIE_NAME) or None


def _cookie_csrf_ok(scope: ASGIScope) -> bool:
    """Double-submit CSRF check for cookie-authenticated state-changing
    requests: the X-CSRF-Token header must match the CSRF cookie.
    বাংলা: cookie থেকে অথেনটিকেট হওয়া state-changing request-এ CSRF হেডার ও
    cookie মিলতে হবে (double-submit pattern)।"""
    method = (scope.get("method") or "GET").upper()
    if method in _CSRF_EXEMPT_METHODS:
        return True
    cookies = _parse_cookies(scope)
    csrf_cookie = cookies.get(CSRF_COOKIE_NAME)
    if not csrf_cookie:
        return False
    for key, value in scope.get("headers", []):
        if key.lower() == b"x-csrf-token":
            return hmac.compare_digest(value.decode("utf-8", errors="replace"), csrf_cookie)
    return False


def _decode_jwt(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT token.

    বাংলা: JWT টোকেন ডিকোড এবং ভ্যালিডেট করে।

    Returns:
        Decoded payload dict, or None if invalid/expired/revoked.

    Note: এই ফাংশন sync — jti revocation চেক করে না। সেটি AuthMiddleware.__call__
    এ async ভাবে করা হয় (নিচে দেখুন)।
    """
    if not settings.jwt_secret:
        logger.critical(
            "JWT_SECRET is missing. Rejecting authentication under fail-closed security policy."
        )
        return None

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        # বাংলা: access type চেক — refresh টোকেন অ্যাক্সেস হিসেবে ব্যবহার রোধ।
        if payload.get("type") == "refresh":
            logger.warning("Refresh token used as access token — rejected")
            return None
        return payload
    except ExpiredSignatureError:
        logger.warning("JWT token has expired")
        return None
    except JWTError as exc:
        logger.warning(f"JWT token validation failed: {exc}")
        return None


def _is_public_path(path: str) -> bool:
    """Check if a path is public (no auth required).

    বাংলা: পাথটি পাবলিক কিনা চেক করে (কোনো অথের প্রয়োজন নেই)।
    """
    # Allow Swagger docs & OpenAPI definitions unconditionally
    if path in (
        "/docs",
        "/redoc",
        "/openapi.json",
        f"{settings.API_V1_STR}/openapi.json",
    ):
        return True

    # Allow Telegram Bot Webhook & Health endpoints
    if path in (
        "/telegram/webhook",
        "/telegram/health",
        f"{settings.API_V1_STR}/telegram/webhook",
        f"{settings.API_V1_STR}/telegram/health",
    ):
        return True

    # বাংলা মন্তব্য: '/' দিয়ে শুরু হওয়া সব পাথকে এভয়েড করতে এবং সেগমেন্ট বাউন্ডারি চেক করতে কাস্টম ম্যাচিং লজিক ব্যবহার করা হচ্ছে।
    for prefix in settings.supremeai_public_paths:
        if prefix == "/":
            if path == "/":
                return True
        elif path == prefix or path.startswith(prefix + "/"):
            return True
    return False


async def _send_json_response(
    send: ASGISend,
    status_code: int,
    body: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> None:
    """Send a raw ASGI JSON response.

    বাংলা: কাঁচা ASGI JSON রেসপন্স পাঠায়।
    """
    response_headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
    ]
    if headers:
        for key, value in headers.items():
            response_headers.append((key.lower().encode(), value.encode()))

    body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
    response_headers.append((b"content-length", str(len(body_bytes)).encode()))

    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": response_headers,
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body_bytes,
        }
    )


class AuthMiddleware:
    """ASGI middleware for JWT-based authentication.

    বাংলা: JWT-ভিত্তিক অথেনটিকেশনের জন্য ASGI মিডলওয়্যার।

    Skips authentication for public paths and test environment.
    Attaches user info (sub, role, tenant_id) to scope on success.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # বাংলা মন্তব্য (ROOT-CAUSE FIX): CORS preflight (OPTIONS) request ব্রাউজার কখনোই
        # Authorization header পাঠায় না — এটাই fetch/XHR স্পেকের normal আচরণ। কিন্তু এই
        # মিডলওয়্যার আগে path পাবলিক না হলে OPTIONS-কেও token-বিহীন request ধরে সরাসরি
        # raw ASGI 401 পাঠাত (_send_json_response), যেখানে কোনো CORS header যোগ হয় না।
        # app_builder.py-তে middleware add করার ক্রম অনুযায়ী AuthMiddleware,
        # CORSMiddleware/TrustedOriginMiddleware-এর চেয়ে বেশি বাইরের (outer) লেয়ারে থাকে
        # (Starlette-এ add_middleware() প্রতিবার তালিকার শুরুতে insert করে, তাই সবার
        # আগে-যোগ-করা middleware সবচেয়ে ভেতরের/router-এর কাছের স্তর হয়ে যায়) — ফলে
        # preflight request CORSMiddleware-এ পৌঁছানোর আগেই এখানে 401 হয়ে যেত, আর ব্রাউজার
        # সেটাকে "blocked by CORS policy: No 'Access-Control-Allow-Origin' header" হিসেবে
        # রিপোর্ট করত, যদিও ADMIN_CORS_ORIGINS ঠিকভাবেই কনফিগার করা ছিল। তাই এখন OPTIONS
        # request auth check ছাড়াই সরাসরি পরের middleware/app-এ পাঠানো হচ্ছে, যাতে
        # CORSMiddleware/TrustedOriginMiddleware প্রকৃত preflight হ্যান্ডলিং করতে পারে।
        if scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if _is_public_path(path) or (is_test_environment() and settings.is_bypass_allowed):
            await self.app(scope, receive, send)
            return

        headers: Headers = scope.get("headers", [])
        # JWT-COOKIE-MIGRATION (issue #1668, ধাপ ২/২): Bearer header first
        # (existing clients), then the httpOnly access cookie, then the
        # SSE-only query param (most leak-prone, stays last).
        cookie_token = _get_cookie_token(scope)
        token = _get_bearer_token(headers) or cookie_token or _get_token_from_query(scope)
        cookie_csrf_verified = cookie_token is not None and _cookie_csrf_ok(scope)

        # বাংলা: is_bypass_allowed production guard সহ check করে (ENV=production → always False)
        allow_bypass = settings.is_bypass_allowed
        if not isinstance(allow_bypass, bool):
            allow_bypass = False
        is_test_auth_bypassed = allow_bypass and is_test_environment()

        if not token:
            if is_test_auth_bypassed:
                user_data = {
                    "sub": "test_admin",
                    "role": "admin",
                    "tenant_id": "test_tenant",
                }
                scope["user"] = user_data
                if "state" not in scope:
                    scope["state"] = {}
                scope["state"]["user"] = user_data
                await self.app(scope, receive, send)
                return

            logger.warning(f"Missing Auth token for path: {path}")
            await _send_json_response(
                send,
                status_code=401,
                body={"detail": "Missing authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            return

        # JWT-COOKIE-MIGRATION (issue #1668): a cookie-authenticated
        # state-changing request must pass the double-submit CSRF check —
        # otherwise a cross-site form could ride the session cookie.
        if cookie_token is not None and not cookie_csrf_verified and not _get_bearer_token(headers):
            logger.warning(
                f"Cookie-auth request rejected: CSRF double-submit check failed for path: {path}"
            )
            await _send_json_response(
                send,
                status_code=403,
                body={"detail": "CSRF validation failed for cookie-authenticated request"},
            )
            return

        # API Key validation for system components / testing
        # বাংলা মন্তব্য: ব্যাকএন্ড/সিস্টেম কল ভ্যালিডেশনের জন্য API কী চেক করা হচ্ছে।
        if settings.supremeai_api_token and hmac.compare_digest(
            token.encode("utf-8"), settings.supremeai_api_token.encode("utf-8")
        ):
            user_data = {
                "sub": "system_api_key",
                "role": "admin",
                "tenant_id": None,
            }
            scope["user"] = user_data
            if "state" not in scope:
                scope["state"] = {}
            scope["state"]["user"] = user_data
            await self.app(scope, receive, send)
            return

        payload = _decode_jwt(token)
        if not payload:
            if is_test_auth_bypassed:
                user_data = {
                    "sub": "test_admin",
                    "role": "admin",
                    "tenant_id": "test_tenant",
                }
                scope["user"] = user_data
                if "state" not in scope:
                    scope["state"] = {}
                scope["state"]["user"] = user_data
                await self.app(scope, receive, send)
                return

            await _send_json_response(
                send,
                status_code=401,
                body={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )
            return

        # AUD-2.1 (logout revocation): the docstring already promised jti
        # revocation support but the check was only applied in selected route
        # dependencies. Verify revocation here so a logged-out access token is
        # rejected on EVERY protected surface, not just some of them.
        #
        # Production-readiness plan, item 2 — availability policy is role-aware:
        #   * admin/master_admin tokens → FAIL-CLOSED (Redis ডাউন হলে রিজেক্ট)
        #   * regular user tokens      → fail-open  (Redis blip-এ লক-আউট নয়)
        jti = payload.get("jti")
        if jti and not is_test_environment():
            token_is_admin = payload.get("role") in ("admin", "master_admin")
            try:
                from core.security import is_token_revoked

                if await is_token_revoked(jti, is_admin=token_is_admin):
                    logger.warning(f"Revoked token used for path: {path}")
                    await _send_json_response(
                        send,
                        status_code=401,
                        body={"detail": "Token has been revoked"},
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                    return
            except Exception as revocation_err:
                # Fail-closed would hard-break auth if Redis blips; instead log
                # loudly. Revocation remains enforced on the sensitive admin
                # paths (require_admin_token) which already fail closed.
                logger.error(f"Token revocation check failed: {revocation_err}")
                if token_is_admin:
                    # বাংলা: অ্যাডমিন টোকেন — ভেরিফাই করতে না পারলে নিরাপদ দিকে
                    # ব্যর্থ করা হয় (fail-closed)।
                    await _send_json_response(
                        send,
                        status_code=401,
                        body={"detail": "Token revocation could not be verified"},
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                    return

        # Attach user info to scope for downstream handlers
        user_data = {
            "sub": payload.get("sub"),
            "role": payload.get("role", "viewer"),
            "tenant_id": payload.get("tenant_id"),
        }
        scope["user"] = user_data
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["user"] = user_data

        await self.app(scope, receive, send)


async def verify_admin_session_fail_closed(request: Any) -> dict[str, Any]:
    """Verify admin session JWT token in a fail-closed manner.

    বাংলা: অ্যাডমিন সেশন JWT টোকেন fail-closed উপায়ে ভ্যালিডেট করে।
    Uses `_decode_jwt` to avoid duplicate JWT decode logic.
    """
    from fastapi import HTTPException

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        logger.warning("Missing Authorization header")
        raise HTTPException(status_code=401, detail="Missing authorization header")

    if not auth_header.startswith("Bearer "):
        logger.warning("Malformed Authorization header scheme")
        raise HTTPException(status_code=401, detail="Malformed authorization header")

    token = auth_header[7:]

    # Fail-closed check for JWT secret config
    if not settings.jwt_secret:
        logger.critical(
            "JWT_SECRET is missing. Rejecting authentication under fail-closed security policy."
        )
        raise HTTPException(status_code=500, detail="Authentication server configuration error")

    # Reuse _decode_jwt to avoid duplicate JWT decode logic
    payload = _decode_jwt(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    role = payload.get("role")
    if role not in ("admin", "master_admin"):
        logger.warning(f"Access denied: role '{role}' is not authorized for admin session")
        raise HTTPException(status_code=401, detail="Not authorized")

    return payload
