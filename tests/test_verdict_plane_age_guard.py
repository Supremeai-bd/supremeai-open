#!/usr/bin/env python3
"""tests/test_verdict_plane_age_guard.py — fail-closed suite for #2567.

Verifies the age-bounded verdict-plane SLA gate delivered by #2567
(the audit's recommendation 4, first half — "age-bounded verdict SLA"):

  - timestamp parsing: 'Z' suffix, numeric offsets, naive-input coercion;
    empty/garbage timestamps reject with ValueError;
  - SLA bucketing: the boundary is strict (age == SLA is OK, age > SLA is
    BREACH) per invariant A;
  - sweep aggregation: totalOpen/okCount/breachCount stay consistent;
    breach ordering is oldest-first with number tie-break (invariant B);
    escalationQueue mirrors the breach ordering for consumers;
  - fail-closed row validation: missing fields, non-int numbers and
    unparseable timestamps raise ValueError (invariant C — the harness
    error path must never be silently swallowed into a PASS);
  - fingerprint: stable for identical inputs, sensitive to SLA and to the
    breach cohort (invariant E — dedup marker, automation_watchdog genre);
  - honest degradation: a missing input file and a malformed JSON file
    surface as exit 2 (harness error), never a fabricated PASS (#1760
    pattern);
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster
    (self-test mode) — the "#57 landed-unwired" recurrence class stays
    closed; never duplicated here beyond this existence check.

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_verdict_plane_age_guard.py
  - stdlib:  python3 tests/test_verdict_plane_age_guard.py  (plain runner)

All scenarios are hermetic: the pure core takes an injected `now`, and the
degradation tests write temp files, so the suite is offline and
deterministic.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "verdict_plane_age_guard.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
TAG = "[verdict-plane-age-guard]"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import verdict_plane_age_guard as guard

NOW = guard.parse_ts("2026-10-30T12:00:00Z")


def row(number: int, created: str, title: str = "t") -> dict:
    return {"number": number, "title": title, "createdAt": created,
            "url": f"https://example/pull/{number}"}


# --------------------------------------------------------------------------- #
# Wiring SSOT: the live roster carries the guard (self-test mode)              #
# --------------------------------------------------------------------------- #

def test_guard_wired_in_roster() -> None:
    assert GUARD.is_file(), f"guard script missing: {GUARD}"
    roster = ROSTER.read_text(encoding="utf-8")
    assert "scripts/ci/verdict_plane_age_guard.py" in roster and \
        "--self-test" in roster, \
        "guard must be wired into the LIVE run_all_guards.py roster"


def test_guard_self_test_passes() -> None:
    res = subprocess.run(
        [sys.executable, str(GUARD), "--self-test"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, timeout=120,
    )
    assert res.returncode == 0, f"self-test failed: {res.stdout} {res.stderr}"
    assert "self-test OK" in res.stdout


# --------------------------------------------------------------------------- #
# Timestamp parsing (invariant A)                                              #
# --------------------------------------------------------------------------- #

def test_parse_ts_z_and_offset_equivalent() -> None:
    assert guard.parse_ts("2026-10-30T11:00:00Z") == \
        guard.parse_ts("2026-10-30T11:00:00+00:00")


def test_parse_ts_naive_coerced_to_utc() -> None:
    dt = guard.parse_ts("2026-10-30T11:00:00")
    assert dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0


def test_parse_ts_rejects_empty() -> None:
    for bad in ("", "   "):
        try:
            guard.parse_ts(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"empty timestamp accepted: {bad!r}")


# --------------------------------------------------------------------------- #
# SLA bucketing (invariant A — strict boundary)                                #
# --------------------------------------------------------------------------- #

def test_bucket_boundary_exact_sla_is_ok() -> None:
    b = guard.bucket_row(row(1, "2026-10-29T12:00:00Z"), NOW, 24.0)
    assert b["verdict"] == "OK" and b["ageHours"] == 24.0


def test_bucket_beyond_sla_is_breach() -> None:
    b = guard.bucket_row(row(2, "2026-10-29T11:59:59Z"), NOW, 24.0)
    assert b["verdict"] == "BREACH"


def test_age_hours_rejects_naive() -> None:
    naive = guard.parse_ts("2026-10-29T12:00:00Z").replace(tzinfo=None)
    try:
        guard.age_hours(naive, NOW)
    except ValueError:
        pass
    else:
        raise AssertionError("naive datetime accepted by age_hours")


# --------------------------------------------------------------------------- #
# Sweep aggregation + ordering (invariant B)                                   #
# --------------------------------------------------------------------------- #

def test_sweep_counts_and_order() -> None:
    rows = [
        row(10, "2026-10-29T00:00:00Z", "mid"),
        row(11, "2026-10-28T00:00:00Z", "eldest"),
        row(12, "2026-10-30T09:00:00Z", "fresh"),
    ]
    rep = guard.sweep(rows, NOW, 24.0)
    assert rep["totalOpen"] == 3
    assert rep["breachCount"] == 2 and rep["okCount"] == 1
    assert [b["number"] for b in rep["breaches"]] == [11, 10]
    assert rep["escalationQueue"] == [11, 10]


def test_sweep_tie_break_by_number() -> None:
    rep = guard.sweep([
        row(21, "2026-10-28T05:00:00Z", "a"),
        row(20, "2026-10-28T05:00:00Z", "b"),
    ], NOW, 24.0)
    assert [b["number"] for b in rep["breaches"]] == [20, 21]


def test_sweep_empty_plane_is_clean_pass() -> None:
    rep = guard.sweep([], NOW, 24.0)
    assert rep["breachCount"] == 0 and rep["totalOpen"] == 0
    assert guard.format_text(rep).endswith("PASS")


# --------------------------------------------------------------------------- #
# Fail-closed row validation (invariant C)                                     #
# --------------------------------------------------------------------------- #

def test_normalize_row_rejects_malformed() -> None:
    bads = [
        {"title": "missing both"},
        {"number": 3},
        {"number": "x", "createdAt": "2026-10-30T00:00:00Z"},
        {"number": 4, "createdAt": "not-a-time"},
        "not-even-a-dict",
    ]
    for bad in bads:
        try:
            guard.normalize_row(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed row accepted: {bad!r}")


# --------------------------------------------------------------------------- #
# Fingerprint (invariant E)                                                    #
# --------------------------------------------------------------------------- #

def test_fingerprint_stable_and_sensitive() -> None:
    rows = [
        row(10, "2026-10-29T00:00:00Z"),
        row(11, "2026-10-28T00:00:00Z"),
    ]
    a = guard.sweep(rows, NOW, 24.0)
    b = guard.sweep(rows, NOW, 24.0)
    assert a["fingerprint"] == b["fingerprint"]
    assert a["fingerprint"] != guard.sweep(rows, NOW, 12.0)["fingerprint"]
    assert a["fingerprint"] != guard.sweep(rows[:1], NOW, 24.0)["fingerprint"]


# --------------------------------------------------------------------------- #
# Honest degradation (invariant C — exit 2, never fabricated PASS)             #
# --------------------------------------------------------------------------- #

def _run_guard(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, timeout=120,
    )


def test_missing_input_file_exits_2() -> None:
    res = _run_guard(["--input-file", "/nonexistent/prs-never.json"])
    assert res.returncode == 2
    assert "HARNESS-ERROR" in res.stderr


def test_malformed_input_file_exits_2() -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".json",
                                     delete=False) as fh:
        fh.write("{not-json")
        path = fh.name
    try:
        res = _run_guard(["--input-file", path])
        assert res.returncode == 2
        assert "HARNESS-ERROR" in res.stderr
    finally:
        Path(path).unlink(missing_ok=True)


def test_clean_input_exits_0_and_breach_exits_1() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        clean = Path(tmp) / "clean.json"
        clean.write_text(json.dumps(
            [row(40, "2026-10-30T11:00:00Z")]), encoding="utf-8")
        res = _run_guard(["--input-file", str(clean)])
        assert res.returncode == 0 and "PASS" in res.stdout

        stale = Path(tmp) / "stale.json"
        stale.write_text(json.dumps(
            [row(41, "2026-10-28T00:00:00Z")]), encoding="utf-8")
        res = _run_guard(["--input-file", str(stale), "--format", "json"])
        assert res.returncode == 1
        payload = json.loads(res.stdout)
        assert payload["schema"] == "verdict-plane-age-report/1"
        assert payload["breachCount"] == 1
        assert payload["breaches"][0]["number"] == 41


# --------------------------------------------------------------------------- #
# stdlib plain runner (dual-mode doctrine)                                     #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(
        (n, f) for n, f in list(globals().items())
        if n.startswith("test_") and callable(f)
    ):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    print(f"{TAG} stdlib runner: "
          f"{'ALL PASS' if not failures else f'{failures} FAILURE(S)'}")
    sys.exit(1 if failures else 0)
