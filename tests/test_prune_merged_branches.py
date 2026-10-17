"""tests/test_prune_merged_branches.py — offline battery for the #578 bridge-able slice.

Hermetic: builds throwaway git fixtures in a temp dir and injects a fake `gh`
CLI on PATH so the --execute path is exercised with zero network and zero
credentials. Mirrors the project's stdlib-only offline test doctrine.
"""

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO_ROOT, "scripts", "bridge", "prune_merged_branches.sh").replace("\\", "/")

BASH = "bash"
if os.name == "nt":
    git_bin = shutil.which("git")
    if git_bin:
        git_bash = os.path.join(os.path.dirname(os.path.dirname(git_bin)), "bin", "bash.exe")
        if os.path.exists(git_bash):
            BASH = git_bash

FAKE_GH = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    # fake gh: records API calls; FAKE_GH_FAIL=1 forces every call to fail.
    printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
    [ "${FAKE_GH_FAIL:-0}" = "1" ] && exit 1
    exit 0
    """
)


class PruneMergedBranchesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = self._tmp.name
        # bare "origin" repo
        self.origin = os.path.join(base, "origin.git")
        subprocess.run(["git", "init", "--bare", "-q", "-b", "main", self.origin], check=True)
        # work clone: seed main, add merged bridge/contributor branches + one unmerged
        self.work = os.path.join(base, "work")
        subprocess.run(["git", "clone", "-q", self.origin, self.work], check=True)
        # hermetic identity for the fixture repo
        for k, v in (("user.name", "fixture"), ("user.email", "fixture@example.test")):
            subprocess.run(["git", "config", k, v], cwd=self.work, check=True)
        # seed main first (clone of an empty origin starts on an unborn HEAD)
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "seed"],
            cwd=self.work, check=True,
        )
        subprocess.run(["git", "push", "-q", "origin", "main"], cwd=self.work, check=True)
        for name, diverge in (
            ("bridge/bridge-20261017-old-wo", False),
            ("contributor/issue-999", False),
            ("feature/unmerged-keep", True),
        ):
            self._commit_on_branch(name, diverge)
            if not diverge:
                # simulate a LANDED PR: merge the branch into main and push
                subprocess.run(["git", "checkout", "-q", "main"], cwd=self.work, check=True)
                subprocess.run(["git", "merge", "-q", "--ff-only", name], cwd=self.work, check=True)
                subprocess.run(["git", "push", "-q", "origin", "main"], cwd=self.work, check=True)
        subprocess.run(
            ["git", "push", "-q", "origin",
             "bridge/bridge-20261017-old-wo", "contributor/issue-999", "feature/unmerged-keep"],
            cwd=self.work, check=True,
        )
        subprocess.run(["git", "fetch", "-q", "origin"], cwd=self.work, check=True)
        # fake gh on PATH
        self.bindir = os.path.join(base, "bin")
        os.makedirs(self.bindir)
        self.ghlog = os.path.join(base, "gh.log").replace("\\", "/")
        with open(os.path.join(self.bindir, "gh"), "w", encoding="utf-8") as fh:
            fh.write(FAKE_GH)
        os.chmod(os.path.join(self.bindir, "gh"), 0o755)
        self.env = dict(
            os.environ,
            PATH=self.bindir + os.pathsep + os.environ["PATH"],
            FAKE_GH_LOG=self.ghlog,
        )
        self.addCleanup(self._tmp.cleanup)

    def _commit_on_branch(self, name, diverge=False):
        subprocess.run(["git", "checkout", "-q", "-B", name, "main"], cwd=self.work, check=True)
        subprocess.run(
            ["git", "commit", "-q", "--allow-empty", "-m", "c-" + name],
            cwd=self.work, check=True,
        )
        if diverge:  # second commit that never lands on main -> branch stays unmerged
            subprocess.run(
                ["git", "commit", "-q", "--allow-empty", "-m", "diverge-" + name],
                cwd=self.work, check=True,
            )

    def _run(self, *extra, base="main"):
        env = dict(self.env, REMOTE="origin", BASE=base)
        return subprocess.run(
            [BASH, SCRIPT, *extra],
            cwd=self.work, env=env, capture_output=True, text=True,
        )

    def test_dry_run_lists_merged_only_and_never_calls_gh(self):
        r = self._run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("would delete bridge/bridge-20261017-old-wo", r.stdout)
        self.assertIn("would delete contributor/issue-999", r.stdout)
        self.assertNotIn("feature/unmerged-keep", r.stdout)
        self.assertNotIn("main", r.stdout.replace("would delete", ""))
        self.assertFalse(os.path.exists(self.ghlog), "dry run must not call gh")

    def test_execute_deletes_merged_only_via_gh(self):
        r = self._run("--execute")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.ghlog, encoding="utf-8") as fh:
            log = fh.read()
        self.assertIn("-X DELETE repos/", log)
        self.assertIn("git/refs/heads/bridge/bridge-20261017-old-wo", log)
        self.assertIn("git/refs/heads/contributor/issue-999", log)
        self.assertNotIn("feature/unmerged-keep", log)
        self.assertNotIn("refs/heads/main", log)

    def test_execute_failure_reflected_in_exit_code(self):
        env = dict(self.env, REMOTE="origin", BASE="main", FAKE_GH_FAIL="1")
        r = subprocess.run(
            [BASH, SCRIPT, "--execute"],
            cwd=self.work, env=env, capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("failed: 2", r.stdout)

    def test_missing_base_fails_closed(self):
        r = self._run(base="does-not-exist")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not found", r.stderr)


if __name__ == "__main__":
    unittest.main()
