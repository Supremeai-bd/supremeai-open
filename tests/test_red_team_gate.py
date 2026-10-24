"""tests/test_red_team_gate.py — Way 30 evidence (rubric rules, fail-closed verdicts)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from core.self_evolution.red_team_gate import RedTeamGate, RedTeamVerdict
except ModuleNotFoundError as _exc:  # core runtime incomplete in the public mirror
    pytest.skip(
        "core runtime unavailable in this mirror (monitoring module lives in the "
        f"private core repo): {_exc}",
        allow_module_level=True,
    )



GOOD_PLAN = (
    "Scope: single file, atomic slice. Replace the in-process limiter behind the "
    "existing RateDecision contract; include a rollback plan (revert commit restores "
    "previous version) and tests."
)

VAGUE_PLAN = (
    "Basically refactor lots of stuff in the gateway. Should work. Rollback is documented."
)  # vague but has rollback → warnings only


@pytest.fixture()
def gate():
    return RedTeamGate()


def test_clean_plan_passes(gate):
    v = gate.evaluate(GOOD_PLAN, model="gpt-4.1-mini")
    assert isinstance(v, RedTeamVerdict)
    assert v.passed is True
    assert v.findings == ()


def test_missing_rollback_blocks(gate):
    v = gate.evaluate("Refactor the provider chain and ship it.")
    assert v.passed is False
    assert any(f.rule == "RT-02 missing-rollback" and f.severity == "blocker" for f in v.findings)


def test_vague_quantifiers_warn(gate):
    v = gate.evaluate(VAGUE_PLAN)
    assert v.passed is True  # warnings don't block
    rules = {f.rule for f in v.findings}
    assert "RT-01 vague-quantifiers" in rules


def test_retired_model_blocks(gate):
    v = gate.evaluate(GOOD_PLAN, model="claude-instant-1")
    assert v.passed is False
    assert any(f.rule == "RT-03 retired-model" for f in v.findings)


def test_retired_model_allowed_with_flag(gate):
    v = gate.evaluate(GOOD_PLAN, model="claude-instant-1", allow_retired=True)
    assert all(f.rule != "RT-03 retired-model" for f in v.findings)


def test_scope_creep_blocks(gate):
    plan = (
        "Refactor and rewrite the entire system and redesign the whole codebase; "
        "rollback plan included."
    )
    v = gate.evaluate(plan)
    assert v.passed is False
    assert any(f.rule == "RT-04 scope-creep" for f in v.findings)


def test_empty_plan_blocks(gate):
    v = gate.evaluate("")
    assert v.passed is False
    assert v.findings[0].rule == "RT-00 empty-plan"


def test_verdict_serialisable(gate):
    v = gate.evaluate("no rollback here")
    d = v.to_dict()
    assert d["passed"] is False and isinstance(d["findings"], list)
    assert set(d["checked_rules"]) == set(RedTeamGate.RULES)
