"""
backend/external_agents/contracts/planner_artifact.py
=====================================================
ISSUE-1572 (Part 3): structured planning artifact — the machine-readable
output of the Planner agent (implementation plan, ordered steps, risks).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

__all__ = ["PlannerArtifact", "PlanStep"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PlanStep(BaseModel):
    """One ordered, verifiable implementation step."""

    index: int = Field(ge=1)
    title: str
    description: str = ""
    target_files: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(
        default_factory=list, description="Verifiable acceptance criteria for this step"
    )


class PlannerArtifact(BaseModel):
    """Structured planning output — feeds the Architect review (#1573 router)."""

    task_id: str
    summary: str = Field(description="One-paragraph plan narrative")
    steps: list[PlanStep] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    estimated_effort: str | None = None
    provider: str | None = Field(
        default=None, description="Which planner provider produced this artifact"
    )
    created_at: datetime = Field(default_factory=_utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)

    def step_targets(self) -> list[str]:
        """Union of all step target files (de-duplicated, order preserved)."""
        seen: set[str] = set()
        ordered: list[str] = []
        for step in self.steps:
            for f in step.target_files:
                if f not in seen:
                    seen.add(f)
                    ordered.append(f)
        return ordered
