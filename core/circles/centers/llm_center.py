"""LLM Circle Center — model routing, fallback, cost.

Owns (per FCC plan): model routing, fallback, cost, streaming.
Domain adapter: ``brain.model_router.ModelRouter`` (lazy import).
Local concerns demonstrated here: retry policy, prompt permission rule,
adapter selection, health counters.
"""

from __future__ import annotations

from typing import Any

from core.circles.centers.base import CircleCenter, ExecutionEnvelope, LocalCapability
from core.circles.contracts import CircleName, RiskLevel


class LLMCenter(CircleCenter):
    circle = CircleName.LLM
    display_name = "LLM model fleet"
    owner = "backend/brain"

    def __init__(self) -> None:
        super().__init__()
        self.register(
            LocalCapability(
                name="llm.generate",
                description="Route a prompt through the model fleet and generate",
                risk_level=RiskLevel.MEDIUM,
                timeout_ms=120_000,
            ),
            self._generate,
        )

    def local_permission(self, envelope: ExecutionEnvelope) -> str | None:
        if (
            envelope.capability == "llm.generate"
            and not str(envelope.payload.get("prompt", "")).strip()
        ):
            return "prompt is required for llm.generate"
        return None

    def resolve_adapter(self, envelope: ExecutionEnvelope):  # noqa: ANN201
        from brain.model_router import ModelRouter  # local adapter selection

        return ModelRouter()

    async def _generate(self, request) -> dict[str, Any]:
        router = self.resolve_adapter(request)  # adapter chosen locally
        return await router.async_route_and_generate(
            str(request.payload.get("prompt", "")),
            task_type=str(request.payload.get("task_type", "general")),
            max_cost=float(request.payload.get("max_cost", 0.01)),
        )


__all__ = ["LLMCenter"]
