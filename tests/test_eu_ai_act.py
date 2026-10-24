"""tests/test_eu_ai_act.py — Way 29 evidence (risk tiers, penalties, Annex IV gaps)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from core.governance.eu_ai_act import (
    ANNEX_IV_CHECKLIST,
    RiskTier,
    classify_risk,
    doc_gap_review,
    estimate_penalty,
)
except ModuleNotFoundError as _exc:  # core runtime incomplete in the public mirror
    pytest.skip(
        "core runtime unavailable in this mirror (monitoring module lives in the "
        f"private core repo): {_exc}",
        allow_module_level=True,
    )



def test_prohibited_social_scoring():
    a = classify_risk("System computes a social scoring of citizens based on behaviour.")
    assert a.tier is RiskTier.PROHIBITED
    assert a.matched_rule == "art5.a"


def test_high_risk_employment_screening():
    a = classify_risk("CV screening of job applicants and worker management scheduling.")
    assert a.tier is RiskTier.HIGH
    assert a.matched_rule.startswith("annex3.")
    assert "human oversight (Art. 14)" in a.obligations


def test_limited_chatbot_transparency():
    a = classify_risk("A chatbot that customers interact with on the pricing page.")
    assert a.tier is RiskTier.LIMITED
    assert a.matched_rule == "art50.1"


def test_minimal_fallback():
    a = classify_risk("A test-data fixture generator for internal unit tests.")
    assert a.tier is RiskTier.MINIMAL


def test_empty_description_fail_open():
    a = classify_risk("")
    assert a.tier is RiskTier.MINIMAL and a.matched_rule == "no-description"


def test_strictest_tier_wins():
    a = classify_risk("Chatbot with social scoring of citizens.")
    assert a.tier is RiskTier.PROHIBITED


def test_penalty_tiers():
    p35 = estimate_penalty(RiskTier.PROHIBITED, global_turnover_eur=1_000_000_000)
    assert p35["flat_cap_eur"] == 35_000_000 and p35["turnover_fraction"] == 0.07
    p15 = estimate_penalty(RiskTier.HIGH, global_turnover_eur=100_000_000)
    assert p15["flat_cap_eur"] == 15_000_000 and p15["turnover_fraction"] == 0.03
    p7 = estimate_penalty(RiskTier.MINIMAL, global_turnover_eur=10_000_000)
    assert p7["flat_cap_eur"] == 7_500_000 and p7["turnover_fraction"] == 0.01


def test_penalty_uses_max_cap_when_repeated():
    # 1% of 10M = 100k < 7.5M flat cap; repeated → higher cap wins (7.5M).
    p = estimate_penalty(RiskTier.MINIMAL, 10_000_000, is_repeated=True)
    assert p["worst_case_eur"] == 7_500_000


def test_penalty_accepts_str_tier_and_never_negative():
    p = estimate_penalty("high", -5)  # negative turnover tolerated → 0
    assert p["turnover_cap_eur"] == 0.0
    assert p["worst_case_eur"] > 0


def test_annex_iv_checklist_and_gap_review():
    assert len(ANNEX_IV_CHECKLIST) == 10
    full = doc_gap_review([
        "1. General description of the system", "2. Instructions for use",
        "3. Detailed information on design, architecture", "4. Data: sources",
        "5. Metrics: accuracy", "6. Human oversight measures", "7. Logging design",
        "8. Post-market monitoring plan", "9. Conformity assessment results",
        "10. Changes since the last conformity assessment",
    ])
    assert full["coverage_ratio"] == 1.0 and full["missing"] == []
    empty = doc_gap_review([])
    assert empty["covered"] == [] and len(empty["missing"]) == 10
