# backend/brain/expert_router.py
"""
SupremeAI Mixture of Experts (MoE) Router — Facade Bridge to AdvancedModelRouter.
"""

from __future__ import annotations

from core.config import settings
from core.llm.advanced_model_router import (
    DomainExpertAnalyzer,
    ExpertType,
    get_advanced_router,
)


class SupremeMoERouter:
    """Backward-compatible facade bridging to core.llm.advanced_model_router."""

    EXPERT_MODEL_MAP: dict[ExpertType, list[str]] = {
        ExpertType.BENGALI: [
            "hf_space/supreme-hybrid-8b",
            "groq/llama-3.3-70b-versatile",
            "gemini/gemini-2.5-flash",
        ],
        ExpertType.CODER: [
            "deepseek/deepseek-coder",
            "groq/qwen-2.5-coder-32b",
            "openai/gpt-4o",
        ],
        ExpertType.REASONER: [
            "deepseek/deepseek-chat",
            "groq/deepseek-r1-distill-llama-70b",
            "gemini/gemini-2.5-pro",
        ],
        ExpertType.CREATIVE: [
            "gemini/gemini-2.5-flash",
            "openai/gpt-4o",
            "groq/llama-3.3-70b-versatile",
        ],
        ExpertType.GENERAL: [
            "gemini/gemini-2.5-flash",
            "groq/llama-3.1-8b-instant",
            "openai/gpt-4o-mini",
        ],
    }

    def __init__(self):
        self.router = get_advanced_router()
        self.analyzer = DomainExpertAnalyzer()

    @classmethod
    def classify_prompt(cls, prompt: str) -> ExpertType:
        return DomainExpertAnalyzer.classify_domain(prompt)

    @classmethod
    def get_model_chain(cls, prompt: str) -> list[str]:
        expert = cls.classify_prompt(prompt)
        return cls.EXPERT_MODEL_MAP.get(expert, cls.EXPERT_MODEL_MAP[ExpertType.GENERAL])

    def route(self, prompt: str) -> tuple[str, list[str]]:
        models = self.get_model_chain(prompt)
        default_fallback = getattr(settings, "model_general", "groq/llama-3.3-70b-versatile")
        primary = models[0] if models else default_fallback
        fallbacks = models[1:] if len(models) > 1 else []
        return primary, fallbacks
