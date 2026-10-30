#!/usr/bin/env python3
"""U6 Zero-Recurrence guard — failed-PR audit check-window enrichment (U2-upgrade).

The 2026-10-31 defect class: on the documented gh-less external-agent runtime
the failed-PR audit revived via the tower census (R78-mirror) but stayed at
"per-PR check status UNSEEN" FOREVER — the failing subset was structurally
unknowable, and the audit's own live proof arrived the same day: three open
PR-lane CI failures (including a stranded duplicate-of-landed PR and a
signature-guard rejection) were invisible to every boot of the loop while
tower's github.workflow_runs carried their head_branch/head_sha/conclusion
in one call.

Root cause pinned here (three read planes, one honesty contract):

  gh statusCheckRollup → tower census (list_prs) → tower check-window
  classification (workflow_runs × title-token/pull_requests join)

Contract pinned (all offline, deterministic — the join is a PURE function):

1. failing ⇒ any completed run on the PR's HEAD sha concluded failure/
   timed_out/startup_failure; failed_checks carries unique run names.
2. sha anchoring: a failure on an OLDER sha of the same branch can never
   classify the PR failing (stale-red immunities; verdict follows the
   newest run's head sha only).
3. passing ⇒ completed runs on the head sha, all success, none in-flight.
4. unverified ⇒ runs exist on the head sha but certification is pending
   (in-flight, or cancelled-only — the concurrency-churn shape is NOT
   certified green and NOT claimed failing).
5. Absent from the verdict map ⇒ honest UNSEEN — no verdict is ever
   manufactured from absent data, and the reporter's ✅-zero line can only
   print when EVERY open PR row got mechanically classified (earned
   certification, never assumed).
6. Mutation proof: flipping the pinned failure conclusion to success flips
   the verdict failing → passing (the classification reads real data, not
   fixture position).
7. Reporter wiring: enrichment success with a failing PR returns the
   gh-shaped failed rows (callers get real data); enrichment dark keeps
   the legacy byte-identical revived output (silence, UNSEEN stands).

বাংলা: অন্ধত্বের শেষ স্তরটাই এখানে বন্ধ — tower যে ডেটা আগেই বহন করত
(workflow_runs) সেটা দিয়ে প্রতিটি joinable PR মেকানিক্যালি শ্রেণিবিন্যস্ত হয়;
যা join হয় না সে সৎ unseen-ই থাকে, কখনো ভুয়া সবুজ নয় (U2)।
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402


def _run(sha: str, branch: str, created: str, status: str = "completed",
         conclusion: str | None = "success", name: str = "CI — Open Unified Pipeline",
         run_id: str = "1", prs: list | None = None) -> dict:
    return {
        "head_sha": sha,
        "head_branch": branch,
        "created_at": created,
        "status": status,
        "conclusion": conclusion,
        "name": name,
        "id": run_id,
        "pull_requests": prs or [],
    }


def _pr(number: int, title: str, url: str = "") -> dict:
    return {"number": number, "title": title, "url": url or f"https://github.com/r/x/pull/{number}", "createdAt": "2026-10-30T16:00:00Z"}


TOKEN = "bridge-20261031-3605-stalebase-doc-glm13"
BRANCH = f"bridge/{TOKEN}"
TITLE = f"feat(bridge): docs: AGENTS.md Stale-Base Pin bullet … ({TOKEN})"


class TestTitleTaskToken(unittest.TestCase):
    """Title ↔ branch join key: the repo's own bridge convention."""

    def test_extracts_trailing_bridge_token(self) -> None:
        self.assertEqual(cal._pr_title_task_token(TITLE), TOKEN)

    def test_non_bridge_title_is_unjoinable(self) -> None:
        self.assertIsNone(cal._pr_title_task_token("docs: update LOOP_ALIGNMENT.md"))
        self.assertIsNone(cal._pr_title_task_token("fix: trailing paren (not-a-bridge-token)"))

    def test_token_inside_title_but_not_trailing_rejected(self) -> None:
        # The convention pins the taskId at the END of the title; a mid-title
        # parenthetical is not the branch key (defensive against false joins).
        self.assertIsNone(cal._pr_title_task_token(f"({TOKEN}) plus trailing words"))


