"""Bounded, owner-scoped Playwright browser sessions.

The manager deliberately owns browser contexts rather than pages globally. A
context is isolated per session and is closed on explicit release or expiry.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

from core.effective_policy import get_effective_policy
from core.logging_config import logger
from core.playwright_manager import get_global_browser


@dataclass
class BrowserSession:
    id: str
    owner_id: str
    context: Any
    page: Any
    created_at: float
    last_used_at: float
    label: str = "Browser session"
    saved_url: str | None = None
    # #2252 (MODULE_04 P-A): click/fill/type handlers exist in _automation.py
    # but were missing from the allowlist → every interactive action
    # returned 403. Frontend + API routes advertise these actions.
    allowed_actions: tuple[str, ...] = (
        "navigate",
        "screenshot",
        "content",
        "extract",
        "click",
        "fill",
        "type",
    )


class BrowserSessionManager:
    def __init__(
        self, max_sessions: int | None = None, idle_timeout_seconds: int | None = None
    ) -> None:
        policy = get_effective_policy()
        self.max_sessions = max_sessions or policy.limits["max_sessions"]
        self.idle_timeout_seconds = idle_timeout_seconds or policy.limits["idle_timeout_seconds"]
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()
        self._slots = asyncio.Semaphore(self.max_sessions)
        self._paused_owners: set[str] = set()

    async def create(
        self, owner_id: str, label: str = "Browser session", saved_url: str | None = None
    ) -> BrowserSession:
        if not owner_id:
            raise ValueError("owner_id is required")
        if owner_id in self._paused_owners:
            raise PermissionError("Browser automation is paused for this owner")
        await self._cleanup_expired()
        await self._slots.acquire()
        try:
            browser = await get_global_browser()
            context = await browser.new_context(viewport={"width": 1280, "height": 800})
            page = await context.new_page()
            session = BrowserSession(
                id=f"bs_{uuid.uuid4().hex}",
                owner_id=owner_id,
                context=context,
                page=page,
                created_at=time.time(),
                last_used_at=time.time(),
                label=label[:120] or "Browser session",
                saved_url=saved_url,
            )
            async with self._lock:
                self._sessions[session.id] = session
            return session
        except Exception:
            self._slots.release()
            raise

    def pause_owner(self, owner_id: str) -> None:
        self._paused_owners.add(owner_id)

    def resume_owner(self, owner_id: str) -> None:
        self._paused_owners.discard(owner_id)

    def is_paused(self, owner_id: str) -> bool:
        return owner_id in self._paused_owners

    async def get(self, session_id: str, owner_id: str) -> BrowserSession:
        if self.is_paused(owner_id):
            raise PermissionError("Browser automation is paused for this owner")
        async with self._lock:
            session = self._sessions.get(session_id)
        if session is None or session.owner_id != owner_id:
            raise KeyError("Browser session not found")
        if time.time() - session.last_used_at > self.idle_timeout_seconds:
            await self.close(session_id, owner_id)
            raise KeyError("Browser session expired")
        session.last_used_at = time.time()
        return session

    async def get_for_admin(self, session_id: str) -> BrowserSession:
        """Privileged lookup for HITL takeover (admin side-channel).

        Deliberately bypasses the owner check: the caller must have already
        authenticated via the takeover-token flow (verify_takeover_token in
        api/routes/session_takeover.py), and the taking-over admin is by
        definition NOT the session's original owner. Refreshes last_used_at
        so a live takeover cannot be reaped by the idle-expiry sweeper
        mid-stream. (#2253 — replaces the dead get_or_create_session call)
        """
        async with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise KeyError("Browser session not found")
        session.last_used_at = time.time()
        return session

    async def close(self, session_id: str, owner_id: str) -> bool:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.owner_id != owner_id:
                return False
            self._sessions.pop(session_id, None)
        try:
            await session.context.close()
        except Exception as exc:
            logger.warning("Browser context close failed for %s: %s", session_id, exc)
        finally:
            self._slots.release()
        return True

    async def _cleanup_expired(self) -> None:
        now = time.time()
        async with self._lock:
            expired = [
                session
                for session in self._sessions.values()
                if now - session.last_used_at > self.idle_timeout_seconds
            ]
        for session in expired:
            await self.close(session.id, session.owner_id)

    async def shutdown(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            try:
                await session.context.close()
            except Exception as exc:
                logger.warning("Browser context shutdown failed for %s: %s", session.id, exc)
            finally:
                self._slots.release()

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "id": session.id,
                "owner_id": session.owner_id,
                "url": session.page.url,
                "label": session.label,
                "saved_url": session.saved_url,
                "allowed_actions": list(session.allowed_actions),
                "created_at": session.created_at,
                "last_used_at": session.last_used_at,
            }
            for session in self._sessions.values()
        ]


session_manager = BrowserSessionManager()


async def shutdown_browser_sessions() -> None:
    await session_manager.shutdown()


__all__ = [
    "BrowserSession",
    "BrowserSessionManager",
    "session_manager",
    "shutdown_browser_sessions",
]


# বাংলা মন্তব্য: সেশন সীমা environment দিয়ে সামঞ্জস্য করা যায়, কিন্তু নিরাপদ default বজায় থাকে।


def configure_session_manager(max_sessions: int, idle_timeout_seconds: int) -> None:
    if max_sessions < 1 or idle_timeout_seconds < 1:
        raise ValueError("Browser session limits must be positive")
    session_manager.max_sessions = max_sessions
    session_manager.idle_timeout_seconds = idle_timeout_seconds
    session_manager._slots = asyncio.Semaphore(max_sessions)


__all__.append("configure_session_manager")
