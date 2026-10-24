"""Firestore-style in-app session store endpoints (VaultPage sync API).

Split out of the former single-module api/routes/browser.py verbatim.

Issue #451: sessions now write through to the durable state store
(Redis federation + in-process mirror) — a deploy/restart no longer
silently erases user session history. Reads are served from the mirror
(zero billable Redis ops); mutations cost 1 op each.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel

from api.routes.browser import router
from core.state_store import durable_state

# ──────────────────────────────────────────────
# বাংলা মন্তব্য: সেশন স্টোর — Firestore-ভিত্তিক সেশন সিঙ্ক (VaultPage-এর মত ব্যাকএন্ড API কল)
# ──────────────────────────────────────────────
_state = durable_state("browser_sessions")
# Module-level alias kept for backwards compatibility with tests/imports;
# it is now a live view over the durable mirror.
SESSIONS: dict[str, dict[str, Any]] = {}


def _rkey(session_id: str) -> str:
    """Hash the id for the Redis key — ids may contain ':' or whitespace."""
    return hashlib.sha1(session_id.encode()).hexdigest()[:16]


def _hydrate_sessions() -> None:
    """Pull durable records into the local view (best-effort, boot/first-use)."""
    if SESSIONS:
        return
    try:
        for data in _state.mirror_items().values():
            sid = data.get("__id__")
            if sid:
                record = {k: v for k, v in data.items() if k != "__id__"}
                SESSIONS[sid] = record
    except Exception as hydrate_err:
        from core.logging_config import logger

        logger.warning("browser session store hydrate failed (mirror-only): %s", hydrate_err)


class SessionMessageIn(BaseModel):
    id: int
    sender: str
    text: str
    timestamp: str


class SessionIn(BaseModel):
    id: str
    title: str
    status: str = "running"
    created_at: str = ""
    updated_at: str = ""
    messages: list[SessionMessageIn] = []


@router.get("/sessions")
def list_sessions():
    """বাংলা মন্তব্য: সব সেশন তালিকা রিটার্ন করে"""
    _hydrate_sessions()
    return {"sessions": list(SESSIONS.values())}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    """বাংলা মন্তব্য: নির্দিষ্ট সেশন রিটার্ন করে"""
    _hydrate_sessions()
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    return SESSIONS[session_id]


@router.post("/sessions")
def create_session(session: SessionIn):
    """বাংলা মন্তব্য: নতুন সেশন তৈরি করে"""
    now = datetime.now(UTC).isoformat()
    data = session.model_dump()
    if not data.get("created_at"):
        data["created_at"] = now
    if not data.get("updated_at"):
        data["updated_at"] = now
    SESSIONS[session.id] = data
    _state.set(_rkey(session.id), {**data, "__id__": session.id})
    return {"success": True, "session": data}


@router.put("/sessions/{session_id}")
def update_session(session_id: str, session: SessionIn):
    """বাংলা মন্তব্য: বিদ্যমান সেশন আপডেট করে"""
    _hydrate_sessions()
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
    data = session.model_dump()
    data["updated_at"] = datetime.now(UTC).isoformat()
    SESSIONS[session_id] = data
    _state.set(_rkey(session_id), {**data, "__id__": session_id})
    return {"success": True, "session": data}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    """বাংলা মন্তব্য: সেশন মুছে ফেলে"""
    SESSIONS.pop(session_id, None)
    _state.delete(_rkey(session_id))
    return {"success": True}
