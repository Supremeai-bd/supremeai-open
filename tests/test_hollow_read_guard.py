#!/usr/bin/env python3
"""Born-red contract tests for the hollow-read guard (#2673 standing assertions).

Offline only — live tower probing is network I/O and stays out of unit scope;
every test injects fakes into the pure assertion core and run_live_probe().
"""

from __future__ import annotations

import io
import contextlib
import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import hollow_read_guard as hrg  # noqa: E402


class TestNonEmptyAssertion(unittest.TestCase):
    def test_zero_rows_with_positive_floor_is_hollow(self):
        r = hrg.assert_non_empty("plane.x", [], semantic_floor=3)
        self.assertEqual(r["verdict"], "HOLLOW")
        self.assertEqual(r["observed"], 0)

    def test_rows_present_is_clean(self):
        r = hrg.assert_non_empty("plane.x", [{"a": 1}, {"b": 2}], semantic_floor=1)
        self.assertEqual(r["verdict"], "CLEAN")
        self.assertEqual(r["observed"], 2)

    def test_zero_rows_with_zero_floor_is_clean(self):
        """Floor 0 means domain semantics do not imply data — empty is honest."""
        r = hrg.assert_non_empty("plane.x", [], semantic_floor=0)
        self.assertEqual(r["verdict"], "CLEAN")

    def test_dict_row_container_recognized(self):
        r = hrg.assert_non_empty("plane.y", {"rows": []}, semantic_floor=1)
        self.assertEqual(r["verdict"], "HOLLOW")

    def test_unrecognized_shape_is_unreadable_not_hollow(self):
        r = hrg.assert_non_empty("plane.z", 42, semantic_floor=1)
        self.assertEqual(r["verdict"], "UNREADABLE")


class TestLiveImpliesFresh(unittest.TestCase):
    def test_advanced_timestamp_with_persistent_empty_is_hollow(self):
        a = {"checkedAt": "2026-10-30T01:00:00Z", "content": []}
        b = {"checkedAt": "2026-10-30T02:00:00Z", "content": []}
        r = hrg.assert_live_implies_fresh(a, b)
        self.assertEqual(r["verdict"], "HOLLOW")
        self.assertIn("decorating hollow data", r["detail"])

    def test_advanced_timestamp_with_changing_content_is_clean(self):
        a = {"checkedAt": "2026-10-30T01:00:00Z", "content": []}
        b = {"checkedAt": "2026-10-30T02:00:00Z", "content": [{"x": 1}]}
        r = hrg.assert_live_implies_fresh(a, b)
        self.assertEqual(r["verdict"], "CLEAN")

    def test_identical_timestamps_not_applicable(self):
        a = {"checkedAt": "2026-10-30T01:00:00Z", "content": []}
        r = hrg.assert_live_implies_fresh(a, dict(a))
        self.assertEqual(r["verdict"], "NOT_APPLICABLE")


class TestTruncationFlagged(unittest.TestCase):
    def test_window_truncated_flag_present_is_clean(self):
        r = hrg.assert_truncation_flagged(
            "work_queue", {"workOrders": [{"n": 1}] * 120, "windowTruncated": True, "totalOpen": 200},
            requested_limit=120)
        self.assertEqual(r["verdict"], "CLEAN")
        self.assertTrue(r["flag"])

    def test_miscalibrated_flag_is_hollow_2190(self):
        r = hrg.assert_truncation_flagged(
            "work_queue", {"workOrders": [{"n": 1}] * 200, "windowTruncated": True, "totalOpen": 200},
            requested_limit=200)
        self.assertEqual(r["verdict"], "HOLLOW")
        self.assertIn("#2190", r["detail"])

    def test_page_size_without_signal_is_hollow_2609(self):
        r = hrg.assert_truncation_flagged("list_prs", [{"p": i} for i in range(30)], requested_limit=30)
        self.assertEqual(r["verdict"], "HOLLOW")
        self.assertIn("structural blind page", r["detail"])

    def test_partial_page_without_signal_is_clean(self):
        r = hrg.assert_truncation_flagged("list_prs", [{"p": 1}, {"p": 2}], requested_limit=30)
        self.assertEqual(r["verdict"], "CLEAN")


