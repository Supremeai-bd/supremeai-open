#!/usr/bin/env python3
"""Born-red contract tests for the closure-time live-state gate.

Lane: scout(R79) #2925, proposal Option A, repo-reachable slice.
Lineage: #2132 queue_consistency_probe family; #2704 fail-loud contract.

Offline only — the live tower probe is network I/O and stays out of unit
scope; every test injects a fake fetch into run_gate()/eval_predicate().
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import closure_live_state_gate as gate  # noqa: E402


NOW = "2026-10-30T01:10:00+00:00"


def _ok_fetch(tool, arguments):
    """All predicates hold — the live plane is healthy."""
    if tool == "resource_status":
        return {"resourceId": arguments["resourceId"], "status": "healthy"}
    if tool == "health_full_sweep":
        return {
            "services": [
                {"name": "render-primary", "evidence": "deploy live", "checkedAt": NOW},
                {"name": "render-worker", "evidence": "deploy live", "checkedAt": NOW},
            ]
        }
    if tool == "policy_list_pending":
        return {"pending": []}
    raise AssertionError(f"unexpected tool {tool}")


def _degraded_fetch(tool, arguments):
    """The #2225 incident shape: both services degraded, evidence says update_failed.

    Uses the REAL health_full_sweep shape observed 2026-10-30T01:12Z:
    snapshots is a dict keyed by provider, evidence is {kind, summary}.
    """
    if tool == "resource_status":
        return {"resourceId": arguments["resourceId"], "status": "degraded"}
    if tool == "health_full_sweep":
        return {
            "snapshots": {
                "render-primary": {
                    "provider": "render-primary",
                    "status": "degraded",
                    "checkedAt": NOW,
                    "evidence": {
                        "kind": "error",
                        "summary": "Container running previous build, but latest deployment update_failed",
                    },
                },
                "render-worker": {
                    "provider": "render-worker",
                    "status": "degraded",
                    "checkedAt": NOW,
                    "evidence": {
                        "kind": "error",
                        "summary": "Container running previous build, but latest deployment update_failed",
                    },
                },
            }
        }
    if tool == "policy_list_pending":
        return []  # real shape: bare array
    raise AssertionError(f"unexpected tool {tool}")


class _BoomFetch:
    def __call__(self, tool, arguments):
        raise ConnectionError("tower unreachable")


class TestRegistryContract(unittest.TestCase):
    def test_registry_covers_2225_with_verbatim_source(self):
        entry = gate.CRITERIA_REGISTRY["2225"]
        self.assertIn("#2738", entry["source"])
        self.assertIn("2026-10-24T08:32:47Z", entry["verbatim"])
        self.assertTrue(entry["predicates"], "criterion must compile to mechanical predicates")

    def test_predicates_are_conservative_kinds(self):
        known = {"resource_status_in", "health_evidence_not_contains", "policy_pending_empty"}
        for number, entry in gate.CRITERIA_REGISTRY.items():
            for pred in entry["predicates"]:
                self.assertIn(
                    pred["kind"],
                    known,
                    f"subject {number}: predicate kind {pred['kind']} is not a conservative kind",
                )


class TestGateVerdicts(unittest.TestCase):
    def test_pass_when_all_predicates_hold(self):
        ev = gate.run_gate("2225", "merge auto-close for #2225", _ok_fetch, now_iso=NOW)
        self.assertEqual(ev["verdict"], "PASS")
        self.assertNotIn("adjudication", ev, "PASS must not carry a refusal adjudication")

    def test_fail_on_incident_shape_refuses_closing_artifact(self):
        ev = gate.run_gate("2225", "merge auto-close for #2225", _degraded_fetch, now_iso=NOW)
        self.assertEqual(ev["verdict"], "FAIL")
        self.assertIn("CLOSING REFUSED", ev["adjudication"])
        self.assertIn("evidence-only", ev["adjudication"])

    def test_fail_without_closing_artifact_omits_adjudication(self):
        ev = gate.run_gate("2225", None, _degraded_fetch, now_iso=NOW)
        self.assertEqual(ev["verdict"], "FAIL")
        self.assertNotIn("adjudication", ev)

    def test_unknown_subject_is_unknown_never_pass(self):
        ev = gate.run_gate("999999", "some close", _ok_fetch, now_iso=NOW)
        self.assertEqual(ev["verdict"], "UNKNOWN")
        self.assertEqual(ev["reason"], "subject-not-in-registry")

    def test_tower_unreachable_is_unknown_never_pass(self):
        ev = gate.run_gate("2225", "close", _BoomFetch(), now_iso=NOW)
        self.assertEqual(ev["verdict"], "UNKNOWN")
        self.assertEqual(ev["reason"], "tower-unreachable")


class TestPredicateLevel(unittest.TestCase):
    def test_resource_status_fail_on_degraded(self):
        r = gate.eval_predicate(
            {"kind": "resource_status_in", "resourceId": "render/render-primary",
             "allowed": ["healthy", "live"]},
            _degraded_fetch,
        )
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["observed"], "degraded")

    def test_health_evidence_needle_fails_when_present(self):
        r = gate.eval_predicate(
            {"kind": "health_evidence_not_contains", "resourceId": "render/render-primary",
             "needle": "update_failed"},
            _degraded_fetch,
        )
        self.assertEqual(r["verdict"], "FAIL")

    def test_health_evidence_real_shape_captures_needle_and_status(self):
        r = gate.eval_predicate(
            {"kind": "health_evidence_not_contains", "resourceId": "render/render-primary",
             "needle": "update_failed"},
            _degraded_fetch,
        )
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["snapshotStatus"], "degraded")
        self.assertIn("update_failed", r["evidence_excerpt"])
        self.assertEqual(r["checkedAt"], NOW)

    def test_policy_pending_bare_array_shape(self):
        r = gate.eval_predicate({"kind": "policy_pending_empty"},
                                lambda tool, args: [])
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["pending_count"], 0)

    def test_health_evidence_missing_plane_fails_not_passes(self):
        r = gate.eval_predicate(
            {"kind": "health_evidence_not_contains", "resourceId": "render/render-primary",
             "needle": "update_failed"},
            lambda tool, args: {"services": []},
        )
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["observed"], "evidence-plane-missing")

    def test_policy_pending_nonempty_fails(self):
        r = gate.eval_predicate({"kind": "policy_pending_empty"},
                                lambda tool, args: {"pending": [{"id": "req-1"}]})
        self.assertEqual(r["verdict"], "FAIL")

    def test_unrecognized_predicate_kind_fails_not_passes(self):
        r = gate.eval_predicate({"kind": "some_future_kind"}, _ok_fetch)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual(r["observed"], "unrecognized-predicate-kind")


class TestExitContract(unittest.TestCase):
    def test_exit_code_table(self):
        self.assertEqual(gate.EXIT_CODES["PASS"], 0)
        self.assertEqual(gate.EXIT_CODES["FAIL"], 2)
        self.assertEqual(gate.EXIT_CODES["UNKNOWN"], 3)

    def test_main_fail_loud_stderr_and_exit2(self, ):
        import io, contextlib
        err = io.StringIO()
        out = io.StringIO()
        argv = ["--subject", "2225", "--closing-artifact", "verdict write for #2225"]
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = gate.main(argv)
        self.assertEqual(code, 2)
        self.assertIn("REFUSED", err.getvalue())
        evidence = json.loads(out.getvalue())
        self.assertEqual(evidence["verdict"], "FAIL")

    def test_main_unknown_exit3_no_silent_pass(self):
        import io, contextlib
        err = io.StringIO()
        out = io.StringIO()
        argv = ["--subject", "424242"]
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            code = gate.main(argv)
        self.assertEqual(code, 3)
        self.assertIn("UNKNOWN", err.getvalue())


class TestEvidenceContract(unittest.TestCase):
    def test_evidence_schema_fields_for_fail(self):
        ev = gate.run_gate("2225", "close", _degraded_fetch, now_iso=NOW)
        for field in ("gate", "lineage", "subject", "criterionSource", "criterionVerbatim",
                      "checkedAt", "verdict", "predicates"):
            self.assertIn(field, ev)
        self.assertTrue(all("verdict" in p for p in ev["predicates"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
