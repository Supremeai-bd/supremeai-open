"""Proposal-only risk scoring with bounded noise and no autonomous execution."""

from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RiskProposal:
    proposal_id: str
    score: float
    severity: str
    signals: tuple[str, ...]
    recommended_action: str
    requires_approval: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PrecognitiveRiskScorer:
    def __init__(self, *, noise_budget: float = 0.03) -> None:
        self.noise_budget = max(0.0, min(0.2, noise_budget))

    def propose(
        self, task: str, *, failure_rate: float = 0.0, irreversible: bool = False
    ) -> RiskProposal:
        normalized = task.strip().lower()
        signals: list[str] = []
        score = max(0.0, min(1.0, failure_rate))
        if irreversible:
            score += 0.45
            signals.append("irreversible action")
        if any(
            word in normalized
            for word in ("delete", "deploy", "payment", "credential", "production")
        ):
            score += 0.2
            signals.append("high-impact keyword")
        if failure_rate > 0:
            signals.append("recent failures")
        digest = hashlib.sha256(normalized.encode()).digest()
        noise = (random.Random(digest).random() * 2 - 1) * self.noise_budget
        score = max(0.0, min(1.0, score + noise))
        severity = "high" if score >= 0.65 else "medium" if score >= 0.35 else "low"
        return RiskProposal(
            proposal_id=f"risk_{hashlib.sha256(normalized.encode()).hexdigest()[:16]}",
            score=round(score, 4),
            severity=severity,
            signals=tuple(signals),
            recommended_action="request human approval"
            if severity != "low"
            else "allow with monitoring",
        )


precognitive_risk = PrecognitiveRiskScorer()

__all__ = ["PrecognitiveRiskScorer", "RiskProposal", "precognitive_risk"]
