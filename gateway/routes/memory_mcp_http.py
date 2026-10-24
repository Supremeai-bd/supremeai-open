"""Issue #1494 — Memory MCP over HTTP (in-process FastAPI mount).

Problem this solves
-------------------
``memory/mcp_server.py`` could only run standalone (stdio for Claude Desktop /
Cursor / VS Code, or its own SSE server on a separate port). External HTTP
clients had no route inside the main FastAPI app — ``/mcp`` 404'd.

What this module adds
---------------------
``create_memory_mcp_asgi_app()`` returns a Starlette sub-application exposing
the SAME memory MCP server over the official MCP SDK SSE transport:

    GET  /mcp/sse          — SSE stream (JSON-RPC session endpoint events)
    POST /mcp/messages/    — client → server JSON-RPC frames

It is mounted by ``api/server.py`` at ``/mcp`` (guarded — the sub-app
degrades to 503 responses when the optional ``mcp`` SDK is unavailable, so
boot never crashes in minimal deployments).

Authentication
--------------
Every request must present ``Authorization: Bearer <MCP_ADMIN_KEY>`` — the
same credential the MCP Control Tower accepts (env var first, Infisical
vault-cache fallback via ``settings.get_secret``, mirroring the 12-factor
order used by ``middleware/cors_policy.py``). Misconfigured/missing key ⇒
every request 401 (fail closed — never serve an unauthenticated MCP session).

Not in FastAPI OpenAPI
----------------------
MCP is a machine protocol, not a REST surface; the sub-app is mounted, not
routed, so it intentionally stays out of ``/openapi.json``.
"""

from __future__ import annotations

import os
from typing import Any

from core.logging_config import logger

try:  # optional dependency — the whole surface degrades to 503 without it
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route

    _SDK_AVAILABLE = True
except ImportError:  # pragma: no cover — exercised only in minimal deployments
    _SDK_AVAILABLE = False


MCP_SESSIONS_PATH = "/mcp/messages/"


def _mcp_admin_key() -> str:
    """12-factor order: process env first, then the Infisical vault cache."""
    val = os.getenv("MCP_ADMIN_KEY", "")
    if val:
        return val
    try:
        from core.config import settings

        if settings._is_test_environment():
            return ""
        return settings.get_secret("MCP_ADMIN_KEY") or ""
    except Exception:  # pragma: no cover — defensive, boot must never crash
        return ""


def _authorize(request: Any) -> JSONResponse | None:
    """Fail-closed bearer check. Returns a 401 response or None when OK."""
    expected = _mcp_admin_key()
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    if not expected or not token or token != expected:
        return JSONResponse({"detail": "Unauthorized MCP transport"}, status_code=401)
    return None


def create_memory_mcp_asgi_app() -> Starlette:
    """Build the mountable MCP-over-HTTP sub-application (SSE transport)."""
    if not _SDK_AVAILABLE:  # pragma: no cover
        raise RuntimeError("mcp SDK unavailable — memory MCP HTTP surface disabled")

    from memory.mcp_server import build_server

    server = build_server()
    sse_transport = SseServerTransport(MCP_SESSIONS_PATH)

    async def handle_sse(request: Request):
        unauthorized = _authorize(request)
        if unauthorized is not None:
            return unauthorized
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0],
                streams[1],
                server.create_initialization_options(),
            )
        # No return: the SSE response was streamed directly via request._send
        # (same contract as the standalone server in memory/mcp_server.py).

    async def authenticated_messages_app(scope, receive, send):
        """Pure-ASGI auth gate in front of the SDK's POST transport."""
        request = Request(scope, receive)
        unauthorized = _authorize(request)
        if unauthorized is not None:
            await unauthorized(scope, receive, send)
            return
        await sse_transport.handle_post_message(scope, receive, send)

    async def endpoint_unavailable(request: Request):  # pragma: no cover
        return JSONResponse(
            {"detail": "Memory MCP transport unavailable (mcp SDK missing)"},
            status_code=503,
        )

    routes = (
        [
            Route("/sse", endpoint=handle_sse, methods=["GET"]),
            Mount("/messages/", app=authenticated_messages_app),
        ]
        if _SDK_AVAILABLE
        else [
            Route("/sse", endpoint=endpoint_unavailable, methods=["GET"]),
            Route("/messages/", endpoint=endpoint_unavailable, methods=["POST"]),
        ]
    )

    logger.info("Memory MCP HTTP sub-app built (SSE at /mcp/sse, auth: Bearer MCP_ADMIN_KEY)")
    return Starlette(routes=routes)
