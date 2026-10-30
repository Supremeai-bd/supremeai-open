#!/usr/bin/env python3
"""Hermetic tests for scripts/ci/pr_landing_age_guard.py (parity heal #3665).

The guard landed without a dedicated test file; its verdict core is pure and
offline, so every class is proven here with zero network. Mirrors the guard's
own self_test() matrix and pins the census rollup contract.
"""

from datetime import datetime, timezone

from scripts.ci.pr_landing_age_guard import (
    DEFAULT_MAX_AGE_HOURS,
    _age_hours,
    census,
    classify_pr,
    self_test,
)

NOW = datetime.strptime("2026-10-31T17:22:00Z", "%Y-%m-%dT%H:%M:%SZ").replace(
    tzinfo=timezone.utc
).timestamp()
FRESH = "2026-10-31T16:00:00Z"     # <2h old
STALE = "2026-10-30T12:00:00Z"     # ~29h old


def test_self_test_matrix_all_green():
    results = self_test()
    assert results, "self_test returned no cases"
    bad = [(name, why) for name, ok, why in results if not ok]
    assert not bad, f"self_test failures: {bad}"


def test_age_hours_parseable_and_honest_none():
    age = _age_hours(FRESH, NOW)
    assert age is not None and 0.0 < age <= DEFAULT_MAX_AGE_HOURS
    assert _age_hours("", NOW) is None
    assert _age_hours("not-a-timestamp", NOW) is None
    assert _age_hours("2026-13-99T99:99:99Z", NOW) is None


def test_classify_in_flight():
    v = classify_pr({"number": 1, "createdAt": FRESH, "updatedAt": FRESH}, NOW)
    assert v["verdict"] == "IN_FLIGHT"
    assert v["never_touched"] is True  # fresh row counts as in-flight regardless


def test_classify_stranded_never_touched():
    v = classify_pr({"number": 2, "createdAt": STALE, "updatedAt": STALE}, NOW)
    assert v["verdict"] == "STRANDED_NEVER_TOUCHED"
    assert v["never_touched"] is True
    assert v["age_hours"] >= DEFAULT_MAX_AGE_HOURS


def test_classify_stranded_touched():
    v = classify_pr(
        {"number": 3, "createdAt": STALE, "updatedAt": "2026-10-31T10:00:00Z"}, NOW
    )
    assert v["verdict"] == "STRANDED_TOUCHED"
    assert v["never_touched"] is False


def test_classify_no_timestamp_is_honest_no_signal():
    v = classify_pr({"number": 4, "createdAt": "", "updatedAt": ""}, NOW)
    assert v["verdict"] == "NO_TIMESTAMP"
    assert v["age_hours"] is None


def test_census_rollup_contract():
    verdicts = [
        classify_pr({"number": 1, "createdAt": FRESH, "updatedAt": FRESH}, NOW),
        classify_pr({"number": 2, "createdAt": STALE, "updatedAt": STALE}, NOW),
        classify_pr({"number": 3, "createdAt": STALE, "updatedAt": "2026-10-31T10:00:00Z"}, NOW),
        classify_pr({"number": 4, "createdAt": "", "updatedAt": ""}, NOW),
    ]
    c = census(verdicts)
    assert c["total"] == 4
    assert c["IN_FLIGHT"] == 1
    assert c["STRANDED_NEVER_TOUCHED"] == 1
    assert c["STRANDED_TOUCHED"] == 1
    assert c["NO_TIMESTAMP"] == 1
    assert c["stranded_total"] == c["STRANDED_NEVER_TOUCHED"] + c["STRANDED_TOUCHED"] == 2
