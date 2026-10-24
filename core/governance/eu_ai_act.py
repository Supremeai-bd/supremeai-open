"""core/governance/eu_ai_act.py — EU AI Act compliance module (Way 29).

বাংলা: EU AI Act Hub প্যাটার্নের SupremeAI অ্যাডাপ্টেশন — রিস্ক টিয়ার
শ্রেণিবিন্যাস, পেনাল্টি ক্যালকুলেটর এবং Annex IV ডকুমেন্ট চেকলিস্ট।
সব স্ট্যাটিক/ডিটারমিনিস্টিক — কোনো নেটওয়ার্ক, কোনো LLM কল নেই।

Plan contract (Way 29):
- risk classification checker  → classify_risk() -> RiskTier
- penalty calculator           → estimate_penalty()
- technical doc templates      → ANNEX_IV_CHECKLIST (+ doc_gap_review())

Sources (checked 2026-10-24, Regulation (EU) 2024/1689):
- Art. 3 / Annex III: prohibited + high-risk categories
- Art. 99: penalty tiers (EUR 35M / 7% → EUR 15M / 3% → EUR 7.5M / 1%)
- Art. 11 + Annex IV: technical documentation requirements

This is a compliance AID, not legal advice (docstring carries the disclaimer
the plan asks the studio page to render).

Local test:
    pytest tests/test_eu_ai_act.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class RiskTier(StrEnum):
    """EU AI Act risk pyramid (Art. 3, Art. 6, Annex III)."""

    PROHIBITED = "prohibited"  # Art. 5 practices (social scoring, subliminal manipulation…)
    HIGH = "high"  # Annex III domains + Art. 6 safety-component rule
    LIMITED = "limited"  # transparency obligations (chatbots, deepfakes — Art. 50)
    MINIMAL = "minimal"  # everything else (voluntary codes of conduct)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    tier: RiskTier
    matched_rule: str  # e.g. "annex3.4.a employment screening" / "art5.a social scoring"
    rationale: str
    obligations: tuple[str, ...] = ()


# Deliberately small, auditable rule tables — extend via PR, never via config hot-patch.
_ART5_PROHIBITED = (
    ("art5.a", ("social scoring", "social score", "credit score of citizens")),
    ("art5.b", ("subliminal", "manipulative technique that materially distorts")),
    ("art5.c", ("predict the commission of criminal offences", "predictive policing of individuals")),
    ("art5.d", ("facial recognition databases scraped", "untargeted scraping of facial images")),
    ("art5.e", ("emotion inference in workplace", "emotion inference in education")),
    ("art5.f", ("biometric categorisation of sensitive", "infer race, infer political opinions")),
)

_ANNEX3_HIGH = (
    ("annex3.1", ("biometric identification", "remote biometric identification")),
    ("annex3.2", ("critical infrastructure", "safety component in the management of")),
    ("annex3.3", ("education and vocational training", "admission to educational")),
    ("annex3.4", ("employment", "worker management", "recruitment", "screening of job")),
    ("annex3.5", ("essential services", "creditworthiness", "life and health insurance")),
    ("annex3.6", ("law enforcement", "assessment of the risk of an offence")),
    ("annex3.7", ("migration", "asylum", "border control")),
    ("annex3.8", ("administration of justice", "democratic processes", "election")),
)

_ART50_LIMITED = (
    ("art50.1", ("chatbot", "conversational assistant", "interact with persons")),
    ("art50.2", ("deepfake", "synthetic content", "ai-generated image", "ai-generated video")),
    ("art50.3", ("emotion recognition", "biometric categorisation disclosed to")),
)

_PENALTY_TIERS = (
    # (label, max_eur_millions, max_fraction, applies-to tiers)
    ("art99.3 prohibited", 35.0, 0.07, RiskTier.PROHIBITED),
    ("art99.4 high-risk obligations", 15.0, 0.03, RiskTier.HIGH),
    ("art99.5 incorrect information to authorities", 7.5, 0.01, RiskTier.LIMITED),
    ("art99.5 limited/minimal", 7.5, 0.01, RiskTier.MINIMAL),
)


def _matches(text: str, phrases: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(p in low for p in phrases)


def classify_risk(system_description: str) -> RiskAssessment:
    """Classify an AI system description into an EU AI Act risk tier.

    বাংলা: বর্ণনার টেক্সট প্রথমে Art.5 (নিষিদ্ধ), তারপর Annex III (high),
    তারপর Art. 50 (limited) — প্রথম মিলেই থামে, সবচেয়ে কঠোর টিয়ার আগে।
    """
    desc = (system_description or "").strip()
    if not desc:
        return RiskAssessment(
            tier=RiskTier.MINIMAL,
            matched_rule="no-description",
            rationale="Empty description — treated as minimal risk pending a real review.",
            obligations=(),
        )
    for rule, phrases in _ART5_PROHIBITED:
        if _matches(desc, phrases):
            return RiskAssessment(
                tier=RiskTier.PROHIBITED,
                matched_rule=rule,
                rationale=f"Matches prohibited practice under {rule} (Art. 5).",
                obligations=("discontinue the practice", "governance escalation"),
            )
    for rule, phrases in _ANNEX3_HIGH:
        if _matches(desc, phrases):
            return RiskAssessment(
                tier=RiskTier.HIGH,
                matched_rule=rule,
                rationale=f"Matches Annex III high-risk domain ({rule}).",
                obligations=(
                    "risk management system (Art. 9)",
                    "data governance (Art. 10)",
                    "technical documentation (Art. 11, Annex IV)",
                    "logging (Art. 12)",
                    "human oversight (Art. 14)",
                    "conformity assessment (Art. 43)",
                ),
            )
    for rule, phrases in _ART50_LIMITED:
        if _matches(desc, phrases):
            return RiskAssessment(
                tier=RiskTier.LIMITED,
                matched_rule=rule,
                rationale=f"Transparency obligation under {rule} (Art. 50).",
                obligations=("disclose AI interaction", "mark synthetic content"),
            )
    return RiskAssessment(
        tier=RiskTier.MINIMAL,
        matched_rule="default",
        rationale="No prohibited/high/limited trigger phrase matched.",
        obligations=("voluntary code of conduct (Art. 95)",),
    )


def estimate_penalty(
    tier: RiskTier | str,
    global_turnover_eur: float,
    *,
    is_repeated: bool = True,
) -> dict[str, Any]:
    """Worst-case administrative fine for a tier (Art. 99), both caps shown.

    বাংলা: টিয়ার অনুযায়ী সর্বোচ্চ জরিমানা — EUR 35M/7% (prohibited),
    15M/3% (high), 7.5M/1% (অন্য) — turnover ও ফ্ল্যাট ক্যাপের মধ্যে min।
    """
    tier = RiskTier(tier)
    found = next((t for t in _PENALTY_TIERS if t[3] == tier), _PENALTY_TIERS[-1])
    label, cap_millions, fraction, _ = found
    flat_cap = cap_millions * 1_000_000
    turnover_cap = max(0.0, global_turnover_eur) * fraction
    # Repeated infringements face the higher of the two caps (Art. 99(1)-(5) pattern).
    capped = max(flat_cap, turnover_cap) if is_repeated else min(flat_cap, turnover_cap or flat_cap)
    return {
        "tier": tier.value,
        "rule": label,
        "flat_cap_eur": flat_cap,
        "turnover_fraction": fraction,
        "turnover_cap_eur": round(turnover_cap, 2),
        "worst_case_eur": round(capped, 2),
        "is_repeated": is_repeated,
        "disclaimer": "Compliance aid only — not legal advice. Consult counsel for filings.",
    }


ANNEX_IV_CHECKLIST: tuple[str, ...] = (
    "1. General description of the system (purpose, version, provider)",
    "2. Instructions for use and intended purpose boundaries",
    "3. Detailed information on design, architecture, and development process",
    "4. Data: sources, governance, preparation, assumptions (Art. 10)",
    "5. Metrics: accuracy/robustness/cybersecurity evaluation (Art. 15)",
    "6. Human oversight measures (Art. 14)",
    "7. Logging design and record-keeping retention (Art. 12)",
    "8. Post-market monitoring plan (Art. 72)",
    "9. Conformity assessment results and notified-body involvement (Art. 43)",
    "10. Changes since the last conformity assessment (versioned diff)",
)


def doc_gap_review(existing_docs: list[str]) -> dict[str, Any]:
    """Check which Annex IV sections exist (fuzzy substring match) and which are missing.

    বাংলা: বিদ্যমান ডকুমেন্ট টাইটেলগুলোর সাথে চেকলিস্ট মিলিয়ে ঘাটতি রিপোর্ট করে।
    """
    blob = " ".join(existing_docs).lower()
    covered: list[str] = []
    missing: list[str] = []
    for item in ANNEX_IV_CHECKLIST:
        number, _, rest = item.partition(". ")
        # keyword probe = first meaningful words of the section title
        probe = next(
            (kw for kw in (
                "general description", "instructions for use", "design, architecture",
                "data:", "metrics:", "human oversight", "logging", "post-market",
                "conformity", "changes since",
            ) if kw in rest.lower()),
            rest.lower()[:24],
        )
        (covered if probe in blob else missing).append(item)
    return {
        "covered": covered,
        "missing": missing,
        "coverage_ratio": round(len(covered) / len(ANNEX_IV_CHECKLIST), 4),
    }
