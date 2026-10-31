#!/usr/bin/env python3
"""Offline tests for loop_v1 (lightweight loop variant, parity close-out).

# বাংলা: loop_v1.py এইমাত্র ল্যান্ড হওয়া নতুন স্ক্রিপ্ট — এর কোনো টেস্ট ছিল
# না, ফলে test parity guard fail-closed লাল হচ্ছিল। এই ফাইল পিওর ফাংশনগুলো
# (is_claimable, pick_next_issue, pick_next_scheduled_role, lease store)
# অফলাইনে পিন করে। নেটওয়ার্ক-নির্ভর অংশ (fetch_open_issues) এখানে পড়ে না।
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import loop_v1 as lv


def _issue(number, title, label_names=None, state="open"):
    return {
        "number": number,
        "title": title,
        "state": state,
        "labels": [{"name": n} for n in (label_names or [])],
    }


class TestIsClaimable(unittest.TestCase):
    def setUp(self):
        # স্টোর ফাইল মডিউল-কনস্ট্যান্ট relative path — tempdir-এ প্যাচ করি
        self._td = tempfile.TemporaryDirectory()
        td = Path(self._td.name)
        self._orig_lease, self._orig_rot = lv.ISSUE_LEASE_STORE, lv.ROTATION_STORE
        lv.ISSUE_LEASE_STORE = td / "lease.json"
        lv.ROTATION_STORE = td / "rotation.json"
        self.addCleanup(self._restore)

    def _restore(self):
        lv.ISSUE_LEASE_STORE, lv.ROTATION_STORE = self._orig_lease, self._orig_rot
        self._td.cleanup()

    def test_open_unlabeled_issue_is_claimable(self):
        self.assertTrue(lv.is_claimable(_issue(1, "Fix the thing")))

    def test_excluded_labels_block_claim(self):
        for label in ("claimed", "in-progress", "blocked", "wip",
                      "ci-failed", "stale", "duplicate", "invalid",
                      "report-only", "bridge:receipt"):
            self.assertFalse(
                lv.is_claimable(_issue(2, "x", [label])), label)

    def test_anchor_and_sentry_titles_excluded(self):
        self.assertFalse(lv.is_claimable(_issue(3, "Anchor Hub alignment")))
        self.assertFalse(lv.is_claimable(_issue(4, "report(sentry): c74")))

    def test_non_open_state_excluded(self):
        self.assertFalse(lv.is_claimable(_issue(5, "x", state="closed")))

    def test_fresh_lease_within_cooldown_blocks_claim(self):
        lv.ISSUE_LEASE_STORE.write_text(
            json.dumps({"6": time.time()}), encoding="utf-8")
        self.assertFalse(lv.is_claimable(_issue(6, "x")))

    def test_lease_older_than_30_min_allows_claim(self):
        lv.ISSUE_LEASE_STORE.write_text(
            json.dumps({"7": time.time() - 1801.0}), encoding="utf-8")
        self.assertTrue(lv.is_claimable(_issue(7, "x")))


class TestPickNextIssue(unittest.TestCase):
    def test_priority_tier_then_number_ordering(self):
        issues = [
            _issue(12, "p3 task", ["p3-low"]),
            _issue(10, "p1 task", ["p1-high"]),
            _issue(11, "p0 task", ["p0-critical"]),
            _issue(9, "unlabeled task"),
        ]
        picked = lv.pick_next_issue(issues)
        self.assertEqual(picked["number"], 11)

    def test_unlabeled_falls_after_all_priorities(self):
        issues = [_issue(9, "unlabeled"), _issue(8, "p3", ["p3-low"])]
        self.assertEqual(lv.pick_next_issue(issues)["number"], 8)

    def test_no_claimable_returns_none(self):
        self.assertIsNone(lv.pick_next_issue([]))
        self.assertIsNone(
            lv.pick_next_issue([_issue(1, "x", ["claimed"])]))


class TestRotationStores(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        td = Path(self._td.name)
        self._orig_lease, self._orig_rot = lv.ISSUE_LEASE_STORE, lv.ROTATION_STORE
        lv.ISSUE_LEASE_STORE = td / "lease.json"
        lv.ROTATION_STORE = td / "rotation.json"
        self.addCleanup(self._restore)

    def _restore(self):
        lv.ISSUE_LEASE_STORE, lv.ROTATION_STORE = self._orig_lease, self._orig_rot
        self._td.cleanup()

    def test_missing_and_corrupt_stores_read_empty(self):
        self.assertEqual(lv.load_issue_lease_store(), {})
        self.assertEqual(lv.load_last_run_store(), {})
        lv.ROTATION_STORE.write_text("{corrupt", encoding="utf-8")
        self.assertEqual(lv.load_last_run_store(), {})

    def test_record_issue_dispatch_persists_lease(self):
        lv.record_issue_dispatch(42)
        store = lv.load_issue_lease_store()
        self.assertIn("42", store)
        self.assertLess(time.time() - store["42"], 60.0)

    def test_scheduled_role_picks_unrun_then_resets(self):
        roles = ["ecosystem-scout", "human-eye", "rules-breaker",
                 "platform-guardian"]
        # প্রথম রান: স্টোর খালি → প্রথম রোল
        self.assertEqual(lv.pick_next_scheduled_role({}), roles[0])
        # দুটো রান হয়ে গেলে → তৃতীয়টি পিক হবে
        lv.save_last_run_store({roles[0]: 1.0, roles[1]: 2.0})
        self.assertEqual(lv.pick_next_scheduled_role({}), roles[2])
        # সবাই রান হয়ে গেলে → স্টোর রিসেট + আবার প্রথম রোল (অটোরোটেশন)
        lv.save_last_run_store({r: 1.0 for r in roles})
        self.assertEqual(lv.pick_next_scheduled_role({}), roles[0])
        self.assertEqual(lv.load_last_run_store(), {})


class TestLoopConstants(unittest.TestCase):
    def test_role_rules_covers_scheduled_roles(self):
        config = json.loads(
            (_ROOT / "scripts" / "agents" / "agent_cadence.json")
            .read_text(encoding="utf-8"))
        for role in config["scheduled_roles"]:
            self.assertIn(role, lv.ROLE_RULES, role)

    def test_common_rules_lists_nine_invariants(self):
        numbered = [ln for ln in lv.COMMON_RULES.splitlines()
                    if re.match(r"^\d+\.", ln)]
        self.assertEqual(len(numbered), 9)


if __name__ == "__main__":
    unittest.main()
