"""
backend/browser/browser_session.py
==================================
ISSUE-1571 (Part 2): Stateful ``BrowserSession`` — a durable handle over one
browser context/page so sequential actions (navigate → type → click → wait →
extract) execute across the SAME context using a stable ``session_id``,
instead of spinning up (and losing the state of) a fresh browser per call.

Lifecycle hooks: :meth:`BrowserSession.close`, :meth:`BrowserSession.reset`
and :meth:`BrowserSession.screenshot` — all safe against missing/async
browser surfaces, never raising on double-close.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from core.logging_config import logger

__all__ = [
    "BrowserSession",
    "SessionStatus",
    "SESSION_TTL_SECONDS",
    "IDLE_TIMEOUT_SECONDS",
]

# ISSUE-1571: hard TTL (15 min) and idle timeout (3 min) — enforced by the
# BrowserSessionManager cleanup daemon.
SESSION_TTL_SECONDS = 15 * 60
IDLE_TIMEOUT_SECONDS = 3 * 60


class SessionStatus(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"
    CLOSED = "closed"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _close_quietly(surface: Any, method: str) -> None:
    """Close a sync browser surface without ever raising (reset() helper)."""
    if surface is None or not hasattr(surface, method):
        return
    try:
        getattr(surface, method)()
    except Exception as exc:
        logger.debug(f"[BrowserSession] {method}() close suppressed: {exc}")


class BrowserSession:
    """One stateful browser context/page bound to a stable ``session_id``."""

    def __init__(
        self,
        session_id: str,
        provider: str = "chrome-dedicated",
        context: Any = None,
        page: Any = None,
        created_at: datetime | None = None,
        last_active_at: datetime | None = None,
        status: SessionStatus = SessionStatus.ACTIVE,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.session_id = session_id
        self.provider = provider
        self.context = context
        self.page = page
        self.created_at = created_at or _utcnow()
        self.last_active_at = last_active_at or self.created_at
        self.status = status
        self.metadata: dict[str, Any] = metadata or {}

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def touch(self, now: datetime | None = None) -> datetime:
        """Mark the session as used right now (resets the idle clock)."""
        self.last_active_at = now or _utcnow()
        if self.status is SessionStatus.IDLE:
            self.status = SessionStatus.ACTIVE
        return self.last_active_at

    @property
    def age_seconds(self) -> float:
        return (_utcnow() - self.created_at).total_seconds()

    @property
    def idle_seconds(self) -> float:
        return (_utcnow() - self.last_active_at).total_seconds()

    def is_expired(self, ttl_seconds: float = SESSION_TTL_SECONDS) -> bool:
        return self.age_seconds >= ttl_seconds

    def is_idle(self, idle_seconds: float = IDLE_TIMEOUT_SECONDS) -> bool:
        return self.idle_seconds >= idle_seconds

    @property
    def url(self) -> str | None:
        url = getattr(self.page, "url", None)
        return url if isinstance(url, str) and url else None

    # ------------------------------------------------------------------
    # Lifecycle hooks — close / reset / screenshot
    # ------------------------------------------------------------------
    async def close(self) -> None:
        """Close page + context (idempotent, async-friendly, never raises)."""
        if self.status is SessionStatus.CLOSED:
            return
        page, context = self.page, self.context
        for surface, method in ((page, "close"), (context, "close")):
            if surface is None or not hasattr(surface, method):
                continue
            try:
                result = getattr(surface, method)()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.debug(f"[BrowserSession] {method}() suppressed: {exc}")
        self.page = None
        self.context = None
        self.status = SessionStatus.CLOSED
        runtime = self.metadata.pop("playwright_runtime", None)
        if runtime is not None and hasattr(runtime, "stop"):
            try:
                runtime.stop()
            except Exception as exc:
                logger.debug(f"[BrowserSession] runtime stop suppressed: {exc}")
        logger.debug(f"[BrowserSession] session '{self.session_id}' closed cleanly")

    async def reset(self) -> None:
        """Reopen a fresh page on the same context; state cleared, session kept."""
        if self.status is SessionStatus.CLOSED:
            raise RuntimeError(f"session '{self.session_id}' is closed and cannot be reset")
        if self.page is not None and hasattr(self.page, "close"):
            _close_quietly(self.page, "close")
        new_page = None
        if self.context is not None and hasattr(self.context, "new_page"):
            result = self.context.new_page()
            if inspect.isawaitable(result):
                result = await result
            new_page = result
        self.page = new_page
        self.status = SessionStatus.ACTIVE
        self.touch()
        logger.debug(f"[BrowserSession] session '{self.session_id}' reset (fresh page bound)")

    async def screenshot(self, path: str | None = None) -> bytes | None:
        """Capture a screenshot of the bound page (sync/async pages)."""
        if self.page is None or not hasattr(self.page, "screenshot"):
            return None
        result = self.page.screenshot(path=path, full_page=False)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, bytes):
            return result
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"BrowserSession(id={self.session_id!r}, provider={self.provider!r}, "
            f"status={self.status.value}, idle={self.idle_seconds:.0f}s)"
        )
