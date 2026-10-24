"""
backend/external_agents/providers/chatgpt.py
============================================
ISSUE-1573 (Part 4): ChatGPT provider adapter — Planner role in the
Planner/Architect router. Talks to the model gateway (lazy import) or an
injected async generator; produces structured :class:`PlannerArtifact`s.
Browser-channel delivery is policy-checked by the Policy Engine.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from external_agents.contracts.planner_artifact import PlannerArtifact, PlanStep
from external_agents.contracts.task_contract import TaskContract

__all__ = ["ChatGPTProvider", "ProviderExecutionError", "extract_json_object"]

Generator = Callable[[str], Awaitable[str]]


class ProviderExecutionError(RuntimeError):
    """Raised honestly when the provider cannot produce a valid artifact."""


def extract_json_object(raw: str) -> dict[str, Any]:
    """Parse the first JSON object from model text (tolerates code fences)."""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in provider response")
    return json.loads(text[start : end + 1])


def _default_generator() -> Generator:
    """Production generator via the model gateway (lazy, offline-honest)."""
    from brain.model_router import ModelRouter

    router = ModelRouter()

    async def generate(prompt: str) -> str:
        res = await router.async_route_and_generate(prompt=prompt, task_type="reasoning")
        if not res or not res.get("success") or not res.get("text"):
            raise ProviderExecutionError(
                f"model gateway unavailable: {res.get('text') if res else 'no response'}"
            )
        return res["text"]

    return generate


class ChatGPTProvider:
    """Planner-side adapter for the ChatGPT external agent."""

    name = "chatgpt"

    def __init__(self, generator: Generator | None = None) -> None:
        self._generator = generator or _default_generator()

    async def generate(self, prompt: str) -> str:
        return await self._generator(prompt)

    async def plan(self, task: TaskContract, context: str = "") -> PlannerArtifact:
        """Produce a structured plan for the task (raises on gateway failure)."""
        prompt = (
            "You are the Planner agent. Produce a JSON object with keys "
            '"summary", "steps" (each: {index, title, description, target_files, '
            '"acceptance"}), "risks", "assumptions".\n'
            f"Task goal: {task.goal}\n"
            f"Constraints: {json.dumps(task.constraints, ensure_ascii=False)}\n"
            f"Context: {context or 'none'}\n"
            "Return ONLY the JSON object."
        )
        raw = await self.generate(prompt)
        try:
            data = extract_json_object(raw)
        except ValueError as exc:
            raise ProviderExecutionError(
                f"ChatGPT planner returned unparseable output: {exc}"
            ) from exc
        steps = [
            PlanStep(
                index=int(s.get("index", i + 1)),
                title=str(s.get("title", f"step {i + 1}")),
                description=str(s.get("description", "")),
                target_files=list(s.get("target_files", [])),
                acceptance=list(s.get("acceptance", [])),
            )
            for i, s in enumerate(data.get("steps", []))
        ]
        return PlannerArtifact(
            task_id=task.task_id,
            summary=str(data.get("summary", "")),
            steps=steps,
            risks=[str(r) for r in data.get("risks", [])],
            assumptions=[str(a) for a in data.get("assumptions", [])],
            provider=self.name,
        )
