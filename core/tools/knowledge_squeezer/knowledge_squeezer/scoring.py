from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Score:
    overall: float
    consensus: float
    coverage: float
    contradiction: float
    evidence: float
    novelty: float
    verification: float

    def as_dict(self) -> dict[str, float]:
        return self.__dict__.copy()


def score_artifact(
    *,
    candidate_count: int,
    critique_count: int,
    gap_count: int,
    contradiction_count: int,
    evidence_count: int,
    novelty: float,
    verification: float,
) -> Score:
    consensus = min(1.0, candidate_count / 3.0) * min(1.0, (candidate_count - contradiction_count) / max(candidate_count, 1))
    coverage = min(1.0, (critique_count + gap_count + evidence_count) / 12.0)
    contradiction = max(0.0, 1.0 - min(1.0, contradiction_count / max(candidate_count, 1)))
    evidence_score = min(1.0, evidence_count / 5.0)
    overall = (
        0.25 * consensus
        + 0.20 * coverage
        + 0.15 * contradiction
        + 0.20 * evidence_score
        + 0.10 * max(0.0, min(1.0, novelty))
        + 0.10 * max(0.0, min(1.0, verification))
    )
    return Score(
        overall=max(0.0, min(1.0, overall)),
        consensus=consensus,
        coverage=coverage,
        contradiction=contradiction,
        evidence=evidence_score,
        novelty=max(0.0, min(1.0, novelty)),
        verification=max(0.0, min(1.0, verification)),
    )
