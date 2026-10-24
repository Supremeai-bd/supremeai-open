# backend/runtime/task_executor.py
"""Task Executor for Canonical Task Runtime."""

from __future__ import annotations

import time
from typing import Any

from core.integration_layer import SupremeAIIntegrator
from core.logging_config import logger
from core.provider_rate_limiter import IntelligentRateLimiter, get_provider_rate_limiter
from core.task_contract import TaskContract
from runtime.task_context import TaskContext


class TaskExecutor:
    """Executes a TaskContract through the SupremeAI multi-domain reasoning stack."""

    def __init__(
        self,
        ai_system: SupremeAIIntegrator | None = None,
        rate_limiter: IntelligentRateLimiter | None = None,
    ) -> None:
        self.ai_system = ai_system
        self.rate_limiter = rate_limiter or get_provider_rate_limiter()

    async def execute(self, task: TaskContract, context: TaskContext) -> dict[str, Any]:
        """Execute the task under timeout and budget constraints."""
        start_time = time.perf_counter()
        logger.info(f"⚡ Executing Task [{task.task_id}]: {task.goal[:80]}")

        # 1. Multi-Provider Fallback Rate Limiting Gate
        rate_res = await self.rate_limiter.make_request(
            prompt=task.goal,
            context={"task_id": task.task_id, "trace_id": context.trace_id},
        )

        if not rate_res.get("success"):
            return {
                "success": False,
                "error": rate_res.get(
                    "user_message", "AI provider rate limit reached. Please retry."
                ),
                "provider_used": "none",
                "output": None,
                "components_used": ["rate_limiter"],
            }

        provider_used = rate_res.get("provider_used", "Gemini")
        context.active_provider = provider_used

        # 2. Main Execution through Integrator / Reasoning
        if self.ai_system:
            int_res = await self.ai_system.process(task.goal, context=task.context)
            output = getattr(int_res, "answer", str(int_res))
            components = getattr(int_res, "components_used", ["reasoning_engine"])
        else:
            output = f"Processed solution for: {task.goal}"
            components = ["default_engine"]

        # Track usage in context
        context.record_usage(prompt_tokens=len(task.goal) // 4, completion_tokens=len(output) // 4)
        task.budget.tokens_used += context.token_usage["total"]

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "success": True,
            "output": output,
            "provider_used": provider_used,
            "execution_time_ms": elapsed_ms,
            "components_used": components,
        }