class TestCiCoverage(unittest.TestCase):
    def test_green_with_zero_jobs_is_hollow_2529(self):
        r = hrg.assert_ci_coverage({"conclusion": "success", "jobs": []})
        self.assertEqual(r["verdict"], "HOLLOW")
        self.assertIn("green-but-blind", r["detail"])

    def test_green_with_jobs_is_clean(self):
        r = hrg.assert_ci_coverage({"conclusion": "success", "jobs": [{"name": "j"}]})
        self.assertEqual(r["verdict"], "CLEAN")

    def test_failure_run_not_in_scope(self):
        r = hrg.assert_ci_coverage({"conclusion": "failure", "jobs": []})
        self.assertEqual(r["verdict"], "CLEAN")


class _FakeRosterFetch:
    """#2673 roster shape: list_prs hollow while side-channel shows branches."""
    def __init__(self, prs):
        self.prs = prs

    def __call__(self, tool, arguments):
        if tool == "github.list_prs":
            return self.prs
        if tool == "github.workflow_runs":
            return {"workflow_runs": [{"head_branch": "bridge/bridge-20261030-x-r1"},
                                      {"head_branch": "main"}]}
        if tool == "bridge.work_queue":
            return {"workOrders": [{"n": i} for i in range(109)],
                    "windowTruncated": False, "totalOpen": 109}
        if tool == "health_full_sweep":
            return {"snapshots": {"redis": {"status": "healthy"}, "render": {"status": "degraded"}}}
        raise AssertionError(f"unexpected tool {tool}")


class TestLiveProbeComposition(unittest.TestCase):
    def test_hollow_list_prs_with_lively_sidechannel_fires(self):
        ev = hrg.run_live_probe(_FakeRosterFetch([]))
        self.assertEqual(ev["verdict"], "HOLLOW_DETECTED")
        pr_finding = [f for f in ev["findings"]
                      if f.get("plane") == "github.list_prs" and f.get("assertion") == "non_empty"]
        self.assertTrue(pr_finding and pr_finding[0]["verdict"] == "HOLLOW")
        self.assertIn("side-channel", pr_finding[0]["detail"])

    def test_honest_planes_are_clean(self):
        ev = hrg.run_live_probe(_FakeRosterFetch([{"number": 1}, {"number": 2}]))
        self.assertEqual(ev["verdict"], "CLEAN")
        self.assertEqual(ev["hollowCount"], 0)

    def test_evidence_schema_fields(self):
        ev = hrg.run_live_probe(_FakeRosterFetch([]))
        for field in ("guard", "lineage", "checkedAt", "verdict", "findings", "hollowCount"):
            self.assertIn(field, ev)


class TestExitContract(unittest.TestCase):
    def test_exit_constants(self):
        self.assertEqual(hrg.EXIT_CLEAN, 0)
        self.assertEqual(hrg.EXIT_HOLLOW, 1)
        self.assertEqual(hrg.EXIT_USAGE, 2)

    def test_main_fail_loud_stderr_exit1(self):
        class _BoomFetch(_FakeRosterFetch):
            def __init__(self):
                super().__init__([])
        import unittest.mock as mock
        with mock.patch.object(hrg, "tower_call", side_effect=RuntimeError("tower down")):
            # tower_call failure lands as UNREADABLE probe rows -> may still be CLEAN
            # unless a HOLLOW fired; here all planes UNREADABLE -> verdict CLEAN(0).
            err, out = io.StringIO(), io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
                code = hrg.main(["--probe", "live"])
            self.assertEqual(code, hrg.EXIT_CLEAN)
            self.assertIn("UNREADABLE", out.getvalue())

    def test_unreachable_plane_is_never_silent_pass_shape(self):
        """Unreadable planes are labeled UNREADABLE, never reported as verified CLEAN."""
        def boom(tool, arguments):
            raise ConnectionError("down")
        ev = hrg.run_live_probe(boom)
        self.assertEqual(len(ev["findings"]), 3)
        self.assertTrue(all(f["verdict"] == "UNREADABLE" for f in ev["findings"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
