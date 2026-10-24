import re
from typing import Any

from core.logging_config import logger


class ComplexityAnalyzer:
    KEYWORDS = {
        "simple": r"\b(hello|hi|ping|summary|list|brief)\b",
        "medium": r"\b(explain|compare|analyze|generate|draft|debug)\b",
        "complex": r"\b(implement|deploy|architecture|system design|codebase|refactor|migrate)\b",
    }

    @classmethod
    def classify(cls, prompt: str) -> str:
        text = (prompt or "").lower()
        for level, pattern in cls.KEYWORDS.items():
            if re.search(pattern, text):
                return level
        return "simple"


class CostOptimizer:
    @property
    def route_ladder(self) -> dict[str, list[str]]:
        from core.config import settings

        return settings.route_ladders

    def __init__(self) -> None:
        self.free_tier_tracker = None
        self.litellm_callbacks: list[Any] = []

    def register_litellm_callback(self, callback: Any) -> None:
        if callback not in self.litellm_callbacks:
            self.litellm_callbacks.append(callback)

    def _get_best_free_provider(self) -> str | None:
        try:
            from core.llm.free_tier_tracker import get_tracker

            self.free_tier_tracker = get_tracker()
            provider = self.free_tier_tracker.get_best_provider()
            if provider:
                return provider
        except Exception as exc:
            logger.debug(f"Free tier tracker unavailable: {exc}")
        return None

    async def get_optimal_route(self, task: dict[str, Any], user_mode: str) -> str:
        prompt = task.get("prompt") or task.get("request") or ""
        complexity = ComplexityAnalyzer.classify(prompt)
        ladders = self.route_ladder
        candidates = ladders.get(complexity, ladders["simple"])
        free = self._get_best_free_provider()
        if free and user_mode != "paid":
            for candidate in candidates:
                if candidate.startswith(free):
                    return candidate
        return candidates[0]