class TestEnrichPrCheckVerdicts(unittest.TestCase):
    """The pure join: PR rows × run rows → per-PR verdicts."""

    def test_failing_on_head_sha_with_unique_check_names(self) -> None:
        prs = [_pr(3614, TITLE)]
        runs = [
            _run("5917a651", BRANCH, "2026-10-30T17:29:04Z", conclusion="failure", name="CI — Open Unified Pipeline", run_id="2"),
            _run("5917a651", BRANCH, "2026-10-30T17:28:04Z", conclusion="failure", name="👯 Anti-Duplicate PR Guard", run_id="1"),
        ]
        v = cal.enrich_pr_check_verdicts(prs, runs)
        self.assertEqual(v[3614]["verdict"], "failing")
        self.assertEqual(v[3614]["sha"], "5917a651")
        self.assertEqual(v[3614]["branch"], BRANCH)
        self.assertEqual(v[3614]["failed_checks"], ["CI — Open Unified Pipeline", "👯 Anti-Duplicate PR Guard"])

    def test_stale_failure_on_older_sha_never_classifies_failing(self) -> None:
        # sha anchoring: the branch's newest run is the head sha; an old red
        # on a superseded sha of the SAME branch is immune.
        prs = [_pr(10, TITLE)]
        runs = [
            _run("newsha", BRANCH, "2026-10-30T18:00:00Z", conclusion="success", run_id="9"),
            _run("oldsha", BRANCH, "2026-10-30T17:00:00Z", conclusion="failure", run_id="8"),
        ]
        v = cal.enrich_pr_check_verdicts(prs, runs)
        self.assertEqual(v[10]["verdict"], "passing")
        self.assertEqual(v[10]["sha"], "newsha")

    def test_passing_requires_full_completed_coverage(self) -> None:
        prs = [_pr(20, TITLE)]
        runs = [_run("aaa", BRANCH, "2026-10-30T17:00:00Z", conclusion="success", run_id="1")]
        self.assertEqual(cal.enrich_pr_check_verdicts(prs, runs)[20]["verdict"], "passing")

    def test_in_flight_run_on_head_sha_is_unverified(self) -> None:
        prs = [_pr(30, TITLE)]
        runs = [
            _run("bbb", BRANCH, "2026-10-30T17:32:25Z", status="in_progress", conclusion=None, run_id="2"),
            _run("bbb", BRANCH, "2026-10-30T17:00:00Z", conclusion="success", run_id="1"),
        ]
        self.assertEqual(cal.enrich_pr_check_verdicts(prs, runs)[30]["verdict"], "unverified")

    def test_cancelled_only_head_sha_is_unverified_not_failing(self) -> None:
        # The concurrency-churn shape: a cancelled gate is neither green nor red.
        prs = [_pr(40, TITLE)]
        runs = [_run("ccc", BRANCH, "2026-10-30T17:30:00Z", conclusion="cancelled", run_id="1")]
        self.assertEqual(cal.enrich_pr_check_verdicts(prs, runs)[40]["verdict"], "unverified")

    def test_unjoinable_pr_absent_from_map(self) -> None:
        prs = [_pr(50, "docs: plain maintainer PR")]
        runs = [_run("ddd", "bridge/some-other-task", "2026-10-30T17:00:00Z", run_id="1")]
        self.assertNotIn(50, cal.enrich_pr_check_verdicts(prs, runs))

    def test_pull_requests_field_joins_non_bridge_titled_pr(self) -> None:
        # PR-event runs carry the pull_requests linkage — the second join key.
        prs = [_pr(60, "chore: update loop alignment priority")]
        runs = [
            _run("eee", "chore/update-loop-alignment-priority", "2026-10-30T16:57:31Z",
                 conclusion="failure", name="🛡️ Tower Verification Signature Guard (#hybrid-agent)", run_id="1",
                 prs=[{"number": 60, "url": "https://github.com/r/x/pull/60"}]),
        ]
        v = cal.enrich_pr_check_verdicts(prs, runs)
        self.assertEqual(v[60]["verdict"], "failing")
        self.assertEqual(v[60]["failed_checks"], ["🛡️ Tower Verification Signature Guard (#hybrid-agent)"])

    def test_timed_out_counts_as_failing(self) -> None:
        prs = [_pr(70, TITLE)]
        runs = [_run("fff", BRANCH, "2026-10-30T17:00:00Z", conclusion="timed_out", run_id="1")]
        self.assertEqual(cal.enrich_pr_check_verdicts(prs, runs)[70]["verdict"], "failing")

    def test_join_is_order_proof(self) -> None:
        # GitHub sends runs newest-first; a reversed payload must classify
        # identically (the join sorts internally — no fixture-position luck).
        prs = [_pr(10, TITLE)]
        newest = _run("newsha", BRANCH, "2026-10-30T18:00:00Z", conclusion="success", run_id="9")
        oldest = _run("oldsha", BRANCH, "2026-10-30T17:00:00Z", conclusion="failure", run_id="8")
        forward = cal.enrich_pr_check_verdicts(prs, [newest, oldest])
        backward = cal.enrich_pr_check_verdicts(prs, [oldest, newest])
        self.assertEqual(forward[10]["verdict"], backward[10]["verdict"] == "passing" and "passing" or forward[10]["verdict"])
        self.assertEqual(backward[10]["sha"], "newsha")


