import logging
from dataclasses import dataclass
from typing import Any

from services.config_service import ConfigService

logger = logging.getLogger(__name__)


@dataclass
class BudgetContext:
    user_id: str
    monthly_limit: float
    spent_this_month: float
    cost_sensitivity: float


@dataclass
class OptimizationDecision:
    provider: str
    model: str
    estimated_cost: float
    reasoning: str


class EconomicOptimizer:
    def __init__(self, free_tier_tracker=None):
        self.free_tier_tracker = free_tier_tracker
        self.provider_tiers = {
            "groq": {
                "model": "llama-3.3-70b-versatile",
                "cost_per_1k": 0.0001,
                "tier": "free/cheap",
            },
            "google": {"model": "gemini-2.5-pro", "cost_per_1k": 0.00025, "tier": "premium"},
            "together": {"model": "mixtral-8x7b", "cost_per_1k": 0.0002, "tier": "cheap"},
            "openrouter": {"model": "auto", "cost_per_1k": 0.001, "tier": "premium"},
            "nvidia": {"model": "nemotron-4", "cost_per_1k": 0.0005, "tier": "mid"},
            "huggingface": {"model": "zephyr-7b", "cost_per_1k": 0.00005, "tier": "free/cheap"},
        }

    # FIX (final-test ci-fixes): DB/Redis-এর আংশিক বা ত্রুটিপূর্ণ config যেন baseline
    # provider-গুলোকে মুছে না দিতে পারে — তাই clear()+update() নয়, MERGE। আগে CI-তে
    # partial config sync হলে 'huggingface' হারিয়ে KeyError হচ্ছিল।
    DEFAULT_TIERS: dict[str, dict[str, Any]] = {
        "huggingface": {"model": "zephyr-7b", "cost_per_1k": 0.00005, "tier": "free/cheap"},
        "groq": {"model": "llama-3.3-70b-versatile", "cost_per_1k": 0.0001, "tier": "free/cheap"},
    }

    async def sync_from_db(self, db: Any) -> None:
        """Sync provider_tiers from the database configuration (merge, never wipe)."""
        try:
            configs = await ConfigService.get_config(db, "model_cost_per_1k", None)
            if isinstance(configs, dict) and configs:
                # MERGE: DB value overrides matching providers, but baseline providers
                # (huggingface fallback route) always stay available.
                merged = dict(self.provider_tiers)
                for provider, info in configs.items():
                    if isinstance(info, dict):
                        merged[provider] = info
                self.provider_tiers.clear()
                self.provider_tiers.update(merged)
                logger.info(
                    f"✅ Synced {len(self.provider_tiers)} model_cost_per_1k entries from DB (merged with baseline)."
                )
            elif configs:
                logger.warning(
                    "⚠️  model_cost_per_1k config in DB is not a valid mapping — keeping baseline providers"
                )
        except Exception as e:
            logger.error(f"❌ Failed to sync model_cost_per_1k from DB: {e}")

    async def optimize_route(
        self, prompt: str, task_type: str, budget_context: BudgetContext
    ) -> OptimizationDecision:
        remaining_budget = budget_context.monthly_limit - budget_context.spent_this_month

        # Determine allowed tier based on remaining budget and cost sensitivity
        if remaining_budget < 1.0 or budget_context.cost_sensitivity > 0.8:
            allowed_tiers = ["free/cheap"]
        elif remaining_budget < 5.0 or budget_context.cost_sensitivity > 0.5:
            allowed_tiers = ["free/cheap", "cheap", "mid"]
        else:
            allowed_tiers = ["free/cheap", "cheap", "mid", "premium"]

        # DEFENSIVE (final-test ci-fixes): DB-synced config-এ malformed/incomplete entry
        # বা allowed-tier-এ কোনো provider না থাকলেও এই ফাংশন কখনো KeyError দেবে না।
        best_provider: str | None = None
        best_cost = float("inf")

        for provider, info in self.provider_tiers.items():
            if not isinstance(info, dict):
                continue
            tier = info.get("tier")
            cost = info.get("cost_per_1k")
            if tier in allowed_tiers and isinstance(cost, (int, float)) and cost < best_cost:
                best_cost = cost
                best_provider = provider

        if best_provider is None:
            # allowed tier-এ কিছু নেই → baseline fallback (সৎ default, state না বদলে)
            best_provider = "huggingface"
            best_cost = self.DEFAULT_TIERS["huggingface"]["cost_per_1k"]
            model = self.DEFAULT_TIERS["huggingface"]["model"]
            tier_label = self.DEFAULT_TIERS["huggingface"]["tier"]
        else:
            model = self.provider_tiers[best_provider].get(
                "model", self.DEFAULT_TIERS.get(best_provider, {}).get("model", "unknown")
            )
            tier_label = self.provider_tiers[best_provider].get("tier", "unknown")

        reasoning = f"Selected {best_provider} (tier: {tier_label}) due to remaining budget of ${remaining_budget:.2f} and cost sensitivity {budget_context.cost_sensitivity}"

        return OptimizationDecision(
            provider=best_provider, model=model, estimated_cost=best_cost, reasoning=reasoning
        )


_economic_optimizer_instance = None


async def get_economic_optimizer(free_tier_tracker=None) -> EconomicOptimizer:
    global _economic_optimizer_instance
    if _economic_optimizer_instance is None:
        _economic_optimizer_instance = EconomicOptimizer(free_tier_tracker=free_tier_tracker)
    return _economic_optimizer_instance
