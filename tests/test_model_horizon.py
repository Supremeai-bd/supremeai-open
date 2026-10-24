"""tests/test_model_horizon.py — unit tests for gateway temporal horizon."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway.model_horizon import ModelHorizonRegistry, intercept_drift, reset_registry


def test_retired_model_flagged():
    reg = reset_registry()
    ev = reg.intercept("anthropic/claude-3-5-sonnet", as_of=date(2026, 10, 24))
    assert ev.kind == "retired"
    assert ev.successor == "anthropic/claude-sonnet-4-5"


def test_active_model_ok():
    reg = reset_registry()
    ev = reg.intercept("groq/llama-3.3-70b-versatile", as_of=date(2024, 11, 10))
    assert ev.kind in ("ok", "freeze_drift")


def test_cutoff_stale():
    reg = reset_registry()
    ev = reg.intercept("groq/llama-3.3-70b-versatile", as_of=date(2025, 6, 1))
    assert ev.kind == "cutoff_stale"


def test_unknown_model():
    reg = reset_registry()
    ev = reg.intercept("nope/model", as_of=date(2026, 1, 1))
    assert ev.kind == "unknown"


def test_all_models_loaded():
    reg = reset_registry()
    assert len(reg.all()) >= 7


def test_intercept_drift_helper():
    reset_registry()
    ev = intercept_drift("anthropic/claude-3-5-sonnet", as_of=date(2026, 10, 24))
    assert ev.kind == "retired"


def test_drift_days_positive_after_freeze():
    reg = reset_registry()
    mh = reg.get("groq/llama-3.3-70b-versatile")
    assert mh is not None
    assert mh.drift_days(date(2024, 11, 20)) >= 5
