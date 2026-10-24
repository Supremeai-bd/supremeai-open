"""
backend/external_agents/channels/browser_channel.py
===================================================
ISSUE-1574 (Part 5): the policy-checked Browser Channel fallback — for
providers WITHOUT native MCP (ChatGPT, Gemini, Lovable, Bolt) work is
delivered through a real browser session driven by
``AutonomousBrowserAgent`` + ``BrowserSessionManager`` (#1570/#1571).

Every dispatch passes the Policy Engine first: BLOCKED/HITL verdicts abort
BEFORE any browser session is acquired.
"""

from __future__ import annotations

from typing import Any

from browser.session_manager import BrowserSessionManager
from core.logging_config import logger
from external_agents.contracts.task_contract import TaskContract
from external_agents.control.policy_engine import PolicyDecision, PolicyEngine
from external_agents.providers.registry import ExecutionMode, ProviderRegistry

__all__ = ["BrowserChannel"]


class BrowserChannel:
    """Policy-gated browser delivery for non-MCP providers."""

    def __init__(
        self,
        registry: ProviderRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        session_manager: BrowserSessionManager | None = None,
    ) -> None:
        self.registry = registry or ProviderRegistry()
        self.policy_engine = policy_engine or PolicyEngine(self.registry)
        # `or` লিখলে ভুল: খালি (0-session) manager falsy (__len__ আছে)।
        self.session_manager = (
            session_manager if session_manager is not None else BrowserSessionManager()
        )

    async def dispatch(
        self,
        task: TaskContract,
        instructions: str,
        provider: str = "chatgpt",
        session_id: str | None = None,
        agent_factory: Any = None,
    ) -> dict[str, Any]:
        """Deliver ``instructions`` through a stateful browser session.

        Returns an honest dict: ``{"ok": False, "status": "POLICY_BLOCKED"|"HITL_REQUIRED", ...}``
        when policy refuses, ``{"ok": True, ...}`` with the agent result otherwise.
        """
        verdict = self.policy_engine.evaluate(provider, ExecutionMode.BROWSER_CHANNEL, task)
        if verdict.decision is PolicyDecision.POLICY_BLOCKED:
            logger.warning(f"[BrowserChannel] dispatch blocked for {provider}: {verdict.reason}")
            return {
                "ok": False,
                "status": "POLICY_BLOCKED",
                "reason": verdict.reason,
                "provider": provider,
            }
        if verdict.decision is PolicyDecision.HITL_REQUIRED:
            return {
                "ok": False,
                "status": "HITL_REQUIRED",
                "reason": verdict.reason,
                "provider": provider,
            }

        # Late import avoids a circular import (browser <-> external_agents).
        from browser.autonomous_browser import AutonomousBrowserAgent

        factory = agent_factory or AutonomousBrowserAgent
        session_id = session_id or f"browser-channel-{provider}-{task.task_id}"
        session = self.session_manager.acquire(
            provider=f"browser-channel-{provider}", session_id=session_id
        )
        session.metadata.update(
            {"channel": "browser", "provider": provider, "task_id": task.task_id}
        )
        try:
            agent = factory(session=session, goal=instructions)
            result = await agent.achieve(instructions)
            return {
                "ok": bool(result.get("achieved")),
                "status": "completed" if result.get("achieved") else "not_achieved",
                "provider": provider,
                "session_id": session_id,
                "result": result,
            }
        finally:
            # No orphaned sessions — guaranteed release.
            await self.session_manager.release(session_id)
