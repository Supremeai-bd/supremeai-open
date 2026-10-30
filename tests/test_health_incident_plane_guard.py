#!/usr/bin/env python3
"""Born-red contract tests for the health incident-plane coherence guard.

Lineage: the #3111 sentry family recorded 8 consecutive passes of
`incidents=[]` while sweep rows were non-OK. These tests pin the three
coherence assertions + advisory note so the defect shape can never again
pass unnoticed. Offline only — the live tower probe is network I/O and
stays out of unit scope; every test injects fakes into the pure core and
run_live_probe().
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import health_incident_plane_guard as ipg  # noqa: E402


def _sweep(statuses: dict, incidents, overall: str) -> dict:
    return {
        "overallStatus": overall,
        "incidents": incidents,
        "snapshots": {
            name: {"status": status, "latencyMs": 100, "checkedAt": "2026-10-30T13:21:42Z"}
            for name, status in statuses.items()
        },
    }


# The exact #3111 8-pass defect shape: telegram DOWN + render degraded,
# incidents plane EMPTY.
DEFECTIVE_SWEEP = _sweep(
    {"telegram": "down", "render-primary": "update_failed", "redis": "healthy"},
    incidents=[],
    overall="degraded",
)

# The live 13:21Z c59 datum: telegram down, incidents plane POPULATED.
COHERENT_DEGRADED_SWEEP = _sweep(
    {"telegram": "down", "redis": "healthy"},
    incidents=[{"id": "INC-mvv0419y", "type": "OUTAGE", "message": "transitioned to down"}],
    overall="down",
)

HEALTHY_SWEEP = _sweep(
    {"telegram": "healthy", "redis": "healthy", "render": "healthy"},
    incidents=[],
    overall="healthy",
)


class TestIncidentsPopulatedWhenRowsNonOk(unittest.TestCase):
    def test_non_ok_rows_with_empty_incidents_is_hollow_3111(self):
        r = ipg.assert_incidents_populated_when_rows_non_ok(DEFECTIVE_SWEEP)
        self.assertEqual(r["verdict"], "HOLLOW")
        self.assertEqual(r["incidentCount"], 0)
        self.assertIn("#3111", r["detail"])
        self.assertIn("telegram", r["nonOkRows"])

    def test_non_ok_rows_with_incidents_is_clean(self):
        r = ipg.assert_incidents_populated_when_rows_non_ok(COHERENT_DEGRADED_SWEEP)
        self.assertEqual(r["verdict"], "CLEAN")
        self.assertEqual(r["incidentCount"], 1)

    def test_all_healthy_with_empty_incidents_is_clean(self):
        r = ipg.assert_incidents_populated_when_rows_non_ok(HEALTHY_SWEEP)
        self.assertEqual(r["verdict"], "CLEAN")

    def test_missing_incidents_array_is_unreadable(self):
        sweep = dict(DEFECTIVE_SWEEP)
        sweep.pop("incidents")
        r = ipg.assert_incidents_populated_when_rows_non_ok(sweep)
        self.assertEqual(r["verdict"], "UNREADABLE")

    def test_non_dict_snapshots_is_unreadable(self):
        r = ipg.assert_incidents_populated_when_rows_non_ok({"snapshots": [], "incidents": []})
        self.assertEqual(r["verdict"], "UNREADABLE")


class TestOverallStatusCohere(unittest.TestCase):
    def test_healthy_summary_over_non_ok_rows_is_hollow(self):
        sweep = _sweep({"telegram": "down"}, incidents=[], overall="healthy")
        r = ipg.assert_overall_status_cohere(sweep)
        self.assertEqual(r["verdict"], "HOLLOW")
        self.assertIn("contradicting its own", r["detail"])

    def test_degraded_summary_over_non_ok_rows_is_clean(self):
        r = ipg.assert_overall_status_cohere(DEFECTIVE_SWEEP)
        self.assertEqual(r["verdict"], "CLEAN")
        self.assertEqual(r["overallStatus"], "degraded")

    def test_down_summary_over_healthy_rows_is_hollow(self):
        r = ipg.assert_overall_status_cohere(
            _sweep({"redis": "healthy"}, incidents=[], overall="down"))
        self.assertEqual(r["verdict"], "HOLLOW")
        self.assertIn("mirror-direction lie", r["detail"])

    def test_healthy_summary_over_healthy_rows_is_clean(self):
        r = ipg.assert_overall_status_cohere(HEALTHY_SWEEP)
        self.assertEqual(r["verdict"], "CLEAN")

    def test_missing_overall_status_is_unreadable(self):
        sweep = dict(HEALTHY_SWEEP)
        sweep.pop("overallStatus")
        r = ipg.assert_overall_status_cohere(sweep)
        self.assertEqual(r["verdict"], "UNREADABLE")


class TestPerRowStatusCoverage(unittest.TestCase):
    def test_row_with_missing_status_is_hollow_2704(self):
        sweep = _sweep({"redis": "healthy", "ghost": None}, incidents=[], overall="down")
        r = ipg.assert_per_row_status_coverage(sweep)
        self.assertEqual(r["verdict"], "HOLLOW")
        self.assertEqual(r["unpopulatedRows"], ["ghost"])

    def test_row_with_empty_status_is_hollow(self):
        sweep = _sweep({"redis": "healthy", "hollow": "  "}, incidents=[], overall="down")
        r = ipg.assert_per_row_status_coverage(sweep)
        self.assertEqual(r["verdict"], "HOLLOW")

    def test_all_rows_populated_is_clean(self):
        r = ipg.assert_per_row_status_coverage(DEFECTIVE_SWEEP)
        self.assertEqual(r["verdict"], "CLEAN")
        self.assertEqual(r["rows"], 3)


class TestAdvisoryNote(unittest.TestCase):
    def test_incidents_without_non_ok_rows_is_note_not_failure(self):
        sweep = _sweep(
            {"redis": "healthy"},
            incidents=[{"id": "INC-1", "type": "OUTAGE"}],
            overall="healthy")
        r = ipg.note_incident_without_non_ok_row(sweep)
        self.assertEqual(r["verdict"], "NOTE")
        # NOTE must never count as a defect.
        self.assertEqual([f for f in ipg.run_assertions(sweep) if f["verdict"] == "HOLLOW"], [])

    def test_no_incidents_is_clean_note(self):
        r = ipg.note_incident_without_non_ok_row(HEALTHY_SWEEP)
        self.assertEqual(r["verdict"], "CLEAN")


class TestRunLiveProbe(unittest.TestCase):
    def test_defective_sweep_yields_defect_detected(self):
        evidence = ipg.run_live_probe(lambda _tool, _args: dict(DEFECTIVE_SWEEP))
        self.assertEqual(evidence["verdict"], "DEFECT_DETECTED")
        self.assertEqual(evidence["defectCount"], 1)
        hollow = [f["assertion"] for f in evidence["findings"] if f["verdict"] == "HOLLOW"]
        self.assertIn("incidents_populated_when_rows_non_ok", hollow)

    def test_summary_lie_is_also_caught_end_to_end(self):
        sweep = _sweep({"telegram": "down"}, incidents=[], overall="healthy")
        evidence = ipg.run_live_probe(lambda _tool, _args: sweep)
        self.assertEqual(evidence["verdict"], "DEFECT_DETECTED")
        hollow = {f["assertion"] for f in evidence["findings"] if f["verdict"] == "HOLLOW"}
        self.assertEqual(hollow, {
            "incidents_populated_when_rows_non_ok", "overall_status_cohere"})

    def test_coherent_degraded_sweep_is_clean(self):
        evidence = ipg.run_live_probe(lambda _tool, _args: dict(COHERENT_DEGRADED_SWEEP))
        self.assertEqual(evidence["verdict"], "CLEAN")

    def test_healthy_sweep_is_clean(self):
        evidence = ipg.run_live_probe(lambda _tool, _args: dict(HEALTHY_SWEEP))
        self.assertEqual(evidence["verdict"], "CLEAN")

    def test_fetch_exception_is_unreadable_never_crash(self):
        def _boom(_tool, _args):
            raise RuntimeError("connection reset")
        evidence = ipg.run_live_probe(_boom)
        self.assertEqual(evidence["verdict"], "CLEAN")  # UNREADABLE probe != defect
        self.assertEqual(evidence["findings"][0]["verdict"], "UNREADABLE")

    def test_unparseable_body_is_unreadable(self):
        def _bad(_tool, _args):
            raise json.JSONDecodeError("Expecting value", "{cut", 0)
        evidence = ipg.run_live_probe(_bad)
        self.assertEqual(evidence["findings"][0]["verdict"], "UNREADABLE")


class TestMainContract(unittest.TestCase):
    def test_sweep_file_mode_clean_exit_0(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(COHERENT_DEGRADED_SWEEP, fh)
            path = fh.name
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ipg.main(["--sweep-file", path])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())["verdict"], "CLEAN")

    def test_sweep_file_mode_defect_exit_1_and_stderr_fail_loud(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(DEFECTIVE_SWEEP, fh)
            path = fh.name
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = ipg.main(["--sweep-file", path])
        self.assertEqual(code, 1)
        evidence = json.loads(out.getvalue())
        self.assertEqual(evidence["verdict"], "DEFECT_DETECTED")
        self.assertIn("INCIDENT PLANE GUARD", err.getvalue())

    def test_no_mode_is_usage_exit_2(self):
        with contextlib.redirect_stderr(io.StringIO()):
            code = ipg.main([])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
