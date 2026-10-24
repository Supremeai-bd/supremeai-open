# backend/learning/experience.py
"""Experience Ledger and Record Primitives for Continual Learning."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging_config import logger


@dataclass
class ExperienceRecord:
    """Immutable record of an executed task with full causal and provenance tracking."""

    task_id: str
    goal: str
    experience_id: str = field(default_factory=lambda: f"exp_{uuid.uuid4().hex[:10]}")
    trace_id: str | None = None
    proposal_id: str | None = None
    plan_steps_count: int = 0
    tools_used: list[str] = field(default_factory=list)
    providers_used: list[str] = field(default_factory=list)
    verified: bool = False
    verification_score: float = 0.0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    failures: list[str] = field(default_factory=list)
    user_feedback: str | None = None
    lessons_extracted: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "task_id": self.task_id,
            "trace_id": self.trace_id,
            "proposal_id": self.proposal_id,
            "goal": self.goal,
            "plan_steps_count": self.plan_steps_count,
            "tools_used": self.tools_used,
            "providers_used": self.providers_used,
            "verified": self.verified,
            "verification_score": self.verification_score,
            "cost_usd": self.cost_usd,
            "latency_ms": self.latency_ms,
            "failures": self.failures,
            "user_feedback": self.user_feedback,
            "lessons_extracted": self.lessons_extracted,
            "timestamp": self.timestamp,
        }


class ExperienceStore:
    """In-memory and persistent Experience Ledger."""

    def __init__(self, storage_dir: str | None = None) -> None:
        self.storage_dir = Path(storage_dir or os.path.expanduser("~/.supremeai/experience"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[ExperienceRecord] = []

    def record(self, experience: ExperienceRecord) -> None:
        self.records.append(experience)
        try:
            filepath = self.storage_dir / f"{experience.experience_id}.json"
            with open(filepath, "w", encoding="utf-8") as fh:
                json.dump(experience.to_dict(), fh, indent=2)
        except Exception as exc:
            logger.warning(f"Could not persist experience {experience.experience_id}: {exc}")

    def get_recent(self, limit: int = 50) -> list[ExperienceRecord]:
        return self.records[-limit:]


# Global Singleton
_experience_store: ExperienceStore | None = None


def get_experience_store() -> ExperienceStore:
    global _experience_store
    if _experience_store is None:
        _experience_store = ExperienceStore()
    return _experience_store
