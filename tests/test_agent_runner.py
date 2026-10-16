#!/usr/bin/env python3
"""tests/test_agent_runner.py — test suite for runner/agent_runner.py (issue #334).

Dual-mode by design (zero-dependency doctrine, AGENT_RULES.md §13):
  - pytest:  pytest tests/test_agent_runner.py -v
  - stdlib:  python3 tests/test_agent_runner.py   (plain runner, no pytest import)

Every test is offline and deterministic. The suite covers the issue's
acceptance criteria: envelope fail-closed validation, atomic claim gating
("no claim, no work"), scope-guard enforcement, the strict 3-tier
verification contract, fail-closed Record, Closes #N embedding (U8),
secret redaction, deterministic run ids, and evidence-ledger roundtrips.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from runner.agent_runner import (  # noqa: E402
    AGENT_LOOP_SPEC_SSOT,
    RUNNER_CONTRACT_VERSION,
    STEPS,
    STEP_TITLES,
    VERIFY_TIERS,
    AgentRunner,
    ClaimError,
    EnvelopeError,
    ScopeViolation,
    VerificationError,
    build_envelope_from_issue,
    load_envelope,
    normalize_path,
    path_matches,
    redact,
)

PASS = [sys.executable, "-c", "print('tier ok')"]
FAIL = [sys.executable, "-c", "import sys; sys.exit(3)"]


def good_envelope() -> dict:
    return build_envelope_from_issue(
        task_id="task-334-test",
        issue="334",
        objective="deterministic 8-step harness with evidence capture",
        touching_files=["runner/**", "tests/test_agent_runner.py"],
    )


def tmp_runner(**overrides) -> tuple[AgentRunner, Path]:
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    base = dict(
        repo_root=root,
        evidence_dir=root / "ev",
        reflection_command=list(PASS),
        boot_command=list(PASS),
        test_command=list(PASS),
        work_callable=lambda env: {"worked": True},
    )
    base.update(overrides)
    runner = AgentRunner(good_envelope(), **base)
    # keep the tmpdir alive until the test ends via an attribute
    runner._tmpdir = td  # type: ignore[attr-defined]
    return runner, root


# --- constants contract -------------------------------------------------------


def test_constants_contract():
    assert len(STEPS) == 8
    assert tuple(STEP_TITLES[s] for s in STEPS) == (
        "Understand", "Rules", "Inspect", "Claim", "Work", "Verify", "Record", "Return",
    )
    assert VERIFY_TIERS == ("reflection", "boot-smoke", "test-suite")
    assert RUNNER_CONTRACT_VERSION == "agent-runner-contract/1"
    assert AGENT_LOOP_SPEC_SSOT.startswith("docs/AGENT_LOOP_SPEC.md")


# --- envelope fail-closed validation -------------------------------------------


def test_load_envelope_happy():
    env = load_envelope(json.dumps({"task_envelope": good_envelope()}))
    assert env["task_id"] == "task-334-test"
    assert env["output_format"] == "task-envelope-v1"


def test_envelope_missing_task_id_rejected():
    broken = good_envelope()
    broken.pop("task_id")
    try:
        load_envelope(json.dumps(broken))
        raise AssertionError("missing task_id must be rejected")
    except EnvelopeError as exc:
        assert "task_id" in str(exc)


def test_envelope_bad_version_rejected():
    broken = good_envelope()
    broken["envelope_version"] = 2
    try:
        load_envelope(json.dumps(broken))
        raise AssertionError("bad envelope_version must be rejected")
    except EnvelopeError:
        pass


def test_envelope_empty_touching_files_rejected():
    broken = good_envelope()
    broken["scope"]["touching_files"] = []
    try:
        load_envelope(json.dumps(broken))
        raise AssertionError("empty touching_files must be rejected")
    except EnvelopeError:
        pass


def test_envelope_issue_required_rejected():
    broken = good_envelope()
    broken.pop("issue")
    try:
        load_envelope(json.dumps(broken))
        raise AssertionError("issue required when issue_reference_required")
    except EnvelopeError as exc:
        assert "issue" in str(exc)


def test_forbidden_defaults_filled():
    runner, _root = tmp_runner()
    assert ".env*" in runner.env["scope"]["forbidden_paths"]
    assert "vault/**" in runner.env["scope"]["forbidden_paths"]


# --- scope guard ----------------------------------------------------------------


def test_scope_matching_semantics():
    assert path_matches("runner/a/b.py", "runner/**")
    assert path_matches("runner/x.py", "runner")
    assert not path_matches("docs/x.md", "runner/**")
    assert not path_matches("runner_evil/x.py", "runner")
    try:
        normalize_path("../escape.py")
        raise AssertionError("traversal must be rejected")
    except ScopeViolation:
        pass


def test_scope_violation_names_path():
    runner, _root = tmp_runner()
    runner.step_inspect()
    runner.step_claim()
    try:
        runner.step_work(["docs/elsewhere.md"])
        raise AssertionError("scope violation must raise")
    except ScopeViolation as exc:
        assert "docs/elsewhere.md" in str(exc)


def test_forbidden_wins_over_touching():
    env = good_envelope()
    env["scope"]["touching_files"].append(".env*")
    runner, _root = tmp_runner()
    runner.env = env
    runner.step_inspect()
    runner.step_claim()
    try:
        runner.step_work([".env.production"])
        raise AssertionError("forbidden must win over touching")
    except ScopeViolation:
        pass


# --- claim gate ------------------------------------------------------------------


def test_no_claim_no_work():
    runner, _root = tmp_runner()
    try:
        runner.step_work(["runner/agent_runner.py"])
        raise AssertionError("work without claim must raise")
    except ClaimError as exc:
        assert "no claim" in str(exc).lower()


def test_claim_marker_lifecycle():
    runner, _root = tmp_runner()
    runner.step_inspect()
    runner.step_claim()
    assert runner.claim_path.is_file()
    marker = json.loads(runner.claim_path.read_text(encoding="utf-8"))
    assert marker["task_id"] == "task-334-test"
    assert marker["claim_id"] == f"claim-{runner.run_id}"
    assert runner.release_claim()
    assert not runner.claim_path.exists()


# --- 3-tier verification gate ------------------------------------------------------


def test_verify_all_pass():
    runner, _root = tmp_runner()
    runner.step_inspect()
    runner.step_claim()
    runner.step_work([])
    detail = runner.step_verify()
    assert len(detail["tiers"]) == 3
    assert all(t["passed"] for t in detail["tiers"])
    assert runner.tiers_passed


def test_verify_failure_names_tier():
    runner, _root = tmp_runner(test_command=list(FAIL))
    runner.step_inspect()
    runner.step_claim()
    runner.step_work([])
    try:
        runner.step_verify()
        raise AssertionError("failing tier must raise")
    except VerificationError as exc:
        assert "test-suite" in str(exc)
    assert not runner.tiers_passed


def test_record_blocked_before_verify():
    runner, _root = tmp_runner()
    runner.step_inspect()
    runner.step_claim()
    runner.step_work([])
    try:
        runner.step_record()
        raise AssertionError("record must be blocked before tiers pass")
    except VerificationError:
        pass


# --- record + U8 doctrine ------------------------------------------------------------


def test_record_embeds_closes_and_commit_message():
    runner, _root = tmp_runner()
    runner.run(plan_only=True)
    record = runner.record
    assert record is not None
    assert "Closes #334" in record["pr_body"]
    assert "Closes #334" in record["commit_message"]
    assert record["pr_title"].startswith("feat(open):")


# --- redaction ------------------------------------------------------------------------


def test_redaction():
    leaked = (
        "api_key=sk-supersecret123 Authorization: Bearer abcdef.ghi.jklmnop "
        "SUPREMEAI_TOKEN=xyz999 password=hunter2"
    )
    red = redact(leaked)
    for secret in ("sk-supersecret123", "abcdef.ghi.jklmnop", "xyz999", "hunter2"):
        assert secret not in red


# --- determinism -------------------------------------------------------------------------


def test_run_id_deterministic():
    runner_a, _ = tmp_runner()
    runner_b, _ = tmp_runner()
    runner_a.step_inspect()  # fingerprint is set by Inspect (git head or root hash)
    runner_b.step_inspect()
    assert runner_a.run_id != runner_b.run_id  # different tmp roots → different fingerprints
    ra, root = tmp_runner()
    rb, _ = tmp_runner(repo_root=root)
    ra.step_inspect()
    rb.step_inspect()
    assert ra.run_id == rb.run_id  # same task + same repo state → same run id


# --- full runs ------------------------------------------------------------------------------


def test_full_run_completed_evidence_roundtrip():
    runner, _root = tmp_runner()
    outcome = runner.run(work_manifest=["runner/agent_runner.py"])
    assert outcome["status"] == "completed"
    assert len(outcome["steps"]) == 8
    assert outcome["tiers_passed"]
    assert outcome["record"]["closes_line"] == "Closes #334"
    assert outcome["claim_released"]
    ev_path = runner.write_evidence()
    assert ev_path.is_file()
    reloaded = json.loads(ev_path.read_text(encoding="utf-8"))
    assert reloaded["task_id"] == "task-334-test"
    assert len(reloaded["steps"]) == 8


def test_full_run_failed_releases_claim():
    runner, _root = tmp_runner(reflection_command=list(FAIL))
    outcome = runner.run(plan_only=True)
    assert outcome["status"] == "failed"
    assert not outcome["tiers_passed"]
    assert outcome["claim_released"]
    assert outcome["record"] is None


def test_boot_smoke_real_repo():
    """The issue's boot smoke, verbatim, against this checkout: import runner.agent_runner."""
    import subprocess

    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import runner.agent_runner"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_self_test_green():
    from runner.agent_runner import self_test

    checks = self_test()
    assert isinstance(checks, int) and checks >= 18


# --- plain stdlib runner (no pytest required) -------------------------------------------


def main() -> int:
    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS {name}")
        except Exception as exc:  # noqa: BLE001 — plain runner reports everything
            failed += 1
            print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed (stdlib mode)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
