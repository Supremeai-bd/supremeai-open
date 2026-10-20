#!/usr/bin/env python3
"""Offline contract tests for Bridge Opener Hardening (#485, S08).

Asserts the "Mistake Immunity" contract the production edits to
scripts/ci/auto_bridge_pr_opener.py + tests/test_ci_guards.py must
satisfy: robust reflection typography, lossless evidence transfer,
stale-base verdicts/plans, and concurrency-limit detection (#479).

Pure stdlib. Run: python3 -m unittest test_s08_mistake_immunity -v
"""

import sys
import unittest
from pathlib import Path
from typing import Any, ClassVar

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "ci"))

import bridge_opener_hardening_reference as hard


def ev(agent, issue, ts, expires, state=None):
    return {
        "agent": agent,
        "issue": issue,
        "ts": ts,
        "expires_at": expires,
        "state": state,
    }


class ReflectionTypography(unittest.TestCase):
    def test_01_colon_passes(self):
        self.assertTrue(hard.has_reflection_evidence("Reflection: why"))

    def test_02_em_dash_passes(self):
        self.assertTrue(hard.has_reflection_evidence("Reflection \u2014 why"))

    def test_03_en_dash_passes(self):
        self.assertTrue(hard.has_reflection_evidence("Reflection\u2013 why"))

    def test_04_hyphen_passes(self):
        self.assertTrue(hard.has_reflection_evidence("Reflection- why"))

    def test_05_case_and_spacing_insensitive(self):
        self.assertTrue(hard.has_reflection_evidence("  reflection:\tvalue"))

    def test_06_negative_cases(self):
        for body in (
            "",
            None,
            "no reflection",
            "Reflections: plural",
            "Reflection without separator",
            "Reflection\t\n",
        ):
            self.assertFalse(hard.has_reflection_evidence(body), repr(body))

    def test_06b_substring_match_is_spec_literal(self):
        # The task mandates the unanchored regex verbatim; "InReflection:"
        # therefore matches (documented behavior, not a bug).
        self.assertTrue(hard.has_reflection_evidence("InReflection: glued"))

    def test_07_regex_constant(self):
        self.assertEqual(
            hard.REFLECTION_RE.pattern, r"Reflection\s*[:\u2014\u2013-]\s*\S"
        )


class LosslessEvidenceTransfer(unittest.TestCase):
    WO = (
        "### Task ID\nbridge-x\n\n## Test Evidence\n- a: 1\n- b: 2\n\n"
        "## Reflection Evidence (why + alternatives_rejected)\n"
        "- **why:** speed\n- **alternatives_rejected:** slow path\n\n"
        "## Rollback\nrevert it"
    )

    def test_08_both_sections_captured_verbatim(self):
        out = hard.extract_evidence_sections(self.WO)
        self.assertIn("## Test Evidence\n- a: 1\n- b: 2", out)
        self.assertIn(
            "## Reflection Evidence (why + alternatives_rejected)\n"
            "- **why:** speed\n- **alternatives_rejected:** slow path",
            out,
        )

    def test_09_why_and_alternatives_survive(self):
        out = hard.extract_evidence_sections(self.WO)
        self.assertIn("- **why:** speed", out)
        self.assertIn("- **alternatives_rejected:** slow path", out)

    def test_10_sections_stop_at_next_heading(self):
        out = hard.extract_evidence_sections(self.WO)
        self.assertNotIn("Rollback", out)
        self.assertNotIn("revert it", out)

    def test_11_non_evidence_body_untouched(self):
        self.assertEqual(hard.extract_evidence_sections("no sections"), "")
        self.assertEqual(hard.extract_evidence_sections(""), "")
        self.assertEqual(hard.extract_evidence_sections(None), "")

    def test_12_heading_suffix_preserved(self):
        out = hard.extract_evidence_sections(self.WO)
        self.assertIn("(why + alternatives_rejected)", out)

    def test_13_order_test_evidence_then_reflection(self):
        out = hard.extract_evidence_sections(self.WO)
        self.assertLess(
            out.index("## Test Evidence"), out.index("## Reflection Evidence")
        )

    def test_14_single_section_only(self):
        wo = "## Reflection Evidence\n- **why:** only"
        self.assertEqual(
            hard.extract_evidence_sections(wo),
            "## Reflection Evidence\n- **why:** only",
        )

    def test_15_indented_heading_variant(self):
        wo = "## Test Evidence\n body\n\n  ## Reflection Evidence\n- x: 1"
        out = hard.extract_evidence_sections(wo)
        self.assertIn("- x: 1", out)


