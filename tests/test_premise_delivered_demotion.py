#!/usr/bin/env python3
"""Pin + behavior: case-file item 15 (§6ak) — premise-delivered pick demotion.

Live anatomy that motivates the filter (GLM Agent 27, Job 486827, 2026-10-30):
the loop dispatched #2395 minutes after its landing receipt hit main (merged
#3158, squash subject "…live-verified by receipt #2395…"), and #2597 after its
evidence refresh landed (merged #1d18bba, "…for #2597…") — the a-lane series
(a39/a40/a41/a45/a46/a48) documents the same class burning whole agent cycles
because the picker reads a body to extract a TASK but never checks whether the
body's PROMISE is already kept.

Fix (item 15, "landing-receipt cross-scan candidate picking", implemented):
pick_next_issue accepts an optional premise_probe; run_dispatch_cycle wires
the live probe at both dispatch surfaces. Two bounded scans, both fail-open:
  A. promised-artifact existence: backticked repo paths inside the reach of a
     promise marker are tested against the current tree; EVERY promised
     artifact existing ⇒ demote (any missing path keeps the row).
  B. merged-landing citation: one cached /pulls?state=closed fetch per pick
     run; a MERGED PR citing the row in delivery form (closes/fixes/resolves/
     for/receipt #N) ⇒ demote with the citing PR named. Closed-unmerged and
     in-gates vehicles never demote.

Pins enforced here (zero gh/network dependency — tree roots and fetchers are
injected fakes):
  1. Promise-marker extraction: marker-reach paths extracted; markerless
     bodies, out-of-reach paths, tree-escapes and malformed bodies extract
     nothing (never raises).
  2. Check A: all promised artifacts exist (temp tree) ⇒ demotion note;
     any missing ⇒ serve; markerless body falls through to Check B.
  3. Check B: merged "for #N"/"receipt #N"/"Closes #N" ⇒ demotion note with
     the citing PR number; closed-unmerged ⇒ serve; non-delivery citations
     ("refs #N", "#N false-close receipt") ⇒ serve; number-boundary safe
     (#N1 does not match #N).
  4. Check A hit short-circuits Check B (fetcher never called).
  5. Raising fetcher ⇒ serve (fail-open); unparseable number ⇒ serve.
  6. Live wrapper never raises.
  7. pick_next_issue integration: premise-delivered top row skipped, advances
     to the next candidate; pure mode (premise_probe=None) serves the row
     with zero probing — hermetic callers keep the pre-item-15 contract;
     a raising probe serves the row.
  8. AST pin: both dispatch surfaces wire premise_probe=_probe_premise_delivered.

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import ast
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal


def _row(number: int, labels: list[str] | None = None, body: str | None = None) -> dict:
    row = {
        "number": number,
        "title": f"row {number}",
        "labels": [{"name": name} for name in (labels or [])],
    }
    if body is not None:
        row["body"] = body
    return row


def _pr(number: int, title: str, merged_at: str | None = "2026-10-30T09:00:00Z", body: str | None = None) -> dict:
    return {"number": number, "title": title, "merged_at": merged_at, "body": body}


class TestPromisedArtifactPaths(unittest.TestCase):
    def test_marker_reach_path_is_extracted(self):
        body = "Full dossier lands in-repo as `docs/AUDIT_x.md` (companion PR). Other `docs/unrelated.md` stays out."
        self.assertEqual(cal._promised_artifact_paths(body), ["docs/AUDIT_x.md"])

    def test_each_marker_form_extracts(self):
        for marker in (
            "lands in-repo as `docs/a.md`",
            "land in repo as `docs/b.md`",
            "dossier at `docs/c.md`",
            "full dossier in `docs/d.md`",
            "companion PR `docs/e.md`",
        ):
            self.assertEqual(cal._promised_artifact_paths(f"promised: {marker}."), [f"docs/{marker.split('`')[1].split('/')[1]}"])

    def test_markerless_body_extracts_nothing(self):
        self.assertEqual(cal._promised_artifact_paths("fix the `scripts/x.py` tool"), [])

    def test_out_of_reach_path_extracts_nothing(self):
        body = "Dossier promise. The path `docs/late.md` appears after the sentence."
        self.assertEqual(cal._promised_artifact_paths(body), [])

    def test_tree_escape_paths_filtered(self):
        body = "lands in-repo as `docs/../../etc/passwd` and `/abs/path.md` and `docs/ok.md`."
        self.assertEqual(cal._promised_artifact_paths(body), ["docs/ok.md"])

    def test_malformed_body_never_raises(self):
        for bad in (None, "", 42, object()):
            self.assertEqual(cal._promised_artifact_paths(bad), [])


class TestPremiseDeliveredCheckA(unittest.TestCase):
    def test_all_promised_artifacts_exist_demotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "AUDIT_x.md").write_text("landed", encoding="utf-8")
            row = _row(3000, body="Full dossier lands in-repo as `docs/AUDIT_x.md` (companion PR).")
            note = cal._premise_delivered_note(
                row,
                tree_root=root,
                fetch_merged=lambda p: (_ for _ in ()).throw(AssertionError("fetch must not run when Check A hits")),
            )
            self.assertIsNotNone(note)
            self.assertIn("premise-delivered", note)
            self.assertIn("docs/AUDIT_x.md", note)
            self.assertIn("item 15", note)

    def test_any_missing_artifact_serves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "present.md").write_text("landed", encoding="utf-8")
            row = _row(3000, body="lands in-repo as `docs/present.md` and `docs/absent.md`.")
            self.assertIsNone(
                cal._premise_delivered_note(row, tree_root=root, fetch_merged=lambda p: [])
            )


class TestPremiseDeliveredCheckB(unittest.TestCase):
    def _row_plain(self, number: int) -> dict:
        # Markerless body: Check A vacuous, Check B decides.
        return _row(number, body="Evidence-only note. No promised artifact here.")

    def test_merged_for_citation_demotes(self):
        rows = [_pr(3158, "R62 disposition promotion — live-verified by receipt #2395 (bridge-x)")]
        note = cal._premise_delivered_note(self._row_plain(2395), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)
        self.assertIn("#3158", note)
        self.assertIn("receipt #2395", note)

    def test_merged_for_word_citation_demotes(self):
        rows = [_pr(3162, "Evidence refresh (report-only, zero-code) for #2597: build-plane burn")]
        note = cal._premise_delivered_note(self._row_plain(2597), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)
        self.assertIn("for #2597", note)

    def test_closed_unmerged_vehicle_serves(self):
        rows = [_pr(3170, "Recovery correction (report-only) for #2792", merged_at=None)]
        self.assertIsNone(
            cal._premise_delivered_note(self._row_plain(2792), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        )

    def test_non_delivery_citations_serve(self):
        # Challenge-style citations are NOT delivery-form: the row may still
        # need its own work.
        rows = [
            _pr(2615, "audit: #2608 false-close receipt — closed completed with zero verdict"),
            _pr(3001, "refs #2608 context in the ops ledger"),
        ]
        self.assertIsNone(
            cal._premise_delivered_note(self._row_plain(2608), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        )

    def test_number_boundary_safe(self):
        rows = [_pr(3001, "fix for #30011 wrong row")]
        self.assertIsNone(
            cal._premise_delivered_note(self._row_plain(3001), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        )

    def test_closes_citation_demotes(self):
        rows = [_pr(2815, "fix(agents): close the audit gap — Closes #2794")]
        note = cal._premise_delivered_note(self._row_plain(2794), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)

    def test_raising_fetcher_fails_open(self):
        def boom(per_page):
            raise RuntimeError("rate limited")

        self.assertIsNone(
            cal._premise_delivered_note(self._row_plain(2395), tree_root=Path("/nonexistent"), fetch_merged=boom)
        )

    def test_unparseable_number_serves(self):
        rows = [_pr(3158, "receipt #2395")]
        self.assertIsNone(
            cal._premise_delivered_note(
                {"number": "not-a-number", "title": "row", "body": "x"},
                tree_root=Path("/nonexistent"),
                fetch_merged=lambda p: rows,
            )
        )

    def test_check_a_hit_skips_the_landing_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "x.md").write_text("landed", encoding="utf-8")
            row = _row(3000, body="lands in-repo as `docs/x.md`.")
            rows = [_pr(9999, "merged landing for #3000")]

            def _guard_fetch(per_page):
                raise AssertionError("landing fetch must not run when Check A already demoted")

            note = cal._premise_delivered_note(row, tree_root=root, fetch_merged=_guard_fetch)
            self.assertIsNotNone(note)
            self.assertIn("docs/x.md", note)
            self.assertNotIn("#9999", note)


class TestLiveWrapper(unittest.TestCase):
    def test_wrapper_never_raises(self):
        with unittest.mock.patch.object(
            cal,
            "_premise_delivered_note",
            side_effect=RuntimeError("boom"),
        ):
            self.assertIsNone(cal._probe_premise_delivered(_row(3000)))


class _LeaseIsolated(unittest.TestCase):
    def setUp(self):
        patcher = unittest.mock.patch.object(
            cal, "load_issue_lease_store", lambda path=None: {}
        )
        patcher.start()
        self.addCleanup(patcher.stop)


class TestPickIntegration(_LeaseIsolated):
    def test_premise_delivered_top_row_advances_to_next_candidate(self):
        board = [_row(2395), _row(3000)]

        def probe(item):
            return (
                "premise-delivered (landing-receipt cross-scan, item 15/§6ak)"
                if item.get("number") == 2395
                else None
            )

        self.assertEqual(
            cal.pick_next_issue(
                issues=board,
                claim_probe=lambda n: (False, "no active claim on the feedback plane"),
                premise_probe=probe,
            ),
            "3000",
        )

    def test_pure_mode_keeps_pre_item_15_contract(self):
        """premise_probe=None ⇒ the row is served, zero probing."""
        board = [_row(2395), _row(3000)]
        self.assertEqual(cal.pick_next_issue(issues=board), "2395")

    def test_raising_premise_probe_serves_the_row(self):
        board = [_row(2395), _row(3000)]

        def probe(item):
            raise RuntimeError("boom")

        self.assertEqual(
            cal.pick_next_issue(
                issues=board,
                claim_probe=lambda n: (False, "no active claim on the feedback plane"),
                premise_probe=probe,
            ),
            "2395",
        )


class TestDefaultProbeWiring(unittest.TestCase):
    def test_loop_source_wires_premise_probe_at_both_dispatch_sites(self):
        """AST pin (signature-robust, #2899-heal precedent): both
        pick_next_issue call sites must carry
        premise_probe=_probe_premise_delivered, so the demotion cannot
        silently regress to prose-only.
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
                    kw.arg == "premise_probe"
                    and isinstance(kw.value, ast.Name)
                    and kw.value.id == "_probe_premise_delivered"
                ):
                    wired += 1
        self.assertEqual(
            wired,
            2,
            "both dispatch surfaces (envelope + dispatch print) must wire the premise probe",
        )


