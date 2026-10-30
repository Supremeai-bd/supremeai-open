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
     for/receipt #N), compound receipt-header form (R<n>/#N, #<n>/#N) or the
     board's bare R-idiom (R<n>) ⇒ demote with the citing PR named.
     Closed-unmerged and in-gates vehicles never demote.

Pins enforced here (zero gh/network dependency — tree roots and fetchers are
injected fakes):
  1. Promise-marker extraction: marker-reach paths extracted; markerless
     bodies, out-of-reach paths, tree-escapes and malformed bodies extract
     nothing (never raises).
  2. Check A: all promised artifacts exist (temp tree) ⇒ demotion note;
     any missing ⇒ serve; markerless body falls through to Check B.
  3. Check B: merged "for #N"/"receipt #N"/"Closes #N", compound receipt
     headers ("R<n>/#N", "#<n>/#N") and the board's bare R-idiom ("R<n>")
     ⇒ demotion note with the citing PR number; closed-unmerged ⇒ serve;
     non-delivery citations ("refs #N", "#N false-close receipt", bare
     "#N") ⇒ serve; number-boundary safe (#N1, R<n>/#N1 and R<n>0 do not
     match #N; branch-slug "...-r<n>-..." never demotes a compound check).
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

    def test_merged_compound_citation_demotes(self):
        # Live miss (2026-10-30 12:52Z): merged #3338's subject carried the
        # row as "R1776/#2766" — slash-adjacent, no whitespace — the keyword
        # regex sailed past it and the loop re-dispatched #2766 ~20 minutes
        # after its own evidence refresh landed.
        rows = [
            _pr(
                3338,
                "report(guard): R1776/#2766 evidence refresh r2 — zizmor 1.31.1 rescan on current main (bridge-20261030-r1776-zizmor-refresh-glm25)",
            )
        ]
        note = cal._premise_delivered_note(self._row_plain(2766), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)
        self.assertIn("#3338", note)
        self.assertIn("R1776/#2766", note)

    def test_merged_hash_compound_citation_demotes(self):
        rows = [_pr(3400, "evidence refresh #1776/#2766 — zero-delta receipt")]
        note = cal._premise_delivered_note(self._row_plain(2766), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)
        self.assertIn("#1776/#2766", note)

    def test_lowercase_compound_citation_demotes(self):
        # "receipt r1776/#2766" defeats the KEYWORD form ("receipt" is not
        # adjacent to #2766) — the compound form must carry it, case-blind.
        rows = [_pr(3401, "rescan r3 receipt r1776/#2766")]
        note = cal._premise_delivered_note(self._row_plain(2766), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)

    def test_bare_r_idiom_demotes_parent_row(self):
        # The same receipt names the parent row bare ("R1776") — the loop's
        # next #1776 serve must see the fresh family receipt too.
        rows = [
            _pr(
                3338,
                "report(guard): R1776/#2766 evidence refresh r2 — zizmor 1.31.1 rescan on current main",
            )
        ]
        note = cal._premise_delivered_note(self._row_plain(1776), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)
        self.assertIn("R1776", note)

    def test_bare_number_mention_serves(self):
        # Non-delivery: bare "#N" with no delivery keyword and no compound
        # slash is related-work context, never a landing receipt.
        rows = [_pr(3402, "per #2766 precedent the refresh method stays pinned-version")]
        self.assertIsNone(
            cal._premise_delivered_note(self._row_plain(2766), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        )

    def test_compound_number_boundary_safe(self):
        rows = [_pr(3403, "R1776/#27661 wrong-row compound")]
        self.assertIsNone(
            cal._premise_delivered_note(self._row_plain(2766), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        )

    def test_bare_r_idiom_number_boundary_safe(self):
        # "R17760" must not demote row 1776 (boundary), and the title carries
        # NO standalone "R1776" token.
        rows = [_pr(3404, "R17760 and R17761 tokens only")]
        self.assertIsNone(
            cal._premise_delivered_note(self._row_plain(1776), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        )

    def test_branch_slug_alone_never_demotes_compound_check(self):
        # "...-r1776-..." inside a branch slug matches \bR<n>\b ONLY when a
        # slash follows for the compound; as a bare token it IS the board's
        # R-idiom and demotes — pin the compound's slug-neutrality instead:
        # a slug WITHOUT the R-token (plain dash-number) must not demote.
        rows = [_pr(3405, "watchdog live run (bridge-20261030-2766-watchdog-live-run-r1) (#3405)")]
        self.assertIsNone(
            cal._premise_delivered_note(self._row_plain(2766), tree_root=Path("/nonexistent"), fetch_merged=lambda p: rows)
        )

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


if __name__ == "__main__":
    unittest.main()
