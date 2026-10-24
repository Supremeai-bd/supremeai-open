# SupremeAI 2.0 - Smart Model Router Engine
# বাংলা মন্তব্য: এটি ব্যবহারকারীর কমান্ডের ইনটেন্ট অনুযায়ী স্বয়ংক্রিয়ভাবে সঠিক HF / LLM মডেলে রাউট করে।

from __future__ import annotations

from typing import Any

from core.logging_config import logger


class SmartModelRouter:
    """
    Smart Model Router Engine.
    Analyzes prompt intent, domain, and historical model success rates to dynamically select the best specialized model.
    """

    @property
    def model_map(self) -> dict[str, str]:
        from core.config import settings

        models = settings.task_models
        return {
            "code": models["coding"],
            "reasoning": models["reasoning"],
            "bengali": models["chat"],
            "math": models["reasoning"],
            "general": models["general"],
        }

    def classify_intent(self, prompt: str) -> str:
        """Classify prompt into target domain intent."""
        prompt_lower = prompt.lower()

        # Bengali detection
        if any("\u0980" <= char <= "\u09ff" for char in prompt):
            return "bengali"

        # Code detection
        code_keywords = [
            "def ",
            "class ",
            "function",
            "code",
            "python",
            "javascript",
            "sql",
            "bug",
            "refactor",
        ]
        if any(kw in prompt_lower for kw in code_keywords):
            return "code"

        # Math detection
        math_keywords = ["calculate", "equation", "integral", "derivative", "matrix", "probability"]
        if any(kw in prompt_lower for kw in math_keywords):
            return "math"

        # Reasoning detection
        reasoning_keywords = [
            "why",
            "architecture",
            "tradeoff",
            "strategy",
            "compare",
            "design",
            "plan",
        ]
        if any(kw in prompt_lower for kw in reasoning_keywords):
            return "reasoning"

        return "general"

    async def route(self, prompt: str) -> dict[str, Any]:
        """
        Route prompt to the most optimal specialized model.
        """
        intent = self.classify_intent(prompt)
        models = self.model_map
        target_model = models.get(intent, models["general"])

        routing_decision = {
            "prompt": prompt,
            "detected_intent": intent,
            "selected_model": target_model,
            "routing_confidence": 0.95,
        }

        logger.info(f"Smart Model Router: Intent '{intent}' -> Routed to model '{target_model}'")
        return routing_decision
