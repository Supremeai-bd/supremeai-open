import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from api.dependencies import get_current_user_token
from core.logging_config import logger
from core.messaging.pubsub import global_pubsub as theme_pubsub
from database.supabase_client import db

router = APIRouter(
    prefix="/preferences",
    tags=["preferences"],
    dependencies=[Depends(get_current_user_token)],
)


class PreferenceUpdate(BaseModel):
    theme: str | None = None
    default_model: str | None = None
    max_tokens: int | None = None
    auto_save: bool | None = None
    custom_shortcuts: dict | None = None
    verbosity: str | None = None
    preferred_frameworks: list[str] | None = None
    # ERR-H01 FIX (2026-09-16): extended preference surfaces the frontend
    # actually sends — I18nProvider → ``preferred_language``; ProfilePage →
    # ``profile`` / ``security`` / ``notifications``. Previously these were
    # not accepted at all (callers also hit 404s on wrong paths — fixed on
    # the frontend side in the same change), so locale/profile settings
    # could never persist.
    preferred_language: str | None = None
    profile: dict | None = None
    security: dict | None = None
    notifications: dict | None = None


# ERR-H01 FIX: physical columns that actually exist in ``user_preferences``
# (migration 03_user_preferences_and_metrics.sql). Everything else the model
# accepts is persisted inside the JSONB ``custom_shortcuts`` column under an
# "_extended" key — nothing silently dropped, no schema migration required.
# ``verbosity`` / ``preferred_frameworks`` were already accepted by the model
# but are NOT physical columns, so upserting them verbatim used to fail with
# an unknown-column error (latent 500) — they now flow through _extended too.
_DB_COLUMNS = frozenset({"theme", "default_model", "max_tokens", "auto_save", "custom_shortcuts"})
_EXTENDED_KEYS = frozenset(
    {
        "verbosity",
        "preferred_frameworks",
        "preferred_language",
        "profile",
        "security",
        "notifications",
    }
)


def _split_extended(data: dict) -> tuple[dict, dict]:
    """Split an update payload into (physical-column values, extended values)."""
    extended = {k: data.pop(k) for k in list(data) if k in _EXTENDED_KEYS}
    return data, extended


def _hoist_extended(row: dict) -> dict:
    """Return the row with ``_extended`` values hoisted back to top level."""
    shortcuts = row.get("custom_shortcuts")
    extended = shortcuts.get("_extended") if isinstance(shortcuts, dict) else None
    if isinstance(extended, dict) and extended:
        return {**row, **extended}
    return row


