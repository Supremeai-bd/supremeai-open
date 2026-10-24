import asyncio
import json

from fastapi import APIRouter, Path, Request
from sse_starlette.sse import EventSourceResponse

from core.logging_config import logger
from core.observability.log_batcher import batcher

router = APIRouter()


@router.get("/session/{session_id}/stream")
async def stream_session(
    request: Request,
    session_id: str = Path(..., title="The ID of the session to stream"),
):
    """
    SSE endpoint for multiplexed session logs, state changes, and filetree diffs.
    Heartbeat every 15 seconds.
    """

    async def event_generator():
        queue = batcher.subscribe(session_id)
        try:
            # Send initial state or connection confirmed
            yield {
                "event": "connected",
                "data": json.dumps({"channel": "system", "data": "connected to stream"}),
            }

            while True:
                if await request.is_disconnected():
                    break

                try:
                    # Wait for log event or 15s heartbeat timeout
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)

                    # Decide channel based on item schema
                    channel = "logs"
                    if item.get("log_type") == "state_change":
                        channel = "state"
                    elif item.get("log_type") == "reasoning_step":
                        # বাংলা: Phase 1 — এজেন্টের চিন্তা-প্রক্রিয়া এখন session SSE-তে
                        # দৃশ্যমান (ReasoningLog.tsx সত্যিকারের ডেটা পায়)
                        channel = "reasoning"
                    elif item.get("log_type") in ("file_write", "file_delete"):
                        channel = "filetree"

                    yield {
                        "event": "message",
                        "data": json.dumps({"channel": channel, "data": item}),
                    }
                except TimeoutError:
                    # Heartbeat
                    yield {
                        "event": "ping",
                        "data": json.dumps({"channel": "heartbeat"}),
                    }
        finally:
            batcher.unsubscribe(session_id, queue)
            # Keep the task alive and surface failures through the shared tracker.
            from core.utils.background_tasks import track_task

            track_task(asyncio.create_task(auto_save_session_memory(session_id)))

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Session Message Buffer & Auto-Save Vector Memory Hook
# ---------------------------------------------------------------------------

_session_message_buffers: dict[str, list[dict[str, str]]] = {}

# Audit B-11 fix (2026-09-17): per-session buffers were capped at 50 msgs but
# the SESSION KEYS themselves grew without limit unless the client POSTed the
# save endpoint. Bounded now — oldest untouched session buffers are evicted.
_MAX_SESSION_BUFFERS = 500


def buffer_session_message(session_id: str, role: str, content: str) -> None:
    """Accumulate messages for a session (kept in memory, cleared on save)."""
    if session_id not in _session_message_buffers:
        _session_message_buffers[session_id] = []
        while len(_session_message_buffers) > _MAX_SESSION_BUFFERS:
            oldest_session = next(iter(_session_message_buffers))
            _session_message_buffers.pop(oldest_session, None)
    _session_message_buffers[session_id].append({"role": role, "content": content})
    if len(_session_message_buffers[session_id]) > 50:
        _session_message_buffers[session_id] = _session_message_buffers[session_id][-50:]


async def auto_save_session_memory(
    session_id: str,
    task_type: str = "general",
    max_retries: int = 2,
) -> None:
    """Call this when a session ends (e.g. client disconnects).

    Summarizes the buffered messages and saves to ai_memory vector table
    with exponential backoff retries if network/database blips occur.
    """
    messages = _session_message_buffers.pop(session_id, [])
    if not messages:
        return

    from services.memory_service import summarize_and_save_session

    backoff = 1.0
    for attempt in range(max_retries + 1):
        try:
            result = await summarize_and_save_session(
                session_id=session_id,
                messages=messages,
                task_type=task_type,
            )
            if result.get("success"):
                logger.info(f"Auto-saved session memory: {session_id} (attempt {attempt + 1})")
                return
            logger.warning(
                f"Auto-save session memory notice (attempt {attempt + 1}): {result.get('error')}"
            )
            if attempt < max_retries:
                await asyncio.sleep(backoff)
                backoff *= 2.0
        except Exception:
            logger.exception(
                f"Auto-save session memory error for {session_id} (attempt {attempt + 1}/{max_retries + 1})"
            )
            if attempt < max_retries:
                await asyncio.sleep(backoff)
                backoff *= 2.0
