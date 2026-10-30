#!/usr/bin/env python3
"""Offline contract tests for evidence-lane role classification (SPEC §2).

Root-cause fix receipt for the live mis-dispatch 2026-10-30T11:19Z: issue #2529
("audit(federation): P0 #2511 RCA verified …", labels: []) was dispatched with
role=coder + task_type=IMPLEMENT although the row's own body declares
"Audit (auditor envelope, evidence-only, zero fixes attempted)". The board's
own title convention "verb(scope):" states the lane; the classifier now maps
the first title token deterministically, while label signals (status:runway,
gate:pre-landing) keep precedence. Envelope task_type derives honestly from
the final role instead of the hardcoded "IMPLEMENT" plaque.

Coverage:
  1. classify_task_role title-prefix mapping (audit/report/triage/verify/
     census/ops/dispatch → task-auditor; guard/sentry → platform-guardian;
     scout → ecosystem-scout), case-insensitive, with label precedence.
  2. Unmapped prefixes (fix/feat/chore…) keep the legacy behavior byte-for-byte.
  3. build_task_envelope derives task_type from the final role (including
     role_override), not the hardcoded IMPLEMENT.
  4. The dispatch path passes the picked title to classify_task_role
     (labels-only call would regress #2529-class rows to coder).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal

LOOP_SOURCE = (_ROOT / "scripts" / "agents" / "continuous_agent_loop.py").read_text(encoding="utf-8")


class TestEvidenceLaneTitleClassification(unittest.TestCase):
    def test_audit_prefix_maps_to_task_auditor(self):
        # The live #2529 case verbatim (first 60 chars).
        self.assertEqual(
            cal.classify_task_role(
                title="audit(federation): P0 #2511 RCA verified from ci.yml source (schedule-only",
                labels=[],
            ),
            "task-auditor",
        )

    def test_report_prefix_case_insensitive(self):
        # Board rows use both "report(...)" and "Report (falsified-first): ...".
        self.assertEqual(
            cal.classify_task_role(title="Report (falsified-first): #2609 Finding 1 not reproduced", labels=[]),
            "task-auditor",
        )
        self.assertEqual(
            cal.classify_task_role(title="report(guard): #2557 post-closure verification", labels=["audit:finding"]),
            "task-auditor",
        )

    def test_keyword_phrases_never_invent_a_role(self):
        # #489 contract (Tier3 zero-regression): keyword-only titles route to
        # the preserved coder default — only the strict "verb(scope)[()]"
        # / "verb:" shape may classify.
        for title in ("audit readiness report", "report the drift", "scouting mission", "verification pass"):
            with self.subTest(title=title):
                self.assertEqual(cal.classify_task_role(title=title, labels=[]), "coder")

    def test_triage_verify_census_ops_dispatch_map_to_task_auditor(self):
        for title in (
            "triage(ci): #3192/merge red is an AUTO-LANDING merge-conflict exit",
            "verify(platform): R62/#2395 third independent per_page probe",
            "census(wq): full-board drain census r2",
            "ops(bridge): drain dynamics r2",
            "dispatch(labels): #1668 has EMPTY GitHub labels since filing",
        ):
            with self.subTest(title=title):
                self.assertEqual(cal.classify_task_role(title=title, labels=[]), "task-auditor")

    def test_guard_sentry_map_to_platform_guardian(self):
        self.assertEqual(
            cal.classify_task_role(title="guard(platform): sentry pass 08:45Z — 7/8 alive", labels=[]),
            "platform-guardian",
        )
        self.assertEqual(cal.classify_task_role(title="sentry: provider reprobe", labels=[]), "platform-guardian")

    def test_scout_maps_to_ecosystem_scout(self):
        self.assertEqual(
            cal.classify_task_role(
                title="scout(R79): closure verdicts lack a live-state gate", labels=["status:unclaimed", "radar"]
            ),
            "ecosystem-scout",
        )

    def test_label_precedence_runway_and_gate_beat_title_prefix(self):
        # A triage/verify-titled row carrying status:runway is a CI lane task.
        self.assertEqual(
            cal.classify_task_role(title="triage(ci): runway red", labels=["status:runway"]),
            "ci-fixer",
        )
        self.assertEqual(
            cal.classify_task_role(title="audit(pre-landing): gate row", labels=["gate:pre-landing"]),
            "task-auditor",
        )

    def test_unmapped_prefixes_keep_legacy_behavior(self):
        # fix/feat/chore and arbitrary titles: label logic unchanged.
        self.assertEqual(cal.classify_task_role(title="fix: something real", labels=[]), "coder")
        self.assertEqual(cal.classify_task_role(title="feat(bridge): new lane", labels=["status:claimed"]), "coder")
        self.assertEqual(cal.classify_task_role(title="chore: tidy", labels=[]), "coder")
        self.assertEqual(cal.classify_task_role(title="", labels=["status:claimed"]), "coder")
        self.assertEqual(cal.classify_task_role(title="", labels=[]), "coder")

    def test_bridge_work_order_emoji_title_unmapped(self):
        self.assertEqual(
            cal.classify_task_role(title="🌉 Bridge Work Order — Identity registration", labels=[]),
            "coder",
        )


class TestEnvelopeTaskTypeDerivation(unittest.TestCase):
    def test_audit_row_gets_auditor_role_and_audit_type(self):
        issue = {
            "number": 2529,
            "title": "audit(federation): P0 #2511 RCA verified from ci.yml source",
            "state": "open",
            "body": "Audit (auditor envelope, evidence-only, zero fixes attempted)",
            "labels": [],
        }
        env = cal.build_task_envelope(issue)["task_envelope"]
        self.assertEqual(env["role"], "task-auditor")
        self.assertEqual(env["task_type"], "AUDIT")

    def test_coder_row_keeps_implement(self):
        issue = {"number": 7, "title": "fix: something real", "state": "open", "labels": []}
        env = cal.build_task_envelope(issue)["task_envelope"]
        self.assertEqual(env["role"], "coder")
        self.assertEqual(env["task_type"], "IMPLEMENT")

    def test_scout_row_gets_scout_type(self):
        issue = {"number": 2925, "title": "scout(R79): closure verdicts lack a live-state gate", "state": "open"}
        env = cal.build_task_envelope(issue)["task_envelope"]
        self.assertEqual(env["role"], "ecosystem-scout")
        self.assertEqual(env["task_type"], "SCOUT")

    def test_guard_row_gets_ops_type(self):
        issue = {"number": 3111, "title": "guard(platform): sentry pass 08:45Z", "state": "open"}
        env = cal.build_task_envelope(issue)["task_envelope"]
        self.assertEqual(env["role"], "platform-guardian")
        self.assertEqual(env["task_type"], "OPS")

    def test_role_override_recomputes_task_type(self):
        issue = {"number": 9, "title": "fix: something real", "state": "open", "labels": []}
        env = cal.build_task_envelope(issue, role_override="ci-fixer")["task_envelope"]
        self.assertEqual(env["role"], "ci-fixer")
        self.assertEqual(env["task_type"], "FIX")

    def test_task_type_stays_in_valid_registry(self):
        # Every role the classifier can emit must map into VALID_TASK_TYPES.
        for role in ("coder", "solver", "ci-fixer", "auditor", "task-auditor", "ecosystem-scout", "platform-guardian"):
            self.assertIn(cal.ROLE_TASK_TYPES.get(role, "IMPLEMENT"), cal.VALID_TASK_TYPES)


class TestDispatchPathPassesTitle(unittest.TestCase):
    def test_dispatch_call_site_passes_picked_title(self):
        # The mandate path must classify with title+labels — a labels-only
        # call regresses audit(/report(/… rows to coder (#2529 live class).
        self.assertIn(
            "classify_task_role(title=picked_title, labels=picked_labels)",
            LOOP_SOURCE,
            "dispatch path must pass the picked title into classify_task_role",
        )


if __name__ == "__main__":
    unittest.main()
