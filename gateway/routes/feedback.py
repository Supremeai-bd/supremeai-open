from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.degraded_mode import sqlite_fallback_allowed
from core.feedback_loop import FeedbackLoop
from core.logging_config import logger


def _get_db_path() -> Path:
    base = Path("data")
    try:
        base.mkdir(parents=True, exist_ok=True)
        return base / "feedback.db"
    except PermissionError:
        fallback = Path(tempfile.gettempdir()) / "data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback / "feedback.db"


DB_PATH = _get_db_path()
_feedback_loop = FeedbackLoop()


def _ensure_db() -> None:
    global DB_PATH
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(
            f"Could not initialize feedback DB at {DB_PATH}: {e}. Falling back to tempdir."
        )
        fallback = Path(tempfile.gettempdir()) / "supremeai_feedback"
        try:
            fallback.mkdir(parents=True, exist_ok=True)
            DB_PATH = fallback / "feedback.db"
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        except Exception as fallback_exc:
            logger.error(f"Fallback feedback DB initialization failed: {fallback_exc}")
            return
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """)
        conn.commit()
    finally:
        conn.close()


def _persist_feedback(event_type: str, payload: dict[str, Any]) -> None:
    # P0 (Task 9-c2): only the SQLite persistence is gated. The in-memory
    # FeedbackLoop above keeps the route fully functional; when the SQLite
    # fallback is refused in production we skip persistence loudly (CRITICAL
    # logged once by core.degraded_mode) instead of crashing the route.
    if not sqlite_fallback_allowed("feedback_events"):
        logger.warning(
            "[P0] feedback event NOT persisted: SQLite fallback refused in "
            "production (in-memory handling only) — the degradation flag no longer "
            "permits SQLite fallback; provision a durable backend."
        )
        return
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.execute(
            "INSERT INTO feedback_events (event_type, payload, created_at) VALUES (?, ?, ?)",
            (event_type, json.dumps(payload), time.time()),
        )
        conn.commit()
        conn.close()
    except Exception as exc:
        logger.error(f"feedback persist failed: {exc}")


def _record_learning_feedback(event_type: str, payload: dict[str, Any]) -> None:
    """Sprint 4: persist a categorical feedback event to the durable learning store.

    Maps the route's event types onto the plan's feedback taxonomy
    (thumbs_up / thumbs_down / retry / regenerate / follow_up / correction).
    Privacy: only categorical data + identifiers are stored — payload text
    is never forwarded (LearningStore scrubs raw-content keys anyway).
    """
    try:
        from core.learning import record_feedback as _record_feedback

        allowed = {"thumbs_up", "thumbs_down", "retry", "regenerate", "follow_up", "correction"}
        feedback_type = event_type if event_type in allowed else "correction"
        _record_feedback(
            feedback_type,
            task_type=str(payload.get("task_type") or "general"),
            skill_id=str(payload.get("skill_id")) if payload.get("skill_id") else None,
            provider=str(payload.get("provider")) if payload.get("provider") else None,
            model=str(payload.get("model")) if payload.get("model") else None,
            session_id=str(payload.get("session_id")) if payload.get("session_id") else None,
            request_id=str(payload.get("request_id")) if payload.get("request_id") else None,
            weight=float(payload.get("weight", 1.0)),
            metadata={
                "source": "api_feedback_route",
                "original_event_type": event_type,
                "accepted": feedback_type == event_type,
            },
        )
    except Exception as exc:
        logger.debug(f"learning-store feedback record skipped: {exc}")


@asynccontextmanager
async def feedback_lifespan(router: APIRouter):
    # P0: skip SQLite schema creation entirely when the fallback is refused —
    # the route keeps working with in-memory handling only.
    if sqlite_fallback_allowed("feedback_events"):
        _ensure_db()
    yield


from api.dependencies import get_current_user_token

router = APIRouter(
    prefix="/api/feedback",
    tags=["feedback"],
    lifespan=feedback_lifespan,
    dependencies=[Depends(get_current_user_token)],
)


class FeedbackEvent(BaseModel):
    event_type: str
    payload: dict[str, Any] | None = None


class FeedbackResponse(BaseModel):
    success: bool
    event_id: int | None = None


@router.post("/ingest", response_model=FeedbackResponse)
async def ingest(event: FeedbackEvent) -> FeedbackResponse:
    try:
        payload = event.payload or {}
        handled = _feedback_loop.handle_feedback({"type": event.event_type, **payload})
        if handled.get("stored"):
            # Sprint 4 (learning loop): durable, privacy-safe feedback event into
            # the Postgres learning store (feedback_events). Categorical types map
            # 1:1; anything else degrades to 'correction'. Never raises.
            _record_learning_feedback(event.event_type, payload)
            _persist_feedback(event.event_type, payload)
            return FeedbackResponse(success=True)
        raise HTTPException(
            status_code=400, detail=handled.get("reason", "Unsupported feedback type")
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"feedback ingest failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