@router.get("/")
async def get_preferences(user_id: str = Query(default="default")):
    if not db.client:
        return {
            "user_id": user_id,
            "theme": "dark",
            "default_model": "gpt-4o",
            "max_tokens": 4096,
            "auto_save": True,
            "custom_shortcuts": {},
        }
    try:
        # Issue #1473 fix: supabase-py v2's client is SYNC — ``await ...execute()``
        # raised TypeError ("object APIResponse can't be used in 'await'") ->
        # GET /api/preferences/ always 500'd in production. Run the blocking
        # PostgREST chain in a worker thread (same pattern as issue #443 fix in
        # memory/long_term_memory.py and services/memory_service.py).
        res = await asyncio.to_thread(
            lambda: db.client.table("user_preferences").select("*").eq("user_id", user_id).execute()
        )
        # FIX (CI red 36219425476): when db.client is an ASYNC client (tests
        # stub it with AsyncMock), the chain above merely CREATES a coroutine
        # inside the worker thread — awaiting to_thread hands it back un-awaited
        # and `res.data` blows up with "'coroutine' object has no attribute
        # 'data'". Await it explicitly in that case; the sync client path is
        # unchanged.
        if asyncio.iscoroutine(res):
            res = await res
        rows = res.data or []
        if rows:
            # ERR-H01 FIX: hoist _extended prefs so callers read them back as
            # top-level keys (preferred_language, profile, security, …).
            return _hoist_extended(dict(rows[0]))
        return {
            "user_id": user_id,
            "theme": "dark",
            "default_model": "gpt-4o",
            "max_tokens": 4096,
            "auto_save": True,
            "custom_shortcuts": {},
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/")
async def upsert_preferences(payload: PreferenceUpdate, user_id: str = Query(default="default")):
    data = payload.dict(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # ADVANCED: Record preference change signal in AdaptiveEngine LearningLoop
    suggestions: list[dict] = []
    try:
        from adaptive_engine.intent_parser import IntentParser
        from adaptive_engine.learning_loop import LearningLoop

        loop = LearningLoop.get_instance()
        context = await IntentParser.extract_context(payload)
        await loop.record_signal(
            user_id=user_id,
            signal_type="preference_change",
            payload=data,
            context=context,
        )
        suggestions = await loop.suggest(user_id=user_id)
    except Exception as e:
        logger.warning(f"[Preferences] AdaptiveEngine signal recording skipped: {e}")

    if not db.client:
        # For offline/local mode, still broadcast the theme
        if payload.theme:
            await theme_pubsub.publish(user_id, {"theme": payload.theme})
        return {
            "status": "success",
            "preferences": data,
            "adaptive_suggestions": suggestions,
        }

    # ERR-H01 FIX: persist extended prefs inside the JSONB custom_shortcuts
    # column (only real physical columns may go to the top-level upsert).
    data, extended = _split_extended(data)
    if extended:
        shortcuts_base = dict(data.get("custom_shortcuts") or {})
        if "custom_shortcuts" not in data:
            try:
                cur = await asyncio.to_thread(
                    lambda: (
                        db.client.table("user_preferences")
                        .select("custom_shortcuts")
                        .eq("user_id", user_id)
                        .execute()
                    )
                )
                if asyncio.iscoroutine(cur):
                    cur = await cur
                cur_rows = cur.data or []
                if cur_rows and isinstance(cur_rows[0].get("custom_shortcuts"), dict):
                    shortcuts_base = dict(cur_rows[0]["custom_shortcuts"])
            except Exception as exc:  # noqa: BLE001 — read is best-effort; upsert must proceed
                logger.warning(f"[Preferences] could not read existing custom_shortcuts: {exc}")
        merged_ext = dict(shortcuts_base.get("_extended") or {})
        merged_ext.update(extended)
        shortcuts_base["_extended"] = merged_ext
        data["custom_shortcuts"] = shortcuts_base
    data["user_id"] = user_id
    try:
        # Issue #1473 fix: sync supabase client must not be awaited — offload
        # the upsert to a worker thread (see GET handler comment above).
        res = await asyncio.to_thread(
            lambda: db.client.table("user_preferences").upsert(data).execute()
        )
        # Same async-client guard as the GET handler (CI red 36219425476).
        if asyncio.iscoroutine(res):
            res = await res
        if payload.theme:
            await theme_pubsub.publish(user_id, {"theme": payload.theme})
        pref_res = res.data[0] if res.data else data
        return {
            "status": "success",
            "preferences": pref_res,
            "adaptive_suggestions": suggestions,
        }
    except Exception as exc:
        # AUD-2.9 follow-up (MANUAL_STEPS 7.4): generic 500 + correlation id —
        # raw exception text (DSN/SQL) must not reach clients.
        correlation_id = uuid.uuid4().hex[:12]
        logger.exception(f"preferences update failed correlation_id={correlation_id}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error (correlation_id: {correlation_id})",
        ) from exc


@router.get("/{user_id}/stream")
async def stream_preferences(
    request: Request, user_id: str, user: dict = Depends(get_current_user_token)
):
    """
    SSE endpoint to listen for real-time theme and preference updates for a specific user.

    AUD-2.5: previously any authenticated user could subscribe to another
    user's preference stream. The "default" pseudo-user remains public (it is
    the pre-login default theme channel); any other user_id must match the JWT sub.
    """
    sub = user.get("sub")
    if user_id != "default" and user_id != sub:
        raise HTTPException(
            status_code=403, detail="Forbidden: cannot stream another user's preferences"
        )

    async def event_generator():
        queue = await theme_pubsub.subscribe(user_id)
        try:
            # Yield connection success
            yield {
                "event": "connected",
                "data": json.dumps({"status": "connected to theme stream"}),
            }

            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for theme change or 15s heartbeat
                    item = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield {"event": "message", "data": json.dumps(item)}
                except TimeoutError:
                    # Heartbeat ping
                    yield {
                        "event": "ping",
                        "data": json.dumps({"channel": "heartbeat"}),
                    }
        finally:
            await theme_pubsub.unsubscribe(user_id, queue)

    return EventSourceResponse(event_generator())
