#!/usr/bin/env python3
"""tests/test_auto_bridge_pr_opener.py — contract tests for scripts/ci/auto_bridge_pr_opener.py.

The ingress PR automation is wired twice into .github/workflows/pipeline.yml
(scheduled job with GH_TOKEN, `--auto-open`) and shipped with no test face.
It wields real authority: `git push --force-with-lease` onto agent branches,
autonomous work-order rejection (rebase-conflict / corrupted-payload closure
comments + labels), and PR creation whose body hard-asserts
"[x] Pre-Push Rebase Invariant verified ... (0 commits behind)".

That assertion used to lie: an unparseable `git rev-list --count` result was
folded to `behind = 0`, silently skipping the rebase while the PR body still
certified the invariant. Same defect family as the stale-branch pruner
(unknown conflated with a safe known value); closed fail-closed — unknown
divergence now aborts with no PR. This face pins that contract plus the
stranded-detection rules (header-over-fallback extraction, report-only
filter, first-seen dedupe), the conflict/corruption closure flows, dry-run
purity, and the fresh-branch no-push path.

Fully offline, stdlib-only, dual mode (unittest + pytest).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import auto_bridge_pr_opener as opener  # noqa: E402


def wo(num, title="Bridge Work Order", body=None):
    return {"number": num, "title": title, "body": body or "", "labels": []}


def issues_json(*rows):
    return json.dumps(list(rows))


HEADER_BODY = "### Patch Branch\n\nbridge/primary-a\n\nsome context `bridge/fallback-b` note"


class FakeCmd:
    """run_cmd stand-in that routes by argv prefix and records every call."""

    def __init__(self, *, issues="[]", existing_prs="[]", behind="0",
                 rebase_rc=0, diff_files="", push_rc=0, pr_create_rc=0):
        self.issues = issues
        self.existing_prs = existing_prs
        self.behind = behind
        self.rebase_rc = rebase_rc
        self.diff_files = diff_files
        self.push_rc = push_rc
        self.pr_create_rc = pr_create_rc
        self.calls: list = []
        self.created_prs: list = []
        self.issue_closes: list = []
        self.issue_comments: list = []

    def __call__(self, args, cwd=None):
        argv = list(args)
        self.calls.append(argv)
        if argv[:3] == ["gh", "issue", "list"]:
            return (0, self.issues, "")
        if argv[:3] == ["gh", "pr", "list"]:
            return (0, self.existing_prs, "")
        if argv[:3] == ["gh", "pr", "create"]:
            self.created_prs.append(argv)
            if self.pr_create_rc == 0:
                return (0, "https://github.com/x/pr/1", "")
            return (self.pr_create_rc, "", "boom")
        if argv[:3] == ["gh", "issue", "close"]:
            self.issue_closes.append(argv)
            return (0, "", "")
        if argv[:3] == ["gh", "issue", "comment"]:
            self.issue_comments.append(argv)
            return (0, "", "")
        if argv[:2] == ["gh"]:
            return (0, "", "")  # issue edit and friends
        if argv[:2] == ["git", "rev-list"]:
            if self.behind is None:
                return (1, "", "fatal: bad revision")
            return (0, self.behind + "\n", "")
        if argv[:2] == ["git", "rebase"]:
            if self.rebase_rc != 0:
                return (self.rebase_rc, "", "CONFLICT (content): conflict in file")
            return (0, "", "")
        if argv[:2] == ["git", "diff"]:
            return (0, self.diff_files, "")
        if argv[:2] == ["git", "push"]:
            return (self.push_rc, "", "" if self.push_rc == 0 else "lease rejected")
        if argv[:2] == ["git"]:
            return (0, "", "")  # fetch/checkout/branch/config
        return (0, "", "")


def flatten(calls):
    return " ".join(" ".join(map(str, c)) for c in calls)


class FindStrandedTest(unittest.TestCase):
    def run_find(self, fake):
        with mock.patch.object(opener, "run_cmd", fake):
            return opener.find_stranded_bridge_work_orders()

    def test_gh_failure_returns_empty(self):
        def broken(args, cwd=None):
            argv = list(args)
            if argv[:3] == ["gh", "issue", "list"]:
                return (1, "", "gh not found")
            return (0, "", "")

        with mock.patch.object(opener, "run_cmd", broken):
            self.assertEqual(opener.find_stranded_bridge_work_orders(), [])

    def test_primary_header_beats_backtick_fallback(self):
        rows = self.run_find(FakeCmd(issues=issues_json(wo(7, "T", HEADER_BODY))))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["branch"], "bridge/primary-a")

    def test_fallback_used_when_header_missing(self):
        body = "notes about `bridge/fallback-b` here"
        rows = self.run_find(FakeCmd(issues=issues_json(wo(8, "T", body))))
        self.assertEqual([r["branch"] for r in rows], ["bridge/fallback-b"])

    def test_report_only_receipts_skipped(self):
        rows = self.run_find(FakeCmd(issues=issues_json(
            wo(9, "report-only receipt for cycle 3", "### Patch Branch\n\nbridge/one"))))
        self.assertEqual(rows, [])

    def test_dedupe_keeps_first_seen_branch(self):
        body = "### Patch Branch\n\nbridge/dup"
        rows = self.run_find(FakeCmd(issues=issues_json(
            wo(11, "A", body), wo(12, "B", body))))
        self.assertEqual([r["issue_number"] for r in rows], [11])

    def test_existing_open_pr_not_stranded(self):
        rows = self.run_find(FakeCmd(
            issues=issues_json(wo(13, "T", "### Patch Branch\n\nbridge/one")),
            existing_prs='[{"number": 50}]'))
        self.assertEqual(rows, [])


class OpenPrFlowTest(unittest.TestCase):
    def test_unknown_divergence_fails_closed(self):
        """Unparseable rev-list output must abort: no push, no PR, no lie."""
        for bad in ("", "fatal: not a git repository"):
            fake = FakeCmd(behind=bad)
            with mock.patch.object(opener, "run_cmd", fake):
                ok = opener.open_pr_for_work_order(
                    {"issue_number": 21, "title": "T", "branch": "bridge/x", "body": ""},
                    dry_run=False,
                )
            self.assertFalse(ok, f"behind={bad!r} must not open a PR")
            self.assertEqual(fake.created_prs, [])
            self.assertFalse(any(c[:2] == ["git", "push"] for c in fake.calls))
            self.assertTrue(any(c[:2] == ["git", "checkout"] for c in fake.calls))

    def test_fresh_branch_opens_pr_without_rebase_or_push(self):
        fake = FakeCmd(behind="0")
        with mock.patch.object(opener, "run_cmd", fake):
            ok = opener.open_pr_for_work_order(
                {"issue_number": 22, "title": "T", "branch": "bridge/x", "body": ""},
                dry_run=False,
            )
        self.assertTrue(ok)
        self.assertEqual(len(fake.created_prs), 1)
        self.assertFalse(any(c[:2] == ["git", "rebase"] for c in fake.calls))
        self.assertFalse(any(c[:2] == ["git", "push"] for c in fake.calls))
        body = " ".join(fake.created_prs[0])
        self.assertIn("Closes #22", body)

    def test_behind_branch_rebases_and_force_pushes_with_lease(self):
        fake = FakeCmd(behind="3")
        with mock.patch.object(opener, "run_cmd", fake):
            ok = opener.open_pr_for_work_order(
                {"issue_number": 23, "title": "T", "branch": "bridge/x", "body": ""},
                dry_run=False,
            )
        self.assertTrue(ok)
        self.assertTrue(any(c[:2] == ["git", "rebase"] and "origin/main" in c for c in fake.calls))
        pushes = [c for c in fake.calls if c[:2] == ["git", "push"]]
        self.assertEqual(len(pushes), 1)
        self.assertIn("--force-with-lease", pushes[0])
        self.assertIn("tmp-23:bridge/x", pushes[0])
        self.assertEqual(len(fake.created_prs), 1)

    def test_rebase_conflict_closes_wo_without_pr(self):
        fake = FakeCmd(behind="3", rebase_rc=1)
        with mock.patch.object(opener, "run_cmd", fake):
            ok = opener.open_pr_for_work_order(
                {"issue_number": 24, "title": "T", "branch": "bridge/x", "body": ""},
                dry_run=False,
            )
        self.assertFalse(ok)
        self.assertEqual(fake.created_prs, [])
        self.assertTrue(any(c[:2] == ["git", "rebase"] and "--abort" in c for c in fake.calls))
        blob = flatten(fake.issue_comments)
        self.assertIn("auto-bridge:conflict-close", blob)
        self.assertEqual(len(fake.issue_closes), 1)

    def test_corrupted_payload_closes_wo_without_pr(self):
        fake = FakeCmd(behind="0", diff_files="bridge/broken.py\n")
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "bridge").mkdir()
            (Path(td) / "bridge" / "broken.py").write_text(
                "diff --git a/broken.py b/broken.py\nindex 1234567..89abcde 100644\n")
            cwd = Path.cwd()
            try:
                os.chdir(td)
                with mock.patch.object(opener, "run_cmd", fake):
                    ok = opener.open_pr_for_work_order(
                        {"issue_number": 25, "title": "T", "branch": "bridge/x", "body": ""},
                        dry_run=False,
                    )
            finally:
                os.chdir(cwd)
        self.assertFalse(ok)
        self.assertEqual(fake.created_prs, [])
        blob = flatten(fake.issue_comments)
        self.assertIn("auto-bridge:corruption-close", blob)
        self.assertEqual(len(fake.issue_closes), 1)

    def test_healthy_payload_opens_pr(self):
        fake = FakeCmd(behind="0", diff_files="bridge/ok.py\n")
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "bridge").mkdir()
            (Path(td) / "bridge" / "ok.py").write_text("print('hello')\n")
            cwd = Path.cwd()
            try:
                os.chdir(td)
                with mock.patch.object(opener, "run_cmd", fake):
                    ok = opener.open_pr_for_work_order(
                        {"issue_number": 26, "title": "T", "branch": "bridge/x", "body": ""},
                        dry_run=False,
                    )
            finally:
                os.chdir(cwd)
        self.assertTrue(ok)
        self.assertEqual(len(fake.created_prs), 1)
        self.assertEqual(fake.issue_closes, [])

    def test_dry_run_performs_zero_mutations(self):
        fake = FakeCmd(behind="0")
        ok = opener.open_pr_for_work_order(
            {"issue_number": 27, "title": "T", "branch": "bridge/x", "body": ""},
            dry_run=True,
        )
        self.assertTrue(ok)
        self.assertEqual(fake.calls, [])


class MainFlowTest(unittest.TestCase):
    def run_main(self, fake, *extra):
        with mock.patch.object(opener, "run_cmd", fake), \
                mock.patch.object(sys, "argv", ["auto_bridge_pr_opener.py", *extra]):
            return opener.main()

    def test_clean_board_exits_zero(self):
        self.assertEqual(self.run_main(FakeCmd(issues="[]"), "--auto-open"), 0)

    def test_auto_open_processes_and_reports(self):
        fake = FakeCmd(issues=issues_json(wo(31, "T", "### Patch Branch\n\nbridge/one")), behind="0")
        rc = self.run_main(fake, "--auto-open")
        self.assertEqual(rc, 0)
        self.assertEqual(len(fake.created_prs), 1)

    def test_dry_run_mode_reports_without_mutations(self):
        fake = FakeCmd(issues=issues_json(wo(32, "T", "### Patch Branch\n\nbridge/one")))
        rc = self.run_main(fake, "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(fake.created_prs, [])
        self.assertFalse(any(c[:2] == ["git", "fetch"] for c in fake.calls))


if __name__ == "__main__":
    unittest.main()
