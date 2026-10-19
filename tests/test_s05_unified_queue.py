#!/usr/bin/env python3
"""Offline contract tests for the unified queue listing (#474, S05).

Asserts the bridge.work_queue contract the TS handler + onboarding test
must satisfy: default = all open issues, optional label filter, PR and
closed exclusion, response shape, deterministic ordering.

Pure stdlib. Run: python3 -m unittest test_s05_unified_queue -v
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "tower"))

import work_queue_query_reference as qref


def mk(num, state="open", labels=None, pr=False, title=None):
    row = {
        "number": num,
        "title": title or f"issue-{num}",
        "state": state,
        "labels": labels or [],
        "html_url": f"https://example.test/{num}",
        "created_at": "2026-10-17T00:00:00Z",
        "updated_at": "2026-10-17T00:00:00Z",
        "comments": 0,
    }
    if pr:
        row["pull_request"] = {"url": "https://example.test/pr"}
    return row


class QueryBuilding(unittest.TestCase):
    def test_01_default_queries_all_open_no_labels(self):
        q = qref.build_queue_query()
        self.assertIsNone(q["applied_label"])
        self.assertNotIn("labels=", q["url"])
        self.assertIn("state=open", q["url"])

    def test_02_empty_string_label_is_default(self):
        self.assertIsNone(qref.build_queue_query("")["applied_label"])

    def test_03_whitespace_label_is_default(self):
        self.assertIsNone(qref.build_queue_query("   ")["applied_label"])

    def test_04_custom_label_urlencoded(self):
        q = qref.build_queue_query("bridge:queued")
        self.assertEqual(q["applied_label"], "bridge:queued")
        self.assertIn("labels=bridge%3Aqueued", q["url"])

    def test_05_label_trimmed(self):
        self.assertEqual(qref.build_queue_query("  ci  ")["applied_label"], "ci")


class Normalization(unittest.TestCase):
    def test_06_unlabeled_open_issue_included_by_default(self):
        norm = qref.normalize_queue([mk(469)])
        self.assertEqual(norm["count"], 1)
        self.assertEqual(norm["workOrders"][0]["number"], 469)
        self.assertIsNone(norm["label"])

    def test_07_pull_requests_always_excluded(self):
        norm = qref.normalize_queue([mk(1, pr=True), mk(2)])
        self.assertEqual([w["number"] for w in norm["workOrders"]], [2])

    def test_08_closed_issues_always_excluded(self):
        norm = qref.normalize_queue([mk(1, state="closed"), mk(2)])
        self.assertEqual([w["number"] for w in norm["workOrders"]], [2])

    def test_09_deterministic_newest_first_ordering(self):
        norm = qref.normalize_queue([mk(3), mk(11), mk(7)])
        self.assertEqual([w["number"] for w in norm["workOrders"]], [11, 7, 3])

    def test_10_response_shape_with_label_echo(self):
        norm = qref.normalize_queue([mk(1)], applied_label="status:unclaimed")
        for key in ("repo", "label", "authenticatedRead", "count", "workOrders"):
            self.assertIn(key, norm)
        self.assertEqual(norm["label"], "status:unclaimed")
        self.assertTrue(norm["authenticatedRead"])

    def test_11_multi_label_issue_included_and_labels_sorted(self):
        row = mk(470, labels=[{"name": "P1-high"}, {"name": "status:unclaimed"}])
        norm = qref.normalize_queue([row])
        self.assertEqual(
            norm["workOrders"][0]["labels"], ["P1-high", "status:unclaimed"]
        )

    def test_12_empty_queue_shape(self):
        norm = qref.normalize_queue([])
        self.assertEqual(norm["count"], 0)
        self.assertEqual(norm["workOrders"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
