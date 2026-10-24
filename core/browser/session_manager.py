"""
backend/browser/session_manager.py
==================================
ISSUE-1571 (Part 2): Stateful ``BrowserSessionManager``.

* Session pool indexed by a stable ``session_id`` — consecutive tool calls on
  the same id reuse the SAME context/page (state + cookies preserved).
* Cleanup daemon enforcing the hard TTL (15 min) and idle timeout (3 min):
  expired sessions are closed cleanly so no orphaned browser processes remain.
* Dedicated Chrome automation profile — ``--user-data-dir=C:/SupremeAI_Automation_Profile``
  (override with ``BROWSER_AUTOMATION_PROFILE_DIR``) with all surfaces bound to
  ``127.0.0.1``; the host's default browser profile is NEVER touched.
* Multi-Action Registry — a small executor registry (navigate / type / click /
  wait / extract) that runs sequential action plans against ONE bound page.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from browser.browser_session import (
    IDLE_TIMEOUT_SECONDS,
    SESSION_TTL_SECONDS,
    BrowserSession,
    SessionStatus,
)
from core.logging_config import logger

__all__ = [
    "BrowserSessionManager",
    "chrome_launch_args",
    "automation_profile_dir",
    "AUTOMATION_BIND_ADDRESS",
    "register_action",
    "run_action_sequence",
    "ACTION_REGISTRY",
]

# Chrome DevTools পোর্ট যেখানে BIND করে — loopback-only (listen address,
# connect-host নয়): ডিবাগ পোর্ট কখনোই বাইরের নেটওয়ার্কে expose হবে না।
AUTOMATION_BIND_ADDRESS = "127.0.0.1"


def automation_profile_dir() -> str:
    """ISSUE-1571: the dedicated automation profile (never the user's own)."""
    return os.getenv("BROWSER_AUTOMATION_PROFILE_DIR", "C:/SupremeAI_Automation_Profile")


def chrome_launch_args(profile_dir: str | None = None) -> list[str]:
    """Chrome flags enforcing the dedicated profile + 127.0.0.1 binding."""
    return [
        f"--user-data-dir={profile_dir or automation_profile_dir()}",
        f"--remote-debugging-address={AUTOMATION_BIND_ADDRESS}",
        "--remote-debugging-port=0",
        "--no-first-run",
        "--no-default-browser-check",
    ]


def _default_session_factory(provider: str, session_id: str) -> dict[str, Any]:
    """Production factory: Playwright persistent context on the dedicated profile.

    Kept lazy — heavy imports only happen when a REAL session is requested
    (unit tests inject their own factory/doubles).
    """
    from playwright.sync_api import sync_playwright

    runtime = sync_playwright().start()
    try:
        context = runtime.chromium.launch_persistent_context(
            user_data_dir=automation_profile_dir(),
            args=chrome_launch_args(),
            headless=True,
        )
        page = context.new_page()
    except Exception:
        with_suppress = getattr(runtime, "stop", None)
        if callable(with_suppress):
            try:
                with_suppress()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
        raise
    return {"context": context, "page": page, "playwright_runtime": runtime}


# ---------------------------------------------------------------------------
# Multi-Action Registry — sequential actions on ONE stateful page
# ---------------------------------------------------------------------------
ACTION_REGISTRY: dict[str, Callable[..., Any]] = {}


def register_action(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Register an action executor: ``executor(page, **args) -> dict``."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        ACTION_REGISTRY[name] = fn
        return fn

    return decorator


@register_action("navigate")
def _action_navigate(page: Any, url: str = "", **_: Any) -> dict[str, Any]:
    if not url:
        return {"action": "navigate", "status": "error", "error": "navigate requires a url"}
    page.goto(url)
    return {"action": "navigate", "status": "success", "url": url}


@register_action("type")
def _action_type(page: Any, selector: str = "", text: str = "", **_: Any) -> dict[str, Any]:
    if not selector:
        return {"action": "type", "status": "error", "error": "type requires a selector"}
    for char in text or "":
        page.type(selector, char)
    return {
        "action": "type",
        "status": "success",
        "selector": selector,
        "typed_chars": len(text or ""),
    }


@register_action("click")
async def _action_click(page: Any, target: str = "", **_: Any) -> dict[str, Any]:
    from browser.action_cascade import execute_click_cascade

    result = await execute_click_cascade(page, target)
    return {"action": "click", **result}


@register_action("wait")
async def _action_wait(page: Any, ms: int = 1000, **_: Any) -> dict[str, Any]:
    await asyncio.sleep(min(max(int(ms), 0), 10_000) / 1000)
    return {"action": "wait", "status": "success", "waited_ms": int(ms)}


@register_action("extract")
def _action_extract(page: Any, selector: str = "", **_: Any) -> dict[str, Any]:
    if not selector:
        return {"action": "extract", "status": "error", "error": "extract requires a selector"}
    text = page.text_content(selector) if hasattr(page, "text_content") else None
    return {"action": "extract", "status": "success", "selector": selector, "text": text or ""}


async def run_action_sequence(
    session: BrowserSession, actions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Execute a sequential action plan against the session's SINGLE bound page."""
    results: list[dict[str, Any]] = []
    if session.page is None:
        return [
            {"action": a.get("type", "?"), "status": "error", "error": "session has no bound page"}
            for a in actions
        ]
    for step in actions:
        name = str(step.get("type", "")).lower()
        executor = ACTION_REGISTRY.get(name)
        if executor is None:
            results.append({"action": name, "status": "error", "error": f"unknown action '{name}'"})
            continue
        args = {k: v for k, v in step.items() if k != "type"}
        try:
            outcome = executor(session.page, **args)
            if asyncio.iscoroutine(outcome) or asyncio.isfuture(outcome):
                outcome = await outcome
        except Exception as exc:
            outcome = {"status": "error", "error": str(exc)}
        outcome.setdefault("action", name)
        results.append(outcome)
        if outcome.get("status") == "error":
            break  # fail fast — the sequence is sequential by contract
    session.touch()
    return results


# ---------------------------------------------------------------------------
# BrowserSessionManager
# ---------------------------------------------------------------------------
class BrowserSessionManager:
    """Pool of stateful browser sessions with TTL/idle cleanup daemon."""

    def __init__(
        self,
        session_factory: Callable[[str, str], dict[str, Any]] | None = None,
        ttl_seconds: float = SESSION_TTL_SECONDS,
        idle_seconds: float = IDLE_TIMEOUT_SECONDS,
        sweep_interval: float = 30.0,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._sessions: dict[str, BrowserSession] = {}
        self._session_factory = session_factory or _default_session_factory
        self.ttl_seconds = ttl_seconds
        self.idle_seconds = idle_seconds
        self.sweep_interval = sweep_interval
        self.now_fn = now_fn or (lambda: datetime.now(UTC))
        self._sweeper_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Pool operations
    # ------------------------------------------------------------------
    def create_session(
        self, provider: str = "chrome-dedicated", session_id: str | None = None
    ) -> BrowserSession:
        session_id = session_id or f"bs-{provider}-{len(self._sessions) + 1:06d}"
        if (
            session_id in self._sessions
            and self._sessions[session_id].status is not SessionStatus.CLOSED
        ):
            return self._sessions[session_id]
        surfaces = self._session_factory(provider, session_id)
        session = BrowserSession(
            session_id=session_id,
            provider=provider,
            context=surfaces.get("context"),
            page=surfaces.get("page"),
            created_at=self.now_fn(),
            last_active_at=self.now_fn(),
            metadata={k: v for k, v in surfaces.items() if k not in ("context", "page")},
        )
        self._sessions[session_id] = session
        logger.info(f"[SessionManager] created session '{session_id}' (provider={provider})")
        return session

    def get_session(self, session_id: str, touch: bool = True) -> BrowserSession | None:
        session = self._sessions.get(session_id)
        if session is None or session.status is SessionStatus.CLOSED:
            return None
        if touch:
            session.touch(self.now_fn())
        return session

    def acquire(
        self, provider: str = "chrome-dedicated", session_id: str | None = None
    ) -> BrowserSession:
        """Stateful acquire: same id → same live session; else a new one."""
        if session_id:
            existing = self.get_session(session_id)
            if existing is not None:
                return existing
        return self.create_session(provider=provider, session_id=session_id)

    async def release(self, session_id: str) -> bool:
        """Close and forget a session — no orphaned browser processes left."""
        session = self._sessions.pop(session_id, None)
        if session is None:
            return False
        await session.close()
        return True

    # ------------------------------------------------------------------
    # Cleanup daemon — hard TTL + idle timeout
    # ------------------------------------------------------------------
    def sweep_expired(self) -> list[str]:
        """Close & drop TTL-expired or idle-expired sessions; return their ids."""
        now = self.now_fn()
        expired: list[str] = []
        for session_id, session in list(self._sessions.items()):
            if session.status is SessionStatus.CLOSED:
                expired.append(session_id)
                continue
            age = (now - session.created_at).total_seconds()
            idle = (now - session.last_active_at).total_seconds()
            if age >= self.ttl_seconds or idle >= self.idle_seconds:
                expired.append(session_id)
        removed: list[str] = []
        for session_id in expired:
            session = self._sessions.pop(session_id, None)
            if session is None:
                continue
            close_result = session.close()
            if asyncio.iscoroutine(close_result):
                # Drive async close to completion on a private loop (sync sweep).
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    asyncio.run(close_result)
                else:
                    asyncio.get_running_loop().create_task(close_result)
            removed.append(session_id)
        if removed:
            logger.info(f"[SessionManager] swept {len(removed)} expired session(s): {removed}")
        return removed

    async def sweep_expired_async(self) -> list[str]:
        now = self.now_fn()
        removed: list[str] = []
        for session_id, session in list(self._sessions.items()):
            age = (now - session.created_at).total_seconds()
            idle = (now - session.last_active_at).total_seconds()
            if (
                session.status is SessionStatus.CLOSED
                or age >= self.ttl_seconds
                or idle >= self.idle_seconds
            ):
                self._sessions.pop(session_id, None)
                await session.close()
                removed.append(session_id)
        return removed

    async def start_sweeper(self) -> None:
        if self._sweeper_task is not None and not self._sweeper_task.done():
            return
        self._sweeper_task = asyncio.create_task(self._sweeper_loop())
        logger.debug(f"[SessionManager] cleanup daemon started (interval={self.sweep_interval}s)")

    async def stop_sweeper(self) -> None:
        task = self._sweeper_task
        self._sweeper_task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        logger.debug("[SessionManager] cleanup daemon stopped")

    async def _sweeper_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self.sweep_interval)
                await self.sweep_expired_async()
        except asyncio.CancelledError:
            raise

    # ------------------------------------------------------------------
    def stats(self) -> dict[str, int]:
        statuses = [s.status for s in self._sessions.values()]
        return {
            "total": len(statuses),
            "active": sum(1 for s in statuses if s is SessionStatus.ACTIVE),
            "idle": sum(1 for s in statuses if s is SessionStatus.IDLE),
            "closed": sum(1 for s in statuses if s is SessionStatus.CLOSED),
        }

    def __len__(self) -> int:
        return len(self._sessions)
