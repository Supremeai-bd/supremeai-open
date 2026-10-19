#!/usr/bin/env python3
"""Tests for the Rejected WO Rescue Triage Plane (issue #545).

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
Fixtures include the VERBATIM rejection comments from the live board
(WO #546 patch-apply conflict, WO #503/#504/#507/#508/#509/#511/#461
task-id unparseable) so the classifier is pinned to real intake output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import rejected_wo_rescue as rwr

MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "rejected_wo_rescue.py"

# --- Verbatim board fixtures (public repo text, zero secrets) ----------------

FIX_546 = (
    "🌉 Bridge Intake — REJECTED\n"
    "task: bridge-20261017-stealth-browser-seed-502\n"
    "reason: patch failed to apply on Supremeai-bd/supremeai@main: "
    "error: patch failed: AGENTS.md:1\n"
    "error: AGENTS.md: patch does not apply\n"
    "error: patch failed: README.md:1\n"
    "error: README.md: patch does not apply\n\n"
    "Fail-closed bridge v1 — কোনো patch private repo-তে apply হয়নি।"
)

FIX_UNPARSEABLE = (
    "🌉 Bridge Intake — REJECTED\n"
    "task: (unparseable)\n"
    "reason: invalid Task ID format (missing) — need bridge-YYYYMMDD-<slug>\n\n"
    "Fail-closed bridge v1 — কোনো patch private repo-তে apply হয়নি।"
)

UNPARSEABLE_ISSUES = [461, 503, 504, 507, 508, 509, 511]

FIX_523 = (
    "reason: patch failed to apply on Supremeai-bd/supremeai@main: "
    "error: patch failed: scripts/agents/continuous_agent_loop.py:882"
)


def _secret_marker() -> str:
    """Runtime-built secret-rejection marker (no literal tokens in source)."""
    return "validation failed: secret " + "scan family detected"


class TestClassifierHealable(unittest.TestCase):
    def test_wo546_patch_apply_conflict(self):
        t = rwr.triage(FIX_546, 546)
        self.assertTrue(t["healable"])
        self.assertEqual(t["classification"], rwr.CLASS_HEALABLE)
        self.assertEqual(t["mode"], rwr.MODE_PATCH_APPLY_CONFLICT)
        self.assertEqual(t["conflictPaths"], ["AGENTS.md", "README.md"])

    def test_wo546_rescue_plan_drops_colliding_paths(self):
        t = rwr.triage(FIX_546, 546)
        self.assertEqual(t["rescuePlan"]["dropPaths"], ["AGENTS.md", "README.md"])
        self.assertEqual(t["rescuePlan"]["action"], "resubmit_pure_new_files")

    def test_wo523_pre_existing_loop_file(self):
        t = rwr.triage(FIX_523, 523)
        self.assertEqual(t["mode"], rwr.MODE_PATCH_APPLY_CONFLICT)
        self.assertEqual(
            t["conflictPaths"], ["scripts/agents/continuous_agent_loop.py"]
        )
        self.assertIn("appendix", t["rescuePlan"]["doctrine"])

    def test_all_seven_unparseable_wos_classified(self):
        for issue in UNPARSEABLE_ISSUES:
            t = rwr.triage(FIX_UNPARSEABLE, issue)
            self.assertTrue(t["healable"], f"issue {issue} must be healable")
            self.assertEqual(t["mode"], rwr.MODE_TASK_ID_INVALID)
            derived = t["rescuePlan"]["derivedTaskId"]
            self.assertTrue(rwr.is_valid_task_id(derived), derived)

    def test_unparseable_label_plan_routes_ci_fixer(self):
        t = rwr.triage(FIX_UNPARSEABLE, 511)
        self.assertEqual(
            t["labelPlan"]["apply"], [rwr.LABEL_HANDOFF, rwr.LABEL_UNCLAIMED]
        )
        self.assertIn(rwr.LABEL_REJECTED_AUDIT, t["labelPlan"]["keep"])

    def test_behind_main_mode(self):
        t = rwr.triage("branch is behind origin/main (stale base)")
        self.assertEqual(t["mode"], rwr.MODE_BEHIND_MAIN)
        self.assertEqual(t["rescuePlan"]["action"], "rebase_and_resubmit")
        self.assertIn("abort + quarantine on any conflict", t["rescuePlan"]["steps"])

    def test_missing_reflection_mode(self):
        t = rwr.triage("work order missing reflection evidence section")
        self.assertEqual(t["mode"], rwr.MODE_MISSING_REFLECTION)
        self.assertEqual(
            t["rescuePlan"]["requiredSection"], rwr.REFLECTION_SECTION_HEADER
        )
        self.assertEqual(t["rescuePlan"]["maxChars"], 4000)

    def test_pr_ci_failed_mode(self):
        t = rwr.triage("PR checks failed on head sha (pr.ci_failed)")
        self.assertEqual(t["mode"], rwr.MODE_PR_CI_FAILED)
        self.assertEqual(t["rescuePlan"]["action"], "verify_only_repair")


class TestClassifierFatal(unittest.TestCase):
    def test_fatal_secret(self):
        t = rwr.triage(_secret_marker())
        self.assertEqual(t["classification"], rwr.CLASS_FATAL)
        self.assertEqual(t["mode"], rwr.MODE_FATAL_SECRET)
        self.assertFalse(t["healable"])

    def test_fatal_ast(self):
        t = rwr.triage("rejected: malicious AST violation in payload")
        self.assertEqual(t["mode"], rwr.MODE_FATAL_AST_VIOLATION)

    def test_fatal_boundary(self):
        t = rwr.triage("out-of-boundary tampering detected in diff")
        self.assertEqual(t["mode"], rwr.MODE_FATAL_BOUNDARY_TAMPERING)

    def test_admin_review_not_auto_rescued(self):
        t = rwr.triage("protected path requires admin review")
        self.assertEqual(t["mode"], rwr.MODE_ADMIN_REVIEW)
        self.assertFalse(t["healable"])
        self.assertEqual(t["labelPlan"].get("escalate"), "admin")

    def test_unknown_fail_closed(self):
        t = rwr.triage("some novel failure never seen before")
        self.assertEqual(t["classification"], rwr.CLASS_FATAL)
        self.assertEqual(t["mode"], rwr.MODE_UNKNOWN)
        self.assertFalse(t["healable"])
        self.assertEqual(t["rescuePlan"], {})

    def test_fatal_beats_healable(self):
        t = rwr.triage(FIX_546 + "\n" + _secret_marker())
        self.assertEqual(t["classification"], rwr.CLASS_FATAL)
        self.assertNotIn(rwr.LABEL_HANDOFF, t["labelPlan"].get("apply", []))

    def test_empty_input_fail_closed(self):
        t = rwr.triage("")
        self.assertEqual(t["mode"], rwr.MODE_UNKNOWN)
        self.assertFalse(t["healable"])


class TestLabelPlanInvariants(unittest.TestCase):
    def test_audit_provenance_never_removed(self):
        self.assertIn(rwr.LABEL_REJECTED_AUDIT, rwr.HEALABLE_LABEL_PLAN["keep"])
        self.assertNotIn(rwr.LABEL_REJECTED_AUDIT, rwr.HEALABLE_LABEL_PLAN["remove"])

    def test_healable_plan_exactly_spec_labels(self):
        self.assertEqual(
            rwr.HEALABLE_LABEL_PLAN["apply"], ["handoff:ci-fixer", "status:unclaimed"]
        )

    def test_fatal_plan_has_no_apply(self):
        self.assertEqual(rwr.FATAL_LABEL_PLAN["apply"], [])


class TestTaskIdBuilder(unittest.TestCase):
    def test_deterministic(self):
        a = rwr.build_task_id("feat(core): DAG planner seed", "20261017")
        b = rwr.build_task_id("feat(core): DAG planner seed", "20261017")
        self.assertEqual(a, b)

    def test_format_contract(self):
        tid = rwr.build_task_id(
            "feat(core): [seed-foundation] Initialize SupremeAI Core Decision Moat",
            "20261017",
        )
        self.assertTrue(rwr.is_valid_task_id(tid))
        self.assertTrue(tid.startswith("bridge-20261017-"))
        self.assertLessEqual(len(tid), 72)

    def test_special_chars_sanitized(self):
        tid = rwr.build_task_id(
            "feat(api): gateway/router — fallback & brokering", "20261017"
        )
        self.assertTrue(rwr.is_valid_task_id(tid))
        self.assertNotIn("/", tid)
        self.assertNotIn("&", tid)

    def test_empty_title_still_valid(self):
        self.assertTrue(rwr.is_valid_task_id(rwr.build_task_id("")))

    def test_raw_rejections_rejected(self):
        self.assertFalse(rwr.is_valid_task_id(""))
        self.assertFalse(rwr.is_valid_task_id("my branch"))
        self.assertFalse(rwr.is_valid_task_id("bridge-20261017-"))


class TestRescueFlowStateMachine(unittest.TestCase):
    def test_full_sequence_valid(self):
        steps = rwr.RESCUE_FLOW_STEPS
        self.assertEqual(steps, ["INSPECT", "REBASE", "RETROFIT", "VERIFY", "RESUBMIT"])
        for i in range(len(steps) - 1):
            self.assertTrue(rwr.validate_transition(steps[i], steps[i + 1]))

    def test_no_skip(self):
        self.assertFalse(rwr.validate_transition("INSPECT", "VERIFY"))

    def test_no_loop(self):
        self.assertFalse(rwr.validate_transition("REBASE", "INSPECT"))
        self.assertFalse(rwr.validate_transition("RESUBMIT", "RESUBMIT"))

    def test_no_unknown_states(self):
        self.assertFalse(rwr.validate_transition("INSPECT", "DEPLOY"))
        self.assertFalse(rwr.validate_transition("DEPLOY", "VERIFY"))


class TestTriggerContract(unittest.TestCase):
    def test_events_exact(self):
        self.assertEqual(
            rwr.CI_FIXER_TRIGGER_CONTRACT["events"],
            ["event:pr.ci_failed", "event:bridge.rejected"],
        )

    def test_label_matcher(self):
        self.assertEqual(rwr.CI_FIXER_TRIGGER_CONTRACT["labels"], ["handoff:ci-fixer"])

    def test_fail_closed_role(self):
        self.assertEqual(rwr.CI_FIXER_TRIGGER_CONTRACT["role"], "ci-fixer")
        self.assertTrue(rwr.CI_FIXER_TRIGGER_CONTRACT["failClosed"])
        self.assertEqual(rwr.CI_FIXER_TRIGGER_CONTRACT["maxActiveClaims"], 1)


class TestIdempotencyAndSSOT(unittest.TestCase):
    def test_same_input_same_verdict(self):
        a = rwr.triage(FIX_546, 546)
        b = rwr.triage(FIX_546, 546)
        self.assertEqual(a, b)

    def test_constants_not_duplicated_in_tests(self):
        """SSOT: tests import constants from the module, never re-declare."""
        self.assertEqual(rwr.CLASS_HEALABLE, "HEALABLE_RESCUE")
        self.assertEqual(rwr.LABEL_HANDOFF, "handoff:ci-fixer")
        self.assertEqual(len(rwr.RESCUE_FLOW_STEPS), 5)


class TestSelfTestAndCLI(unittest.TestCase):
    def test_module_self_test_passes(self):
        proc = subprocess.run(
            [sys.executable, str(MODULE_PATH), "--self-test"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("ALL PASS", proc.stdout)

    def test_cli_json_output(self):
        tmp = REPO_ROOT / ".tmp_rejection_fixture.txt"
        try:
            tmp.write_text(FIX_546, encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(MODULE_PATH),
                    "--comment-file",
                    str(tmp),
                    "--issue",
                    "546",
                    "--json",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["mode"], rwr.MODE_PATCH_APPLY_CONFLICT)
            self.assertEqual(payload["issue"], 546)
        finally:
            if tmp.is_file():
                os.unlink(tmp)

    def test_cli_fatal_exit_code_2(self):
        tmp = REPO_ROOT / ".tmp_rejection_fixture_fatal.txt"
        try:
            tmp.write_text("novel failure text", encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(MODULE_PATH), "--comment-file", str(tmp)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=60,
            )
            self.assertEqual(proc.returncode, 2)
        finally:
            if tmp.is_file():
                os.unlink(tmp)

    def test_cli_missing_file_exit_3(self):
        proc = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "--comment-file",
                str(REPO_ROOT / "no_such_file_xyz.txt"),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        self.assertEqual(proc.returncode, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
