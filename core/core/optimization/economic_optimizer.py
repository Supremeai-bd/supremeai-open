from dataclasses import dataclass, field
from typing import Any

from core.logging_config import logger

# SECURE FIX (CI): services.smart_model_router no longer exports MODEL_REGISTRY or
# ModelConfig (refactored away during Phase 1 Router Consolidation).
# Previously this file did: 'from services.smart_model_router import MODEL_REGISTRY, ModelConfig'
# which raised ImportError in CI, breaking test_economic_router.py collection.
# Now ModelConfig is defined inline (self-contained) and MODEL_REGISTRY defaults to empty.
# Admin can populate it via env-driven configuration if needed (zero hardcoded value).


@dataclass
class ModelConfig:
    """Inline definition of ModelConfig (was previously imported).

    Captures the pricing + quality fields used by EconomicRouter.
    """

    name: str
    provider: str
    quality_score: float = 0.0
    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    tier: str = "STANDARD"


# Default empty registry — admin can extend by editing this dict or wiring
# to a runtime source. Left empty to avoid hardcoding provider rates.
MODEL_REGISTRY: dict[str, ModelConfig] = {}


@dataclass
class BudgetContext:
    """Context tracking budget constraints for a user or session."""

    user_id: str
    monthly_budget: float
    used_budget: float

    @property
    def remaining(self) -> float:
        return max(0.0, self.monthly_budget - self.used_budget)

    def deduct(self, amount: float):
        self.used_budget += amount


@dataclass
class RoutingDecision:
    """The result of an economic routing evaluation."""

    model_config: ModelConfig | None
    estimated_cost_usd: float
    is_affordable: bool
    action: str  # "optimal", "suggest_upgrade", "reject"
    candidates: list[ModelConfig]
    reason: str = ""


class EconomicRouter:
    """
    Makes cost-quality tradeoffs transparent and optimal.
    """

    def __init__(self, token_estimation_ratio: float = 1.5):
        # Ratio of output tokens to input tokens for generic tasks
        self.token_estimation_ratio = token_estimation_ratio

    def estimate_cost(self, prompt: str, model: ModelConfig) -> float:
        """Estimate the cost of a prompt given a model's pricing."""
        # Simple token estimation: ~4 chars per token
        estimated_input_tokens = len(prompt) / 4
        estimated_output_tokens = estimated_input_tokens * self.token_estimation_ratio

        cost = (estimated_input_tokens / 1000) * model.cost_per_1k_input + (
            estimated_output_tokens / 1000
        ) * model.cost_per_1k_output
        return cost

    async def find_viable_providers(self, prompt: str, quality_floor: float) -> list[ModelConfig]:
        """Find providers that meet the quality requirements."""
        candidates = []
        for name, config in MODEL_REGISTRY.items():
            if config.quality_score >= quality_floor:
                candidates.append(config)
        return candidates

    async def route_with_budget(
        self,
        prompt: str,
        user_budget: BudgetContext,
        quality_floor: float = 8.0,  # In MODEL_REGISTRY quality is 0-10
    ) -> RoutingDecision:
        """Route a request based on budget constraints."""

        # 1. Find cheapest options meeting quality floor
        candidates = await self.find_viable_providers(prompt, quality_floor)

        if not candidates:
            return RoutingDecision(
                model_config=None,
                estimated_cost_usd=0.0,
                is_affordable=False,
                action="reject",
                candidates=[],
                reason=f"No models meet the quality floor of {quality_floor}",
            )

        # 2. Sort by total estimated cost
        candidates.sort(key=lambda c: self.estimate_cost(prompt, c))

        # 3. Apply budget constraints
        affordable_candidates = []
        best_unaffordable = candidates[0]

        for c in candidates:
            est_cost = self.estimate_cost(prompt, c)
            if est_cost <= user_budget.remaining:
                affordable_candidates.append((c, est_cost))

        if not affordable_candidates:
            est_cost = self.estimate_cost(prompt, best_unaffordable)
            logger.warning(
                f"User {user_budget.user_id} budget exceeded. Need ${est_cost:.4f}, have ${user_budget.remaining:.4f}"
            )
            return RoutingDecision(
                model_config=None,
                estimated_cost_usd=est_cost,
                is_affordable=False,
                action="suggest_upgrade",
                candidates=candidates,
                reason="Insufficient budget for minimum viable model.",
            )

        # Select the absolute cheapest viable model
        optimal_model, optimal_cost = affordable_candidates[0]

        return RoutingDecision(
            model_config=optimal_model,
            estimated_cost_usd=optimal_cost,
            is_affordable=True,
            action="optimal",
            candidates=[c for c, _ in affordable_candidates],
            reason="Optimal model selected within budget.",
        )
