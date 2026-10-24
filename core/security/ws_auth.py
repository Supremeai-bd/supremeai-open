"""WebSocket authentication helpers (AUD-2.1 / AUD-2.6).

FastAPI ``AuthMiddleware`` only guards ``http`` scopes, so every WebSocket
endpoint must perform its own token verification. Historically several WS
endpoints accepted connections without any check; this module centralises the
fail-closed handshake so endpoints cannot drift apart again.

Supported client styles:
1. Query-string token: ``ws://host/path?token=<jwt>``
2. First-message handshake: client sends ``{"type": "auth", "token": "<jwt>"}``
"""

from __future__ import annotations

from typing import Any

from fastapi import WebSocket, status
from fastapi.websockets import WebSocketDisconnect

from core.logging_config import logger
from core.security import verify_token


async def authenticate_websocket(
    websocket: WebSocket,
    token: str | None = None,
    *,
    require_admin: bool = False,
) -> dict[str, Any] | None:
    """Authenticate a WebSocket connection.

    Args:
        websocket: The incoming WebSocket.
        token: Token supplied by the caller (e.g. from the query string). When
            omitted, the helper waits for the first message and expects a JSON
            auth handshake ``{"type": "auth", "token": "..."}``.
        require_admin: When True the verified payload must carry the ``admin``
            role (403-equivalent close otherwise).

    Returns:
        The verified token payload, or ``None`` when the connection was closed.
    """
    payload: dict[str, Any] | None = None
    # বাংলা (JWT-COOKIE-MIGRATION): query-token না থাকলে httpOnly cookie
    # ফলব্যাক -- same-site WebSocket handshake-এ cookie ব্রাউজার নিজেই পাঠায়।
    if not token:
        token = websocket.cookies.get("supreme_access_token")
    try:
        if token:
            payload = verify_token(token)
        else:
            # First-message auth handshake (mirrors websocket_agent.manager).
            auth_msg = await websocket.receive_json()
            candidate = auth_msg.get("token") if isinstance(auth_msg, dict) else None
            if auth_msg.get("type") == "auth" and candidate:
                payload = verify_token(candidate)
    except WebSocketDisconnect:
        raise
    except Exception as exc:  # invalid/expired/malformed token
        logger.warning(f"[WS-AUTH] Rejected WebSocket connection: {type(exc).__name__}")
        payload = None

    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return None

    if require_admin and str(payload.get("role", "")).lower() != "admin":
        logger.warning("[WS-AUTH] Rejected non-admin WebSocket connection")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Forbidden")
        return None

    return payload
