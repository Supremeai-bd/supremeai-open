"""Recommender — score findings (relevance × improvement × cost) (#4055).

বাংলা: প্রতিটি finding-এর recommendation score compute করে। score > threshold
হলে auditor review-এ যায়।
"""

from __future__ import annotations

from dataclasses import replace

from ..models import Recommendation, ScoutFinding

# Threshold: findings with score < this are filtered out before auditor review
RECOMMENDATION_THRESHOLD = 0.4

# Keywords that increase relevance to SupremeAI
RELEVANCE_KEYWORDS = {
    "ai",
    "llm",
    "agent",
    "automation",
    "coding",
    "memory",
    "context",
    "inference",
    "provider",
    "router",
    "governance",
    "security",
    "sandbox",
    "mcp",
    "tool",
    "browser",
    "scraping",
    "analytics",
}

# Keywords that indicate architectural significance (→ Tier-3 admin gate)
ARCHITECTURAL_KEYWORDS = {
    "architecture",
    "constitutional",
    "core",
    "foundation",
    "breaking",
    "migration",
    "rewrite",
    "deprecated",
}


def score_finding(finding: ScoutFinding) -> Recommendation:
    """Score a finding for recommendation.

    বাংলা: relevance × improvement × cost = recommendation score।
    score > threshold হলে auditor review-এ যায়।

    Args:
        finding: ScoutFinding with gap_analysis already populated

    Returns:
        Recommendation with score + breakdown
    """
    # Relevance: based on topic/keyword match with SupremeAI domain
    relevance = _compute_relevance(finding)

    # Improvement: based on stars + gap (new gap = higher improvement potential)
    improvement = _compute_improvement(finding)

    # Cost: based on language + complexity (lower cost = higher score)
    cost = _compute_cost(finding)

    # Overall score = geometric mean (penalizes any single low dimension)
    score = (relevance * improvement * cost) ** (1.0 / 3.0)

    # Check if architectural (→ Tier-3 admin gate)
    is_architectural = _is_architectural(finding)

    reason = (
        f"relevance={relevance:.2f} (topic match) × "
        f"improvement={improvement:.2f} (stars={finding.stars}, gap={finding.gap_analysis.get('gap', False)}) × "
        f"cost={cost:.2f} (lang={finding.language or 'unknown'}) → "
        f"score={score:.4f}"
    )

    return Recommendation(
        finding=finding,
        score=score,
        relevance=relevance,
        improvement=improvement,
        cost=cost,
        reason=reason,
        is_architectural=is_architectural,
    )


def _compute_relevance(finding: ScoutFinding) -> float:
    """Compute relevance score (0.0-1.0) based on keyword match."""
    text = f"{finding.repo_name} {finding.description} {' '.join(finding.topics)}".lower()
    matches = sum(1 for kw in RELEVANCE_KEYWORDS if kw in text)
    # 3+ matches → 1.0, 0 matches → 0.2 (baseline)
    return min(1.0, 0.2 + matches * 0.25)


def _compute_improvement(finding: ScoutFinding) -> float:
    """Compute improvement potential (0.0-1.0)."""
    # Stars: more stars → more proven → higher improvement potential
    star_score = min(1.0, finding.stars / 50000.0)  # 50k stars → 1.0

    # Gap: if it fills a gap (not in inventory) → bonus
    gap_bonus = 0.2 if finding.gap_analysis.get("gap", False) else 0.0

    return min(1.0, star_score + gap_bonus)


def _compute_cost(finding: ScoutFinding) -> float:
    """Compute cost score (0.0-1.0, higher = lower cost = better)."""
    # Python → easy integration (high score)
    # TypeScript/JS → medium
    # C++/Rust/Go → harder (lower score)
    lang = finding.language.lower()
    if lang in ("python", ""):
        return 0.9
    if lang in ("typescript", "javascript"):
        return 0.7
    if lang in ("go", "rust"):
        return 0.5
    if lang in ("c++", "c"):
        return 0.3
    return 0.6  # unknown


def _is_architectural(finding: ScoutFinding) -> bool:
    """Check if finding is architecturally significant (→ Tier-3)."""
    text = f"{finding.repo_name} {finding.description}".lower()
    return any(kw in text for kw in ARCHITECTURAL_KEYWORDS)


def filter_recommendations(
    recommendations: list[Recommendation],
    threshold: float = RECOMMENDATION_THRESHOLD,
) -> list[Recommendation]:
    """Filter recommendations by score threshold.

    বাংলা: score < threshold ফিল্টার হয়ে যায় — auditor শুধু high-score findings দেখে।
    """
    return [r for r in recommendations if r.score >= threshold]


def score_findings_batch(findings: list[ScoutFinding]) -> list[Recommendation]:
    """Score a batch of findings → Recommendations."""
    return [score_finding(f) for f in findings]
