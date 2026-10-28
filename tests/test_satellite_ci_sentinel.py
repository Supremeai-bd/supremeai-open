#!/usr/bin/env python3
"""Offline unit tests for the #2111 satellite main-CI sentinel kernel.

No network access is required - every test drives the pure verdict kernel
over fixtures. Run:  python -m unittest tests.test_satellite_ci_sentinel -v
(or: python tests/test_satellite_ci_sentinel.py)
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import satellite_ci_sentinel as sentinel  # noqa: E402

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
OLD = datetime(2026, 10, 26, 0, 0, tzinfo=timezone.utc)  # 60h before NOW


def mk_run(created=NOW, status="completed", conclusion="success", branch="main", run_id=1):
    return {
        "id": run_id,
        "status": status,
        "conclusion": conclusion,
        "created_at": created.isoformat().replace("+00:00", "Z"),
        "head_branch": branch,
        "head_sha": "a" * 40,
    }


class SelectionKernel(unittest.TestCase):
    def test_newest_completed_wins_and_ignores_in_progress(self):
        runs = [mk_run(NOW, conclusion="failure", run_id=2), mk_run(OLD, run_id=1),
                mk_run(NOW, status="in_progress", conclusion=None, run_id=3)]
        best = sentinel.latest_completed_run(runs)
        self.assertIsNotNone(best)
        self.assertEqual(best["id"], 2)
        self.assertEqual(best["conclusion"], "failure")

    def test_non_main_branches_ignored_when_main_present(self):
        best = sentinel.latest_completed_run([mk_run(NOW, branch="feature/x", run_id=9), mk_run(OLD)])
        self.assertIsNotNone(best)
        self.assertEqual(best["head_branch"], "main")

    def test_empty_and_garbage_rows_never_crash(self):
        self.assertIsNone(sentinel.latest_completed_run([]))
        self.assertIsNone(sentinel.latest_completed_run([None, "x", {"status": "completed"}]))


class Classification(unittest.TestCase):
    def test_green(self):
        self.assertEqual(sentinel.classify_run(mk_run(), NOW, 48), "green")

    def test_red(self):
        self.assertEqual(sentinel.classify_run(mk_run(conclusion="failure"), NOW, 48), "RED")

    def test_stale_green_disclosed(self):
        v = sentinel.classify_run(mk_run(OLD), NOW, 48)
        self.assertTrue(v.startswith("green (stale"))
        self.assertIn("60.0h", v)

    def test_staleness_never_downgrades_red(self):
        v = sentinel.classify_run(mk_run(OLD, conclusion="failure"), NOW, 48)
        self.assertTrue(v.startswith("RED (stale"))

    def test_unknown_when_no_completed_run(self):
        self.assertTrue(sentinel.classify_run(None, NOW, 48).startswith("unknown"))

    def test_unknown_on_unfamiliar_conclusion(self):
        self.assertTrue(sentinel.classify_run(mk_run(conclusion="timed_out"), NOW, 48).startswith("unknown"))


class ExitMapping(unittest.TestCase):
    def test_all_green_is_zero(self):
        self.assertEqual(sentinel.exit_code_for({"a": "green", "b": "green"}), 0)

    def test_any_red_is_one(self):
        self.assertEqual(sentinel.exit_code_for({"a": "green", "b": "RED"}), 1)

    def test_all_unknown_is_two_fail_close(self):
        self.assertEqual(sentinel.exit_code_for({"a": "unknown (x)", "b": "skip (y)"}), 2)

    def test_empty_is_two(self):
        self.assertEqual(sentinel.exit_code_for({}), 2)

    def test_stale_green_is_not_fatal(self):
        self.assertEqual(sentinel.exit_code_for({"a": "green (stale 50.0h > 48h window)"}), 0)


class SseAndReport(unittest.TestCase):
    def test_sse_data_line_extracted(self):
        raw = ': ping\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        self.assertTrue(sentinel.extract_sse_data(raw)["result"]["ok"])

    def test_plain_json_passthrough(self):
        self.assertEqual(sentinel.extract_sse_data('{"a":1}')["a"], 1)

    def test_roster_integrity(self):
        self.assertEqual(len(sentinel.SATELLITES), 6)
        self.assertNotIn("supremeai-open", sentinel.SATELLITES)
        self.assertEqual(sentinel.ORG, "Supremeai-bd")

    def test_report_shape_end_to_end(self):
        sweep = {
            "supremeai": {"runs": [mk_run()], "note": None},
            "supremeai-core": {"runs": [mk_run(conclusion="failure")], "note": None},
            "supremeai-api": {"runs": None, "note": "skip (timeout)"},
        }
        report = sentinel.build_report(sweep, NOW, 48)
        self.assertEqual(len(report["repos"]), 3)
        self.assertEqual(report["summary"]["exit_code"], 1)
        self.assertEqual(report["summary"]["red"], ["Supremeai-bd/supremeai-core"])
        self.assertEqual(report["summary"]["unknown_or_skipped"], ["Supremeai-bd/supremeai-api"])
        self.assertTrue(json.loads(json.dumps(report))["generated_at"].startswith("2026-10-28T12:00"))

    def test_human_report_mentions_reds(self):
        sweep = {"supremeai-core": {"runs": [mk_run(conclusion="failure")], "note": None}}
        text = sentinel.human_report(sentinel.build_report(sweep, NOW, 48))
        self.assertIn("RED", text)
        self.assertIn("supremeai-core", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
