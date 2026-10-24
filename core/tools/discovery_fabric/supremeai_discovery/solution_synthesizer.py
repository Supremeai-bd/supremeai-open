from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .trust_engine import Evidence, aggregate


@dataclass
class SolutionCandidate:
    name: str
    approach: str
    sources: list[dict[str, Any]]
    expected_benefit: float
    implementation_effort: float
    risk: float
    verification_plan: list[str] = field(default_factory=list)
    confidence: float = 0.0
    verdict: str = "candidate"

    def score(self) -> float:
        return max(0.0, 0.45*self.expected_benefit + 0.25*self.confidence + 0.20*(1-self.implementation_effort) + 0.10*(1-self.risk))


def synthesize(problem: str, candidates: list[dict[str, Any]], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    ev = [Evidence(**x) for x in evidence]
    trust = aggregate(ev)
    ranked: list[dict[str, Any]] = []
    for i, c in enumerate(candidates):
        s = SolutionCandidate(
            name=c.get("name", f"solution-{i+1}"),
            approach=c.get("approach", ""),
            sources=c.get("sources", []),
            expected_benefit=float(c.get("expected_benefit", 0.5)),
            implementation_effort=float(c.get("implementation_effort", 0.5)),
            risk=float(c.get("risk", 0.5)),
            verification_plan=list(c.get("verification_plan", [])),
            confidence=float(c.get("confidence", trust["confidence"])),
        )
        s.verdict = "recommended" if s.score() >= 0.72 and s.risk <= 0.35 and trust["confidence"] >= 0.60 else "review"
        ranked.append(s.__dict__ | {"score": round(s.score(), 4)})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return {"problem": problem, "evidence_confidence": trust["confidence"], "evidence_status": trust["status"], "solutions": ranked}
