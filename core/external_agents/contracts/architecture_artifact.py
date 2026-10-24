"""
backend/external_agents/contracts/architecture_artifact.py
==========================================================
ISSUE-1572 (Part 3): architecture review + edge-case verification schema —
the Architect agent's structured verdict over a PlannerArtifact.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

__all__ = ["ArchitectureArtifact", "EdgeCaseFinding"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EdgeCaseFinding(BaseModel):
    """One edge case the architect verified (or found unhandled)."""

    scenario: str
    handled: bool
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    notes: str = ""


class ArchitectureArtifact(BaseModel):
    """Architecture review verdict over a plan/code changeset."""

    task_id: str
    verdict: Literal["approved", "approved_with_changes", "rejected"]
    rationale: str = ""
    edge_cases: list[EdgeCaseFinding] = Field(default_factory=list)
    required_changes: list[str] = Field(
        default_factory=list,
        description="Blocking changes that must land before verification",
    )
    non_blocking_notes: list[str] = Field(default_factory=list)
    reviewed_planner_provider: str | None = None
    provider: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def blocking_edge_cases(self) -> list[EdgeCaseFinding]:
        return [e for e in self.edge_cases if not e.handled and e.severity in {"high", "critical"}]

    @property
    def is_actionable(self) -> bool:
        """True when a coder may proceed (approved, nothing blocking open)."""
        if self.verdict == "rejected":
            return False
        return not self.blocking_edge_cases and not self.required_changes
