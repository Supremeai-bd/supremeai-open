"""tests/test_model_churn_gate.py — unit tests for the token-churn regression gate (#1662).

The gate must fail closed: any missing baseline, malformed artifact, task-set
mismatch, or degenerate baseline metric blocks the bump. Budget boundaries
come from the admin-ratified reopen of #1662 (>30% output-token growth or >2x
diff churn, without a same-task quality case).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway.model_churn_gate import (
    ALLOW,
    BLOCK,
    LEDGER_SCHEMA,
    evaluate_bump,
    load_ledger,
    main,
)


def _ledger(**baseline_overrides):
    baseline = {
        "output_tokens": 1000,
        "diff_files_changed": 10,
        "task_set_id": "golden-2026-10",
        "quality_score": 0.80,
        "measured_at": "2026-10-01",
    }
    baseline.update(baseline_overrides)
    return {"schema": LEDGER_SCHEMA, "entries": {"incumbent-a": baseline}}


def _candidate(**overrides):
    cand = {
        "model_id": "candidate-b",
        "baseline_id": "incumbent-a",
        "output_tokens": 1100,       # +10% growth
        "diff_files_changed": 12,    # 1.2x churn
        "task_set_id": "golden-2026-10",
    }
    cand.update(overrides)
    return cand


# ---------- budget math ----------

def test_within_budget_allows():
    v = evaluate_bump(_candidate(), _ledger())
    assert v.allowed and v.kind == ALLOW


def test_exactly_at_budget_allows():
    # >30% blocks; exactly 30% does not. Same for exactly 2.0x churn.
    v = evaluate_bump(_candidate(output_tokens=1300, diff_files_changed=20), _ledger())
    assert v.allowed
    assert v.metrics["output_growth"] == 0.3
    assert v.metrics["churn_ratio"] == 2.0


def test_output_growth_over_budget_blocks():
    v = evaluate_bump(_candidate(output_tokens=1301), _ledger())
    assert not v.allowed and v.kind == BLOCK
    assert any("output-token growth" in r for r in v.reasons)


def test_churn_over_budget_blocks():
    v = evaluate_bump(_candidate(diff_files_changed=21), _ledger())
    assert not v.allowed
    assert any("diff churn" in r for r in v.reasons)


def test_both_over_budget_blocks_with_both_reasons():
    v = evaluate_bump(_candidate(output_tokens=2000, diff_files_changed=40), _ledger())
    assert not v.allowed
    assert len(v.reasons) == 2


def test_output_decrease_and_churn_decrease_allow():
    v = evaluate_bump(_candidate(output_tokens=500, diff_files_changed=5), _ledger())
    assert v.allowed


# ---------- quality escape hatch ----------

def test_quality_case_allows_over_budget_bump():
    v = evaluate_bump(
        _candidate(output_tokens=2000, quality_comparison={"quality_score": 0.85}),
        _ledger(),
    )
    assert v.allowed
    assert any("quality" in r for r in v.reasons)


def test_quality_regression_does_not_rescue_over_budget_bump():
    v = evaluate_bump(
        _candidate(output_tokens=2000, quality_comparison={"quality_score": 0.70}),
        _ledger(),
    )
    assert not v.allowed


def test_quality_case_without_baseline_quality_does_not_rescue():
    # Baseline has no quality_score -> comparison cannot demonstrate non-regression.
    v = evaluate_bump(
        _candidate(output_tokens=2000, quality_comparison={"quality_score": 0.9}),
        _ledger(quality_score=None),
    )
    assert not v.allowed


# ---------- fail-closed paths ----------

def test_no_baseline_blocks():
    v = evaluate_bump(_candidate(baseline_id="unknown-model"), _ledger())
    assert not v.allowed
    assert v.reasons and "no_baseline" in v.reasons[0]


def test_malformed_ledger_blocks():
    v = evaluate_bump(_candidate(), {"schema": LEDGER_SCHEMA})  # entries missing
    assert not v.allowed
    assert "malformed_ledger" in v.reasons[0]


def test_malformed_candidate_blocks():
    v = evaluate_bump({"model_id": "candidate-b"}, _ledger())
    assert not v.allowed
    assert "malformed_candidate" in v.reasons[0]


def test_task_set_mismatch_blocks():
    v = evaluate_bump(_candidate(task_set_id="other-set"), _ledger())
    assert not v.allowed
    assert "task_set_mismatch" in v.reasons[0]


def test_degenerate_baseline_blocks():
    v = evaluate_bump(_candidate(), _ledger(output_tokens=0))
    assert not v.allowed
    assert "degenerate_baseline" in v.reasons[0]


def test_non_dict_candidate_blocks():
    v = evaluate_bump("not-a-dict", _ledger())  # type: ignore[arg-type]
    assert not v.allowed


# ---------- ledger loading ----------

def test_load_ledger_round_trip(tmp_path):
    import json
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps(_ledger()), encoding="utf-8")
    loaded = load_ledger(p)
    assert loaded["schema"] == LEDGER_SCHEMA
    assert "incumbent-a" in loaded["entries"]


def test_load_ledger_rejects_bad_schema(tmp_path):
    import json
    import pytest
    p = tmp_path / "ledger.json"
    p.write_text(json.dumps({"schema": "nope/9", "entries": {}}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_ledger(p)


def test_committed_baseline_ledger_is_valid():
    """A malformed committed ledger must born-red on main (suite-enforced)."""
    ledger = load_ledger(REPO_ROOT / "gateway" / "model_churn_baseline.json")
    assert isinstance(ledger["entries"], dict)


# ---------- CLI ----------

def _cli_args(tmp_path, ledger_doc, candidate_doc):
    import json
    lp = tmp_path / "l.json"
    cp = tmp_path / "c.json"
    lp.write_text(json.dumps(ledger_doc), encoding="utf-8")
    cp.write_text(json.dumps(candidate_doc), encoding="utf-8")
    return ["--ledger", str(lp), "--candidate", str(cp)]


def test_cli_allow_exit_zero(tmp_path):
    rc = main(_cli_args(tmp_path, _ledger(), _candidate()))
    assert rc == 0


def test_cli_block_exit_two(tmp_path):
    rc = main(_cli_args(tmp_path, _ledger(), _candidate(output_tokens=2000)))
    assert rc == 2


def test_cli_config_error_exit_three(tmp_path):
    rc = main(_cli_args(tmp_path, {"schema": "bogus"}, _candidate()))
    assert rc == 3
