"""Docs / OpenAPI exposure gate (P0 production hardening).

বাংলা: প্রোডাকশনে Swagger/ReDoc/OpenAPI স্কিমা পাবলিক থাকা একটি
sign-off blocker। এই মিডলওয়্যার দুটি কাজ করে:

1. docs নিষ্ক্রিয় থাকলে (settings.effective_docs_enabled == False) —
   /docs, /redoc, /docs/oauth2-redirect এবং openapi.json সব 404 দেয়,
   যাতে এন্ডপয়েন্টের অস্তিত্বই ফাঁস না হয় (FastAPI docs_url=None দিলেও
   কোনো ভুল কনফিগে আংশিক রেসপন্স আসার ঝুঁকি থাকে — defense in depth)।

2. docs স্পষ্টভাবে অপট-ইন করা থাকলে (SUPREMEAI_DOCS_ENABLED=true +
   শক্তিশালী SUPREMEAI_DOCS_PASSWORD) — production/staging-এ HTTP Basic
   auth চায় (docs_username / docs_password, constant-time তুলনা)।
   local/dev/test-এ গেট পাস-থ্রু থাকে যাতে ডেভেলপার এক্সপেরিয়েন্স নষ্ট না হয়।

AuthMiddleware এই পাথগুলোকে JWT-পাবলিক হিসেবে রাখে (core/security/
authentication/auth_middleware.py) — কারণ docs গেট JWT নয়, আলাদা
basic-auth দিয়ে সুরক্ষিত। এই মিডলওয়্যারটি innermost হিসেবে বসানো হয়
(core/app_builder.py) যাতে CORS/সিকিউরিটি চেইনের অর্ডারিং অক্ষত থাকে।
"""

from __future__ import annotations

import base64
import json
import secrets
from collections.abc import Callable

from core.config import settings
from core.logging_config import logger

# বাংলা: যেসব পাথ docs/OpenAPI exposure হিসেবে গণ্য হবে — AuthMiddleware-এর
# পাবলিক লিস্টের সাথে consistent রাখা হয়েছে।
_DOCS_PATHS = (
    "/docs",
    "/docs/oauth2-redirect",
    "/docs/oauth2-redirect/",
    "/redoc",
)
_OPENAPI_PATHS = (
    "/openapi.json",
    f"{settings.API_V1_STR}/openapi.json",
)


def _is_docs_path(path: str) -> bool:
    return path in _DOCS_PATHS or path in _OPENAPI_PATHS


def _check_basic_auth(header_value: str | None) -> bool:
    """Validate an HTTP Basic authorization header against docs credentials.

    বাংলা: Basic অথ হেডার docs_username/docs_password-এর সাথে মিলছে কিনা।
    """
    if not header_value or not header_value.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header_value.split(" ", 1)[1].strip()).decode("utf-8")
        username, _, password = decoded.partition(":")
    except Exception as exc:  # noqa: BLE001 — malformed header must never 500
        logger.debug(f"Malformed Basic auth header on docs gate rejected: {exc}")
        return False
    expected_user = settings.docs_username or "admin"
    expected_pass = settings.docs_password.get_secret_value() if settings.docs_password else ""
    user_ok = secrets.compare_digest(username or "", expected_user)
    pass_ok = secrets.compare_digest(password or "", expected_pass)
    return user_ok and pass_ok


class DocsAuthMiddleware:
    """Starlette-style raw ASGI middleware guarding docs/OpenAPI endpoints."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if not _is_docs_path(path):
            await self.app(scope, receive, send)
            return

        env = (getattr(settings, "env", "") or "").lower()
        gated_env = env in ("production", "staging")

        # Case 1: docs disabled → 404 (hide existence).
        if not settings.effective_docs_enabled:
            logger.debug("Docs endpoint requested while disabled: %s", path)
            response = _json_response(404, {"detail": "Not Found"})
            await response(scope, receive, send)
            return

        # Case 2: docs enabled, gated env → require HTTP Basic auth.
        if gated_env and getattr(settings, "docs_auth_enabled", True):
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            auth_header = headers.get("authorization")
            if not _check_basic_auth(auth_header):
                response = _json_response(
                    401,
                    {"detail": "API documentation requires authentication."},
                    headers={"WWW-Authenticate": 'Basic realm="SupremeAI Docs", charset="UTF-8"'},
                )
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)


def _json_response(status_code: int, body: dict, headers: dict[str, str] | None = None) -> Callable:
    """Build a raw ASGI JSON response sender (mirrors auth_middleware helper)."""

    async def _send(scope, receive, send):
        body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
        response_headers = [(b"content-type", b"application/json")]
        if headers:
            for name, value in headers.items():
                response_headers.append((name.lower().encode(), value.encode()))
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": response_headers,
            }
        )
        await send({"type": "http.response.body", "body": body_bytes})

    return _send
