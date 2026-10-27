"""gateway/middleware/security_headers.py — baseline security headers on every response (#1728).

# বাংলা: পাবলিক গেটওয়ে সারফেস (service/app.py, uvicorn origin) এখন পর্যন্ত একটিও
# বেসলাইন সিকিউরিটি হেডার দেয় না (live probe 2026-10-27: HSTS/CSP/XFO/XCTO সব
# অনুপস্থিত, HEAD / 405) — এই মিডলওয়্যার প্রতিটি রেসপন্সে সেগুলো স্ট্যাম্প করে।

Contract (additive, P2-safe, #1728 AC1-AC4):
- Pure-ASGI header injection on ``http.response.start`` — never touches the
  body, never buffers, SSE-safe (no BaseHTTPMiddleware in the stream path).
- SET semantics (replace, not append): exactly one occurrence of each header
  per response — never duplicated (browsers resolve duplicate security headers
  inconsistently; CSP duplicates intersect and can break). The middleware value
  uniformly wins (defense-in-depth: no route can weaken XFO/XCTO by accident).
- CSP ships report-only first (#1728 AC3): ``Content-Security-Policy-Report-Only``
  carries the JSON-API lockdown policy; the enforce flip is a one-line rename
  of the CSP key into the enforced header name in the follow-up PR, gated on a
  clean report window.
- HSTS ``includeSubDomains`` is safe here (anti-pattern checked): the service
  host is a Render leaf host (*.onrender.com); the platform terminates TLS for
  every path beneath it and no HTTP-only internal host exists under it.
- Stdlib + starlette only; no new dependencies.

Mount (must be added AFTER the CORS middleware so it is OUTERMOST — Starlette
``add_middleware`` prepends; outermost = stamped on every response, CORS
preflight included):
    from gateway.middleware.security_headers import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)

Local test:
    pytest gateway/tests/test_security_headers.py
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# #1728 proposal step 1: the four baseline headers + the two optional hardeners.
# Report-only phase (#1728 AC3): the CSP policy travels in the -Report-Only
# variant; flipping to enforce renames the key — no policy text change.
SECURITY_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy-Report-Only": (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "interest-cohort=()",
}


class SecurityHeadersMiddleware:
    """Stamp the baseline security headers onto every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_security_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS.items():
                    headers[name] = value
            await send(message)

        await self.app(scope, receive, send_with_security_headers)
