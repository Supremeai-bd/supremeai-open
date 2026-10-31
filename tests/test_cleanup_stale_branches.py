#!/usr/bin/env python3
"""tests/test_cleanup_stale_branches.py — contract tests for scripts/ci/cleanup_stale_branches.py.

The stale-branch pruner is wired twice into .github/workflows/pipeline.yml
(best-effort `|| true`) and deletes remote branches, yet shipped with no test
face and a destructive fail-open defect family: `get_open_pr_head_branches()`
swallowed every failure into an empty set, so a transient `gh pr list`
failure (gh missing — observed live in agent sandboxes, auth expired, rate
limit, malformed JSON) was indistinguishable from "zero open PRs" and the
very next step deleted EVERY transient branch on origin, in-flight work
included. Class-close scan: the same swallow-to-empty shape exists in
transit_prune.py and group_closeout_janitor.py, but neither is wired to any
workflow — the live instance was cleanup_stale_branches.py only.

Pins the fail-closed contract hermetically (no network, no git mutations):
  - unknown protected set (gh rc!=0, malformed JSON, valid non-list JSON)
    aborts with exit 1 and never issues `git push origin --delete`;
  - verified-empty protected set proceeds; open-PR heads and main/master
    survive; unprefixed branches survive; prefixed orphans are deleted;
  - --dry-run lists without deleting; deletion batches in chunks of 20;
  - get_remote_branches() parsing filters HEAD/main/master and non-origin
    lines; enumeration failure aborts fail-closed.

Fully offline, stdlib-only, dual mode (unittest + pytest).
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import cleanup_stale_branches as cleanup  # noqa: E402


class FakeCompleted:
    def __init__(self, rc: int = 0, out: str = "", err: str = ""):
        self.returncode = rc
        self.stdout = out
        self.stderr = err


class FakeRun:
    """subprocess.run stand-in that routes by argv prefix and records pushes.

    Mirrors check=True semantics: nonzero `git branch -r` / `gh pr list` raises
    CalledProcessError exactly as the real run() would under check=True.
    """

    def __init__(self, *, gh_rc=0, gh_out="[]", branch_rc=0, branch_out=""):
        self.gh_rc = gh_rc
        self.gh_out = gh_out
        self.branch_rc = branch_rc
        self.branch_out = branch_out
        self.push_calls: list = []

    def __call__(self, args, **kwargs):
        argv = list(args)
        if argv[:2] == ["gh", "pr"]:
            if self.gh_rc != 0:
                raise subprocess.CalledProcessError(self.gh_rc, argv)
            return FakeCompleted(0, self.gh_out, "")
        if argv[:2] == ["git", "branch"]:
            if self.branch_rc != 0:
                raise subprocess.CalledProcessError(self.branch_rc, argv)
            return FakeCompleted(0, self.branch_out, "")
        if argv[:2] == ["git", "push"]:
            self.push_calls.append(argv)
            return FakeCompleted(0, "", "")
        return FakeCompleted(0, "", "")  # git fetch --prune and anything else


def branch_listing(names) -> str:
    return "".join(f"  origin/{n}\n" for n in names)


class CleanupStaleBranchesFailClosedTest(unittest.TestCase):
    """The core class: unverified protected set must abort, never delete."""

    def run_main(self, fake, extra_args=()):
        with mock.patch.object(cleanup.subprocess, "run", fake), \
                mock.patch.object(sys, "argv", ["cleanup_stale_branches.py", *extra_args]):
            rc = cleanup.main()
        return rc, fake.push_calls

    def test_gh_failure_fails_closed_no_delete(self):
        """gh pr list rc!=0 -> exit 1, zero push-deletes."""
        rc, pushes = self.run_main(FakeRun(gh_rc=1))
        self.assertEqual(rc, 1)
        self.assertEqual(pushes, [])

    def test_gh_malformed_json_fails_closed(self):
        rc, pushes = self.run_main(FakeRun(gh_out="not-json"))
        self.assertEqual(rc, 1)
        self.assertEqual(pushes, [])

    def test_gh_non_list_json_fails_closed(self):
        """gh error payloads are valid JSON but not a PR list: unknown, not empty."""
        rc, pushes = self.run_main(FakeRun(gh_out='{"message": "Bad credentials"}'))
        self.assertEqual(rc, 1)
        self.assertEqual(pushes, [])

    def test_git_branch_failure_fails_closed_no_delete(self):
        rc, pushes = self.run_main(FakeRun(branch_rc=1))
        self.assertEqual(rc, 1)
        self.assertEqual(pushes, [])

    def test_unverified_set_returns_none(self):
        with mock.patch.object(cleanup.subprocess, "run", FakeRun(gh_rc=1)):
            self.assertIsNone(cleanup.get_open_pr_head_branches())


class CleanupStaleBranchesBehaviorTest(unittest.TestCase):
    """Verified inputs: protection, selection, dry-run, batching, parsing."""

    def run_main(self, fake, extra_args=()):
        with mock.patch.object(cleanup.subprocess, "run", fake), \
                mock.patch.object(sys, "argv", ["cleanup_stale_branches.py", *extra_args]):
            rc = cleanup.main()
        return rc, fake.push_calls

    def test_verified_empty_set_proceeds_to_delete_orphans(self):
        rc, pushes = self.run_main(
            FakeRun(gh_out="[]", branch_out=branch_listing(["bridge/stale-a", "feat/orphan-b"]))
        )
        self.assertEqual(rc, 0)
        self.assertEqual(
            pushes,
            [["git", "push", "origin", "--delete", "bridge/stale-a", "feat/orphan-b"]],
        )

    def test_open_pr_heads_survive(self):
        rc, pushes = self.run_main(
            FakeRun(
                gh_out='[{"headRefName": "bridge/inflight"}, {"headRefName": "feat/also-open"}]',
                branch_out=branch_listing(["bridge/inflight", "feat/also-open", "bridge/stale"]),
            )
        )
        self.assertEqual(rc, 0)
        self.assertEqual(
            pushes, [["git", "push", "origin", "--delete", "bridge/stale"]]
        )

    def test_unprefixed_branches_survive(self):
        rc, pushes = self.run_main(
            FakeRun(gh_out="[]", branch_out=branch_listing(["release-9", "someone-fork"]))
        )
        self.assertEqual(rc, 0)
        self.assertEqual(pushes, [])

    def test_main_master_head_filtered_by_parsing(self):
        listing = (
            "  origin/HEAD -> origin/main\n"
            "  origin/main\n"
            "  origin/master\n"
            "  origin/bridge/x\n"
            "  not-an-origin-line\n"
        )
        with mock.patch.object(cleanup.subprocess, "run", FakeRun(gh_out="[]", branch_out=listing)):
            self.assertEqual(cleanup.get_remote_branches(), {"bridge/x"})

    def test_dry_run_lists_without_deleting(self):
        rc, pushes = self.run_main(
            FakeRun(gh_out="[]", branch_out=branch_listing(["bridge/stale-a"])),
            extra_args=["--dry-run"],
        )
        self.assertEqual(rc, 0)
        self.assertEqual(pushes, [])

    def test_no_stale_branches_returns_zero(self):
        rc, pushes = self.run_main(
            FakeRun(gh_out="[]", branch_out=branch_listing(["main"]))
        )
        self.assertEqual(rc, 0)
        self.assertEqual(pushes, [])

    def test_deletion_batches_in_chunks_of_20(self):
        stale = [f"bridge/b{i:03d}" for i in range(45)]
        rc, pushes = self.run_main(
            FakeRun(gh_out="[]", branch_out=branch_listing(stale))
        )
        self.assertEqual(rc, 0)
        self.assertEqual([len(c) - 4 for c in pushes], [20, 20, 5])
        self.assertEqual(pushes[0][4], "bridge/b000")
        self.assertEqual(pushes[2][-1], "bridge/b044")


if __name__ == "__main__":
    unittest.main()