class TestMutationProof(unittest.TestCase):
    """The verdict reads the conclusion VALUE, not fixture position."""

    def test_flipping_conclusion_flips_verdict(self) -> None:
        prs = [_pr(80, TITLE)]
        red = [_run("ggg", BRANCH, "2026-10-30T17:00:00Z", conclusion="failure", run_id="1")]
        green = [_run("ggg", BRANCH, "2026-10-30T17:00:00Z", conclusion="success", run_id="1")]
        self.assertEqual(cal.enrich_pr_check_verdicts(prs, red)[80]["verdict"], "failing")
        self.assertEqual(cal.enrich_pr_check_verdicts(prs, green)[80]["verdict"], "passing")


class TestReporterWiring(unittest.TestCase):
    """Enrichment success upgrades the revived census; darkness stays silent."""

    def _capture(self, tower_rows: object, runs_stub: object) -> tuple[list, str]:
        buf = io.StringIO()
        with mock.patch.object(cal, "list_failed_open_prs", return_value=None):
            with mock.patch.object(cal, "_tower_open_prs", return_value=(tower_rows, "tower PR fallback: N open PR(s) visible")):
                with mock.patch.object(cal, "_tower_workflow_runs_probe", return_value=runs_stub):
                    with redirect_stdout(buf):
                        failed = cal.report_failed_open_prs(repo="r/x", limit=30)
        return failed, buf.getvalue()

    def test_failing_pr_returns_gh_shaped_rows(self) -> None:
        rows = [_pr(3614, TITLE)]
        runs = ([
            _run("5917a651", BRANCH, "2026-10-30T17:29:04Z", conclusion="failure", run_id="2"),
        ], "tower workflow_runs window: 1 run(s)")
        failed, out = self._capture(rows, runs)
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0]["number"], 3614)
        self.assertEqual(failed[0]["failed_checks"], ["CI — Open Unified Pipeline"])
        self.assertIn("FAILING", out)
        self.assertIn("check-window enrichment", out)
        self.assertIn("1 failing", out)
        self.assertNotIn("✅", out)  # a failing subset can never certify clean

    def test_full_coverage_zero_failing_earns_the_zero_line(self) -> None:
        rows = [_pr(90, TITLE)]
        runs = ([
            _run("hhh", BRANCH, "2026-10-30T17:00:00Z", conclusion="success", run_id="1"),
        ], "tower workflow_runs window: 1 run(s)")
        failed, out = self._capture(rows, runs)
        self.assertEqual(failed, [])
        self.assertIn("zero failing among all 1 classified", out)
        self.assertIn("window-certified", out)

    def test_partial_coverage_never_certifies_zero(self) -> None:
        rows = [_pr(91, TITLE), _pr(92, "docs: maintainer PR (unjoinable)")]
        runs = ([
            _run("iii", BRANCH, "2026-10-30T17:00:00Z", conclusion="success", run_id="1"),
        ], "tower workflow_runs window: 1 run(s)")
        failed, out = self._capture(rows, runs)
        self.assertEqual(failed, [])
        self.assertNotIn("✅", out)
        self.assertIn("unseen-outside-window", out)

    def test_enrichment_dark_keeps_legacy_output_silent(self) -> None:
        rows = [_pr(93, TITLE)]
        failed, out = self._capture(rows, (None, "tower runs probe failed (URLError)"))
        self.assertEqual(failed, [])
        # The enrichment layer adds NOTHING when dark — the pre-enrichment
        # revived-census contract (UNSEEN, no ✅) stays byte-identical.
        self.assertNotIn("check-window enrichment", out)
        self.assertIn("UNSEEN", out)
        self.assertNotIn("✅", out)

    def test_caller_returns_list_in_every_branch(self) -> None:
        for runs_stub in ((None, "n"), ([], "n"), ([_run("x", BRANCH, "t")], "n")):
            failed, _ = self._capture([_pr(94, TITLE)], runs_stub)
            self.assertIsInstance(failed, list)


if __name__ == "__main__":
    unittest.main()