class TestReceiptLabelDemotion(unittest.TestCase):
    """Item 15 R2 (GLM Agent 23, Job 486814, 2026-10-30) — label-plane truth.

    Live anatomy: the picker dispatched #3351 (bridge:receipt — GLM Agent 10's
    zizmor-guard receipt) as a fresh coder-IMPLEMENT task while its own scope
    artifact tests/test_zizmor_profile_guard.py was already byte-on-main, and
    re-picked #2360 one run after demoting it — both because the anonymous
    /pulls citation scan silently failed open on the burned-out 60 req/h IP
    quota. A receipt row is a record of already-submitted work by
    construction; the label check demotes it with ZERO network dependency.
    """

    def test_bridge_receipt_label_demotes_with_zero_fetch(self):
        row = _row(3351, labels=["report", "bridge:receipt"], body="Bridge Work Order receipt body.")
        note = cal._premise_delivered_note(
            row,
            tree_root=Path("/nonexistent"),
            fetch_merged=lambda p: (_ for _ in ()).throw(AssertionError("fetch must not run for a receipt row")),
        )
        self.assertIsNotNone(note)
        self.assertIn("bridge:receipt", note)
        self.assertIn("already-submitted", note)

    def test_receipt_label_check_runs_before_tree_scans(self):
        # A receipt row with NO body at all still demotes — the label alone
        # is the plane of truth (zero-network, zero-heuristic).
        row = _row(3353, labels=["bridge:receipt"])
        note = cal._premise_delivered_note(row, tree_root=Path("/nonexistent"), fetch_merged=lambda p: [])
        self.assertIsNotNone(note)

    def test_non_receipt_labels_serve(self):
        row = _row(2360, labels=["p2-medium", "status:unclaimed", "repo:core", "audit:finding"], body="audit prose only.")
        self.assertIsNone(
            cal._premise_delivered_note(row, tree_root=Path("/nonexistent"), fetch_merged=lambda p: [])
        )

    def test_dict_labels_and_str_labels_both_recognized(self):
        for labels in (["bridge:receipt"], [{"name": "bridge:receipt"}]):
            row = {"number": 3345, "title": "r", "labels": labels, "body": ""}
            note = cal._premise_delivered_note(row, tree_root=Path("/nonexistent"), fetch_merged=lambda p: [])
            self.assertIsNotNone(note, f"label shape {labels!r} must be recognized")

    def test_malformed_labels_never_raise(self):
        for bad in (None, 42, [object()], [{"name": 42}]):
            row = {"number": 1, "title": "r", "labels": bad, "body": ""}
            try:
                cal._premise_delivered_note(row, tree_root=Path("/nonexistent"), fetch_merged=lambda p: [])
            except Exception as exc:  # noqa: BLE001
                self.fail(f"malformed labels {bad!r} raised {type(exc).__name__}")


