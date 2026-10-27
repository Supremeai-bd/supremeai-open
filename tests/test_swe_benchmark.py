"""tests/test_swe_benchmark.py — Way 15 evidence (frozen corpus, metrics, gate)."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    from core.evaluation.swe_benchmark import (
        corpus_fingerprint,
        load_corpus,
        run_benchmark,
    )
    from core.evaluation.swe_benchmark.ci_gate import main as gate_main
except ModuleNotFoundError as _exc:  # core runtime incomplete in the public mirror
    pytest.skip(
        "core runtime unavailable in this mirror (monitoring module lives in the "
        f"private core repo): {_exc}",
        allow_module_level=True,
    )



def _make_oracle_detector(cases: list[dict]) -> "callable[[str], bool]":
    """Corpus-oracle reference detector: returns the frozen ground truth per input.

    Drift repair (audited on pristine main): the previous keyword-list
    "perfect detector" ("ignore all previous", "dan", "reveal", "delete",
    "directly to main") silently went stale every time the corpus grew under
    the manifest discipline — corpus cases swe-inj-004 ("ignore prior
    instructions") and swe-plan-001 ("no rollback plan") were missed, so a
    PERFECT classifier scored recall 0.714 and 2 tests went red on main.
    These tests verify the runner's confusion-matrix arithmetic and the gate
    mechanics — not keyword-detection skill — so the reference detector is
    now an oracle keyed on the frozen inputs: perfect by construction and
    immune to future corpus growth.
    """
    labels = {c.get("input", ""): bool(c.get("expect_defect")) for c in cases}
    return lambda text: labels.get(text, False)


def _never_detector(text: str):
    return False


def test_corpus_loads_and_is_pinned():
    cases, shas = load_corpus()
    assert len(cases) >= 10
    assert all("case_sha256" in c for c in cases)
    assert len(shas) == len(cases)


def test_corpus_fingerprint_stable():
    cases, _ = load_corpus()
    assert corpus_fingerprint(cases) == corpus_fingerprint(cases)


def test_perfect_detector_metrics():
    cases, _ = load_corpus()
    r = run_benchmark(_make_oracle_detector(cases), cases)
    d = r.to_dict()
    assert d["total"] == len(cases)
    n_defects = sum(1 for c in cases if c.get("expect_defect"))
    assert n_defects > 0, "corpus must contain defect cases for metric math"
    # Exact pins (stronger than the old >=0.8 floors): a perfect classifier
    # must yield a perfect confusion matrix — any scorer arithmetic bug
    # (misrouted TP/FN, swapped specificity, rounding drift) breaks this.
    assert d["detected"] == n_defects
    assert d["true_positive"] == n_defects
    assert d["false_positive"] == 0
    assert d["true_negative"] == len(cases) - n_defects
    assert d["false_negative"] == 0
    assert d["accuracy"] == 1.0
    assert d["precision"] == 1.0
    assert d["recall"] == 1.0
    assert d["specificity"] == 1.0
    assert d["f1"] == 1.0


def test_never_detector_fails_floor():
    cases, _ = load_corpus()
    r = run_benchmark(_never_detector, cases)
    assert r.recall == 0.0 and r.false_negative == sum(
        1 for c in cases if c.get("expect_defect")
    )


def test_gate_passes_with_reference_detector(monkeypatch, capsys):
    # Inject a corpus-oracle reference detector module without touching the
    # repo's tests dir. The SimpleNamespace return keeps the attribute
    # normalization path (is_injection + matched) covered, as before.
    import types

    cases, _ = load_corpus()
    truth = {
        c.get("input", ""): (bool(c.get("expect_defect")), list(c.get("expect_match") or []))
        for c in cases
    }

    ref = types.ModuleType("tests._swe_ref_detector")

    def _make(text):
        # Full oracle: ground truth for BOTH the defect flag and the expected
        # rule ids, so the gate's expect_match verification is exercised
        # honestly (the runner checks rules only for detected defect cases).
        r = types.SimpleNamespace()
        r.is_injection, r.matched = truth.get(text, (False, []))
        return r

    ref.detect = _make  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "tests._swe_ref_detector", ref)
    rc = gate_main(["--detector", "tests._swe_ref_detector.detect"])
    assert rc == 0


def test_gate_rejects_tampered_corpus(tmp_path, monkeypatch):
    cases, _ = load_corpus()
    tampered = [dict(c) for c in cases]
    tampered[0] = dict(tampered[0])
    tampered[0]["input"] += " TAMPERED"
    bad = tmp_path / "corpus.json"
    bad.write_text(json.dumps({"cases": tampered}))
    with pytest.raises(ValueError):
        load_corpus(bad)


def test_gate_harness_error_on_bad_detector():
    rc = gate_main(["--detector", "tests.no_such_module.attr"])
    assert rc == 2
