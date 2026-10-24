"""SSE bridge for the swarm event stream (issue #446).

The frontend EvolutionForge DebateOverlay has called ``GET /api/v1/swarm/stream``
since its introduction, but the route never existed in the live router (the
Phase-1 Router Consolidation deleted ``api.routes.swarm``), so live debate
telemetry was permanently dead.  This module re-exposes the REAL Redis-backed
SwarmPubSub channel as Server-Sent Events — no simulation, exactly the
``{"type": "DEBATE_UPDATE", ...}`` payloads engine/debate_engine.py broadcasts.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from api.deps import get_current_user_token
from core.swarm_pubsub import get_swarm_streamer

# Issue #1652: the deprecated unauthenticated /execute-healing surface is
# gone; the remaining stream endpoint is middleware-gated, and the explicit
# router-level dependency keeps it that way regardless of allowlist changes.
router = APIRouter(
    prefix="/api/v1/swarm",
    tags=["swarm"],
    dependencies=[Depends(get_current_user_token)],
)

_PING_INTERVAL_SECONDS = 15.0


@router.get("/stream")
async def swarm_stream() -> StreamingResponse:
    """Stream live swarm events as SSE.

    Events are the raw SwarmPubSub channel contents (multi-worker safe).
    Periodic ``: ping`` SSE comments keep proxies from idling the connection
    out; clients that parse only ``data:`` lines (the established frontend
    contract) ignore them by construction.
    """

    async def event_gen():
        streamer = get_swarm_streamer()
        source = streamer.subscribe()
        try:
            while True:
                try:
                    raw = await asyncio.wait_for(source.__anext__(), timeout=_PING_INTERVAL_SECONDS)
                    yield f"data: {raw}\n\n"
                except TimeoutError:
                    yield ": ping\n\n"
                except StopAsyncIteration:
                    break
        except asyncio.CancelledError:
            raise
        finally:
            await source.aclose()

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
