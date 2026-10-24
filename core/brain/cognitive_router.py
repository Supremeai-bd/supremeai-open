from typing import Any

from brain.economic_optimizer import BudgetContext, EconomicOptimizer
from core.config import settings


class CognitiveRouter:
    def __init__(self, economic_optimizer: EconomicOptimizer = None):
        self.economic_optimizer = economic_optimizer

    async def route(
        self, prompt: str, user_id: str, budget_context: BudgetContext = None
    ) -> dict[str, Any]:
        # Simple heuristic to determine if decomposed
        if "analyze" in prompt.lower() and "implement" in prompt.lower():
            # Decompose
            return {
                "routing_mode": "decomposed",
                "task_graph": {
                    "task_count": 2,
                    "tasks": {
                        "task_1": {"type": "analysis", "provider": "google", "depends_on": []},
                        "task_2": {
                            "type": "implementation",
                            "provider": "groq",
                            "depends_on": ["task_1"],
                        },
                    },
                },
            }

        # Direct route
        if self.economic_optimizer and budget_context:
            decision = await self.economic_optimizer.optimize_route(
                prompt, "general", budget_context
            )
            return {
                "routing_mode": "direct",
                "provider": decision.provider,
                "model": decision.model,
            }

        default_model = getattr(settings, "model_general", "groq/llama-3.3-70b-versatile")
        if "/" in default_model:
            prov, mod = default_model.split("/", 1)
        else:
            prov, mod = "groq", default_model
        return {"routing_mode": "direct", "provider": prov, "model": mod}


_cognitive_router_instance = None


def get_cognitive_router(economic_optimizer: EconomicOptimizer = None) -> CognitiveRouter:
    global _cognitive_router_instance
    if _cognitive_router_instance is None:
        _cognitive_router_instance = CognitiveRouter(economic_optimizer)
    return _cognitive_router_instance
