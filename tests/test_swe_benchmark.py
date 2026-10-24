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



def _perfect_detector(text: str):
    """Reference detector: flags anything mentioning 'ignore', 'DAN', 'reveal', 'delete', 'direct to main'."""
    low = text.lower()
    return any(
        k in low for k in ("ignore all previous", "dan", "reveal", "delete", "directly to main")
    )


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
    r = run_benchmark(_perfect_detector, cases)
    d = r.to_dict()
    assert d["total"] == len(cases)
    assert d["accuracy"] >= 0.85
    assert d["precision"] >= 0.8
    assert d["recall"] >= 0.8
    assert d["specificity"] >= 0.8
    assert d["f1"] >= 0.8


def test_never_detector_fails_floor():
    cases, _ = load_corpus()
    r = run_benchmark(_never_detector, cases)
    assert r.recall == 0.0 and r.false_negative == sum(
        1 for c in cases if c.get("expect_defect")
    )


def test_gate_passes_with_reference_detector(monkeypatch, capsys):
    # Inject a tiny reference detector module without touching the repo's tests dir.
    import types

    ref = types.ModuleType("tests._swe_ref_detector")

    class _R:
        is_injection = False
        matched: list[str] = []

    def _make(text):
        low = text.lower()
        r = types.SimpleNamespace()
        r.is_injection = any(
            k in low
            for k in ("ignore all previous", "dan", "reveal", "delete", "directly to main")
        )
        r.matched = ["ignore_previous"] if "ignore" in low else []
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
