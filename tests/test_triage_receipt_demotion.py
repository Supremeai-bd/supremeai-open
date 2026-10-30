#!/usr/bin/env python3
"""Pin + behavior: Zero-Recurrence U6 — triage-receipt pick demotion.

Live anatomy (GLM Agent 14, Job 486785, 2026-10-30): the loop dispatched
#3399 — an auto-landing policy-block CI incident — within hours of the class
census landing on main (#3416, docs/bridge/bridge-20261030-landingrace-class-
3instances.md), whose standing instruction says exactly this row should be
skip-with-evidence: triage plane complete (receipts #3407/#3410), remaining
work owner-lane (.github/ workflow internals — bridge-protected path). The
prose instruction is passive; the picker re-served the row and a full agent
cycle burned on log-probing a structurally blocked row.

Fix (machine remedy): scripts/agents/incident_triage_receipts.json is the ONE
machine index census PRs append to; pick_next_issue accepts an optional
triage_probe; run_dispatch_cycle wires the live probe at both dispatch
surfaces. Board-local, zero-network, fail-open:
  - a listed incident number demotes with a census-citing note (skip-and-
    advance, same shape as the live-claim/#3050/item-15 filters);
  - a missing or malformed registry serves every row unchanged;
  - the filter can only REMOVE a dispatch, never block one.

Pins enforced here (zero gh/network dependency — registry paths injected):
  1. Registry load: valid index built; missing file / malformed JSON /
     receipts non-list / malformed rows -> {} (fail-open); booleans are not
     incident numbers.
  2. Note: listed incident -> note carries censusRef + remainingWork +
     "skip-with-evidence"; unlisted -> None; non-numeric number -> None;
     number boundary safe (#33990 never matches #3399).
  3. Live wrapper never raises.
  4. pick_next_issue integration: triage-complete top row skipped, advances
     to the next candidate; triage_probe=None serves the row with zero
     probing (pre-change contract); a raising probe serves the row.
  5. AST pin: both dispatch surfaces wire triage_probe=_probe_triage_receipt.
  6. Registry file sanity: the shipped registry parses and every receipt row
     carries class/censusRef/remainingWork (a corrupt index shipped to main
     would silently disable the demotion).

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402


def _row(number: int, title: str = "fix(ci): CI — pipeline failed (Run 1)") -> dict:
    """gh-shaped board row (the picker only needs number/labels/title here)."""
    return {"number": number, "title": title, "labels": [], "state": "open"}


class TestLoadTriageReceipts(unittest.TestCase):
    def test_valid_registry_builds_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "receipts.json"
            p.write_text(json.dumps({
                "schema": "incident-triage-receipts/1",
                "receipts": [{"class": "c1", "incidents": [3390, 3399, 3400],
                              "censusRef": "PR #3416", "remainingWork": "owner-lane"}],
            }), encoding="utf-8")
            idx = cal._load_triage_receipts(p)
            self.assertEqual(sorted(idx), [3390, 3399, 3400])
            self.assertEqual(idx[3399]["censusRef"], "PR #3416")

    def test_missing_file_is_empty_fail_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(cal._load_triage_receipts(Path(tmp) / "absent.json"), {})

    def test_malformed_json_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "bad.json"
            p.write_text("{not json", encoding="utf-8")
            self.assertEqual(cal._load_triage_receipts(p), {})

    def test_receipts_non_list_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.json"
            p.write_text(json.dumps({"receipts": "nope"}), encoding="utf-8")
            self.assertEqual(cal._load_triage_receipts(p), {})

    def test_malformed_rows_skipped_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "r.json"
            p.write_text(json.dumps({"receipts": [
                "junk", 42, {"incidents": "not-a-list"}, {"no-incidents": 1},
                {"incidents": [1, "two", None, True, 2]},
            ]}), encoding="utf-8")
            idx = cal._load_triage_receipts(p)
            self.assertEqual(sorted(idx), [1, 2])
            # bool-exclusion must hold by IDENTITY: True == 1 in Python, so a
            # membership check would false-pass — pin no boolean key shipped.
            self.assertFalse(any(k is True or k is False for k in idx))


class TestTriageReceiptNote(unittest.TestCase):
    def setUp(self):
        self.index = {3399: {"censusRef": "docs/bridge/census.md (PR #3416)",
                             "remainingWork": "owner-lane only: (A) --auto queueing"}}

    def test_listed_incident_demotes_with_census_citation(self):
        note = cal._triage_receipt_note(_row(3399), index=self.index)
        self.assertIsNotNone(note)
        self.assertIn("triage-receipt demotion", note)
        self.assertIn("Zero-Recurrence U6", note)
        self.assertIn("PR #3416", note)
        self.assertIn("owner-lane only: (A) --auto queueing", note)
        self.assertIn("skip-with-evidence", note)

    def test_unlisted_incident_served(self):
        self.assertIsNone(cal._triage_receipt_note(_row(3401), index=self.index))

    def test_number_boundary_safe(self):
        self.assertIsNone(cal._triage_receipt_note(_row(33990), index=self.index))
        self.assertIsNone(cal._triage_receipt_note(_row(339), index=self.index))

    def test_non_numeric_number_is_unjudgeable(self):
        self.assertIsNone(cal._triage_receipt_note({"number": "abc"}, index=self.index))
        self.assertIsNone(cal._triage_receipt_note({}, index=self.index))

    def test_string_number_is_lenient(self):
        note = cal._triage_receipt_note({"number": "3399"}, index=self.index)
        self.assertIsNotNone(note)

    def test_empty_registry_serves(self):
        self.assertIsNone(cal._triage_receipt_note(_row(3399), index={}))


class TestLiveWrapper(unittest.TestCase):
    def test_wrapper_never_raises(self):
        with unittest.mock.patch.object(
            cal, "_triage_receipt_note", side_effect=RuntimeError("boom"),
        ):
            self.assertIsNone(cal._probe_triage_receipt(_row(3399)))


class _LeaseIsolated(unittest.TestCase):
    def setUp(self):
        patcher = unittest.mock.patch.object(
            cal, "load_issue_lease_store", lambda path=None: {}
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class TestPickIntegration(_LeaseIsolated):
    def test_triage_complete_top_row_advances_to_next_candidate(self):
        board = [_row(3399), _row(5000)]  # 3399 sorts FIRST (lower number)

        self.assertEqual(
            cal.pick_next_issue(
                issues=board,
                claim_probe=lambda n: (False, "no active claim on the feedback plane"),
                incident_probe=lambda item: None,
                premise_probe=lambda item: None,
                triage_probe=cal._probe_triage_receipt,
            ),
            "5000",
        )

    def test_probe_none_keeps_pre_u6_contract(self):
        """triage_probe=None ⇒ the triage-complete row is served as top pick,
        zero probing (pre-change contract byte-equivalent)."""
        board = [_row(3399), _row(5000)]
        self.assertEqual(
            cal.pick_next_issue(issues=board),
            "3399",
        )

    def test_raising_triage_probe_serves_the_row(self):
        board = [_row(3399), _row(5000)]

        def probe(item):
            raise RuntimeError("boom")

        self.assertEqual(
            cal.pick_next_issue(
                issues=board,
                claim_probe=lambda n: (False, "no active claim on the feedback plane"),
                triage_probe=probe,
            ),
            "3399",
        )


class TestDefaultProbeWiring(unittest.TestCase):
    def test_loop_source_wires_triage_probe_at_both_dispatch_sites(self):
        """AST pin (signature-robust, #2899-heal precedent): both
        pick_next_issue call sites must carry triage_probe=_probe_triage_receipt,
        so the demotion cannot silently regress to prose-only.
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
                    kw.arg == "triage_probe"
                    and isinstance(kw.value, ast.Name)
                    and kw.value.id == "_probe_triage_receipt"
                ):
                    wired += 1
        self.assertEqual(
            wired,
            2,
            "both dispatch surfaces (envelope + dispatch print) must wire the triage probe",
        )


class TestShippedRegistrySanity(unittest.TestCase):
    def test_shipped_registry_parses_and_rows_are_complete(self):
        """A corrupt index shipped to main would silently disable the
        demotion — pin the shipped file's shape (fail-closed sanity)."""
        idx = cal._load_triage_receipts(cal.TRIAGE_RECEIPTS_FILE)
        self.assertIn(3399, idx)
        for number, receipt in idx.items():
            self.assertTrue(receipt.get("class"), f"#{number} receipt missing class")
            self.assertTrue(receipt.get("censusRef"), f"#{number} receipt missing censusRef")
            self.assertTrue(receipt.get("remainingWork"), f"#{number} receipt missing remainingWork")


if __name__ == "__main__":
    unittest.main(verbosity=2)
