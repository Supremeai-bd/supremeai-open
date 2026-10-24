"""
backend/external_agents/providers/gemini.py
===========================================
ISSUE-1573 (Part 4): Gemini provider adapter — Architect role in the
Planner/Architect router. Reviews a :class:`PlannerArtifact` and returns a
structured :class:`ArchitectureArtifact` with edge-case verification.
Browser-channel delivery is policy-checked by the Policy Engine.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from external_agents.contracts.architecture_artifact import ArchitectureArtifact, EdgeCaseFinding
from external_agents.contracts.planner_artifact import PlannerArtifact
from external_agents.contracts.task_contract import TaskContract

__all__ = ["GeminiProvider"]

Generator = Callable[[str], Awaitable[str]]

_VERDICTS = {"approved", "approved_with_changes", "rejected"}
_SEVERITIES = {"low", "medium", "high", "critical"}


def _default_generator() -> Generator:
    from brain.model_router import ModelRouter

    router = ModelRouter()

    async def generate(prompt: str) -> str:
        res = await router.async_route_and_generate(prompt=prompt, task_type="reasoning")
        if not res or not res.get("success") or not res.get("text"):
            raise RuntimeError(
                f"model gateway unavailable: {res.get('text') if res else 'no response'}"
            )
        return res["text"]

    return generate


class GeminiProvider:
    """Architect-side adapter for the Gemini external agent."""

    name = "gemini"

    def __init__(self, generator: Generator | None = None) -> None:
        self._generator = generator or _default_generator()

    async def generate(self, prompt: str) -> str:
        return await self._generator(prompt)

    async def review(
        self,
        task: TaskContract,
        plan: PlannerArtifact,
    ) -> ArchitectureArtifact:
        """Review the planner output — architecture verdict + edge cases."""
        prompt = (
            "You are the Architect agent. Review the plan JSON and return a JSON "
            'object with keys "verdict" (approved|approved_with_changes|rejected), '
            '"rationale", "edge_cases" (each: {scenario, handled, severity, notes}), '
            '"required_changes", "non_blocking_notes".\n'
            f"Task goal: {task.goal}\n"
            f"Plan: {plan.model_dump_json()}\n"
            "Return ONLY the JSON object."
        )
        raw = await self.generate(prompt)
        from external_agents.providers.chatgpt import extract_json_object

        try:
            data = extract_json_object(raw)
        except ValueError as exc:
            raise RuntimeError(f"Gemini architect returned unparseable output: {exc}") from exc

        verdict = str(data.get("verdict", "rejected"))
        if verdict not in _VERDICTS:
            verdict = "rejected"  # fail-closed on unknown verdicts

        edge_cases = []
        for e in data.get("edge_cases", []):
            severity = str(e.get("severity", "medium"))
            edge_cases.append(
                EdgeCaseFinding(
                    scenario=str(e.get("scenario", "unspecified")),
                    handled=bool(e.get("handled", False)),
                    severity=severity if severity in _SEVERITIES else "medium",
                    notes=str(e.get("notes", "")),
                )
            )
        return ArchitectureArtifact(
            task_id=task.task_id,
            verdict=verdict,
            rationale=str(data.get("rationale", "")),
            edge_cases=edge_cases,
            required_changes=[str(c) for c in data.get("required_changes", [])],
            non_blocking_notes=[str(n) for n in data.get("non_blocking_notes", [])],
            reviewed_planner_provider=plan.provider,
            provider=self.name,
        )
