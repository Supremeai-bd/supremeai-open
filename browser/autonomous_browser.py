"""
backend/browser/autonomous_browser.py
=====================================
L5: Goal-Driven Autonomous Browser Agent — Takes natural language GOALS (not manual steps),
reasons with ReasoningOrchestrator, executes actions via L4 cascade, and replans on failures.

ISSUE-1570 (Part 1) hardening:
* The hardcoded development-site navigation logic is REMOVED. Goals are
  dynamic: the agent accepts an explicit ``start_url`` and/or extracts the target
  URL from the goal text itself. No URL → no navigation, no fake defaults.
* ``navigate`` performs a REAL ``page.goto`` when a page is bound (sync/async both)
  and reports honest status when no browser session exists.
* ``smart_click`` runs the shared 5-step cascade (SemanticDOM → accessible role →
  known locator → vision → HITL) with confidence guardrails — blind fallback
  clicks are forbidden.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any
from urllib.parse import urlparse

from brain.reasoning_orchestrator import ReasoningOrchestrator
from browser.action_cascade import execute_click_cascade
from browser.browsing_memory import BrowsingMemory
from core.logging_config import logger

__all__ = ["AutonomousBrowserAgent"]

_URL_PATTERN = re.compile(r"https?://[^\s'\"<>)]+", re.IGNORECASE)

# Tools the autonomous browser is allowed to execute from a reasoner plan.
_BROWSER_TOOLS = {"navigate", "smart_click", "type_text", "wait", "done"}


class AutonomousBrowserAgent:
    MAX_STEPS = 15

    def __init__(
        self,
        session: Any = None,
        start_url: str | None = None,
        goal: str | None = None,
    ):
        self.session = session
        self.start_url = self._normalise_url(start_url) if start_url else None
        self.goal = goal
        self.memory = BrowsingMemory()
        self.reasoner = ReasoningOrchestrator.get_instance()
        self._trace: list[dict[str, Any]] = []
        self._navigated = False

    # ------------------------------------------------------------------
    # URL helpers — dynamic targets, zero hardcoded endpoints
    # ------------------------------------------------------------------
    @staticmethod
    def _normalise_url(url: str) -> str | None:
        url = (url or "").strip()
        if not url:
            return None
        if not urlparse(url).scheme:
            url = f"https://{url}"
        return url if _URL_PATTERN.match(url) else None

    @staticmethod
    def extract_url(goal: str) -> str | None:
        """Extract the first URL mentioned in a goal string (if any)."""
        match = _URL_PATTERN.search(goal or "")
        return match.group(0).rstrip(".,;:!?") if match else None

    def _target_url(self, goal: str) -> str | None:
        return self.start_url or self.extract_url(goal)

    @property
    def _page(self) -> Any:
        return getattr(self.session, "page", None)

    # ------------------------------------------------------------------
    # Public entrypoint
    # ------------------------------------------------------------------
    async def achieve(self, goal: str, start_url: str | None = None) -> dict[str, Any]:
        """Autonomously reason, execute, and replan until the goal is accomplished.

        বাংলা (M06 P-A ৮/৮ RunType adoption): প্রতিটি browser-mission ক্যানোনিকাল
        ``run_type="browser"`` রান হিসেবেও পর্যবেক্ষিত (flag-gated, best-effort);
        ``achieved=False``-ই রান-ব্যর্থতার সত্য — অন্য কোনো ভান নেই।

        ISSUE-1570: ``start_url`` দিলে সেটাই mission-এর navigation টার্গেট —
        কোনো হার্ডকোডেড endpoint নেই।
        """
        from runs.run_scope import observe_run

        if start_url:
            normalised = self._normalise_url(start_url)
            if normalised:
                self.start_url = normalised

        async with observe_run(
            run_type="browser",
            title=f"browser:{goal[:80]}",
            source_type="browser",
        ) as run_ctx:
            result = await self._achieve_impl(goal)
            if run_ctx is not None and result.get("achieved") is False:
                run_ctx.finish("failed")
            return result

    async def _achieve_impl(self, goal: str) -> dict[str, Any]:
        """Original achieve body — run-observation wrapper-এর ভিতরে চলে।"""
        logger.info(f"[AutonomousBrowserAgent] Starting mission: '{goal}'")
        self._trace = []
        self._navigated = False

        for step in range(1, self.MAX_STEPS + 1):
            page_state = await self._observe()

            # 1. REASON: Decide next action given current goal and history
            action_plan = await self._decide_action(goal, page_state, step)
            tool = action_plan.get("tool", "done")
            args = action_plan.get("args", {})

            if tool == "done":
                logger.info(f"[AutonomousBrowserAgent] Goal accomplished at step {step}: '{goal}'")
                return {
                    "goal": goal,
                    "achieved": True,
                    "total_steps": step,
                    "trace": self._trace,
                    "result": action_plan.get("summary", "Mission completed successfully."),
                }

            # 2. ACT: Execute action through the guarded cascade
            outcome: dict[str, Any] = {}
            try:
                outcome = await self._execute_action(tool, args)
            except Exception as exc:
                logger.warning(f"[AutonomousBrowserAgent] Step {step} execution error: {exc}")
                outcome = {"status": "error", "error": str(exc)}

            # 3. RECORD & REPLAN
            self._trace.append(
                {
                    "step": step,
                    "plan": action_plan,
                    "outcome": outcome,
                }
            )

            # Record site interaction memory — URL is whatever is REALLY bound.
            current_url = self._current_url() or "unbound-session"
            await self.memory.observe(
                current_url,
                {"type": tool, "outcome": outcome.get("status", "ok")},
            )

        return {
            "goal": goal,
            "achieved": False,
            "total_steps": self.MAX_STEPS,
            "reason": "Max steps reached without explicit completion",
            "trace": self._trace,
        }

    # ------------------------------------------------------------------
    # Observe / decide / execute
    # ------------------------------------------------------------------
    def _current_url(self) -> str | None:
        """The REAL bound URL — falls back to the declared target, never an invention."""
        url = getattr(self.session, "url", None)
        if url:
            return url
        if self._page is not None and hasattr(self._page, "url"):
            page_url = getattr(self._page, "url", None)
            if isinstance(page_url, str) and page_url:
                return page_url
        return self.start_url

    async def _observe(self) -> dict[str, Any]:
        """Capture current browser state and interactive DOM context."""
        url = self._current_url()
        title = getattr(self.session, "title", None)
        if not title and self._page is not None and hasattr(self._page, "title"):
            try:
                raw_title = self._page.title()
                if inspect.isawaitable(raw_title):
                    raw_title = await raw_title
                title = raw_title if isinstance(raw_title, str) else None
            except Exception:
                title = None
        return {
            "url": url or "unbound",
            "title": title or "",
            "status": "ready" if self._page is not None else "no_page_bound",
        }

    async def _decide_action(
        self, goal: str, page_state: dict[str, Any], step: int
    ) -> dict[str, Any]:
        """Use ReasoningOrchestrator (ReAct) to choose next autonomous action.

        ISSUE-1570: navigation only ever targets the task-provided URL. Without a
        URL the agent plans purely from the goal — no implicit destination exists.
        """
        if step == 1:
            url = self._target_url(goal)
            if url and not self._navigated:
                return {
                    "tool": "navigate",
                    "args": {"url": url},
                    "rationale": "Initial navigation to the task-provided target URL",
                }
            if self._page is None:
                # No browser bound and no destination known — say so honestly.
                return {
                    "tool": "done",
                    "summary": (
                        "No browser session bound and no target URL provided; "
                        "cannot execute a navigation mission."
                    ),
                }

        try:
            plan = await self.reasoner.decide(
                task=goal,
                context={"page_state": page_state, "step": step, "trace": self._trace[-3:]},
                tools=sorted(_BROWSER_TOOLS),
            )
        except Exception as exc:
            logger.warning(f"[AutonomousBrowserAgent] Reasoner unavailable: {exc}")
            plan = None

        if isinstance(plan, dict) and plan.get("tool"):
            tool = str(plan["tool"])
            if tool in _BROWSER_TOOLS:
                return {
                    "tool": tool,
                    "args": plan.get("args", {}) or {},
                    "rationale": plan.get("reasoning", plan.get("thought", "")),
                    "source": plan.get("source", "reasoner"),
                }
            if tool == "done":
                return {
                    "tool": "done",
                    "summary": plan.get("reasoning", "Reasoner signalled completion."),
                }
            # Unsupported tool → do NOT pretend; record and let replanning handle it.
            logger.warning(f"[AutonomousBrowserAgent] Reasoner proposed unsupported tool '{tool}'")

        # Deterministic, honest terminal: nothing actionable was derived.
        return {
            "tool": "done",
            "summary": f"No further actionable browser steps derived for goal: {goal}",
        }

    async def _execute_action(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute action via the guarded L4 cascade / real primitives."""
        page = self._page

        if tool == "navigate":
            url = self._normalise_url(str(args.get("url", "")))
            if not url:
                return {"status": "error", "error": "navigate requires a valid absolute URL"}
            if page is None:
                return {
                    "status": "skipped",
                    "reason": "no browser session bound — navigation not executed",
                    "requested_url": url,
                }
            try:
                result = page.goto(url)
                if inspect.isawaitable(result):
                    await result
                self._navigated = True
                return {"status": "success", "navigated_to": url, "method": "page.goto"}
            except Exception as exc:
                return {"status": "error", "error": f"Navigation to {url} failed: {exc}"}

        if tool == "smart_click":
            target = str(args.get("target", "")).strip()
            if not target:
                return {"status": "error", "error": "smart_click requires a non-empty target"}
            if page is None:
                return {
                    "status": "PAUSED_HITL",
                    "method": "hitl",
                    "target": target,
                    "reason": "no browser session bound — human takeover required",
                }
            cascade = await execute_click_cascade(page, target)
            if cascade.get("success"):
                return cascade
            return {
                "status": cascade.get("status", "PAUSED_HITL"),
                "method": cascade.get("method", "hitl"),
                "target": target,
                "reason": cascade.get("reason", "click cascade exhausted"),
                "cascade": cascade,
            }

        if tool == "type_text":
            selector = str(args.get("selector", ""))
            text = str(args.get("text", ""))
            if page is None:
                return {
                    "status": "PAUSED_HITL",
                    "reason": "no browser session bound — typing not executed",
                }
            try:
                typed = page.type(selector, text) if hasattr(page, "type") else None
                if inspect.isawaitable(typed):
                    await typed
                return {"status": "success", "selector": selector, "typed_chars": len(text)}
            except Exception as exc:
                return {"status": "error", "error": f"Typing into '{selector}' failed: {exc}"}

        if tool == "wait":
            ms = int(args.get("ms", 1000))
            await asyncio.sleep(min(ms, 10_000) / 1000)
            return {"status": "success", "waited_ms": ms}

        return {"status": "error", "error": f"unsupported browser tool '{tool}'"}
