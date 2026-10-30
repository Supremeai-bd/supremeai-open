#!/usr/bin/env python3
"""Pin + behavior: U3 family extension — referenced-PR-landed CI-row demotion.

Live anatomy (GLM Agent 20, Job 486804, 2026-10-31 ~22:2xZ): the loop served
#3858 ("fix(ci): PR #3534 failing checks (bridge/bridge-20261030-3402-twin-
closure-r1)") minutes after the referenced PR itself landed green — merged as
eed3470 (2026-10-30T22:21:35Z, 45/45 checks passed). Sibling #3857 was served
while its referenced PR (#3537) had been superseded by r4 (#3655). The
existing guards miss the shape because the citation relation is INVERTED:
item 15 (§6ak) looks for merged PRs that CITE the row, while a CI-ingress row
names the PR in its own TITLE and the PR never cites the row back.

Fix (machine remedy): _ci_row_pr_landed_note / _probe_ci_row_pr_landed — the
probe parses the referenced PR number from the row title (boundary-safe,
premise-gated on "failing check(s)" / "checks failed" / "check failure"),
reuses the SAME single per-run landing fetch item 15 already pays for (zero
extra network), and demotes only on the airtight premise: the referenced PR
is verifiably MERGED inside the fetched window. Closed-unmerged (supersession,
e.g. #3537) stays served — that judgement needs the successor-PR identity,
which is owner/U3-lane, not mechanical.

Pins enforced here (zero gh/network dependency — fetchers injected):
  1. Behavior: merged referenced PR demotes with a note naming #N;
     closed-unmerged serves; PR absent from the window serves; a title
     without the premise words serves without fetching; a title without a
     PR number serves.
  2. Boundary safety: "PR #35374" never demotes row-PR 3537 and vice versa;
     "PR#3537" (no space) matches.
  3. Fail-open: raising fetcher / malformed rows / non-dict item / None title
     serve unchanged; the live wrapper never raises.
  4. pick_next_issue integration: a CI row with a landed referenced PR is
     skipped in the same run and the next candidate is served;
     ci_landed_probe=None serves the row (pre-change contract); a raising
     probe serves the row.
  5. AST pin: both dispatch surfaces wire ci_landed_probe=_probe_ci_row_pr_landed.

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

import continuous_agent_loop as cal  # noqa: E402


def _ci_row(number: int, pr: int, words: str = "failing checks") -> dict:
    title = f"fix(ci): PR #{pr} {words} (bridge/bridge-20261030-{pr}-twin-closure-r1)"
    return {"number": number, "title": title, "labels": ["status:unclaimed"], "state": "open"}


def _merged(pr: int, title: str = "feat(bridge): twin closure receipt") -> dict:
    return {"number": pr, "title": title, "merged_at": "2026-10-30T22:21:35Z", "state": "closed"}


def _closed_unmerged(pr: int) -> dict:
    return {"number": pr, "title": "superseded r3", "merged_at": None, "state": "closed"}


class TestCiRowPrLandedNote(unittest.TestCase):
    def test_merged_referenced_pr_demotes(self):
        rows = [_merged(3534)]
        note = cal._ci_row_pr_landed_note(_ci_row(3858, 3534), fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)
        self.assertIn("#3534", note)
        self.assertIn("landed green", note)
        self.assertIn("skip-with-evidence", note)

    def test_closed_unmerged_referenced_pr_serves(self):
        # Supersession (#3537 r3 -> r4 #3655) needs successor identity: owner lane.
        rows = [_closed_unmerged(3537)]
        self.assertIsNone(
            cal._ci_row_pr_landed_note(_ci_row(3857, 3537), fetch_merged=lambda p: rows)
        )

    def test_referenced_pr_absent_from_window_serves(self):
        rows = [_merged(9999)]
        self.assertIsNone(
            cal._ci_row_pr_landed_note(_ci_row(3858, 3534), fetch_merged=lambda p: rows)
        )

    def test_no_premise_words_serves_without_fetch(self):
        # A plain "PR #N" title mention is related work, not a CI incident.
        def _boom(per_page):
            raise AssertionError("fetch must not run when the premise gate fails")

        row = {"number": 4000, "title": f"report: analysis of PR #3534 landing shape", "labels": []}
        self.assertIsNone(cal._ci_row_pr_landed_note(row, fetch_merged=_boom))

    def test_title_without_pr_number_serves(self):
        rows = [_merged(3534)]
        row = {"number": 4001, "title": "fix(ci): pipeline failing checks again", "labels": []}
        self.assertIsNone(cal._ci_row_pr_landed_note(row, fetch_merged=lambda p: rows))

    def test_premise_word_variants_demote(self):
        rows = [_merged(3534)]
        for words in ("checks failed", "check failure"):
            note = cal._ci_row_pr_landed_note(_ci_row(4002, 3534, words=words), fetch_merged=lambda p: rows)
            self.assertIsNotNone(note, words)

    def test_number_boundary_safe(self):
        # "PR #35374" must not demote via PR 3537, and "PR #3537" not via 35374.
        rows = [_merged(3537)]
        self.assertIsNone(
            cal._ci_row_pr_landed_note(_ci_row(4003, 35374), fetch_merged=lambda p: rows)
        )
        rows2 = [_merged(35374)]
        self.assertIsNone(
            cal._ci_row_pr_landed_note(_ci_row(4004, 3537), fetch_merged=lambda p: rows2)
        )

    def test_no_space_compound_matches(self):
        rows = [_merged(3534)]
        row = {"number": 4005, "title": "fix(ci): PR#3534 failing checks", "labels": []}
        note = cal._ci_row_pr_landed_note(row, fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)

    def test_malformed_rows_fail_open(self):
        rows = [None, "junk", {"number": "x"}, {"number": 3534, "title": "t", "merged_at": "2026-10-30T22:21:35Z"}]
        note = cal._ci_row_pr_landed_note(_ci_row(4006, 3534), fetch_merged=lambda p: rows)
        self.assertIsNotNone(note)

    def test_raising_fetcher_fails_open(self):
        def _boom(per_page):
            raise RuntimeError("dark plane")

        self.assertIsNone(
            cal._ci_row_pr_landed_note(_ci_row(4007, 3534), fetch_merged=_boom)
        )

    def test_none_item_and_empty_title_never_raise(self):
        self.assertIsNone(cal._ci_row_pr_landed_note(None, fetch_merged=lambda p: []))
        self.assertIsNone(
            cal._ci_row_pr_landed_note({"number": 4008, "title": None}, fetch_merged=lambda p: [])
        )


class TestLiveWrapper(unittest.TestCase):
    def test_wrapper_never_raises(self):
        for bad in (None, {}, {"number": "x", "title": "fix(ci): PR #1 failing checks"}, 42):
            try:
                note = cal._probe_ci_row_pr_landed(bad)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"wrapper raised {exc!r} for {bad!r}")
            self.assertIsNone(note)


class _LeaseIsolated(unittest.TestCase):
    def setUp(self):
        patcher = unittest.mock.patch.object(
            cal, "load_issue_lease_store", lambda path=None: {}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self._log = []

    def _log_fn(self, level, msg):
        self._log.append(f"{level} {msg}")


class TestPickIntegration(_LeaseIsolated):
    def test_landed_pr_row_advances_to_next_candidate(self):
        issues = [
            _ci_row(3858, 3534),
            {"number": 3860, "title": "docs: unrelated row", "labels": ["status:unclaimed"], "state": "open"},
        ]
        picked = cal.pick_next_issue(
            issues=issues,
            claim_probe=lambda n: (False, "no active claim on the feedback plane"),
            ci_landed_probe=lambda item: cal._ci_row_pr_landed_note(
                item, fetch_merged=lambda p: [_merged(3534)]
            ),
            log_fn=self._log_fn,
        )
        self.assertEqual(picked, "3860")
        self.assertTrue(any("referenced-PR-landed demotion" in line for line in self._log))

    def test_probe_none_keeps_pre_change_contract(self):
        # claim_probe absent -> pure mode serves the top row label-only
        # (pre-change contract byte-equivalent, zero probing).
        issues = [_ci_row(3858, 3534)]
        picked = cal.pick_next_issue(
            issues=issues,
            ci_landed_probe=None,
            log_fn=self._log_fn,
        )
        self.assertEqual(picked, "3858")

    def test_raising_probe_serves_the_row(self):
        def _boom(item):
            raise RuntimeError("probe dark")

        issues = [_ci_row(3858, 3534)]
        picked = cal.pick_next_issue(
            issues=issues,
            claim_probe=lambda n: (False, "no active claim on the feedback plane"),
            ci_landed_probe=_boom,
            log_fn=self._log_fn,
        )
        self.assertEqual(picked, "3858")
        self.assertTrue(any("ci-landed probe raised" in line for line in self._log))


class TestDefaultProbeWiring(unittest.TestCase):
    def test_loop_source_wires_ci_landed_probe_at_both_dispatch_sites(self):
        """AST pin (signature-robust, #2899-heal precedent): both
        pick_next_issue call sites must carry
        ci_landed_probe=_probe_ci_row_pr_landed, so the demotion cannot
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
                    kw.arg == "ci_landed_probe"
                    and isinstance(kw.value, ast.Name)
                    and kw.value.id == "_probe_ci_row_pr_landed"
                ):
                    wired += 1
        self.assertEqual(
            wired,
            2,
            "both dispatch surfaces (envelope + dispatch print) must wire the ci_landed probe",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
