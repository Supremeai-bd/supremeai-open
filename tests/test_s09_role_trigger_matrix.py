#!/usr/bin/env python3
"""Offline contract tests for the S09 Deterministic Role Trigger Matrix
(issue #489).

Asserts the Continuous Agent Loop role plane satisfies:

  * 8 canonical role contracts carrying the full Triad (responsibility,
    must-follow rules, negative constraints, scoped weapons);
  * two-paradigm partition (task-driven vs time-driven) with a bijective
    deterministic event router;
  * fail-closed structured dispatch (labels/payload gates, no keyword
    matching anywhere);
  * least-privilege RBAC provisioning;
  * role-specific output contracts (Scout ≥10 proposals, adversarial
    exploit scope, Human-Eye issue-only findings).

Pure stdlib. Run: python3 -m unittest test_s09_role_trigger_matrix -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "agents"))

import role_trigger_matrix as rtm


def proposal(n: int, **overrides) -> rtm.ScoutProposal:
    base = dict(
        title=f"proposal {n}",
        source="web",
        pros=("p",),
        cons=("c",),
        anti_patterns=("a",),
        risks=("r",),
        dont_do_this=("d",),
        philosophy_verdict=rtm.CORE_PHILOSOPHY_FILTERS[0],
    )
    base.update(overrides)
    return rtm.ScoutProposal(**base)


class RoleDirectory(unittest.TestCase):
    def test_01_exactly_eight_roles(self):
        self.assertEqual(len(rtm.ROLE_CONTRACTS), 8)
        self.assertEqual(
            sorted(rtm.ROLE_IDS),
            [
                "ci-fixer",
                "coder",
                "ecosystem-scout",
                "federation-auditor",
                "human-eye",
                "platform-guardian",
                "rules-breaker",
                "task-auditor",
            ],
        )

    def test_02_triad_complete_every_role(self):
        for role in rtm.ROLE_IDS:
            c = rtm.ROLE_CONTRACTS[role]
            self.assertTrue(c.responsibility, role)
            self.assertTrue(c.must_follow, role)
            self.assertTrue(c.must_not, role)
            self.assertTrue(c.weapons, role)
            self.assertTrue(c.forbidden_operations, role)
            self.assertIn(c.paradigm, rtm.PARADIGMS)

    def test_03_bengali_identity_present(self):
        for role in rtm.ROLE_IDS:
            self.assertTrue(rtm.ROLE_CONTRACTS[role].name_bn, role)

    def test_04_paradigm_partition_matches_issue_diagram(self):
        task = {
            r for r, c in rtm.ROLE_CONTRACTS.items() if c.paradigm == rtm.TASK_DRIVEN
        }
        time_ = {
            r for r, c in rtm.ROLE_CONTRACTS.items() if c.paradigm == rtm.TIME_DRIVEN
        }
        self.assertEqual(task, {"coder", "ci-fixer", "task-auditor"})
        self.assertEqual(
            time_,
            {
                "ecosystem-scout",
                "federation-auditor",
                "human-eye",
                "rules-breaker",
                "platform-guardian",
            },
        )
        self.assertEqual(task | time_, set(rtm.ROLE_IDS))
        self.assertFalse(task & time_)

    def test_05_weapon_types_from_issue_matrix(self):
        expected = {
            "coder": "Surgical Knife",
            "ci-fixer": "Emergency Defibrillator",
            "task-auditor": "Policy Stamp",
            "ecosystem-scout": "Long-Range Telescope",
            "federation-auditor": "Ledger Microscope",
            "human-eye": "Stylist Camera",
            "rules-breaker": "Sledgehammer",
            "platform-guardian": "Circuit Breaker",
        }
        for role, weapon in expected.items():
            self.assertIn(weapon, rtm.ROLE_CONTRACTS[role].weapon_type)

    def test_06_get_contract_fail_closed(self):
        with self.assertRaises(ValueError):
            rtm.get_contract("nonexistent")
        self.assertIs(rtm.get_contract("coder"), rtm.ROLE_CONTRACTS["coder"])


class TriggerMatrix(unittest.TestCase):
    def test_07_event_router_bijective(self):
        self.assertEqual(len(rtm.EVENT_INDEX), 8)
        self.assertEqual(
            set(rtm.EVENT_INDEX),
            {c.trigger.event_type for c in rtm.ROLE_CONTRACTS.values()},
        )
        for event, role in rtm.EVENT_INDEX.items():
            self.assertEqual(rtm.ROLE_CONTRACTS[role].trigger.event_type, event)

    def test_08_dispatch_coder_requires_claim_label(self):
        d = rtm.dispatch(
            rtm.DispatchSignal(
                "event:task.claimed", frozenset({"status:claimed", "P1-high"})
            )
        )
        self.assertEqual(d.decision, rtm.DECISION_DISPATCH)
        self.assertEqual(d.role_id, "coder")
        self.assertEqual(d.paradigm, rtm.TASK_DRIVEN)
        self.assertIn("write_to_file", d.weapons)

    def test_09_label_gate_deny_carries_missing_labels(self):
        d = rtm.dispatch(rtm.DispatchSignal("event:task.claimed"))
        self.assertEqual(d.decision, rtm.DECISION_DENY)
        self.assertEqual(d.reason, "LABEL_GATE")
        self.assertEqual(d.missing_labels, ("status:claimed",))

    def test_10_unknown_event_denied(self):
        d = rtm.dispatch(rtm.DispatchSignal("event:totally.unknown"))
        self.assertEqual(d.reason, "UNKNOWN_EVENT")

    def test_11_payload_gates(self):
        ok = rtm.dispatch(
            rtm.DispatchSignal(
                "event:pr.ci_failed",
                payload={"pr_number": 7, "checks_state": "failing"},
            )
        )
        self.assertEqual(ok.role_id, "ci-fixer")
        self.assertEqual(
            rtm.dispatch(
                rtm.DispatchSignal(
                    "event:pr.ci_failed",
                    payload={"pr_number": 7, "checks_state": "passing"},
                )
            ).reason,
            "PAYLOAD_MISMATCH",
        )
        self.assertEqual(
            rtm.dispatch(
                rtm.DispatchSignal(
                    "event:pr.ci_failed", payload={"checks_state": "failing"}
                )
            ).reason,
            "PAYLOAD_GATE",
        )
        self.assertEqual(
            rtm.dispatch(
                rtm.DispatchSignal(
                    "event:pr.pre_landing", payload={"landing_gate": "disarmed"}
                )
            ).reason,
            "PAYLOAD_MISMATCH",
        )
        self.assertEqual(
            rtm.dispatch(
                rtm.DispatchSignal(
                    "event:pr.pre_landing", payload={"landing_gate": "armed"}
                )
            ).role_id,
            "task-auditor",
        )

    def test_12_schedule_gates(self):
        ok = rtm.dispatch(
            rtm.DispatchSignal(
                "event:schedule.federation_audit",
                payload={"schedule_kind": "cron", "schedule_expr": "0 3 * * *"},
            )
        )
        self.assertEqual(ok.role_id, "federation-auditor")
        self.assertEqual(
            rtm.dispatch(
                rtm.DispatchSignal(
                    "event:schedule.federation_audit",
                    payload={"schedule_kind": "fixed_rate", "schedule_expr": "5m"},
                )
            ).reason,
            "SCHEDULE_GATE",
        )
        self.assertEqual(
            rtm.dispatch(
                rtm.DispatchSignal(
                    "event:schedule.adversarial_probe", payload={"schedule_expr": "15m"}
                )
            ).reason,
            "SCHEDULE_GATE",
        )

    def test_13_provider_alert_gate(self):
        self.assertEqual(
            rtm.dispatch(
                rtm.DispatchSignal(
                    "event:provider.health_alert", payload={"alert_state": "unhealthy"}
                )
            ).role_id,
            "platform-guardian",
        )
        self.assertEqual(
            rtm.dispatch(
                rtm.DispatchSignal(
                    "event:provider.health_alert", payload={"alert_state": "healthy"}
                )
            ).reason,
            "PAYLOAD_MISMATCH",
        )

    def test_14_label_plane_priority_and_deny(self):
        self.assertEqual(
            rtm.dispatch_from_labels(["status:runway", "status:claimed"]).role_id,
            "ci-fixer",
        )
        self.assertEqual(
            rtm.dispatch_from_labels(["gate:pre-landing", "status:claimed"]).role_id,
            "task-auditor",
        )
        self.assertEqual(rtm.dispatch_from_labels(["status:claimed"]).role_id, "coder")
        d = rtm.dispatch_from_labels(["P1-high", "area:ci", "enhancement"])
        self.assertEqual(d.reason, "NO_TRIGGER")
        self.assertEqual(rtm.dispatch_from_labels([]).reason, "NO_TRIGGER")

    def test_15_signal_is_structural_only(self):
        self.assertEqual(
            set(rtm.DispatchSignal.__dataclass_fields__),
            {"event_type", "labels", "payload"},
        )
        self.assertTrue(rtm.KEYWORD_MATCHING_DEPRECATED)

    def test_16_dispatch_rejects_non_signal(self):
        with self.assertRaises(TypeError):
            rtm.dispatch("event:task.claimed")  # type: ignore[arg-type]

    def test_17_decision_json_round_trip(self):
        import json

        d = rtm.dispatch(
            rtm.DispatchSignal("event:task.claimed", frozenset({"status:claimed"}))
        )
        parsed = json.loads(d.to_json())
        self.assertEqual(parsed["decision"], "DISPATCH")
        self.assertEqual(parsed["role_id"], "coder")
        self.assertIn("test_runner", parsed["weapons"])


class RbacLeastPrivilege(unittest.TestCase):
    def test_18_provision_exact_allowlist(self):
        for role in rtm.ROLE_IDS:
            self.assertEqual(
                rtm.provision_weapons(role), rtm.ROLE_CONTRACTS[role].weapons
            )

    def test_19_authorize_fail_closed(self):
        self.assertTrue(rtm.authorize("ci-fixer", "pr_branch_commit"))
        self.assertFalse(rtm.authorize("ci-fixer", "pr_review_approve_block"))
        self.assertFalse(rtm.authorize("ghost", "anything"))
        self.assertFalse(rtm.authorize("coder", "pr_merge_admin"))

    def test_20_auditor_family_holds_no_write_weapons(self):
        for role in (
            "task-auditor",
            "ecosystem-scout",
            "federation-auditor",
            "human-eye",
            "platform-guardian",
        ):
            overlap = rtm.provision_weapons(role) & rtm.CODE_WRITE_WEAPONS
            self.assertEqual(overlap, frozenset(), role)

    def test_21_rules_breaker_cannot_self_patch(self):
        weapons = rtm.provision_weapons("rules-breaker")
        self.assertFalse(
            weapons
            & {"replace_file_content", "multi_replace_file_content", "write_to_file"}
        )
        self.assertIn(rtm.SCOPED_COMMIT_WEAPON, weapons)

    def test_22_least_privilege_violation_raises(self):
        with self.assertRaises(rtm.LeastPrivilegeViolation):
            rtm.assert_least_privilege(
                "human-eye", ["browser_subagent", "write_to_file"]
            )
        rtm.assert_least_privilege("human-eye", ["browser_subagent", "gh_issue_create"])

    def test_23_adversarial_commit_scope(self):
        rtm.assert_commit_scope("rules-breaker", "tests/adversarial/probe.py")
        rtm.assert_commit_scope("rules-breaker", "tests/adversarial/nested/t.py")
        with self.assertRaises(rtm.LeastPrivilegeViolation):
            rtm.assert_commit_scope("rules-breaker", "src/app.py")
        with self.assertRaises(rtm.LeastPrivilegeViolation):
            rtm.assert_commit_scope("rules-breaker", "tests/test_x.py")

    def test_24_unrestricted_roles_have_no_scope(self):
        self.assertEqual(rtm.ROLE_CONTRACTS["coder"].commit_scopes, ())


class ScoutContract(unittest.TestCase):
    def test_25_minimum_ten_proposals(self):
        self.assertEqual(rtm.MIN_SCOUT_PROPOSALS, 10)
        batch = [proposal(i) for i in range(10)]
        self.assertEqual(rtm.validate_scout_batch(batch), tuple(range(10)))
        with self.assertRaises(rtm.ScoutBatchError):
            rtm.validate_scout_batch(batch[:9])

    def test_26_full_spectrum_fields_mandatory(self):
        for field_name in ("pros", "cons", "risks", "dont_do_this"):
            batch = [
                proposal(0, **{field_name: ()}) for _ in range(rtm.MIN_SCOUT_PROPOSALS)
            ]
            with self.assertRaises(rtm.ScoutBatchError):
                rtm.validate_scout_batch(batch)

    def test_27_philosophy_filter_enforced(self):
        batch = [
            proposal(0, philosophy_verdict="follow the hype")
            for _ in range(rtm.MIN_SCOUT_PROPOSALS)
        ]
        with self.assertRaises(rtm.ScoutBatchError):
            rtm.validate_scout_batch(batch)
        self.assertEqual(
            rtm.CORE_PHILOSOPHY_FILTERS,
            ("Simple > Clever", "Complexity must earn existence", "Zero-Admin"),
        )

    def test_28_scout_is_read_only(self):
        self.assertEqual(
            rtm.provision_weapons("ecosystem-scout"),
            frozenset({"search_web", "read_url_content", "gh_issue_create"}),
        )


class ExploitContract(unittest.TestCase):
    def test_29_valid_guard_evasion(self):
        rtm.validate_exploit_report(
            rtm.ExploitReport(
                vector="guard_evasion",
                failing_test_path="tests/adversarial/double_claim.py",
                p0_issue_filed=True,
            )
        )

    def test_30_scope_enforced(self):
        for path in (
            "src/attack.py",
            "tests/unit/attack.py",
            "adversarial/attack.py",
            "tests/adversarial_evil/t.py",
        ):
            with self.assertRaises(rtm.ExploitContractError):
                rtm.validate_exploit_report(
                    rtm.ExploitReport(
                        vector="guard_evasion",
                        failing_test_path=path,
                        p0_issue_filed=True,
                    )
                )

    def test_31_p0_and_vector_and_no_self_patch(self):
        with self.assertRaises(rtm.ExploitContractError):
            rtm.validate_exploit_report(
                rtm.ExploitReport(
                    vector="guard_evasion",
                    failing_test_path="tests/adversarial/t.py",
                    p0_issue_filed=False,
                )
            )
        with self.assertRaises(rtm.ExploitContractError):
            rtm.validate_exploit_report(
                rtm.ExploitReport(
                    vector="race_condition",
                    failing_test_path="tests/adversarial/t.py",
                    p0_issue_filed=True,
                )
            )
        with self.assertRaises(rtm.ExploitContractError):
            rtm.validate_exploit_report(
                rtm.ExploitReport(
                    vector="guard_evasion",
                    failing_test_path="tests/adversarial/t.py",
                    p0_issue_filed=True,
                    patch_code_present=True,
                )
            )

    def test_32_unguarded_damage_requires_evidence(self):
        rtm.validate_exploit_report(
            rtm.ExploitReport(
                vector="unguarded_damage",
                failing_test_path="tests/adversarial/memory_leak.py",
                p0_issue_filed=True,
                damage_evidence="cpu 100% spike 3min",
            )
        )
        with self.assertRaises(rtm.ExploitContractError):
            rtm.validate_exploit_report(
                rtm.ExploitReport(
                    vector="unguarded_damage",
                    failing_test_path="tests/adversarial/memory_leak.py",
                    p0_issue_filed=True,
                )
            )

    def test_33_p0_label_is_issue_ssot(self):
        self.assertEqual(rtm.P0_LABEL, "P0-critical")
        self.assertEqual(
            rtm.ROLE_CONTRACTS["rules-breaker"].issue_labels, (rtm.P0_LABEL,)
        )
        self.assertEqual(rtm.ADVERSARIAL_SCOPE, "tests/adversarial/")


class HumanEyeContract(unittest.TestCase):
    def test_34_issue_only_findings(self):
        rtm.validate_visual_finding(
            rtm.VisualFinding(
                surface="landing page",
                finding="font pair clashes",
                color_harmony_ok=False,
                typography_ok=False,
                premium_feel_ok=True,
                recommended_issue="swap heading font to the display family",
            )
        )

    def test_35_code_edit_proposals_rejected(self):
        with self.assertRaises(rtm.VisualFindingError):
            rtm.validate_visual_finding(
                rtm.VisualFinding(
                    surface="dashboard",
                    finding="bad spacing",
                    color_harmony_ok=True,
                    typography_ok=True,
                    premium_feel_ok=True,
                    recommended_issue="fix it",
                    code_edit_proposed=True,
                )
            )

    def test_36_no_git_weapons(self):
        weapons = rtm.provision_weapons("human-eye")
        self.assertFalse(weapons & rtm.CODE_WRITE_WEAPONS)
        self.assertEqual(weapons, frozenset({"browser_subagent", "gh_issue_create"}))


class DeprecationGuarantees(unittest.TestCase):
    def test_37_no_keyword_api_on_matrix_module(self):
        self.assertFalse(hasattr(rtm, "classify_task_role"))
        self.assertFalse(hasattr(rtm, "classify_from_text"))
        self.assertFalse(hasattr(rtm, "match_keywords"))
        self.assertTrue(rtm.KEYWORD_MATCHING_DEPRECATED)

    def test_38_label_matching_is_exact_not_substring(self):
        # A label that merely CONTAINS a trigger string must not trigger.
        d = rtm.dispatch_from_labels(["xstatus:claimedx"])
        self.assertEqual(d.reason, "NO_TRIGGER")
        # Event type must match exactly too.
        self.assertEqual(
            rtm.dispatch(rtm.DispatchSignal("event:task.claimedX")).reason,
            "UNKNOWN_EVENT",
        )

    def test_39_self_test_entrypoint_green(self):
        self.assertTrue(rtm.self_test())


if __name__ == "__main__":
    unittest.main(verbosity=2)
