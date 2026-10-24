"""Provider Intelligence — Sprint 5 (bounded, evidence-driven, reversible).

Implements the plan's §8.1/§8.2/§7.2 rules:

  * provider_score from MEASURED provider_metrics rows (never fabricated):
    quality (success rate) + reliability (rate-limit resistance) + latency
    (p95 vs reference) + cost (est cost vs reference), fixed configurable
    weights, output clamped to [0, 1].
  * Sample-size tiers (plan §7.2): <10 observations = INSUFFICIENT evidence
    → the provider may NEVER be ranked preferred (§8.1); 10-49 = cautious
    (score discounted); 50+ = normal evaluation.
  * Exploration vs exploitation (§8.2): ``exploration_candidate`` returns at
    most ONE alternative provider for limited measurement so the system can
    never permanently lock onto an initially lucky provider.

Pure functions only — no network, no state; the LearningLoopAgent refreshes
an in-process score snapshot each cycle and the gateway reads it behind
ENABLE_ADAPTIVE_ROUTING (default false).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "MIN_SAMPLES_CAUTIOUS",
    "MIN_SAMPLES_NORMAL",
    "ProviderScore",
    "compute_provider_scores",
    "exploration_candidate",
    "get_adaptive_routing_enabled",
    "score_snapshot",
]

MIN_SAMPLES_CAUTIOUS = 10
MIN_SAMPLES_NORMAL = 50

# Fixed weights (sum = 1.0). Configurable via env, bounded to [0, 1] each.
_DEFAULT_WEIGHTS = {
    "quality": 0.45,
    "reliability": 0.25,
    "latency": 0.15,
    "cost": 0.15,
}
# Reference points for the bounded component scores.
_P95_REFERENCE_MS = 1000.0
_COST_REFERENCE_USD = 0.01


@dataclass
class ProviderScore:
    """One measured provider/model evaluation (no fabricated fields)."""

    provider: str
    model: str
    requests: int
    successes: int
    failures: int
    rate_limited: int
    latency_p95_ms: float | None
    estimated_cost: float
    sample_tier: str  # "insufficient" | "cautious" | "normal"
    score: float  # bounded [0,1]; 0.0 for insufficient evidence
    components: dict[str, float] = field(default_factory=dict)


def _weight(name: str) -> float:
    try:
        return min(1.0, max(0.0, float(os.getenv(f"SCORE_WEIGHT_{name.upper()}", ""))))
    except (TypeError, ValueError):
        return _DEFAULT_WEIGHTS[name]


def _sample_tier(requests: int) -> str:
    if requests < MIN_SAMPLES_CAUTIOUS:
        return "insufficient"
    if requests < MIN_SAMPLES_NORMAL:
        return "cautious"
    return "normal"


def compute_provider_scores(rows: list[dict[str, Any]] | None) -> list[ProviderScore]:
    """Deterministically score provider_metrics rows (highest score first).

    Insufficient-evidence rows get score 0.0 — they can never outrank a
    measured provider (plan §8.1). Cautious rows are discounted 50%.
    """
    scores: list[ProviderScore] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        provider = str(row.get("provider") or "").strip()
        model = str(row.get("model") or "").strip()
        if not provider or not model:
            continue
        requests = int(row.get("requests") or 0)
        successes = int(row.get("successes") or 0)
        failures = int(row.get("failures") or 0)
        rate_limited = int(row.get("rate_limited") or 0)
        p95 = row.get("latency_p95_ms")
        est_cost = float(row.get("estimated_cost") or 0.0)

        tier = _sample_tier(requests)
        total = max(1, successes + failures)
        quality = successes / float(total)
        reliability = max(0.0, 1.0 - (rate_limited / float(max(1, requests))))
        latency_score = max(0.0, 1.0 - (float(p95) / _P95_REFERENCE_MS)) if p95 is not None else 0.5
        cost_score = max(0.0, 1.0 - (est_cost / _COST_REFERENCE_USD))

        components = {
            "quality": round(min(1.0, max(0.0, quality)), 4),
            "reliability": round(reliability, 4),
            "latency": round(latency_score, 4),
            "cost": round(cost_score, 4),
        }
        raw = (
            _weight("quality") * components["quality"]
            + _weight("reliability") * components["reliability"]
            + _weight("latency") * components["latency"]
            + _weight("cost") * components["cost"]
        )
        if tier == "insufficient":
            score = 0.0  # §8.1: insufficient observations can never be preferred
        elif tier == "cautious":
            score = round(raw * 0.5, 4)
        else:
            score = round(min(1.0, max(0.0, raw)), 4)

        scores.append(
            ProviderScore(
                provider=provider,
                model=model,
                requests=requests,
                successes=successes,
                failures=failures,
                rate_limited=rate_limited,
                latency_p95_ms=float(p95) if p95 is not None else None,
                estimated_cost=est_cost,
                sample_tier=tier,
                score=score,
                components=components,
            )
        )
    scores.sort(key=lambda s: s.score, reverse=True)
    return scores


def exploration_candidate(
    scores: list[ProviderScore], epsilon: float = 0.05
) -> ProviderScore | None:
    """§8.2: return ONE alternative candidate for limited measurement.

    Deterministic (no RNG in request path): the best-scoring candidate whose
    evidence is adequate (sample_tier == "normal", M05 P-A sample-tier
    guardrail — cautious/insufficient evidence never explores) and that is
    NOT the current leader. Callers decide probabilistically whether to use
    it (bounded epsilon).
    """
    measured = [s for s in scores if s.sample_tier == "normal" and s.score > 0.0]
    if len(measured) < 2:
        return None
    leader = measured[0]
    for candidate in measured[1:]:
        if (candidate.provider, candidate.model) != (leader.provider, leader.model):
            return candidate
    return None


def get_adaptive_routing_enabled() -> bool:
    """Gateway flag: adaptive chain-tail exploration (M05 P-A দ্বিতীয় অর্ধ)।

    বাংলা মন্তব্য: সুইটেবল-ডিফল্ট true — exploration শূন্য-অতিরিক্ত-খরচ
    (চেইন-লেজে ১ candidate, normal-tier evidence-কেবল)। kill-switch অক্ষত:
    ENABLE_ADAPTIVE_ROUTING=false → flag-off = আজকের আচরণ (গেট OFF)।
    অজানা-মান fail-closed (নীরব সক্রিয় নয়)।
    """
    raw = (os.getenv("ENABLE_ADAPTIVE_ROUTING", "") or "").strip().lower()
    if raw == "false":
        return False  # সুস্পষ্ট kill-switch
    if raw == "true":
        return True
    if raw == "":
        return True  # সুইটেবল-ডিফল্ট: bounded exploration খোলা
    return False  # অজানা-মান → fail-closed


# In-process snapshot refreshed by the LearningLoopAgent (no network in
# request path). Bounded size by construction (one row per provider/model).
score_snapshot: list[ProviderScore] = []


def refresh_score_snapshot(rows: list[dict[str, Any]] | None) -> list[ProviderScore]:
    """Recompute + cache the process-wide score snapshot. Returns the scores."""
    global score_snapshot
    score_snapshot = compute_provider_scores(rows)
    return score_snapshot
