"""Pattern miner — cluster decisions by (task_type, decision_type, outcome) (#4054).

বাংলা: DecisionMetadata records থেকে patterns mine করে। successful patterns
(≥3 occurrences + outcome=success) → skill template candidates। failed patterns
(≥2 occurrences + outcome=failure) → regression guard candidates।
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DecisionPattern:
    """A cluster of decisions with the same (task_type, decision_type, outcome)."""

    task_type: str
    decision_type: str  # "provider_choice", "tool_use", "task_approach"
    outcome: str  # "success", "failure", "ambiguous"
    count: int
    sample_decision_ids: list[str] = field(default_factory=list)
    common_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0  # 0.0-1.0 (higher = more confident pattern is real)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "decision_type": self.decision_type,
            "outcome": self.outcome,
            "count": self.count,
            "sample_decision_ids": self.sample_decision_ids[:5],  # cap for display
            "common_evidence": self.common_evidence[:5],
            "confidence": round(self.confidence, 4),
        }


def mine_patterns(
    decisions: list[dict[str, Any]],
    min_occurrences: int = 3,
) -> list[DecisionPattern]:
    """Mine patterns from a list of decision metadata records.

    বাংলা: DecisionMetadata records থেকে patterns mine করে। প্রতিটি unique
    (task_type, decision_type, outcome) combination একটি pattern।

    Args:
        decisions: list of decision metadata dicts (from #4052 DecisionMetadata)
        min_occurrences: minimum count to be considered a pattern (default 3)

    Returns:
        list of DecisionPattern sorted by count (descending)
    """
    clusters: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

    for d in decisions:
        task_type = d.get("task_type", "unknown")
        decision_type = d.get("decision_type", "unknown")
        outcome = d.get("outcome", "unknown")
        key = (task_type, decision_type, outcome)
        clusters[key].append(d)

    patterns: list[DecisionPattern] = []
    for (task_type, decision_type, outcome), records in clusters.items():
        if len(records) < min_occurrences:
            continue

        # Collect evidence + decision IDs
        evidence_set: set[str] = set()
        decision_ids: list[str] = []
        for r in records:
            decision_ids.append(r.get("decision_id", r.get("id", "")))
            for ev in r.get("evidence", []) or []:
                if isinstance(ev, str):
                    evidence_set.add(ev)

        # Confidence = count / (count + 2) — simple Bayesian-ish smoothing
        count = len(records)
        confidence = min(1.0, count / (count + 2.0))

        patterns.append(
            DecisionPattern(
                task_type=task_type,
                decision_type=decision_type,
                outcome=outcome,
                count=count,
                sample_decision_ids=decision_ids,
                common_evidence=list(evidence_set),
                confidence=confidence,
            )
        )

    # Sort by count descending
    return sorted(patterns, key=lambda p: p.count, reverse=True)


def filter_successful_patterns(patterns: list[DecisionPattern]) -> list[DecisionPattern]:
    """Filter to only successful patterns (candidates for skill templates)."""
    return [p for p in patterns if p.outcome == "success" and p.confidence >= 0.5]


def filter_failed_patterns(patterns: list[DecisionPattern]) -> list[DecisionPattern]:
    """Filter to only failed patterns (candidates for regression guards)."""
    return [p for p in patterns if p.outcome == "failure"]
