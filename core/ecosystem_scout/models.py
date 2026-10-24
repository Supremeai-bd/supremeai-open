"""Ecosystem Scout models — ScoutFinding + Recommendation (#4055).

বাংলা: ScoutFinding = একটি discovered repo/technology। Recommendation = filtered
+ scored finding ready for auditor review।
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FindingSource(StrEnum):
    """Where the finding was discovered."""

    GITHUB_TRENDING = "github_trending"
    X_POST = "x_post"
    REDDIT = "reddit"
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    MANUAL = "manual"


class FindingStatus(StrEnum):
    """Status of a finding in the pipeline."""

    NEW = "new"
    DEDUPED = "deduped"
    GAP_ANALYZED = "gap_analyzed"
    SCORED = "scored"
    AUDITOR_APPROVED = "auditor_approved"
    AUDITOR_REJECTED = "auditor_rejected"
    ISSUE_CREATED = "issue_created"
    ADMIN_GATE = "admin_gate"


@dataclass(frozen=True)
class ScoutFinding:
    """A single discovered repo/technology."""

    finding_id: str
    source: FindingSource
    repo_name: str
    repo_url: str
    description: str
    stars: int = 0
    language: str = ""
    topics: list[str] = field(default_factory=list)
    discovered_at: str = field(default_factory=lambda: _dt.datetime.utcnow().isoformat() + "Z")
    fingerprint: str = ""
    status: FindingStatus = FindingStatus.NEW
    gap_analysis: dict[str, Any] = field(default_factory=dict)
    recommendation_score: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "source": self.source.value,
            "repo_name": self.repo_name,
            "repo_url": self.repo_url,
            "description": self.description,
            "stars": self.stars,
            "language": self.language,
            "topics": self.topics,
            "discovered_at": self.discovered_at,
            "fingerprint": self.fingerprint,
            "status": self.status.value,
            "gap_analysis": self.gap_analysis,
            "recommendation_score": round(self.recommendation_score, 4),
            "details": self.details,
        }


@dataclass(frozen=True)
class Recommendation:
    """A scored recommendation ready for auditor review."""

    finding: ScoutFinding
    score: float
    relevance: float
    improvement: float
    cost: float
    reason: str
    is_architectural: bool = False
    auditor_reviewed: bool = False
    auditor_approved: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding": self.finding.to_dict(),
            "score": round(self.score, 4),
            "relevance": round(self.relevance, 4),
            "improvement": round(self.improvement, 4),
            "cost": round(self.cost, 4),
            "reason": self.reason,
            "is_architectural": self.is_architectural,
            "auditor_reviewed": self.auditor_reviewed,
            "auditor_approved": self.auditor_approved,
        }


def make_finding(
    source: FindingSource,
    repo_name: str,
    repo_url: str,
    description: str,
    **kwargs: Any,
) -> ScoutFinding:
    """Create a ScoutFinding with auto-generated ID + fingerprint."""
    fingerprint_input = f"{repo_name.lower().strip()}|{description[:200].lower().strip()}"
    fingerprint = hashlib.sha256(fingerprint_input.encode()).hexdigest()[:16]

    return ScoutFinding(
        finding_id=f"sf-{uuid.uuid4().hex[:12]}",
        source=source,
        repo_name=repo_name,
        repo_url=repo_url,
        description=description,
        fingerprint=fingerprint,
        **kwargs,
    )
