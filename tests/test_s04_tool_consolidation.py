#!/usr/bin/env python3
"""Dual-mode tests for S0.4 tool consolidation (task #459).

The no-regression guarantee is executable: full coverage, zero ambiguity,
deterministic sha256 receipts. UNIT runs offline; CONTRACT skips until live.

Run: pytest tests/test_s04_tool_consolidation.py  OR  python3 tests/test_s04_tool_consolidation.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REF_DIR = HERE.parent / "scripts" / "tower"
if str(REF_DIR) not in sys.path:
    sys.path.insert(0, str(REF_DIR))

import tool_consolidation_reference as s04  # noqa: E402
import work_claim_reference as s01  # noqa: E402  (heartbeat-via-claim SSOT)


class UnitMappingCoverage(unittest.TestCase):
    def setUp(self):
        self.report = s04.coverage_report()

    def test_01_all_nine_legacy_tools_present(self):
        self.assertEqual(self.report["legacy_count"], 9)
        self.assertEqual(len(s04.REGISTRY), 9)

    def test_02_zero_orphans(self):
        self.assertEqual(self.report["orphans"], [])

    def test_03_zero_ambiguity(self):
        self.assertEqual(self.report["ambiguous"], [])

    def test_04_all_targets_in_core_or_removed(self):
        self.assertEqual(self.report["unknown_targets"], [])

    def test_05_core_is_five(self):
        self.assertEqual(len(s04.CORE_TOOLS), 5)

    def test_06_route_each_legacy_deterministic(self):
        for name in s04.LEGACY_NAMES:
            self.assertIs(s04.route(name), s04.route(name))

    def test_07_route_unknown_fails_closed(self):
        with self.assertRaises(s04.ConsolidationError) as ctx:
            s04.route("no_such_tool")
        self.assertEqual(ctx.exception.code, "E_UNKNOWN_TOOL")

    def test_08_bridge_guide_is_removal_not_hiding(self):
        m = s04.route("bridge_guide")
        self.assertEqual(m.kind, "REMOVED")

    def test_09_heartbeat_goes_to_claim(self):
        self.assertEqual(s04.route("agent_heartbeat").target, "work_claim")

    def test_10_assert_no_regression_passes_now(self):
        s04.assert_no_regression()  # must not raise

    def test_11_registry_edit_breaks_suite(self):
        # simulate a future bad edit: a mapping to a non-core target must fail the gate
        bad = s04.Mapping("system_summary", "rogue_tool", 'rogue()', "MERGED")
        saved = s04.REGISTRY
        try:
            s04.REGISTRY = tuple(m for m in saved if m.legacy != "system_summary") + (bad,)
            with self.assertRaises(s04.ConsolidationError):
                s04.assert_no_regression()
        finally:
            s04.REGISTRY = saved


class UnitHeartbeatSemantics(unittest.TestCase):
    def test_12_claim_renew_is_presence_via_s01_matrix(self):
        # SSOT: heartbeat absorbed by work.claim — renewal path proves presence
        from datetime import datetime, timedelta, timezone
        t0 = datetime(2026, 10, 17, 4, 0, 0, tzinfo=timezone.utc)
        stale = s01.Claim(issue=1, agent="zai", ts=t0 - timedelta(minutes=s01.TTL_MINUTES + 1))
        self.assertEqual(s01.evaluate_claim(stale, 1, "zai", t0), s01.GRANT_RENEW)


class UnitReceipts(unittest.TestCase):
    def test_13_receipt_digests_correct(self):
        r = s04.build_submission_receipt({"x.py": "print(1)\n"}, commit_sha="abc")
        entry = r["files"][0]
        self.assertEqual(entry["bytes"], 9)
        self.assertEqual(entry["sha256"], hashlib.sha256(b"print(1)\n").hexdigest())
        self.assertTrue(r["verified"])

    def test_14_receipt_sorted_deterministic(self):
        a = s04.build_submission_receipt({"b.md": "b", "a.py": "a"})
        b = s04.build_submission_receipt({"a.py": "a", "b.md": "b"})
        self.assertEqual(a, b)
        self.assertEqual([e["path"] for e in a["files"]], ["a.py", "b.md"])

    def test_15_receipt_fail_closed_on_unreadable(self):
        r = s04.build_submission_receipt({"ok.py": "x", "bad.py": None})
        self.assertFalse(r["verified"])
        self.assertEqual(r["unverified_paths"], ["bad.py"])
        self.assertEqual(len(r["files"]), 1)  # no partial digest for the broken file

    def test_16_tree_sha_changes_with_content(self):
        a = s04.build_submission_receipt({"f.txt": "one"})
        b = s04.build_submission_receipt({"f.txt": "two"})
        self.assertNotEqual(a["tree_sha256"], b["tree_sha256"])

    def test_17_tree_sha_stable_across_key_order(self):
        a = s04.build_submission_receipt({"a": "1", "b": "2"})
        b = s04.build_submission_receipt({"b": "2", "a": "1"})
        self.assertEqual(a["tree_sha256"], b["tree_sha256"])


class LiveContract(unittest.TestCase):
    def test_18_registry_healthy(self):
        s04.assert_no_regression()


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
