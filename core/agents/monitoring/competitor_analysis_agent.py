"""
SupremeAI — Competitor Analysis Agent
======================================
Monitors competitor AI systems and features.
Tracks releases, benchmarks, and feature comparisons.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.logging_config import logger

COMPETITOR_CACHE_TTL = 86400  # 24 hours


@dataclass(frozen=True)
class CompetitorFeature:
    """Immutable competitor feature record."""

    competitor_name: str
    feature_name: str
    description: str
    release_date: datetime | None
    category: str
    impact_score: float  # 0-1


@dataclass(frozen=True)
class FeatureGap:
    """Immutable feature gap analysis."""

    feature_name: str
    competitor: str
    description: str
    priority: str  # critical, high, medium, low
    estimated_effort: str
    recommendation: str


@dataclass(frozen=True)
class CompetitorReport:
    """Immutable competitor analysis report."""

    competitors_analyzed: list[str]
    new_features: list[CompetitorFeature]
    gaps: list[FeatureGap]
    market_position: str
    generated_at: datetime


# Built-in competitor tracking
DEFAULT_COMPETITORS = {
    "OpenAI": {
        "url": "https://openai.com/blog",
        "products": ["GPT-4", "GPT-4o", "DALL-E", "Whisper"],
        "focus_areas": ["LLM", "multimodal", "code_generation"],
    },
    "Anthropic": {
        "url": "https://anthropic.com/blog",
        "products": ["Claude 3", "Claude 3.5"],
        "focus_areas": ["safety", "long_context", "reasoning"],
    },
    "Google DeepMind": {
        "url": "https://deepmind.google/blog",
        "products": ["Gemini", "Gemma"],
        "focus_areas": ["multimodal", "research", "efficiency"],
    },
    "Meta AI": {
        "url": "https://ai.meta.com/blog",
        "products": ["Llama 3", "Code Llama"],
        "focus_areas": ["open_source", "code", "language"],
    },
    "Mistral AI": {
        "url": "https://mistral.ai/news",
        "products": ["Mistral Large", "Mixtral"],
        "focus_areas": ["efficiency", "open_source", "multilingual"],
    },
}


class CompetitorAnalysisAgent:
    """
    Monitors competitor AI systems and features.
    Tracks releases, benchmarks, and feature comparisons.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm = llm_router or ModelRouter()
        self.cache = get_cache()
        self._competitors = dict(DEFAULT_COMPETITORS)
        self._tracked_features: list[CompetitorFeature] = []

    def _cache_key(self, prefix: str) -> str:
        raw = f"competitor:{prefix}:{datetime.now(UTC).strftime('%Y%m%d')}"
        return f"competitor:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def register_competitor(self, name: str, products: list[str], focus_areas: list[str]) -> None:
        """Register a new competitor to track."""
        self._competitors[name] = {
            "products": products,
            "focus_areas": focus_areas,
        }
        logger.info("Registered competitor: %s", name)

    def record_feature(
        self,
        competitor: str,
        feature: str,
        description: str,
        category: str = "general",
        impact: float = 0.5,
    ) -> CompetitorFeature:
        """Record a new feature from a competitor."""
        cf = CompetitorFeature(
            competitor_name=competitor,
            feature_name=feature,
            description=description,
            release_date=datetime.now(UTC),
            category=category,
            impact_score=min(1.0, max(0.0, impact)),
        )
        self._tracked_features.append(cf)
        return cf

    async def analyze_gaps(self, our_features: list[str]) -> list[FeatureGap]:
        """Analyze feature gaps between us and competitors."""
        cache_key = self._cache_key("gaps")
        cached = await self.cache.get(cache_key)
        if cached:
            return [FeatureGap(**g) for g in cached]

        gaps = []
        our_set = set(f.lower() for f in our_features)

        for feature in self._tracked_features:
            if feature.feature_name.lower() not in our_set:
                priority = (
                    "critical"
                    if feature.impact_score > 0.8
                    else "high"
                    if feature.impact_score > 0.6
                    else "medium"
                    if feature.impact_score > 0.4
                    else "low"
                )
                effort = (
                    "high"
                    if priority == "critical"
                    else "medium"
                    if priority in ("high", "medium")
                    else "low"
                )

                gaps.append(
                    FeatureGap(
                        feature_name=feature.feature_name,
                        competitor=feature.competitor_name,
                        description=feature.description,
                        priority=priority,
                        estimated_effort=effort,
                        recommendation=f"Implement {feature.feature_name} to match {feature.competitor_name} capability",
                    )
                )

        # Sort by priority
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        gaps.sort(key=lambda g: priority_order.get(g.priority, 4))

        await self.cache.set(
            cache_key,
            [
                {
                    "feature_name": g.feature_name,
                    "competitor": g.competitor,
                    "description": g.description,
                    "priority": g.priority,
                    "estimated_effort": g.estimated_effort,
                    "recommendation": g.recommendation,
                }
                for g in gaps
            ],
            ttl=COMPETITOR_CACHE_TTL,
        )

        return gaps

    async def generate_report(self, our_features: list[str]) -> CompetitorReport:
        """Generate a comprehensive competitor analysis report."""
        gaps = await self.analyze_gaps(our_features)

        # Determine market position
        critical_gaps = sum(1 for g in gaps if g.priority == "critical")
        total_features = len(self._tracked_features) + len(our_features)
        coverage = len(our_features) / total_features if total_features > 0 else 0

        if coverage > 0.8 and critical_gaps == 0:
            position = "market_leader"
        elif coverage > 0.6 and critical_gaps <= 2:
            position = "competitive"
        elif coverage > 0.4:
            position = "emerging"
        else:
            position = "lagging"

        return CompetitorReport(
            competitors_analyzed=list(self._competitors.keys()),
            new_features=self._tracked_features[-20:] if self._tracked_features else [],
            gaps=gaps,
            market_position=position,
            generated_at=datetime.now(UTC),
        )

    def get_competitor_summary(self) -> dict[str, Any]:
        """Get summary of tracked competitors."""
        return {
            name: {
                "products": info["products"],
                "focus_areas": info.get("focus_areas", []),
            }
            for name, info in self._competitors.items()
        }


# Singleton
_competitor_instance: CompetitorAnalysisAgent | None = None


def get_competitor_analysis() -> CompetitorAnalysisAgent:
    """Get or create the singleton CompetitorAnalysisAgent."""
    global _competitor_instance
    if _competitor_instance is None:
        _competitor_instance = CompetitorAnalysisAgent()
    return _competitor_instance
