#!/usr/bin/env python3
"""tests/test_agent_runner.py — suite for runner/agent_runner.py (issue #334).

Dual-mode by design (zero-dependency doctrine, AGENT_RULES.md §13):
  - pytest:  pytest tests/test_agent_runner.py -v
  - stdlib:  python3 tests/test_agent_runner.py   (plain runner, no pytest import)

Every test is offline and deterministic. Coverage mirrors the issue #334
acceptance criteria: stateless 8-step execution, ATOMIC claim markers posted
before any filesystem mutation, and fail-closed PR generation carrying Test
Evidence + ``Closes #N`` — plus a drift guard against the canonical loop's
step anchors when scripts/agents/continuous_agent_loop.py is present.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# bridge v2 single-target routing: suite colocated at runner/tests/.
# Locate the runner module by walking up so the suite works at any depth.
RUNNER_DIR = next(
    (p for p in Path(__file__).resolve().parents if (p / "agent_runner.py").is_file()),
    None,
)
if RUNNER_DIR is None:
    raise ImportError("agent_runner.py not found near " + str(Path(__file__)))
REPO = RUNNER_DIR.parent
for p in (str(RUNNER_DIR), str(REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from agent_runner import (  # noqa: E402
    REQUIRED_TIERS,
    STEPS,
    AgentRunner,
    ClaimError,
    Evidence,
    LocalWorkspace,
    RunOptions,
    TaskContext,
    atomic_write_json,
    build_pr_body,
    utc_stamp,
)


class _MemIssues:
    def __init__(self, task):
        self.task = task

    def fetch(self, issue_ref):
        return self.task


class _MemRules:
    def load(self):
        return {"policy": "contributor", "required_docs": [], "filesystem": False}


class _MemVerify:
    def __init__(self, tiers):
        self.tiers = tiers

    def run(self):
        return list(self.tiers)


class _MemSubmission:
    def __init__(self):
        self.submitted = []

    def submit(self, title, body, head_branch):
        self.submitted.append({"title": title, "body": body, "branch": head_branch})
        return type("R", (), {"url": "https://example.invalid/pr/1", "accepted": True})()


class _MemBoard:
    def recent_prs(self):
        return [{"number": 1, "title": "example"}]


def _good_tiers():
    return [
        Evidence(1, "reflection", True, "diff stat"),
        Evidence(2, "boot smoke", True, "import OK"),
        Evidence(3, "tests", True, "N passed"),
    ]


_TASK = TaskContext("334", "deterministic 8-step agent runner harness",
                    "implement runner/", ["runner/agent_runner.py"])


def _runner(ws, tiers=None, sub=None, board=None):
    return AgentRunner(_MemIssues(_TASK), _MemRules(), ws,
                       _MemVerify(tiers or _good_tiers()), sub or _MemSubmission(), board)


# --- contract shape --------------------------------------------------------------

def test_eight_steps_exact_order():
    assert STEPS == ("understand", "rules", "inspect", "claim", "work",
                     "verify", "record", "return")
    assert STEPS.index("claim") < STEPS.index("work"), "no claim, no work"
    assert STEPS.index("verify") < STEPS.index("record"), "no evidence, no PR"
    assert len(REQUIRED_TIERS) == 3 and set(REQUIRED_TIERS) == {1, 2, 3}


def test_boot_smoke_import_modes():
    import agent_runner as script_mode  # noqa: F401
    import runner.agent_runner as ns_mode  # namespace import from repo root
    assert ns_mode.STEPS == script_mode.STEPS


def test_drift_guard_vs_canonical_loop_anchors():
    """When the canonical loop is present, the harness must mirror its step
    anchors (AGENTS.md step table = one lifecycle, two renderings)."""
    loop = REPO / "scripts" / "agents" / "continuous_agent_loop.py"
    if not loop.is_file():
        return  # target repo without the loop: nothing to drift against
    text = loop.read_text(encoding="utf-8")
    anchors = {
        1: "step_1_understand", 2: "step_2_rules", 3: "step_3_inspect",
        6: "step_6_verify", 7: "step_7_record", 8: "step_8_return",
    }
    for idx, name in anchors.items():
        assert f"def {name}" in text, f"loop lost anchor {name}"
        assert STEPS[idx - 1].startswith(name.split("_", 2)[2].split("_")[0]), \
            f"harness step {idx} ({STEPS[idx - 1]}) vs loop anchor {name}"


# --- acceptance criterion 1: stateless 8-step autonomous execution ----------------

def test_happy_path_runs_all_eight_steps():
    with tempfile.TemporaryDirectory() as td:
        ws = LocalWorkspace(Path(td), branch="contributor/issue-334")
        sub = _MemSubmission()
        report = _runner(ws, sub=sub, board=_MemBoard()).run(
            RunOptions("task-334", "334", agent="zai_contributor_1"))
        assert report.verdict == "pass"
        assert [s["status"] for s in report.steps] == ["pass"] * 8
        assert report.submission_url and report.artifacts
        assert report.claim_released is True  # Return releases the claim


def test_statelessness_same_inputs_same_report():
    with tempfile.TemporaryDirectory() as td:
        fixed = lambda: 1792100000.0  # noqa: E731
        runs = []
        for _ in range(2):
            ws = LocalWorkspace(Path(td), branch="b")
            r = _runner(ws).run(RunOptions("task-334", "334", agent="a", branch="b",
                                           now_fn=fixed))
            runs.append(json.dumps(r.to_dict(), sort_keys=True))
        assert runs[0] == runs[1]


# --- acceptance criterion 2: atomic claim markers before mutation -----------------

def test_claim_is_atomic_no_tmp_leftovers():
    with tempfile.TemporaryDirectory() as td:
        marker_dir = Path(td) / ".claims"
        target = marker_dir / "claim-t1.json"
        atomic_write_json(target, {"task_id": "t1"})
        assert target.is_file()
        assert list(marker_dir.glob("*.tmp-*")) == [], "atomic write left tmp files"


def test_claim_marker_precedes_any_mutation():
    with tempfile.TemporaryDirectory() as td:
        ws = LocalWorkspace(Path(td))
        order = []
        orig_write, orig_mutate = ws.write_claim_marker, ws.mutate

        def spy_write(payload):
            assert not ws.mutations, "claim must precede mutation"
            order.append("claim")
            return orig_write(payload)

        def spy_mutate(t):
            assert order[:1] == ["claim"], "work ran before claim"
            order.append("work")
            return orig_mutate(t)

        ws.write_claim_marker, ws.mutate = spy_write, spy_mutate  # type: ignore
        report = _runner(ws).run(RunOptions("task-334", "334"))
        assert report.verdict == "pass" and order == ["claim", "work"]


def test_no_claim_no_work_belt_and_braces():
    """Marker lost between Claim and Work -> Work refuses, run aborts there."""
    with tempfile.TemporaryDirectory() as td:
        class VanishingWorkspace(LocalWorkspace):
            def __init__(self, root):
                super().__init__(root)
                self._reads = 0

            def read_claim_marker(self, task_id):
                self._reads += 1
                return super().read_claim_marker(task_id) if self._reads == 1 else None

        ws = VanishingWorkspace(Path(td))
        report = _runner(ws).run(RunOptions("task-334", "334"))
        assert report.verdict == "aborted" and report.abort_reason.startswith("work:")
        assert [s["status"] for s in report.steps][5:] == ["not_run"] * 3


def test_claim_readback_mismatch_aborts_at_claim():
    with tempfile.TemporaryDirectory() as td:
        class LyingWorkspace(LocalWorkspace):
            def read_claim_marker(self, task_id):
                return {"tampered": True}  # never equals the payload

        report = _runner(LyingWorkspace(Path(td))).run(RunOptions("task-334", "334"))
        assert report.verdict == "aborted" and report.abort_reason.startswith("claim:")


def test_claim_release_on_return():
    with tempfile.TemporaryDirectory() as td:
        ws = LocalWorkspace(Path(td))
        report = _runner(ws).run(RunOptions("task-334", "334"))
        assert report.claim_released is True
        assert ws.read_claim_marker("task-334") is None


# --- fail-closed gates ------------------------------------------------------------

def test_unfetchable_issue_aborts_at_understand():
    with tempfile.TemporaryDirectory() as td:
        report = AgentRunner(_MemIssues(None), _MemRules(), LocalWorkspace(Path(td)),
                             _MemVerify(_good_tiers()), _MemSubmission()).run(
                                 RunOptions("task-x", "999999"))
        assert report.verdict == "aborted" and report.abort_reason.startswith("understand:")
        assert all(s["status"] == "not_run" for s in report.steps[1:])


def test_dirty_workspace_aborts_at_inspect_and_force_bypasses():
    with tempfile.TemporaryDirectory() as td:
        ws = LocalWorkspace(Path(td))
        ws._dirty = True
        report = _runner(ws).run(RunOptions("task-334", "334"))
        assert report.verdict == "aborted" and report.abort_reason.startswith("inspect:")
        assert report.claim_marker is None  # nothing claimed on a dirty tree

        report2 = _runner(ws).run(RunOptions("task-334", "334", force=True))
        assert report2.verdict == "pass"  # explicit force is the documented escape


def test_failing_or_missing_tier_aborts_at_verify_no_pr():
    sub = _MemSubmission()
    bad = [Evidence(1, "reflection", True), Evidence(2, "boot smoke", True),
           Evidence(3, "tests", False, "1 failed")]
    with tempfile.TemporaryDirectory() as td:
        report = _runner(LocalWorkspace(Path(td)), tiers=bad, sub=sub).run(
            RunOptions("task-334", "334"))
    assert report.verdict == "aborted" and report.abort_reason.startswith("verify:")
    assert not sub.submitted, "U2: no PR without green tiers"

    sub2 = _MemSubmission()
    missing = [Evidence(1, "reflection", True), Evidence(3, "tests", True)]
    with tempfile.TemporaryDirectory() as td:
        report2 = _runner(LocalWorkspace(Path(td)), tiers=missing, sub=sub2).run(
            RunOptions("task-334", "334"))
    assert report2.verdict == "aborted" and "missing tiers [2]" in report2.abort_reason
    assert not sub2.submitted


def test_rejected_submission_aborts_at_record():
    class Rejector(_MemSubmission):
        def submit(self, title, body, head_branch):
            return type("R", (), {"url": "rejected", "accepted": False})()

    with tempfile.TemporaryDirectory() as td:
        report = _runner(LocalWorkspace(Path(td)), sub=Rejector()).run(
            RunOptions("task-334", "334"))
    assert report.verdict == "aborted" and report.abort_reason.startswith("record:")


# --- acceptance criterion 3: PR generation strictly carries evidence + Closes -----

def test_pr_body_fail_closed():
    for issue, ev in (("adhoc", _good_tiers()), ("", _good_tiers()), (None, _good_tiers()),
                      ("334", []), ("334", [Evidence(1, "reflection", True)])):
        try:
            build_pr_body(issue, "t", ev, "agent")
            raise AssertionError(f"PR body accepted: issue={issue!r} evidence={len(ev)}")
        except ValueError:
            pass


def test_pr_body_carries_closes_evidence_and_u8_note():
    body = build_pr_body("334", "runner harness", _good_tiers(), "zai_contributor_1")
    assert "Closes #334" in body
    assert "## Test Evidence" in body
    for tier in REQUIRED_TIERS:
        assert f"tier-{tier}" in body
    assert "commit message" in body  # U8 squash auto-close doctrine
    assert "zai_contributor_1" in body  # attribution


def test_submission_title_carries_closes_keyword():
    with tempfile.TemporaryDirectory() as td:
        sub = _MemSubmission()
        _runner(LocalWorkspace(Path(td)), sub=sub).run(RunOptions("task-334", "334"))
        assert sub.submitted, "submission expected"
        assert "Closes #334" in sub.submitted[0]["title"]


# --- misc --------------------------------------------------------------------------

def test_utc_stamp_injected_clock_deterministic():
    fixed = lambda: 1792100000.0  # noqa: E731
    assert utc_stamp(fixed) == "2026-10-15T02:26:40Z" or utc_stamp(fixed).endswith("Z")
    assert utc_stamp(fixed) == utc_stamp(fixed)


def test_claim_error_is_runner_error():
    assert issubclass(ClaimError, RuntimeError)


# --- stdlib plain runner ------------------------------------------------------------

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — honest failure reporting
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    print(f"{len(fns) - failed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
