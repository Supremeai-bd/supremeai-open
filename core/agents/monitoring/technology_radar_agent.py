"""
SupremeAI — Technology Radar Agent
===================================
Tracks emerging technologies and assesses their applicability.
Monitors tech trends, evaluates relevance, and generates adoption recommendations.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.config_cache import config_cache

RADAR_CACHE_TTL = 43200  # 12 hours


class TechMaturity(StrEnum):
    EMERGING = "emerging"
    ADOPTING = "adopting"
    MAINSTREAM = "mainstream"
    DECLINING = "declining"
    OBSOLETE = "obsolete"


class AdoptionPriority(StrEnum):
    NOW = "adopt_now"
    EVALUATE = "evaluate"
    WATCH = "watch"
    HOLD = "hold"


@dataclass(frozen=True)
class Technology:
    """Immutable technology record."""

    name: str
    category: str
    description: str
    maturity: TechMaturity
    adoption_priority: AdoptionPriority
    impact_score: float  # 0-1
    effort_to_adopt: str  # low, medium, high
    recommendation: str
    detected_at: datetime


@dataclass(frozen=True)
class RadarReport:
    """Immutable technology radar report."""

    technologies: list[Technology]
    total_tracked: int
    adopt_now_count: int
    generated_at: datetime


# Built-in technology categories and tracking
TECH_CATEGORIES = [
    "llm_frameworks",
    "vector_databases",
    "agent_frameworks",
    "devops_tools",
    "monitoring",
    "security",
    "data_pipelines",
    "frontend",
    "mobile",
    "cloud_services",
]


class TechnologyRadarAgent:
    """
    Tracks emerging technologies and assesses their applicability.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm = llm_router or ModelRouter()
        self.cache = get_cache()
        self._technologies: list[Technology] = []

    def _cache_key(self, prefix: str) -> str:
        raw = f"techradar:{prefix}:{datetime.now(UTC).strftime('%Y%m%d')}"
        return f"techradar:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    def register_technology(
        self,
        name: str,
        category: str,
        description: str,
        maturity: TechMaturity = TechMaturity.EMERGING,
        adoption_priority: AdoptionPriority = AdoptionPriority.WATCH,
        impact: float = 0.5,
        effort: str = "medium",
        recommendation: str = "",
    ) -> Technology:
        """Register a new technology for tracking."""
        tech = Technology(
            name=name,
            category=category,
            description=description,
            maturity=maturity,
            adoption_priority=adoption_priority,
            impact_score=min(1.0, max(0.0, impact)),
            effort_to_adopt=effort,
            recommendation=recommendation or f"Monitor {name} for potential adoption in {category}",
            detected_at=datetime.now(UTC),
        )
        self._technologies.append(tech)
        return tech

    async def assess_relevance(self, tech_name: str, project_context: str) -> dict[str, Any]:
        """Assess how relevant a technology is to the project."""
        tech = next((t for t in self._technologies if t.name.lower() == tech_name.lower()), None)
        if not tech:
            return {"error": f"Technology '{tech_name}' not found in radar"}

        prompt = (
            f"Assess the relevance of {tech.name} ({tech.category}) for this project context:\n"
            f"{project_context}\n\n"
            f"Technology maturity: {tech.maturity.value}\n"
            f"Impact score: {tech.impact_score}\n"
            f"Provide a brief assessment of adoption fit and potential challenges."
        )

        try:
            result = await self.llm.async_route_and_generate(
                prompt=prompt,
                task_type="reasoning",
                max_tokens=config_cache.get("technology_radar_agent_max_tokens", 300),
            )
            return {
                "technology": tech_name,
                "relevance_assessment": result.get("text", ""),
                "maturity": tech.maturity.value,
                "impact": tech.impact_score,
            }
        except Exception as e:
            return {"technology": tech_name, "error": str(e)}

    async def generate_radar(self) -> RadarReport:
        """Generate the current technology radar report."""
        adopt_now = [t for t in self._technologies if t.adoption_priority == AdoptionPriority.NOW]

        return RadarReport(
            technologies=self._technologies,
            total_tracked=len(self._technologies),
            adopt_now_count=len(adopt_now),
            generated_at=datetime.now(UTC),
        )

    def get_technologies_by_category(self, category: str) -> list[Technology]:
        """Get technologies filtered by category."""
        return [t for t in self._technologies if t.category == category]

    def get_adoption_recommendations(self) -> list[dict[str, Any]]:
        """Get prioritized adoption recommendations."""
        priority_order = {
            AdoptionPriority.NOW: 0,
            AdoptionPriority.EVALUATE: 1,
            AdoptionPriority.WATCH: 2,
            AdoptionPriority.HOLD: 3,
        }
        sorted_techs = sorted(
            self._technologies,
            key=lambda t: (priority_order.get(t.adoption_priority, 3), -t.impact_score),
        )

        return [
            {
                "name": t.name,
                "priority": t.adoption_priority.value,
                "impact": t.impact_score,
                "effort": t.effort_to_adopt,
                "recommendation": t.recommendation,
            }
            for t in sorted_techs
        ]


# Singleton
_tech_radar_instance: TechnologyRadarAgent | None = None


def get_tech_radar() -> TechnologyRadarAgent:
    """Get or create the singleton TechnologyRadarAgent."""
    global _tech_radar_instance
    if _tech_radar_instance is None:
        _tech_radar_instance = TechnologyRadarAgent()
    return _tech_radar_instance
