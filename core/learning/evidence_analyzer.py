# backend/learning/evidence_analyzer.py
"""Statistical Evidence Analyzer for Validating Learning Patterns."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from learning.pattern_detector import DetectedPattern, EvidenceReference


@dataclass
class PatternEvidenceMetrics:
    """Rigorous statistical metrics backing an identified pattern."""

    pattern_type: str
    support: int
    population: int
    observed_rate: float
    baseline_rate: float
    effect_size: float  # Observed rate / baseline rate
    confidence_interval_low: float
    confidence_interval_high: float
    is_statistically_significant: bool
    evidence_references: list[EvidenceReference] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_type": self.pattern_type,
            "support": self.support,
            "population": self.population,
            "observed_rate": round(self.observed_rate, 4),
            "baseline_rate": round(self.baseline_rate, 4),
            "effect_size": round(self.effect_size, 2),
            "confidence_interval": [
                round(self.confidence_interval_low, 4),
                round(self.confidence_interval_high, 4),
            ],
            "is_statistically_significant": self.is_statistically_significant,
        }


class EvidenceAnalyzer:
    """Evaluates the statistical validity of detected patterns before formulating hypotheses."""

    def analyze_pattern_evidence(
        self,
        pattern: DetectedPattern,
        baseline_rate: float = 0.05,
        confidence_level_z: float = 1.96,  # 95% confidence
    ) -> PatternEvidenceMetrics:
        n = max(1, pattern.population_size)
        p = pattern.occurrence_rate
        base = max(0.001, baseline_rate)

        # Standard error: sqrt(p * (1 - p) / n)
        se = math.sqrt((p * (1.0 - p)) / n) if (0.0 < p < 1.0) else (1.0 / n)
        ci_low = max(0.0, p - (confidence_level_z * se))
        ci_high = min(1.0, p + (confidence_level_z * se))
        effect_size = p / base
        is_significant = (pattern.support_count >= 2) and (
            p >= base or effect_size >= 1.2 or ci_low > base
        )

        return PatternEvidenceMetrics(
            pattern_type=pattern.pattern_type,
            support=pattern.support_count,
            population=pattern.population_size,
            observed_rate=p,
            baseline_rate=base,
            effect_size=effect_size,
            confidence_interval_low=ci_low,
            confidence_interval_high=ci_high,
            is_statistically_significant=is_significant,
            evidence_references=pattern.evidence,
        )


# Global Singleton
_analyzer: EvidenceAnalyzer | None = None


def get_evidence_analyzer() -> EvidenceAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = EvidenceAnalyzer()
    return _analyzer
