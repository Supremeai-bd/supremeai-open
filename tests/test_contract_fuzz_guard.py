#!/usr/bin/env python3
"""Offline tests for the runtime contract-fuzzing guard (#1898, R40).

The guard itself runs a live in-memory ASGI fuzz (60s, seed 42) when invoked
with --check; these tests deliberately do NOT: they pin the ratchet logic,
the landed baseline floor, the roster wiring, and the fail-closed conditions
— all offline, dual-mode (pytest + stdlib runner), mirroring the house style
of test_mcp_access_policy_guard.py / test_security_gate_selftest.py.

The zero-5xx hard assertion and honest-skip behaviors are covered by the
guard's own --self-test (11 hermetic cases) and by the roster run in an
environment with schemathesis installed.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "contract_fuzz_guard.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
BASELINE = REPO_ROOT / "scripts" / "ci" / "contract_fuzz_baseline.json"

# The landed floor (2026-10-28, seed 42, 60s, 8165 interactions): the four
# known-failing classes the landing run and the #1898 scout run agree on.
LANDED_FLOOR_CLASSES = {
    "ignored_auth",
    "missing_required_header",
    "negative_data_rejection",
    "status_code_conformance",
}


def _load_guard_module():
    spec = importlib.util.spec_from_file_location("contract_fuzz_guard", GUARD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_guard(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_self_test_matrix_passes() -> None:
    """All hermetic ratchet-logic cases behave."""
    r = _run_guard("--self-test")
    assert r.returncode == 0, f"self-test failed:\n{r.stdout}\n{r.stderr}"
    assert "11/11" in r.stdout


def test_baseline_floor_pinned() -> None:
    """The landed baseline carries exactly the four agreed failing classes."""
    data = json.loads(BASELINE.read_text(encoding="utf-8"))
    known = data.get("known_failing", {})
    assert set(known) == LANDED_FLOOR_CLASSES, f"floor drifted: {set(known)}"
    # crash class must never appear in the baseline
    assert "not_a_server_error" not in known
    prov = data.get("provenance", {})
    assert prov.get("issue") == "1898" and prov.get("radar") == "R40"
    assert prov.get("pinned_schemathesis") == "4.32.7"
    assert "shrink-only" in prov.get("ratchet", "")


def test_roster_wiring_pinned() -> None:
    """The guard is discoverable/executable via the run_all_guards roster."""
    roster = ROSTER.read_text(encoding="utf-8")
    assert "scripts/ci/contract_fuzz_guard.py" in roster, (
        "guard unwired from roster — the #1735 zero-callers death mode repeats"
    )


def test_corrupt_baseline_fails_closed_fast() -> None:
    """A corrupt baseline is exit 1 BEFORE any fuzzing (fast, no schemathesis)."""
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        r = _run_guard("--check", "--baseline-path", str(bad), "--max-time", "1")
    assert r.returncode == 1
    assert "corrupt" in r.stdout.lower()


def test_missing_baseline_fails_closed_fast() -> None:
    """An absent baseline never silently bootstraps on --check."""
    with tempfile.TemporaryDirectory() as td:
        r = _run_guard("--check", "--baseline-path", str(Path(td) / "nope.json"), "--max-time", "1")
    assert r.returncode == 1
    assert "missing" in r.stdout.lower()


def test_ratchet_semantics() -> None:
    """Unit-level: class-set shrink-only ratchet (evaluate + intersection)."""
    mod = _load_guard_module()
    known = {"status_code_conformance": 4125, "ignored_auth": 4124}
    # same set -> compliant
    assert mod.evaluate_against_baseline(set(known), known) == ([], [])
    # new class -> drift
    drift, _ = mod.evaluate_against_baseline(set(known) | {"new_class"}, known)
    assert drift == ["new_class"]
    # removed class -> shrink candidate
    _, shrunk = mod.evaluate_against_baseline(set(known) - {"ignored_auth"}, known)
    assert shrunk == ["ignored_auth"]
    # intersection-only rewrite: growth impossible
    assert mod.intersect_baseline(known, {"status_code_conformance": 99}) == {
        "status_code_conformance": 4125
    }
    # crash class hard-asserted
    assert "not_a_server_error" in mod.HARD_ASSERT_CLASSES


def test_growth_refusal_requires_no_fuzz() -> None:
    """intersect_baseline can only shrink the key set (never add classes)."""
    mod = _load_guard_module()
    known = {"a": 5, "b": 2}
    out = mod.intersect_baseline(known, {"a": 1, "c": 9})
    assert "c" not in out and set(out) <= set(known)


def test_guard_provenance_documented() -> None:
    """The docstring carries the R40 mission, binding method, and never-dos."""
    doc = GUARD.read_text(encoding="utf-8")
    assert "#1898" in doc and "R40" in doc
    assert "gateway/service/app.py" in doc
    assert "ASGI" in doc
    assert "never baselined" in doc or "never tolerated" in doc
    assert "No agent fixes" in doc or "never an agent fix" in doc


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(
        (k, v) for k, v in globals().items()
        if k.startswith("test_") and callable(v)
    ):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
    total = 8
    print(f"{total - failures}/{total} passed" if failures else f"{total}/{total} passed (stdlib mode)")
    sys.exit(1 if failures else 0)