class TestReceiptScopePaths(unittest.TestCase):
    """Item 15 R2 — structured `### Scope Paths` extraction (receipt-shape gated)."""

    RECEIPT_BODY = (
        "### Task ID\nbridge-20261030-x\n\n### Patch Branch\nbridge/x\n\n"
        "### Summary\nwork already submitted elsewhere.\n\n"
        "### Scope Paths\n- scripts/ci/guard.py\n- tests/test_guard.py\n\n"
        "### Test Evidence\nTier-1 reflection.\n"
    )

    def test_scope_block_extracts_list_paths(self):
        self.assertEqual(
            cal._receipt_scope_paths(self.RECEIPT_BODY),
            ["scripts/ci/guard.py", "tests/test_guard.py"],
        )

    def test_receipt_shape_gate_blocks_non_receipt_bodies(self):
        # A fresh work order that merely lists files to create must NOT be
        # demotable off this scan alone (no ### Task ID / ### Patch Branch).
        body = "### Deliverables\nPlease create:\n- scripts/new_thing.py\n"
        self.assertEqual(cal._receipt_scope_paths(body), [])

    def test_backticked_scope_items_extracted(self):
        body = "### Task ID\nx\n\n### Scope Paths\n- `docs/report.md`\n"
        self.assertEqual(cal._receipt_scope_paths(body), ["docs/report.md"])

    def test_tree_escape_and_absolute_paths_filtered(self):
        body = (
            "### Task ID\nx\n\n### Scope Paths\n- ../escape.md\n- /abs.md\n"
            "- ok/rel.md\n- no-slash.md\n"
        )
        self.assertEqual(cal._receipt_scope_paths(body), ["ok/rel.md"])

    def test_prose_after_scope_block_ends_extraction(self):
        body = (
            "### Task ID\nx\n\n### Scope Paths\n- docs/a.md\n"
            "Some prose line that is not a list item.\n- docs/b.md\n"
        )
        self.assertEqual(cal._receipt_scope_paths(body), ["docs/a.md"])

    def test_malformed_body_never_raises(self):
        for bad in (None, "", 42, object()):
            self.assertEqual(cal._receipt_scope_paths(bad), [])

    def test_all_scope_artifacts_exist_demotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests").mkdir()
            (root / "tests" / "test_zizmor_profile_guard.py").write_text("guard", encoding="utf-8")
            row = _row(
                3351,
                body="### Task ID\nx\n\n### Scope Paths\n- tests/test_zizmor_profile_guard.py\n",
            )
            note = cal._premise_delivered_note(
                row,
                tree_root=root,
                fetch_merged=lambda p: (_ for _ in ()).throw(AssertionError("fetch must not run when the scope scan hits")),
            )
            self.assertIsNotNone(note)
            self.assertIn("receipt scope cross-scan", note)
            self.assertIn("tests/test_zizmor_profile_guard.py", note)

    def test_missing_scope_artifact_serves(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = _row(3360, body="### Task ID\nx\n\n### Scope Paths\n- scripts/ci/not_yet.py\n")
            self.assertIsNone(
                cal._premise_delivered_note(row, tree_root=root, fetch_merged=lambda p: [])
            )


class TestDarkScanHonesty(unittest.TestCase):
    """Item 15 R2 — a failed anonymous fetch is a first-class dark state.

    Fail-open dispatch stays (never-raise contract), but the silence is gone:
    the advisory surfaces at landing_crossscan_advisory() for the pick log and
    the envelope board_note.
    """

    def setUp(self):
        self._orig = cal._LANDING_FETCH_FAILED

    def tearDown(self):
        cal._LANDING_FETCH_FAILED = self._orig

    def test_healthy_scan_advisory_is_none(self):
        cal._LANDING_FETCH_FAILED = False
        self.assertIsNone(cal.landing_crossscan_advisory())

    def test_failed_scan_advisory_honest(self):
        cal._LANDING_FETCH_FAILED = True
        advisory = cal.landing_crossscan_advisory()
        self.assertIsNotNone(advisory)
        self.assertIn("DARK", advisory)
        self.assertIn("re-verify", advisory)

    def test_live_fetch_failure_sets_dark_state(self):
        # The LIVE fetcher (not an injected one) must flip the dark flag on
        # any failure — that is the exact silent path this R2 closes.
        # R3 update (item 15, GLM Agent 05): the fetcher now has TWO
        # transports (REST first, tower second, one shared cache). With every
        # urlopen patched dark, both transports fail, and the live fetcher
        # raises HONESTLY (the R3 contract pinned in
        # test_landing_fetch_tower_fallback.py) while still flipping the dark
        # flag and caching the darkness — the note's fail-open layer serves
        # the row, never blocks. The R2-era silent-return shape would be a
        # false-green here: the raise is the honesty signal itself.
        cal._LANDING_FETCH_FAILED = False
        cal._LANDING_FETCH_DONE = False
        with unittest.mock.patch.object(
            cal.urllib.request, "urlopen", side_effect=OSError("rate limited")
        ):
            with self.assertRaises(RuntimeError):
                cal._fetch_merged_landing_prs(80)
        self.assertEqual(cal._LANDING_ROWS, [])
        self.assertTrue(cal._LANDING_FETCH_FAILED)
        self.assertEqual(cal._LANDING_PLANE, "dark")
        self.assertIsNotNone(cal.landing_crossscan_advisory())
        # darkness is cached: a later candidate re-networks nothing
        self.assertEqual(cal._fetch_merged_landing_prs(80), [])
        cal._LANDING_FETCH_DONE = True  # keep the module cache coherent

    def test_envelope_carries_dark_advisory_in_board_note(self):
        # build_task_envelope itself stays pure; the threading lives in
        # run_dispatch_cycle. Pin the SOURCE so the advisory cannot silently
        # regress out of the envelope path (same AST-pin style as above).
        loop_src = Path(cal.__file__).read_text(encoding="utf-8")
        self.assertIn("landing_crossscan_advisory()", loop_src)
        self.assertIn("board_note=note", loop_src)
        # the dark advisory must be threaded INTO note before the envelope call
        self.assertLess(
            loop_src.index("dark_note = landing_crossscan_advisory()"),
            loop_src.rindex("board_note=note"),
            "dark advisory must be computed before build_task_envelope consumes board_note",
        )


if __name__ == "__main__":
    unittest.main()
