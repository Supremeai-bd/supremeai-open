#!/usr/bin/env python3
"""S15 tests — Admin Sovereignty Guard (issue #528).

Dual-mode: stdlib unittest AND pytest. Constants are imported from the
reference module (SSOT) — never duplicated.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))

import admin_sovereignty_guard as guard  # noqa: E402

ADMIN = [guard.ADMIN_ONLY_LABEL]
SWARM = ["enhancement", "P1-high"]


class TestD1QuarantineDecision(unittest.TestCase):
    def test_admin_only_issue_denied(self):
        d = guard.quarantine_decision(ADMIN, 42)
        self.assertFalse(d.allowed)
        self.assertEqual(d.code, guard.DENIAL_CODE)
        self.assertEqual(d.execution_lane, guard.LANE_ADMIN)

    def test_denial_message_exact_contract(self):
        d = guard.quarantine_decision(ADMIN, 42)
        self.assertEqual(
            d.message,
            "CLAIM_DENIED_ADMIN_ONLY: Issue #42 is strictly reserved for "
            "human Admin execution. Autonomous bots cannot claim.")

    def test_swarm_issue_allowed(self):
        d = guard.quarantine_decision(SWARM, 43)
        self.assertTrue(d.allowed)
        self.assertEqual(d.code, guard.GRANT_CODE)
        self.assertEqual(d.execution_lane, guard.LANE_SWARM)

    def test_empty_labels_allowed(self):
        self.assertTrue(guard.quarantine_decision([], 44).allowed)

    def test_case_variants_fail_closed(self):
        for variant in ("Authority:Admin-Only", "AUTHORITY:ADMIN-ONLY",
                        " authority:admin-only "):
            self.assertFalse(
                guard.quarantine_decision([variant], 45).allowed, variant)

    def test_mixed_labels_still_denied(self):
        self.assertFalse(
            guard.quarantine_decision(SWARM + ADMIN, 46).allowed)

    def test_malformed_labels_raise(self):
        for bad in ("authority:admin-only", {"a": 1}, 7, None,
                    [1, 2], ["ok", 3]):
            with self.assertRaises(ValueError):
                guard.quarantine_decision(bad, 47)


class TestD2PickNextFilter(unittest.TestCase):
    def test_admin_only_excluded(self):
        queue = [{"number": 1, "labels": SWARM},
                 {"number": 2, "labels": ADMIN}]
        eligible, quarantined = guard.filter_pick_next(queue)
        self.assertEqual([c["number"] for c in eligible], [1])
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0]["candidate"]["number"], 2)
        self.assertEqual(quarantined[0]["reason"], guard.ADMIN_ONLY_LABEL)

    def test_malformed_candidates_never_eligible(self):
        queue = [{"number": "bad", "labels": []}, {"number": 4},
                 {"labels": SWARM}, "junk", 9]
        eligible, quarantined = guard.filter_pick_next(queue)
        self.assertEqual(eligible, [])
        self.assertEqual(len(quarantined), 5)
        self.assertTrue(all("reason" in q for q in quarantined))

    def test_empty_queue(self):
        self.assertEqual(guard.filter_pick_next([]), ([], []))

    def test_all_swarm_passes_through(self):
        queue = [{"number": n, "labels": SWARM} for n in (1, 2, 3)]
        eligible, quarantined = guard.filter_pick_next(queue)
        self.assertEqual([c["number"] for c in eligible], [1, 2, 3])
        self.assertEqual(quarantined, [])


class TestD3WorkQueueMarking(unittest.TestCase):
    def test_admin_only_marking(self):
        self.assertEqual(
            guard.work_queue_marking(ADMIN),
            {"claimable": False, "executionLane": guard.LANE_ADMIN})

    def test_swarm_marking(self):
        self.assertEqual(
            guard.work_queue_marking(SWARM),
            {"claimable": True, "executionLane": guard.LANE_SWARM})

    def test_case_variant_marked_admin(self):
        marking = guard.work_queue_marking(["AUTHORITY:ADMIN-ONLY"])
        self.assertFalse(marking["claimable"])


class TestD4CiClaimGate(unittest.TestCase):
    def test_agent_pr_closing_admin_issue_blocked(self):
        allowed, msg = guard.ci_claim_gate(True, ADMIN, 42)
        self.assertFalse(allowed)
        self.assertIn("CI CLAIM GATE", msg)
        self.assertIn("42", msg)

    def test_admin_own_pr_allowed(self):
        self.assertTrue(guard.ci_claim_gate(False, ADMIN, 42)[0])

    def test_agent_pr_on_swarm_issue_allowed(self):
        self.assertTrue(guard.ci_claim_gate(True, SWARM, 43)[0])

    def test_missing_labels_allowed(self):
        self.assertTrue(guard.ci_claim_gate(True, None, 44)[0])

    def test_agent_pr_mixed_labels_blocked(self):
        allowed, _ = guard.ci_claim_gate(True, SWARM + ADMIN, 45)
        self.assertFalse(allowed)


class TestConstantsSSOT(unittest.TestCase):
    def test_label_contract(self):
        self.assertEqual(guard.ADMIN_ONLY_LABEL, "authority:admin-only")
        self.assertEqual(guard.DENIAL_CODE, "CLAIM_DENIED_ADMIN_ONLY")
        self.assertEqual(guard.LABEL_COLOR, "B60205")

    def test_exit_code_contract(self):
        self.assertEqual(guard.EXIT_ALLOW, 0)
        self.assertEqual(guard.EXIT_DENY, 2)
        self.assertEqual(guard.EXIT_MALFORMED, 3)

    def test_lane_values(self):
        self.assertEqual(guard.LANE_ADMIN, "admin-only")
        self.assertEqual(guard.LANE_SWARM, "swarm")


class TestSelfTestAndCli(unittest.TestCase):
    def test_module_self_test_passes(self):
        self.assertTrue(guard.self_test())

    def test_cli_check_allow_exit_0(self):
        proc = run_cli("--check", "--issue", "43",
                       "--labels-json", json.dumps(SWARM))
        self.assertEqual(proc.returncode, 0, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["allowed"])

    def test_cli_check_deny_exit_2(self):
        proc = run_cli("--check", "--issue", "42",
                       "--labels-json", json.dumps(ADMIN))
        self.assertEqual(proc.returncode, 2)
        payload = json.loads(proc.stdout)
        self.assertFalse(payload["allowed"])
        self.assertIn("CLAIM_DENIED_ADMIN_ONLY", payload["message"])

    def test_cli_filter_queue(self):
        queue = json.dumps([{"number": 1, "labels": SWARM},
                            {"number": 2, "labels": ADMIN}])
        proc = run_cli("--filter", "--queue-json", queue)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["eligible"], [1])
        self.assertEqual(len(payload["quarantined"]), 1)

    def test_cli_malformed_fail_closed(self):
        proc = run_cli("--check", "--issue", "1", "--labels-json", "{oops")
        self.assertEqual(proc.returncode, 3)


def run_cli(*cli_args: str):
    import subprocess as sp
    module = Path(guard.__file__).resolve()
    return sp.run(
        [sys.executable, str(module), *cli_args],
        capture_output=True, text=True, encoding="utf-8", timeout=60)


if __name__ == "__main__":
    unittest.main()
