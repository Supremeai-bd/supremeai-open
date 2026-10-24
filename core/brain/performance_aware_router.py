# backend/brain/performance_aware_router.py
"""
Performance-Aware Router for SupremeAI 2.0 — Facade Bridge to AdvancedModelRouter.
"""

from __future__ import annotations

from typing import Any, TypedDict

from brain.economic_optimizer import BudgetContext, get_economic_optimizer
from core.config import settings
from core.llm.advanced_model_router import (
    get_advanced_router,
)


class ProviderHealth(TypedDict):
    status: str
    latency_ms: int


PROVIDER_HEALTH: dict[str, ProviderHealth] = {
    "groq": {"status": "ok", "latency_ms": 50},
    "google": {"status": "ok", "latency_ms": 250},
    "openrouter": {"status": "degraded", "latency_ms": 1200},
    "together": {"status": "ok", "latency_ms": 300},
    "nvidia": {"status": "ok", "latency_ms": 180},
    "huggingface": {"status": "ok", "latency_ms": 800},
}


class PerformanceAwareRouter:
    """Backward-compatible facade bridging to core.llm.advanced_model_router."""

    def __init__(self):
        self._core_router = get_advanced_router()
        self.providers = [
            {"name": "groq", "cost_per_1k": 0.0001, "quality": 9},
            {"name": "google", "cost_per_1k": 0.00025, "quality": 10},
            {"name": "together", "cost_per_1k": 0.0002, "quality": 8},
            {"name": "openrouter", "cost_per_1k": 0.001, "quality": 9},
            {"name": "nvidia", "cost_per_1k": 0.0005, "quality": 8},
            {"name": "huggingface", "cost_per_1k": 0.00005, "quality": 6},
        ]
        self.latency_weight = 0.5
        self.cost_weight = 0.3
        self.quality_weight = 0.2

    def _is_provider_healthy(self, provider_name: str) -> bool:
        health = PROVIDER_HEALTH.get(provider_name, {"status": "down"})
        return health.get("status") == "ok"

    def _get_provider_latency(self, provider_name: str) -> int:
        health = PROVIDER_HEALTH.get(provider_name)
        if health is None:
            return 9999
        return health["latency_ms"]

    def _calculate_score(self, provider_info: dict, latency_ms: int) -> float:
        if not self._is_provider_healthy(provider_info.get("name", "")):
            return float("inf")

        max_latency = 2000
        max_cost = 0.01
        min_quality, max_quality = 1, 10

        norm_latency = min(latency_ms / max_latency, 1.0)
        norm_cost = min(provider_info.get("cost_per_1k", 0.0005) / max_cost, 1.0)
        quality = provider_info.get("quality", 7)
        norm_quality = (quality - min_quality) / (max_quality - min_quality)
        norm_quality_inv = 1.0 - norm_quality

        return (
            (norm_latency * self.latency_weight)
            + (norm_cost * self.cost_weight)
            + (norm_quality_inv * self.quality_weight)
        )

    async def route(
        self, prompt: str, task_type: str = "general", budget_context: BudgetContext = None
    ) -> dict[str, Any]:
        if budget_context:
            optimizer = await get_economic_optimizer()
            decision = await optimizer.optimize_route(
                prompt=prompt, task_type=task_type, budget_context=budget_context
            )
            return {
                "provider": decision.provider,
                "model": decision.model,
                "score": 0.0,
                "latency_ms": 0,
                "estimated_cost": decision.estimated_cost,
                "route_class": "economic",
                "reasoning": decision.reasoning,
            }

        scored_providers = []
        for p in self.providers:
            if self._is_provider_healthy(p["name"]):
                lat = self._get_provider_latency(p["name"])
                score = self._calculate_score(p, lat)
                if score < float("inf"):
                    scored_providers.append((score, p, lat))

        if not scored_providers:
            raise Exception("No healthy providers available")

        scored_providers.sort(key=lambda x: x[0])
        best_score, best_provider, lat = scored_providers[0]

        return {
            "provider": best_provider["name"],
            "model": (
                settings.model_coding.split("/", 1)[-1]
                if best_provider["name"] == "groq"
                else settings.model_general.split("/", 1)[-1]
            ),
            "score": best_score,
            "latency_ms": lat,
            "estimated_cost": best_provider["cost_per_1k"],
            "route_class": "cheap" if best_provider["cost_per_1k"] <= 0.0002 else "premium",
        }
