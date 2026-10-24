"""
backend/external_agents/providers/zai.py
========================================
ISSUE-1574 (Part 5): the ZCode provider adapter — native MCP client interface
(stdio / HTTP / SSE transports abstracted behind :class:`ZcodeTransport`),
the Goal Mode protocol (/goal prompt injection + multi-round monitoring) and
durable per-round signal tracking in the state manager.

ZCode NEVER touches browser UI automation — its channel is native MCP
(enforced by the capability matrix in #1573).
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger
from external_agents.contracts.task_contract import TaskContract
from external_agents.control.state_manager import AgentStateManager

__all__ = [
    "GoalRoundResult",
    "GoalRunResult",
    "HttpMcpTransport",
    "StdioMcpTransport",
    "ZcodeTransport",
    "ZCodeProvider",
]

DEFAULT_MAX_ROUNDS = 8
GOAL_TOOL_NAME = "supremeai_goal_mode"


class ZcodeTransport(ABC):
    """Transport seam for talking to a ZCode agent over MCP."""

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...

    async def close(self) -> None:  # optional
        return None


class HttpMcpTransport(ZcodeTransport):
    """MCP over HTTP (Streamable-HTTP / SSE endpoints) with Bearer auth."""

    def __init__(
        self,
        base_url: str | None = None,
        bearer_token: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        # unguarded-localhost idiom: local-dev fallback only — production-এ
        # silent localhost default ভুল হোস্টে connect করাত; unset হলে
        # fail-closed (empty base → caller-এর কাছে স্পষ্ট error)।
        mcp_default = "http://127.0.0.1:8000" if settings.env == "local" else ""
        self.base_url = (
            base_url or os.getenv("ZCODE_MCP_URL", "") or os.getenv("MCP_URL", mcp_default)
        ).rstrip("/")
        self.bearer_token = bearer_token or os.getenv("ZCODE_MCP_TOKEN", "")
        self.timeout = timeout

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(f"{self.base_url}/mcp", json=payload, headers=headers)
            resp.raise_for_status()
            text = resp.text
            if text.startswith("data:"):  # SSE frame
                for line in text.splitlines():
                    if line.startswith("data:"):
                        text = line[len("data:") :].strip()
                        break
            data = json.loads(text)
        if data.get("error"):
            raise RuntimeError(f"ZCode MCP error: {data['error']}")
        return (data.get("result") or {}).get("content") or {}


class StdioMcpTransport(ZcodeTransport):
    """MCP over stdio — drives a local ZCode subprocess via JSON-RPC lines."""

    def __init__(self, command: list[str] | None = None) -> None:
        self.command = command or ["zcode", "mcp-serve"]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        import asyncio

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await proc.communicate(json.dumps(payload).encode() + b"\n")
        if proc.returncode != 0:
            raise RuntimeError(f"zcode stdio transport exited {proc.returncode}")
        data = json.loads(out.decode().strip().splitlines()[-1])
        if data.get("error"):
            raise RuntimeError(f"ZCode MCP error: {data['error']}")
        return (data.get("result") or {}).get("content") or {}

    async def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Goal Mode protocol
# ---------------------------------------------------------------------------
class GoalRoundResult(dict):
    """One monitored round: {round, signal, detail}."""


class GoalRunResult(dict):
    """Final outcome of a multi-round /goal execution."""


class ZCodeProvider:
    """Native-MCP adapter for the ZCode external agent (goal mode)."""

    name = "zcode"

    def __init__(
        self,
        transport: ZcodeTransport | None = None,
        state_manager: AgentStateManager | None = None,
        max_rounds: int = DEFAULT_MAX_ROUNDS,
    ) -> None:
        self.transport = transport or HttpMcpTransport()
        self.state_manager = state_manager
        self.max_rounds = max_rounds

    # ------------------------------------------------------------------
    # /goal prompt construction — boundaries, file targets, constraints
    # ------------------------------------------------------------------
    def build_goal_prompt(self, task: TaskContract, brief: dict[str, Any] | None = None) -> str:
        constraints = dict(task.constraints)
        file_targets = list(constraints.pop("target_files", []) or [])
        file_targets += [f for f in (brief or {}).get("target_files", []) if f not in file_targets]
        arch_notes = (brief or {}).get("architecture_summary", "")
        forbidden = constraints.pop("forbidden_paths", [])
        lines = [
            f"/goal {task.goal}",
            "",
            "## Task boundaries",
            f"- task_id: {task.task_id}",
            f"- allowed_providers: {', '.join(p.value for p in task.allowed_providers)}",
        ]
        if file_targets:
            lines.append("- file targets (touch ONLY these):")
            lines.extend(f"  - {f}" for f in file_targets)
        if forbidden:
            lines.append("- forbidden paths (NEVER modify):")
            lines.extend(f"  - {f}" for f in forbidden)
        for key, value in constraints.items():
            lines.append(f"- {key}: {value}")
        if arch_notes:
            lines.append("")
            lines.append("## Architectural constraints")
            lines.append(arch_notes)
        lines.append("")
        lines.append(
            "## Completion protocol"
            "\n- Work in rounds; after each round emit JSON "
            '{"signal": "running" | "completed" | "failed" | "awaiting_input", "note": "..."}'
            '\n- Declare "completed" ONLY when every boundary is satisfied.'
        )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Multi-round execution with durable signal tracking
    # ------------------------------------------------------------------
    async def execute_goal(
        self,
        task: TaskContract,
        brief: dict[str, Any] | None = None,
        state_manager: AgentStateManager | None = None,
    ) -> GoalRunResult:
        """Run /goal to completion (or honest failure), checkpointing per round."""
        sm = state_manager or self.state_manager
        prompt = self.build_goal_prompt(task, brief)
        rounds: list[GoalRoundResult] = []

        for round_no in range(1, self.max_rounds + 1):
            response = await self.transport.call_tool(
                GOAL_TOOL_NAME,
                {"task_id": task.task_id, "round": round_no, "goal_prompt": prompt},
            )
            signal = GoalRoundResult(
                round=round_no,
                signal=str(response.get("signal", "running")),
                note=str(response.get("note", "")),
                detail=response.get("detail", {}),
            )
            rounds.append(signal)
            if sm is not None:
                # Durable multi-round tracking (issue acceptance) — survives restarts.
                # Tolerant of tasks not yet advanced to RUNNING by the orchestrator:
                # a mis-sequenced flow degrades to a log line, never a crash mid-mission.
                try:
                    sm.checkpoint(
                        task.task_id,
                        payload={
                            "round": round_no,
                            "signal": signal["signal"],
                            "note": signal["note"],
                        },
                        note=f"goal round {round_no}",
                    )
                except Exception as exc:
                    logger.warning(
                        f"[ZCodeProvider] round-{round_no} checkpoint skipped for "
                        f"'{task.task_id}': {exc}"
                    )
            if signal["signal"] == "completed":
                return GoalRunResult(
                    task_id=task.task_id,
                    completed=True,
                    rounds=rounds,
                    summary=signal["note"] or "goal completed",
                )
            if signal["signal"] == "failed":
                return GoalRunResult(
                    task_id=task.task_id,
                    completed=False,
                    failed=True,
                    rounds=rounds,
                    error=signal["note"] or "zcode declared failure",
                )
            if signal["signal"] == "awaiting_input":
                return GoalRunResult(
                    task_id=task.task_id,
                    completed=False,
                    rounds=rounds,
                    error=f"awaiting human input after round {round_no}: {signal['note']}",
                    awaiting_input=True,
                )

        return GoalRunResult(
            task_id=task.task_id,
            completed=False,
            rounds=rounds,
            error=f"max rounds ({self.max_rounds}) exhausted without completion",
        )
