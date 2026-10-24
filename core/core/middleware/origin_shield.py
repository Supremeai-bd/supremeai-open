# বাংলা কমেন্ট: #781 ফিক্স — Origin Shield Middleware (Cloudflare Worker প্রি-শেয়ার্ড সিক্রেট ভ্যালিডেশন)।
#
# সমস্যা: Render free-tier সার্ভিসের ipAllowList আনরেস্ট্রিক্টেড থাকতেই হয় (Render-এর নিজস্ব
# health probe + dynamic egress IP এর জন্য)। ফলে যে কেউ সরাসরি Render-এর ডিফল্ট ডোমেইনে
# হিট করে backend-এ ঢুকে যেতে পারে।
#
# সমাধান (Option 1 — Zero-cost Cloudflare Fronting):
#   1. Cloudflare Worker (infrastructure/cloudflare_worker.js) প্রতিটি প্রক্সাইড রিকোয়েস্টে
#      `X-Origin-Verify-Key: <secret>` হেডার যোগ করে (withOriginShield)।
#   2. এই middleware-টি প্রোডাকশনে (ENV=production) ORIGIN_VERIFY_KEY সেট থাকলে সক্রিয় হয়।
#   3. /health, /health/live, /api/v1/health পাথগুলো Render-এর নিজস্ব health probe-এর জন্য
#      উন্মুক্ত থাকে (bypass)।
#   4. অন্য সমস্ত রিকোয়েস্টে বৈধ X-Origin-Verify-Key হেডার থাকতেই হবে — নাহলে 403 Forbidden।
#   5. ডিরেক্ট Render অরিজিন হিট (Worker ছাড়া) হেডার পাবে না → ব্লক হবে।
#
# Fail-closed: প্রোডাকশনে key সেট থাকলে অথেনটিকেটেড রিকোয়েস্ট ছাড়া কিছুই ঢুকবে না।
# Fail-open: ডেভ/টেস্ট env বা key সেট না থাকলে middleware no-op (যাতে লোকাল dev ব্রেক না হয়)।
from __future__ import annotations

import hmac
import os
from collections.abc import Iterable

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.logging_config import logger

# বাংলা: এই পাথগুলো Render-এর নিজস্ব health probe + Firebase init-এর জন্য উন্মুক্ত থাকবে।
# এগুলো কোনো sensitive ডেটা রিটার্ন করে না, তাই অরিজিন শিল্ড বাইপাস করা নিরাপদ।
_PUBLIC_BYPASS_PREFIXES: tuple[str, ...] = (
    "/health",  # /health, /health/live, /health/ready
    "/api/v1/health",  # legacy admin health path
    "/api/v1/public/",  # explicitly public API surface (read-only, no auth)
    "/__/firebase/",  # Firebase Hosting reserved init endpoint
    "/favicon",  # static favicon
    "/manifest.json",  # PWA manifest
    "/robots.txt",  # robots
)

# বাংলা: docs/openapi প্রোডাকশনে অন্য DocsAuthMiddleware দিয়ে সুরক্ষিত —
# এখানে ব্লক করলে সেই middleware-এর আগেই 403 চলে যাবে। তাই docs-কে বাইপাস রাখা হয়েছে
# (DocsAuthMiddleware নিজেই এটা সুরক্ষিত করবে)।
_DOCS_BYPASS_PREFIXES: tuple[str, ...] = (
    "/docs",
    "/redoc",
    "/openapi.json",
)


def _is_production() -> bool:
    """প্রোডাকশন env চেক — ENV বা NODE_ENV যেকোনো একটা 'production'/'prod' হলে True।"""
    env = os.getenv("ENV", "").lower()
    node_env = os.getenv("NODE_ENV", "").lower()
    return env in ("production", "prod") or node_env in ("production", "prod")


def _is_test_env() -> bool:
    """টেস্ট/CI env-এ middleware no-op (যাতে test suite ব্রেক না হয়)।"""
    env = os.getenv("ENV", "").lower()
    return env in ("test", "testing", "ci") or os.getenv("CI") == "true"


def _path_matches(path: str, prefixes: Iterable[str]) -> bool:
    """পাথ কোনো prefix-এর সাথে ম্যাচ করে কিনা।"""
    return any(path == p or path.startswith(p) for p in prefixes)


def _constant_time_eq(a: str, b: str) -> bool:
    """Timing-safe তুলনা — timing attack প্রতিরোধ।"""
    if not a or not b:
        return False
    return hmac.compare_digest(a.encode(), b.encode())


class OriginShieldMiddleware(BaseHTTPMiddleware):
    """#781 fix — Cloudflare Origin Shield pre-shared secret validation.

    প্রোডাকশনে (ENV=production) এবং ORIGIN_VERIFY_KEY সেট থাকলে:
    - /health*, /api/v1/health, /api/v1/public/, /__/firebase/, docs পাথ bypass করে।
    - বাকি সব রিকোয়েস্টে X-Origin-Verify-Key হেডার ORIGIN_VERIFY_KEY-এর সাথে timing-safe ম্যাচ করতে হবে।
    - ম্যাচ না করলে 403 Forbidden।

    Fail-open: ENV প্রোডাকশন না হলে বা key সেট না থাকলে middleware no-op (dev/test ব্রেক হয় না)।
    """

    async def dispatch(self, request: Request, call_next):
        # Fail-open: টেস্ট env-এ সম্পূর্ণ no-op
        if _is_test_env():
            return await call_next(request)

        # প্রোডাকশন না হলে বা key সেট না থাকলে no-op (dev/local ব্রেক হয় না)
        # বাংলা: এটি fail-open ডিজাইন — ORIGIN_VERIFY_KEY না থাকলে middleware সাইলেন্টলি বাইপাস হবে।
        # অপারেটর প্রোডাকশনে এটি সেট করতে বাধ্য — নাহলে Render ipAllowList খোলাই থাকবে।
        expected_key = os.getenv("ORIGIN_VERIFY_KEY", "").strip()
        if not expected_key or not _is_production():
            return await call_next(request)

        path = request.url.path

        # Public health + static + docs পাথ bypass
        if _path_matches(path, _PUBLIC_BYPASS_PREFIXES) or _path_matches(
            path, _DOCS_BYPASS_PREFIXES
        ):
            return await call_next(request)

        # মূল চেক: X-Origin-Verify-Key হেডার timing-safe ম্যাচ
        provided = request.headers.get("X-Origin-Verify-Key", "").strip()
        if not _constant_time_eq(provided, expected_key):
            client_ip = request.client.host if request.client else "unknown"
            logger.critical(
                "🛡️ OriginShield: direct origin access blocked "
                f"path={path} ip={client_ip} ua={request.headers.get('user-agent', '?')[:60]} "
                f"(missing/invalid X-Origin-Verify-Key — not from Cloudflare Worker)"
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": "Access denied. Requests must be routed through the official endpoint."
                },
            )

        return await call_next(request)
