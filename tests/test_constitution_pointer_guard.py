#!/usr/bin/env python3
"""Contract tests for scripts/ci/constitution_pointer_guard.py (#1642).

Pins the dead-authority-pointer guard end-to-end:
  - hermetic scan semantics (flag / skip / boundary precision)
  - stale-allowlist detection (no ghost entries)
  - the shipped configuration scans the REAL repo clean (the #1642 sweep
    acceptance criterion — this is the anti-regression ratchet)

This file legitimately contains AGENT_RULES.md fixture strings; it is
allowlisted in the guard's ALLOWLIST under the `enforcement` class.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "constitution_pointer_guard.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))

import constitution_pointer_guard as cpg  # noqa: E402


class HermeticScanTests(unittest.TestCase):
    """scan_tree semantics on a tempdir — no git, no network, no repo writes."""

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self.root = Path(self._td.name)
        (self.root / "clean.md").write_text(
            "Governance lives in AGENTS.md — the Single Door SSOT.\n", encoding="utf-8"
        )
        (self.root / "doc.md").write_text(
            "see AGENT_RULES.md §3 for the U-rules\n", encoding="utf-8"
        )
        (self.root / "code.py").write_text(
            "# legacy: AGENT_RULES U4 doctrine\n"
            'x = "AGENT_RULES_PATH is a different, live surface"\n'
            'y = "agent_rules.json too"\n',
            encoding="utf-8",
        )
        (self.root / "allowed.md").write_text(
            "historical: AGENT_RULES.md was deleted by #1526\n", encoding="utf-8"
        )
        (self.root / "bin.dat").write_bytes(b"\x00 AGENT_RULES.md inside binary")

    def tearDown(self) -> None:
        self._td.cleanup()

    def _scan(self, files, allowlist):
        violations, stale = cpg.scan_tree(
            self.root, files, cpg._compile_patterns(), allowlist
        )
        return violations, stale

    def test_clean_file_not_flagged(self):
        violations, _ = self._scan(["clean.md"], {})
        self.assertEqual([v["file"] for v in violations], [])

    def test_md_citation_flagged_with_line(self):
        violations, _ = self._scan(["doc.md"], {})
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["file"], "doc.md")
        self.assertEqual(violations[0]["line"], 1)
        self.assertEqual(violations[0]["dead_path"], "AGENT_RULES.md")

    def test_py_comment_flagged(self):
        violations, _ = self._scan(["code.py"], {})
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0]["file"], "code.py")
        self.assertEqual(violations[0]["line"], 1)

    def test_word_boundary_precision(self):
        """AGENT_RULES_PATH / agent_rules.json name a live config file — out of class."""
        violations, _ = self._scan(["code.py"], {})
        self.assertTrue(all(v["line"] == 1 for v in violations))

    def test_binary_skipped(self):
        violations, _ = self._scan(["bin.dat"], {})
        self.assertEqual(violations, [])

    def test_allowlisted_file_skipped(self):
        violations, _ = self._scan(
            ["allowed.md"], {"allowed.md": ("historical", "test entry")}
        )
        self.assertEqual(violations, [])

    def test_stale_allowlist_entry_detected(self):
        _, stale = self._scan(["clean.md"], {"ghost.md": ("debt", "x")})
        self.assertEqual(stale, ["ghost.md"])


class ShippedConfigurationTests(unittest.TestCase):
    """Integration against the real repo — the #1642 acceptance ratchet."""

    def test_guard_self_test_mode_passes(self):
        proc = subprocess.run(  # noqa: S603
            [sys.executable, str(GUARD), "--self-test"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_real_repo_scan_is_clean(self):
        """The sweep landed: zero non-allowlisted citations on the live tree."""
        violations, stale = cpg.scan_tree(REPO_ROOT, cpg.tracked_files(REPO_ROOT))
        self.assertEqual(
            violations, [], "new citation of a deleted constitution path introduced"
        )
        self.assertEqual(stale, [], "allowlist drift — entry no longer tracked")

    def test_allowlist_classes_are_reasoned(self):
        """Every allowlist entry carries a non-empty class + reason."""
        for path, (cls, reason) in cpg.ALLOWLIST.items():
            self.assertIn(cls, {"historical", "protected", "mirror-parity", "enforcement", "debt"})
            self.assertTrue(reason.strip(), f"empty reason for {path}")


if __name__ == "__main__":
    unittest.main()
