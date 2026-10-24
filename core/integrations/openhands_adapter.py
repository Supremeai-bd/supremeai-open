"""OpenHands-inspired autonomous coding-agent adapter for SupremeAI.
STATUS: orphaned — see docs/operations/MODULE_STATUS_REGISTRY.md (#449).

OpenHands (AI software-engineering agent) থেকে নেওয়া মূল ধারণা: একটি টাস্ক দিলে
এজেন্ট নিজে codebase-এ কোড পড়ে/লিখে/টেস্ট চালিয়ে decoupled Agent Server-এ কাজ করে।
SupremeAI থিন-ক্লায়েন্ট নীতি অনুযায়ী এক্সটেনশন ভারী কিছু embedded করে না — বরং
backend এই adapter-এর মাধ্যমে OpenHands **agent-server REST API**-কে রিমোট control করে।

এখানে কোনো ভারী dependency নেই (শুধু `requests`, যা project-এ already আছে)। flag +
server URL না থাকলে graceful fallback ("skipped + planner") → এজেন্ট কাজের বদলে
অকপট নোটসহ normal chat-এ রুট হয়, crash হয় না।

কনফিগারেশন (env):
- SUPREMEAI_OPENHANDS_ENABLED=true
- OPENHANDS_SERVER_URL=http://localhost:8000   # agent-server base (REST) # is_local()
"""

from __future__ import annotations

import os
from typing import Any

from core.logging_config import logger
from integrations._flags import flag

_ENABLED_FLAG = "SUPREMEAI_OPENHANDS_ENABLED"


class OpenHandsAdapter:
    """Autonomous coding agent bridging an OpenHands agent-server with a safe fallback."""

    def __init__(self, server_url: str | None = None, timeout: float = 60.0) -> None:
        self.enabled_flag = _ENABLED_FLAG
        self.server_url = server_url or os.getenv("OPENHANDS_SERVER_URL", "").strip()
        self.timeout = timeout
        self._http = None
        self._active = False
        if flag(_ENABLED_FLAG) and self.server_url:
            try:
                import httpx as _req

                self._http = _req
                self._active = True
                logger.info(f"OpenHandsAdapter: connected to agent-server at {self.server_url}")
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"OpenHandsAdapter: httpx unavailable: {exc}")
        else:
            logger.info(
                "OpenHandsAdapter: inactive (flag=%s, server_url=%s) — autonomous coding "
                "skips to fallback.",
                flag(_ENABLED_FLAG),
                bool(self.server_url),
            )

    @property
    def active(self) -> bool:
        return self._active

    def _base(self) -> str:
        return self.server_url.rstrip("/")

    def _create_session(self, workspace: str | None) -> str:
        resp = self._http.post(  # type: ignore[union-attr]
            f"{self._base()}/api/sessions",
            json={"headless": True, "codebase": workspace or "", "selected_agent": "CodeActAgent"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        sid = resp.json().get("id")
        if not sid:
            raise RuntimeError("agent-server did not return a session id")
        return str(sid)

    def _send_message(self, session_id: str, task: str) -> None:
        resp = self._http.post(  # type: ignore[union-attr]
            f"{self._base()}/api/sessions/{session_id}/actions",
            json={"action": "message", "args": {"content": task}},
            timeout=self.timeout,
        )
        resp.raise_for_status()

    def _collect(self, session_id: str, max_steps: int) -> str:
        """Poll events until a terminal/observation with content arrives (bounded)."""
        last: list[str] = []
        for _ in range(max_steps):
            resp = self._http.get(  # type: ignore[union-attr]
                f"{self._base()}/api/sessions/{session_id}/events",
                timeout=self.timeout,
            )
            resp.raise_for_status()
            events = resp.json() if isinstance(resp.json(), list) else []
            for ev in events:
                text = self._extract_text(ev)
                if text:
                    last.append(text)
            if any(self._is_terminal(ev) for ev in events):
                break
        return " ".join(last[-5:]) if last else ""

    @staticmethod
    def _extract_text(ev: Any) -> str:
        msg = ev.get("message") or {}
        args = msg.get("args") or {}
        content = args.get("content")
        return content if isinstance(content, str) else ""

    @staticmethod
    def _is_terminal(ev: Any) -> bool:
        msg = ev.get("message") or {}
        return str(msg.get("event", "")).lower() in {"done", "error"}

    def run_coding_task(
        self, task: str, workspace: str | None = None, max_steps: int = 50
    ) -> dict[str, Any]:
        """Ask the autonomous coding agent to complete a coding task."""
        if not self._active:
            return {
                "status": "skipped",
                "engine": "fallback",
                "result": {
                    "task": task,
                    "plan": [
                        "Open autonomous coding server is disabled or unreachable.",
                        "Task routed to regular SupremeAI chat/coding path.",
                    ],
                },
                "note": "Set SUPREMEAI_OPENHANDS_ENABLED=true and OPENHANDS_SERVER_URL to activate.",
            }
        try:
            sid = self._create_session(workspace)
            self._send_message(sid, task)
            output = self._collect(sid, max_steps)
            return {"status": "ok", "engine": "upstream", "session_id": sid, "result": output}
        except Exception as exc:
            logger.error(f"OpenHandsAdapter: run_coding_task failed: {exc}")
            return {"status": "error", "engine": "upstream", "error": str(exc)}
