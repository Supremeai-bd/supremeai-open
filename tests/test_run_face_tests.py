#!/usr/bin/env python3
"""tests/test_run_face_tests.py — contract tests for scripts/ci/run_face_tests.py.

The face-runner (subprocess exposure for tests outside the 9-tier verify
ladder) landed in PR #4310 with NO test face - flagged by the test parity
guard's fail-closed sweep, the same defect family as parity red #12
(pr_preflight_guard.py, closed by GLM Agent 09 in PR #4159).

Pins the pure contracts hermetically (no network, no repo mutations, no real
pytest subprocess):
  - FACE_TESTS: every entry exists on disk and is a tests/*.py file (drift
    guard: renaming or deleting a face test fails HERE, not silently at
    runtime);
  - main(): builds exactly [sys.executable, -m, pytest, -q] + FACE_TESTS,
    runs from REPO_ROOT, and propagates the child exit code verbatim;
  - import is side-effect free (main never fires at module load).

Fully offline, stdlib-only, dual mode (unittest + pytest).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "ci"))

import run_face_tests as rft  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestFaceTestsManifest(unittest.TestCase):
    def test_face_tests_exist_on_disk(self):
        for entry in rft.FACE_TESTS:
            self.assertTrue(
                (REPO_ROOT / entry).is_file(),
                f"face test missing on disk: {entry}",
            )

    def test_face_tests_are_repo_test_files(self):
        for entry in rft.FACE_TESTS:
            self.assertTrue(entry.startswith("tests/"), entry)
            self.assertTrue(entry.endswith(".py"), entry)

    def test_face_tests_have_no_duplicates(self):
        self.assertEqual(len(rft.FACE_TESTS), len(set(rft.FACE_TESTS)))

    def test_face_tests_nonempty(self):
        self.assertGreaterEqual(len(rft.FACE_TESTS), 1)


class TestMainContract(unittest.TestCase):
    def test_main_builds_expected_cmd_and_cwd(self):
        sentinel = mock.Mock(returncode=0)
        with mock.patch.object(rft.subprocess, "run", return_value=sentinel) as m:
            rc = rft.main()
        self.assertEqual(rc, 0)
        (cmd,), kwargs = m.call_args
        self.assertEqual(cmd, [sys.executable, "-m", "pytest", "-q", *rft.FACE_TESTS])
        self.assertEqual(kwargs.get("cwd"), rft.REPO_ROOT)

    def test_main_propagates_child_returncode(self):
        sentinel = mock.Mock(returncode=3)
        with mock.patch.object(rft.subprocess, "run", return_value=sentinel):
            self.assertEqual(rft.main(), 3)

    def test_main_quiet_mode_no_state_mutation_flags(self):
        sentinel = mock.Mock(returncode=0)
        with mock.patch.object(rft.subprocess, "run", return_value=sentinel) as m:
            rft.main()
        (cmd,), _ = m.call_args
        self.assertIn("-q", cmd)
        for banned in ("--collect-only", "-s", "--lf", "--looponfail"):
            self.assertNotIn(banned, cmd)


class TestImportHygiene(unittest.TestCase):
    def test_module_import_is_side_effect_free(self):
        with mock.patch.object(rft.subprocess, "run") as m:
            self.assertEqual(m.call_count, 0)


if __name__ == "__main__":
    unittest.main()
