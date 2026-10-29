#!/usr/bin/env python3
"""tests/test_script_index_coverage.py — #1812 coverage contract for scripts/ops/_INDEX.md.

Background (issue #1812): generate_script_index.py advertised "Discovers every
script under scripts/" but passed base=SCRIPTS_DIR (= scripts/ops, the
generator's own directory) to the discovery lib, so the index covered ONLY the
ops subtree — 265 rows, zero hits for scripts/ci/security_gate.py or
scripts/agents/continuous_agent_loop.py despite 20+ live CI guards. The #1630
freshness gate kept passing because it checks STALENESS, not COVERAGE.

Landed contract (this suite pins it):
  1. The regenerated index has rows from multiple top-level groups (the bug's
     core symptom was a single-group index).
  2. Known cross-tree scripts (a CI guard, an agent runner, an ops tool) are
     indexed.
  3. COVERAGE: every tracked script under scripts/ (git ls-files) appears as a
     row in the regenerated index — the direct anti-regression pin for #1812.
  4. Internal consistency: the header's total count equals the actual row count.

Offline, stdlib-only, regenerates into a temp file (never touches the real
_INDEX.md — freshness of the committed copy is #1630's suite, not this one).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "ops" / "generate_script_index.py"

ROW_RE = re.compile(r"^\| `([^`]+)` \|", re.MULTILINE)
TOTAL_RE = re.compile(r"\*\*(\d+) scripts\*\*")


@unittest.skipUnless(
    GENERATOR.is_file() and (REPO_ROOT / "scripts").is_dir(),
    "scripts tree absent in this mirror layout",
)
class TestScriptIndexCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "index.md"
        r = subprocess.run(
            [sys.executable, str(GENERATOR), "--output", str(cls.out)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        cls.gen_stdout = r.stdout + r.stderr
        if r.returncode != 0:
            raise AssertionError(f"generator failed:\n{cls.gen_stdout}")
        cls.rows = set(ROW_RE.findall(cls.out.read_text(encoding="utf-8")))
        cls.header_total = int(TOTAL_RE.search(cls.out.read_text(encoding="utf-8")).group(1))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_index_spans_multiple_top_level_groups(self):
        """The #1812 symptom was a single-subtree (ops-only) index."""
        groups = {row.split("/", 1)[0] for row in self.rows if "/" in row}
        self.assertGreaterEqual(
            len(groups), 5,
            f"index covers only {sorted(groups)} — scan root collapsed again?\n{self.gen_stdout}",
        )
        for required in ("agents", "ci", "ops"):
            self.assertIn(required, groups)

    def test_known_cross_tree_scripts_are_indexed(self):
        for known in (
            "ci/security_gate.py",
            "agents/continuous_agent_loop.py",
            "ops/generate_script_index.py",
        ):
            self.assertIn(known, self.rows, f"{known} missing from the index")

    def test_every_tracked_script_is_indexed(self):
        """Direct #1812 anti-regression pin: zero tracked scripts outside the index."""
        ls = subprocess.run(
            ["git", "ls-files", "scripts/"], cwd=REPO_ROOT,
            capture_output=True, text=True, timeout=60,
        )
        if ls.returncode != 0:
            self.skipTest("git ls-files unavailable (non-git checkout)")
        tracked = {
            f[len("scripts/"):]
            for f in ls.stdout.splitlines()
            if f.startswith("scripts/") and f.endswith((".py", ".sh", ".mjs", ".js", ".dart"))
        }
        missing = sorted(tracked - self.rows)
        self.assertEqual(
            missing, [],
            f"{len(missing)} tracked script(s) invisible to the index — scan-root regression "
            f"(#1812 class): {missing[:10]}",
        )

    def test_header_total_matches_row_count(self):
        self.assertEqual(
            self.header_total, len(self.rows),
            "header total disagrees with actual row count — composition drift",
        )


if __name__ == "__main__":
    unittest.main()
