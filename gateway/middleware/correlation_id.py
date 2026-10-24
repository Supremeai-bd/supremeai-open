"""gateway/middleware/correlation_id.py — X-Correlation-ID for every request (Way 28).

বাংলা: প্রতিটি রিকোয়েস্টে correlation id — inbound হেডার থাকলে সেটাই ধরে রাখা,
না থাকলে নতুন uuid; রেসপন্স হেডারে ফেরত + contextvar-এ সব লগের জন্য দুর্গম।
Infinity "Observe" প্যাটার্নের SupremeAI অ্যাডাপ্টেশন (plan Way 28)।

Contract (additive, P3-safe):
- Inbound `X-Correlation-ID` (or `X-Request-ID`) is honoured verbatim when it
  matches a safe charset; otherwise a fresh UUID4 hex is minted.
- The id is exposed via:
    * response header `X-Correlation-ID`
    * `current_correlation_id()` contextvar (usable from any logger/format)
- Never blocks, never rejects: worst case (bad header) → new id.
- Stdlib-only; safe to mount before any other middleware.

Mount (INTEGRATION.diff included):
    from gateway.middleware.correlation_id import CorrelationIdMiddleware
    app.add_middleware(CorrelationIdMiddleware)

Local test:
    pytest tests/test_correlation_id.py
"""

from __future__ import annotations

import contextvars
import re
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

CORRELATION_HEADER = "X-Correlation-ID"
_REQUEST_ID_HEADERS = ("X-Correlation-ID", "X-Request-ID")
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-.:]{8,128}$")

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


def current_correlation_id() -> str:
    """The correlation id bound to the current async context ('' outside requests)."""
    return _correlation_id.get()


def mint_correlation_id() -> str:
    return uuid.uuid4().hex


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind one correlation id per request; echo it back on the response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint):
        cid = ""
        for header in _REQUEST_ID_HEADERS:
            candidate = request.headers.get(header, "").strip()
            if candidate and _SAFE_ID_RE.match(candidate):
                cid = candidate
                break
        if not cid:
            cid = mint_correlation_id()
        token = _correlation_id.set(cid)
        try:
            response = await call_next(request)
        finally:
            # Reset before exception propagation continues; response header set below.
            pass
        if isinstance(response, JSONResponse) or hasattr(response, "headers"):
            try:
                response.headers[CORRELATION_HEADER] = cid
            except Exception:  # streaming responses may be immutable
                pass
        _correlation_id.reset(token)
        return response
