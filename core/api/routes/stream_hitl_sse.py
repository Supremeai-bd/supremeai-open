"""SSE replacement for websocket_hitl.py `/` endpoint.

Streams Human-In-The-Loop approval events to the admin Command Center.

R10 FIX (corrected): Uses the REAL `error_event_bus` from
`core/messaging/event_bus.py`, NOT the non-existent `task_queue.subscribe_hitl_events`
that was hallucinated in the first version.

The existing websocket_hitl.py uses this exact pattern:
  error_event_bus.register_listener("*", hitl_event_listener)
We replicate the same pattern as an SSE generator instead of WS connection.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import get_current_user_token
from core.logging_config import logger
from core.messaging.event_bus import ErrorEvent, error_event_bus

router = APIRouter(prefix="/api/v1/stream", tags=["SSE HITL Stream"])

HEARTBEAT_SECONDS = 15


async def _hitl_event_stream(user_id: str, tenant_id: str) -> AsyncIterator[str]:
    """Subscribe to the global error_event_bus and forward HITL events as SSE.

    The existing websocket_hitl.py uses the same pattern — we mirror it
    for the SSE transport.
    """
    queue: asyncio.Queue[ErrorEvent] = asyncio.Queue()

    def _on_event(event: ErrorEvent) -> None:
        """Sync listener callback — push event into async queue."""
        try:
            # Filter: only HITL_REVIEW_REQUIRED events (same as websocket_hitl.py)
            if event.error_type != "HITL_REVIEW_REQUIRED":
                return
            context = getattr(event, "context", None) or {}
            if not isinstance(context, dict) or str(context.get("tenant_id")) != tenant_id:
                return
            queue.put_nowait(event)
        except Exception as e:
            logger.error(f"[SSE HITL] queue put failed: {e}")

    # Register listener with the global event bus
    error_event_bus.register_listener("*", _on_event)

    yield f"event: connected\ndata: {json.dumps({'user_id': user_id})}\n\n"

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                payload = {
                    "type": "HITL_REVIEW_REQUIRED",
                    "message": getattr(event, "message", str(event)),
                    "context": getattr(event, "context", None),
                    "severity": getattr(event, "severity", "info"),
                    "module": getattr(event, "module", None),
                }
                yield f"event: hitl\ndata: {json.dumps(payload, default=str)}\n\n"
            except TimeoutError:
                yield ": ping\n\n"
    except asyncio.CancelledError:
        logger.info(f"[SSE] HITL stream cancelled for {user_id}")
        raise
    finally:
        # Best-effort cleanup — event bus may not have an unregister method
        try:
            if hasattr(error_event_bus, "unregister_listener"):
                error_event_bus.unregister_listener("*", _on_event)
        except Exception as e:
            logger.debug(f"[SSE HITL] unregister failed: {e}")


@router.get("/hitl")
async def stream_hitl_sse(user: dict = Depends(get_current_user_token)):
    """SSE replacement for ``ws://.../ws/hitl`` (HITL approval events).

    Returns events of type ``HITL_REVIEW_REQUIRED`` from the global
    ``error_event_bus`` — same source as the existing WebSocket route.
    """
    user_id = str(user.get("user_id") or user.get("sub") or "")
    tenant_id = user.get("tenant_id") or user.get("org_id")
    if not user_id or not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return StreamingResponse(
        _hitl_event_stream(user_id, str(tenant_id)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
