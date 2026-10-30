#!/usr/bin/env python3
"""Pin + behavior: #3050 — stale-incident demotion in the dispatch pick.

Live anatomy that motivates the filter (a43 dossier #3048, item 18 cost
model): the #3019 CI incident was triaged as TRANSIENT by peer PR #3023
(merged 03:09:30Z, same-sha rerun green) yet kept dispatching as the top-P0
row for hours — 4 dispatches and a claim-release lap were consumed by one
falsified premise, every agent re-deriving the same U3 staleness by hand
because the falsified premise lived above the pick line.

Fix (the closure record #3051's side datum, implemented): pick_next_issue
accepts an optional incident_probe; run_dispatch_cycle wires the live runs-
surface probe. An incident whose referenced run is superseded by >=5 green
main runs of the SAME workflow (zero newer reds; cancelled runs are
inconclusive and ignored — storm concurrency pruning must not read as red)
is skipped IN THE SAME RUN with an evidence note, advancing to the next
candidate. Fail-open by construction: non-incident titles, scrolled-off
runs, renamed workflows, rate limits and fetch errors all serve the row
unchanged — the filter can only REMOVE a dispatch, never block one.

Pins enforced here (zero gh/network dependency — fetchers are injected
fakes):
  1. Non-incident titles are never probed (None ⇒ served).
  2. >=5 newer greens of the same workflow ⇒ demotion note.
  3. Any newer red ⇒ serve (the incident may be live).
  4. Newer greens with run_number BELOW the incident's ⇒ serve (not
     supersession).
  5. Fewer than N greens ⇒ serve.
  6. Cancelled runs interleaved among newer greens ⇒ demotion stands.
  7. Workflow-name mismatch only ⇒ serve (fail-open).
  8. Incident run scrolled off the window ⇒ serve.
  9. A raising fetcher ⇒ serve (never-raise).
 10. pick_next_issue integration: stale top row skipped, advances to the
     next candidate; pure mode (incident_probe=None) serves the row with
     zero probing — hermetic callers keep the pre-#3050 contract.
 11. AST pin: both dispatch surfaces wire incident_probe=_probe_incident_stale.

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import ast
import sys
import unittest
import unittest.mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal

WORKFLOW = "CI — Open Unified Pipeline"


def _incident(number: int, run_id: int = 40994815953) -> dict:
    return {
        "number": number,
        "title": f"fix(ci): [open] {WORKFLOW} failed on main (Run #{run_id})",
        "labels": [{"name": "P0-critical"}, {"name": "status:unclaimed"}],
    }


def _row(number: int, labels: list[str] | None = None) -> dict:
    return {
        "number": number,
        "title": f"row {number}",
        "labels": [{"name": name} for name in (labels or [])],
    }


def _run(run_id: int, run_number: int, conclusion: str, name: str = WORKFLOW):
    return {
        "id": run_id,
        "run_number": run_number,
        "conclusion": conclusion,
        "status": "completed" if conclusion else "in_progress",
        "name": name,
        "head_branch": "main",
    }


def _green_fetcher(
    incident_id: int,
    incident_number: int,
    greens: int,
    name: str = WORKFLOW,
    interleaved: list[dict] | None = None,
):
    """Newest-first runs list: incident + `greens` newer greens (+ extras)."""
    runs: list[dict] = []
    for i in range(greens):
        runs.append(_run(900000 + i, incident_number + 10 - i, "success", name))
    for extra in interleaved or []:
        runs.append(extra)
    runs.append(_run(incident_id, incident_number, "failure", name))
    return runs


class TestIncidentStaleNote(unittest.TestCase):
    def test_non_incident_title_is_never_judged(self):
        for title in (
            "row 3001",
            "fix(ci): something else entirely",
            f"fix(ci): [open] {WORKFLOW} failed on main (no run id)",
        ):
            self.assertIsNone(
                cal._incident_stale_note(
                    {"number": 1, "title": title},
                    fetch_runs=lambda p: (_ for _ in ()).throw(AssertionError("fetch called")),
                ),
                f"non-incident title must not be probed: {title}",
            )

    def test_superseded_incident_gets_demotion_note(self):
        note = cal._incident_stale_note(
            _incident(3019),
            fetch_runs=lambda p: _green_fetcher(40994815953, 7183, greens=5),
        )
        self.assertIsNotNone(note)
        self.assertIn("incident-stale", note)
        self.assertIn("40994815953", note)
        self.assertIn("#3050", note)

    def test_newer_red_vetoes_demotion(self):
        runs = _green_fetcher(40994815953, 7183, greens=5)
        runs.insert(0, _run(910001, 7193, "failure"))  # newest concluded is red
        self.assertIsNone(cal._incident_stale_note(_incident(3019), fetch_runs=lambda p: runs))

    def test_older_greens_are_not_supersession(self):
        # Greens exist but all carry run_number BELOW the incident's.
        runs = [
            _run(900000 + i, 7100 + i, "success") for i in range(5)
        ]
        runs.append(_run(40994815953, 7183, "failure"))
        self.assertIsNone(cal._incident_stale_note(_incident(3019), fetch_runs=lambda p: runs))

    def test_too_few_greens_serves(self):
        self.assertIsNone(
            cal._incident_stale_note(
                _incident(3019),
                fetch_runs=lambda p: _green_fetcher(40994815953, 7183, greens=4),
            )
        )

    def test_cancelled_runs_do_not_read_as_red(self):
        interleaved = [
            _run(920001, 7190, "cancelled"),
            _run(920002, 7189, None),
        ]
        note = cal._incident_stale_note(
            _incident(3019),
            fetch_runs=lambda p: _green_fetcher(
                40994815953, 7183, greens=5, interleaved=interleaved
            ),
        )
        self.assertIsNotNone(note)

    def test_workflow_mismatch_fails_open(self):
        # Greens carry a different workflow name than the incident run's own
        # name (both resolved from the same surface): no same-workflow newer
        # runs can be identified, so the note must fail open and serve.
        runs = [
            _run(900000 + i, 7193 - i, "success", "Other Workflow")
            for i in range(5)
        ]
        runs.append(_run(40994815953, 7183, "failure", WORKFLOW))
        self.assertIsNone(cal._incident_stale_note(_incident(3019), fetch_runs=lambda p: runs))

    def test_scrolled_off_incident_fails_open(self):
        runs = [_run(900000 + i, 7300 + i, "success") for i in range(5)]
        self.assertIsNone(cal._incident_stale_note(_incident(3019), fetch_runs=lambda p: runs))

    def test_raising_fetcher_fails_open(self):
        def boom(per_page):
            raise RuntimeError("rate limited")

        self.assertIsNone(cal._incident_stale_note(_incident(3019), fetch_runs=boom))

    def test_live_wrapper_never_raises(self):
        with unittest.mock.patch.object(
            cal,
            "_incident_stale_note",
            side_effect=RuntimeError("boom"),
        ):
            self.assertIsNone(cal._probe_incident_stale(_incident(3019)))


class _LeaseIsolated(unittest.TestCase):
    def setUp(self):
        patcher = unittest.mock.patch.object(
            cal, "load_issue_lease_store", lambda path=None: {}
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class TestPickIntegration(_LeaseIsolated):
    def test_stale_top_row_advances_to_next_candidate(self):
        board = [_incident(3019), _row(3000)]
        self.assertEqual(
            cal.pick_next_issue(
                issues=board,
                claim_probe=lambda n: (False, "no active claim on the feedback plane"),
                incident_probe=lambda item: (
                    "incident-stale (U3 demotion, #3050)" if item.get("number") == 3019 else None
                ),
            ),
            "3000",
        )

    def test_pure_mode_keeps_pre_3050_contract(self):
        """incident_probe=None ⇒ the stale incident is served, zero probing."""
        board = [_incident(3019), _row(3000)]
        self.assertEqual(cal.pick_next_issue(issues=board), "3019")

    def test_raising_incident_probe_serves_the_row(self):
        board = [_incident(3019), _row(3000)]

        def probe(item):
            raise RuntimeError("boom")

        self.assertEqual(
            cal.pick_next_issue(
                issues=board,
                claim_probe=lambda n: (False, "no active claim on the feedback plane"),
                incident_probe=probe,
            ),
            "3019",
        )


class TestDefaultProbeWiring(unittest.TestCase):
    def test_loop_source_wires_incident_probe_at_both_dispatch_sites(self):
        """AST pin (signature-robust, #2899-heal precedent): both
        pick_next_issue call sites must carry
        incident_probe=_probe_incident_stale, so the demotion cannot silently
        regress to prose-only.
        """
        src = cal.__file__
        self.assertTrue(src.endswith("continuous_agent_loop.py"))
        loop_src = Path(src).read_text(encoding="utf-8")
        tree = ast.parse(loop_src)
        wired = 0
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fname = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            if fname != "pick_next_issue":
                continue
            for kw in node.keywords:
                if (
                    kw.arg == "incident_probe"
                    and isinstance(kw.value, ast.Name)
                    and kw.value.id == "_probe_incident_stale"
                ):
                    wired += 1
        self.assertEqual(
            wired,
            2,
            "both dispatch surfaces (envelope + dispatch print) must wire the incident probe",
        )


if __name__ == "__main__":
    unittest.main()