class FreshBase(unittest.TestCase):
    def test_16_verdict_mapping(self):
        self.assertEqual(hard.fresh_base_verdict("ahead"), "fresh")
        self.assertEqual(hard.fresh_base_verdict("identical"), "fresh")
        self.assertEqual(hard.fresh_base_verdict("behind"), "stale")
        self.assertEqual(hard.fresh_base_verdict("diverged"), "stale")
        self.assertEqual(hard.fresh_base_verdict(None), "unknown")
        self.assertEqual(hard.fresh_base_verdict("weird"), "unknown")

    def test_17_plan_fresh_is_noop(self):
        self.assertEqual(
            hard.rebase_plan("b", "fresh", None), {"branch": "b", "action": "none"}
        )

    def test_18_plan_stale_clean_rebases(self):
        p = hard.rebase_plan("b", "stale", True)
        self.assertEqual(p["action"], "rebase_and_push")
        self.assertEqual(len(p["commands"]), 3)
        self.assertIn("force-with-lease", p["commands"][2])

    def test_19_plan_stale_conflict_skips(self):
        p = hard.rebase_plan("b", "stale", False)
        self.assertEqual(p["action"], "skip")
        self.assertEqual(p["reason"], "stale-base-conflict")

    def test_20_plan_unknown_fails_closed(self):
        self.assertEqual(hard.rebase_plan("b", "unknown", None)["action"], "skip")

    def test_21_plan_deterministic(self):
        a = hard.rebase_plan("b", "stale", True)
        b = hard.rebase_plan("b", "stale", True)
        self.assertEqual(a, b)


class ConcurrencyDetection(unittest.TestCase):
    EVENTS: ClassVar[list[dict[str, Any]]] = [
        ev("a", 900, "2026-10-17T06:00:00Z", "2026-10-17T06:30:00Z"),
        ev("a", 901, "2026-10-17T06:05:00Z", "2026-10-17T06:35:00Z"),
        ev("b", 905, "2026-10-17T06:00:00Z", "2026-10-17T06:30:00Z"),
    ]

    def test_22_hoarder_flagged(self):
        flagged = hard.detect_concurrent_claims(self.EVENTS, "2026-10-17T06:10:00Z")
        self.assertEqual(
            flagged, [{"agent": "a", "active_claims": [900, 901], "limit": 1}]
        )

    def test_23_expired_leases_do_not_count(self):
        self.assertEqual(
            hard.detect_concurrent_claims(self.EVENTS, "2026-10-17T06:40:00Z"), []
        )

    def test_24_closed_issues_do_not_count(self):
        events = self.EVENTS + [
            ev("c", 910, "2026-10-17T06:00:00Z", "2026-10-17T06:30:00Z", state="closed")
        ]
        self.assertEqual(
            len(hard.detect_concurrent_claims(events, "2026-10-17T06:10:00Z")), 1
        )

    def test_25_deterministic_agent_order(self):
        events = self.EVENTS + [
            ev("b", 906, "2026-10-17T06:05:00Z", "2026-10-17T06:35:00Z")
        ]
        got = [
            f["agent"]
            for f in hard.detect_concurrent_claims(events, "2026-10-17T06:10:00Z")
        ]
        self.assertEqual(got, ["a", "b"])

    def test_26_boundary_exactly_at_expiry_is_inactive(self):
        self.assertEqual(
            hard.detect_concurrent_claims(self.EVENTS, "2026-10-17T06:30:00Z"), []
        )

    def test_27_fail_closed_inputs(self):
        for bad_now in ("", "not-a-time", None, "2026-10-17 06:00:00"):
            with self.assertRaises(ValueError):
                hard.detect_concurrent_claims(self.EVENTS, bad_now)  # type: ignore[arg-type]
        for bad_ev in ([{"agent": "a"}], [{"issue": 1}], [{"agent": 5, "issue": "x"}]):
            with self.assertRaises(ValueError):
                hard.detect_concurrent_claims(bad_ev, "2026-10-17T06:00:00Z")


class Contract(unittest.TestCase):
    def test_28_constants(self):
        self.assertEqual(hard.MAX_ACTIVE_CLAIMS, 1)
        self.assertEqual(
            hard.EVIDENCE_HEADINGS, ("## Test Evidence", "## Reflection Evidence")
        )
        self.assertIn("identical", hard.FRESH_COMPARE_STATUSES)


if __name__ == "__main__":
    unittest.main(verbosity=2)
