from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Evidence:
    source_type: str
    url: str
    claim: str
    authority: float
    freshness: float
    reproducibility: float
    directness: float
    conflict: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return max(0.0, min(1.0, 0.30*self.authority + 0.25*self.freshness + 0.20*self.reproducibility + 0.20*self.directness - 0.20*self.conflict))


def freshness_from_iso(value: str | None) -> float:
    if not value:
        return 0.4
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
        days = max(0, (datetime.now(timezone.utc) - t).days)
        return max(0.05, 1 - min(days, 3650) / 3650)
    except Exception:
        return 0.4


def aggregate(evidence: Iterable[Evidence]) -> dict:
    items = list(evidence)
    if not items:
        return {"confidence": 0.0, "status": "unverified", "evidence": []}
    scores = sorted((e.score for e in items), reverse=True)
    # Two independent sources are materially stronger than one.
    independence_bonus = min(0.20, 0.10 * (len({e.source_type for e in items}) - 1))
    conflict_penalty = min(0.30, sum(e.conflict for e in items) / len(items))
    confidence = min(1.0, (0.60 * scores[0] + 0.25 * (scores[1] if len(scores) > 1 else 0) + 0.15 * (sum(scores) / len(scores))) + independence_bonus - conflict_penalty)
    status = "verified" if confidence >= 0.80 else "probable" if confidence >= 0.60 else "weak"
    return {"confidence": round(confidence, 4), "status": status, "evidence": [e.__dict__ | {"score": round(e.score, 4)} for e in items]}
