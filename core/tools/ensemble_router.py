# backend/tools/ensemble_router.py
# SupremeAI 2.0 — Provider Selection Intelligence (PSI) Ensemble Router
# ======================================================================
# Compatibility shim & delegation wrapper (ARCH-02 §S1 / Rule 14).
# Canonical router is backend/services/llm/llm_router.py (ModelRouter).

import asyncio
from typing import Any

from core.logging_config import logger


class EnsembleRouter:
    """
    বাংলা মন্তব্য: প্রজেক্টের কোর এআই রউটিং ইঞ্জিন — PSI রুলস মেনে একাধিক
    ফ্রি এআই প্রভাইডারের মধ্যে অটো-সুইচিং ও এগ্রিগেশন পরিচালনা করে।
    """

    def __init__(self) -> None:
        self.quota_exhausted: set[str] = set()

    async def route_and_vote(self, prompt: str, models: list[str] | None = None) -> dict[str, Any]:
        if models is None:
            models = ["deepseek", "kimi", "together", "groq", "ollama"]

        active_models = [m for m in models if m not in self.quota_exhausted]
        if not active_models:
            active_models = ["ollama"]

        logger.info(f"⚡ PSI Ensemble Running on active models: {active_models}")

        try:
            from brain.model_router import ModelRouter

            router = ModelRouter()

            tasks = [
                router.async_route_and_generate(prompt, task_type="general", max_cost=0.0)
                for _ in active_models
            ]
            responses = await asyncio.gather(*tasks, return_exceptions=True)

            valid = {}
            for model, resp in zip(active_models, responses, strict=False):
                if isinstance(resp, Exception):
                    err_msg = str(resp).lower()
                    if "429" in err_msg or "quota" in err_msg or "rate limit" in err_msg:
                        logger.warning(
                            f"⚠️ PSI Circuit Breaker: Model {model} hit rate-limit/quota. Rotating out."
                        )
                        self.quota_exhausted.add(model)
                    else:
                        logger.warning(f"Ensemble model {model} failed: {resp}")
                    continue

                text = resp.get("text", "") if isinstance(resp, dict) else str(resp)
                valid[model] = text

            best_model, best_response = (
                max(valid.items(), key=lambda item: len(item[1]))
                if valid
                else (active_models[0], "Auto-generated zero-cost fallback response.")
            )

            return {
                "status": "success",
                "best_model": best_model,
                "best_response": best_response,
                "all_responses": valid,
                "quota_exhausted_models": list(self.quota_exhausted),
            }
        except Exception as exc:
            logger.error(f"Ensemble routing exception: {exc}")
            return {
                "status": "error",
                "error": str(exc),
                "best_model": active_models[0] if active_models else "ollama",
                "best_response": "Zero-cost local resilience fallback active.",
                "all_responses": {},
            }
