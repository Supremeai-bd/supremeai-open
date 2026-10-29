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


class PaginationCompleteness(unittest.TestCase):
    """r2 contract (#2115/#2123): the queue enumerates, it never samples."""

    def test_13_query_carries_page_and_page_size(self):
        q1 = qref.build_queue_query()
        self.assertIn("page=1", q1["url"])
        self.assertIn(f"per_page={qref.QUEUE_PAGE_SIZE}", q1["url"])
        q3 = qref.build_queue_query("status:unclaimed", page=3)
        self.assertIn("page=3", q3["url"])
        self.assertEqual(q3["page"], 3)

    def test_14_page_clamps_to_one(self):
        self.assertEqual(qref.build_queue_query(page=0)["page"], 1)
        self.assertEqual(qref.build_queue_query(page=-5)["page"], 1)

    def test_15_fetch_stops_at_first_short_page(self):
        full = [{"number": i} for i in range(200, 100, -1)]
        short = [{"number": i} for i in range(100, 95, -1)]
        pages = qref.fetch_all_pages(lambda p: full if p == 1 else short)
        self.assertEqual(len(pages), 2)

    def test_16_fetch_caps_saturated_feed(self):
        full = [{"number": i} for i in range(1000, 0, -1)]
        pages = qref.fetch_all_pages(lambda p: full, max_pages=qref.QUEUE_MAX_PAGES)
        self.assertEqual(len(pages), qref.QUEUE_MAX_PAGES)

    def test_17_merge_dedupes_by_number(self):
        merged = qref.merge_pages(
            [[{"number": 7}, {"number": 8}], [{"number": 8}, {"number": 9}]]
        )
        self.assertEqual([r["number"] for r in merged], [7, 8, 9])
        self.assertEqual(qref.merge_pages([]), [])

    def test_18_old_open_issue_survives_saturated_page(self):
        # Regression for the live #1912-class drop: one saturated page of
        # PRs + new issues must not evict an older open unclaimed issue.
        prs = [{"number": 3000 - i, "title": f"pr{i}", "state": "open",
                "pull_request": {"url": "x"}} for i in range(40)]
        newest = [{"number": 2126 - i, "title": f"i{i}", "state": "open",
                   "labels": []} for i in range(10)]
        old = {"number": 1912, "title": "old", "state": "open",
               "labels": [{"name": "status:unclaimed"}]}
        single = qref.normalize_queue(qref.merge_pages([prs + newest]))
        self.assertNotIn(1912, [w["number"] for w in single["workOrders"]])
        paged = qref.normalize_queue(qref.merge_pages([prs + newest, [old]]))
        self.assertIn(1912, [w["number"] for w in paged["workOrders"]])
        self.assertEqual(paged["count"], 11)

    def test_19_paging_constants_pinned(self):
        self.assertEqual(qref.QUEUE_PAGE_SIZE, 100)
        self.assertEqual(qref.QUEUE_MAX_PAGES, 5)
        self.assertEqual(qref.QUEUE_LIMIT_MAX, 200)


if __name__ == "__main__":
    unittest.main(verbosity=2)
