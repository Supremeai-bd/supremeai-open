#!/usr/bin/env python3
"""tests/test_script_index_freshness.py — #1630 CI gate for scripts/ops/_INDEX.md.

Background (issue #1630): the ops script index advertises a ``--check`` CI
gate that was never wired into any workflow, so the index drifted 47 days
(2026-09-10 -> 2026-10-27; 269 -> 253 scripts, 34 -> 36 groups) while
documenting scripts that no longer exist and hiding new ones from agents.

Landed contract (this suite pins it):
  1. ``scripts/ops/generate_script_index.py --check`` exits 0 on a fresh repo
     (the index is derived and regenerated, hand sections preserved).
  2. The generator's self-referenced paths point at the REAL location
     (``scripts/ops/generate_script_index.py``) — the pre-#1630 docstring and
     generated header pointed at ``scripts/generate_script_index.py`` which
     does not exist (agents following the hint hit FileNotFoundError).
  3. The freshness gate is actually WIRED: ``scripts/ci/run_all_guards.py``
     roster carries the ``--check`` invocation, and
     ``scripts/ci/deploy_preflight_guard.py --step1-syntax`` (CI Step 1, run
     on every PR and push-to-main by pipeline.yml) fails closed when the
     index is stale — enforced in full-repo mode only, never in the offline
     self-test fixture path.

Offline, stdlib-only. CI rides the existing test-matrix/preflight plumbing —
no .github/ edits (admin-owned path).
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GENERATOR = REPO_ROOT / "scripts" / "ops" / "generate_script_index.py"
INDEX = REPO_ROOT / "scripts" / "ops" / "_INDEX.md"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"
PREFLIGHT = REPO_ROOT / "scripts" / "ci" / "deploy_preflight_guard.py"

STALE_PATH_REF = "scripts/generate_script_index.py"
CANONICAL_PATH_REF = "scripts/ops/generate_script_index.py"


@unittest.skipUnless(
    GENERATOR.is_file() and INDEX.is_file(),
    "ops index tree absent in this mirror layout",
)
class TestScriptIndexFreshness(unittest.TestCase):
    def test_check_gate_passes_on_fresh_repo(self):
        """--check exits 0 when the committed index matches the live tree."""
        r = subprocess.run(
            [sys.executable, str(GENERATOR), "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            r.returncode, 0, f"index stale — regenerate it:\n{r.stdout}\n{r.stderr}"
        )

    def test_check_gate_ignores_untracked_strays(self):
        """A machine-local untracked stray must never poison the inventory.

        Phantom-row defect (2026-10-31, live on main): the generator scanned
        untracked working-tree files, so an index regenerated on a machine
        holding a stray script (ops/download_all_pr_diffs.py — never in git
        history) committed a row for a file no clean checkout has; every
        fresh tree then read the committed index as stale and the #1630
        gate went red (test_check_gate_passes_on_fresh_repo failure class).
        Mechanical cure: discovery is tracked-only, so this pin creates an
        untracked stray and demands --check stays green with it present.
        """
        stray = REPO_ROOT / "scripts" / "ops" / "_stray_poison_probe.py"
        original = INDEX.read_text(encoding="utf-8")
        try:
            stray.write_text(
                '"""stray poison probe — must stay untracked and unindexed."""\n',
                encoding="utf-8",
            )
            r = subprocess.run(
                [sys.executable, str(GENERATOR), "--check"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                r.returncode, 0,
                "untracked stray poisoned the inventory — generator must be "
                f"tracked-only:\n{r.stdout}\n{r.stderr}",
            )
        finally:
            if stray.exists():
                stray.unlink()
            INDEX.write_text(original, encoding="utf-8")

    def test_generator_self_references_real_path(self):
        """The generator's own docs/header must point at its real location."""
        src = GENERATOR.read_text(encoding="utf-8")
        self.assertNotIn(
            STALE_PATH_REF,
            src,
            "generator still self-references the non-existent "
            f"'{STALE_PATH_REF}' (pre-#1630 defect)",
        )
        header = INDEX.read_text(encoding="utf-8")
        self.assertIn(CANONICAL_PATH_REF, header)

    def test_freshness_gate_is_wired_into_guards(self):
        """The gate must be reachable from the guard roster AND CI Step 1."""
        roster = ROSTER.read_text(encoding="utf-8")
        self.assertIn(
            'generate_script_index.py", "--check',
            roster,
            "run_all_guards.py roster lost the index freshness entry",
        )
        preflight = PREFLIGHT.read_text(encoding="utf-8")
        self.assertIn(
            "_script_index_freshness",
            preflight,
            "deploy_preflight_guard.py --step1-syntax lost the #1630 sub-check",
        )

    def test_step1_syntax_fails_closed_on_stale_index(self):
        """Full-repo Step 1 must FAIL when the index is stale (fail-closed)."""
        sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
        try:
            import deploy_preflight_guard as dpg
        finally:
            sys.path.pop(0)
        original = INDEX.read_text(encoding="utf-8")
        try:
            INDEX.write_text(
                original + "\n<!-- #1630 test tamper: stale marker -->\n",
                encoding="utf-8",
            )
            ok, errs = dpg.run_step1_syntax(None)
            self.assertFalse(ok, "Step 1 passed despite a tampered (stale) index")
            self.assertTrue(
                any("STALE" in e for e in errs),
                f"expected a STALE diagnostic, got: {errs[:5]}",
            )
        finally:
            INDEX.write_text(original, encoding="utf-8")

    def test_step1_syntax_self_test_ignores_index(self):
        """Explicit-target mode (self-test fixtures) must NOT consult the index."""
        sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
        try:
            import deploy_preflight_guard as dpg
        finally:
            sys.path.pop(0)
        ok, errs = dpg.run_step1_syntax([PREFLIGHT])
        self.assertTrue(ok, f"self-test fixture path must stay deterministic: {errs[:5]}")

    def test_check_committed_gate_passes_on_fresh_repo(self):
        """#4471: --check-committed exits 0 when HEAD's index matches the regen."""
        r = subprocess.run(
            [sys.executable, str(GENERATOR), "--check-committed"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            r.returncode, 0,
            f"committed index stale — regenerate and commit it:\n{r.stdout}\n{r.stderr}",
        )

    def test_committed_layer_is_wired_into_preflight(self):
        """#4471: the committed-blob layer must be reachable from CI Step 1."""
        preflight = PREFLIGHT.read_text(encoding="utf-8")
        self.assertIn(
            "--check-committed",
            preflight,
            "deploy_preflight_guard.py lost the #4471 committed-blob layer",
        )

    def test_committed_gate_fails_closed_on_stale_head(self):
        """#4471 class-kill pin: a stale COMMITTED index must fail --check-committed.

        The ordering hole (regen-first CI step mutates the runner's workspace
        copy, so any workspace read sees a fresh index) is only provable
        against the committed basis: in a throwaway --shared clone we commit
        a tampered index to HEAD and demand exit 1. The real checkout is
        never touched (clone is discarded; no commits, no ref changes here).
        """
        import shutil
        import tempfile

        with tempfile.TemporaryDirectory(prefix="idx4471-") as tmp:
            clone = str(Path(tmp) / "clone")
            setup = subprocess.run(
                ["git", "clone", "--shared", "--quiet", str(REPO_ROOT), clone],
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(setup.returncode, 0, f"clone failed: {setup.stderr[:300]}")
            gen_in_clone = Path(clone) / "scripts" / "ops" / "generate_script_index.py"
            index_in_clone = Path(clone) / "scripts" / "ops" / "_INDEX.md"
            # A clone carries committed state only, so the clone's generator is
            # the pre-change blob; overlay THIS checkout's generator (the one
            # under test, with --check-committed) onto the clone. The clone's
            # lib.auto_discovery and SCAN_ROOT resolve inside the clone, so the
            # regen basis stays the clone's own tree.
            shutil.copy2(GENERATOR, gen_in_clone)
            fresh = subprocess.run(
                [sys.executable, str(gen_in_clone), "--check-committed"],
                cwd=clone,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(fresh.returncode, 0,
                             f"clone baseline must be green: {fresh.stdout}\n{fresh.stderr}")
            original = index_in_clone.read_text(encoding="utf-8")
            index_in_clone.write_text(
                original + "\n<!-- #4471 test tamper: stale-at-HEAD marker -->\n",
                encoding="utf-8",
            )
            commit = subprocess.run(
                ["git", "-c", "user.name=gate-pin", "-c", "user.email=gate-pin@test",
                 "commit", "-aqm", "#4471 pin: stale committed index"],
                cwd=clone,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(commit.returncode, 0, f"commit failed: {commit.stderr[:300]}")
            stale = subprocess.run(
                [sys.executable, str(gen_in_clone), "--check-committed"],
                cwd=clone,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                stale.returncode, 1,
                "--check-committed passed despite a stale committed index at HEAD "
                f"(ordering hole reopened):\n{stale.stdout}\n{stale.stderr}",
            )
            self.assertIn("STALE", stale.stdout + stale.stderr)

    def test_check_fails_closed_on_stale_hand_refs(self):
        """Prune-wave residue class (2026-11-02): a hand block referencing a
        pruned path must FAIL --check, not merely warn on stderr.

        Lived defect: #4975/#4976 pruned 256 ops scripts and regenerated the
        auto sections (so every match check stayed green) while 4 hand blocks
        kept pointing at 9 dead paths — the preserved-verbatim design carries
        the rot into every future regen, and the only signal was an advisory
        the guard never escalates. Fail-closed in the check modes makes the
        next purge land green only with truthful hand sections.
        """
        probe_block = (
            "\n<!-- hand:Stale Probe -->\n"
            "## Stale Probe\n"
            "| `definitely_pruned_glm07_probe.py` | probe row |\n"
            "<!-- /hand:Stale Probe -->\n"
        )
        original = INDEX.read_text(encoding="utf-8")
        try:
            INDEX.write_text(original + probe_block, encoding="utf-8")
            r = subprocess.run(
                [sys.executable, str(GENERATOR), "--check"],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            self.assertEqual(
                r.returncode, 1,
                "--check passed despite a hand block referencing a pruned path "
                f"(fail-closed class reopened):\n{r.stdout}\n{r.stderr}",
            )
            self.assertIn("STALE HAND SECTION", r.stderr)
            self.assertIn("FAIL (--check)", r.stdout + r.stderr)
        finally:
            INDEX.write_text(original, encoding="utf-8")

    def test_regen_mode_stays_advisory_on_stale_hand_refs(self):
        """The write/regen mode must stay advisory (exit 0): writing is not
        the enforcement surface; the check modes and the guard layer are.
        Restores the original index afterwards so the probe leaves no trace.
        """
        probe_block = (
            "\n<!-- hand:Stale Probe 2 -->\n"
            "## Stale Probe 2\n"
            "| `also_pruned_glm07_probe.py` | probe row |\n"
            "<!-- /hand:Stale Probe 2 -->\n"
        )
        original = INDEX.read_text(encoding="utf-8")
        try:
            INDEX.write_text(original + probe_block, encoding="utf-8")
            r = subprocess.run(
                [sys.executable, str(GENERATOR)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=180,
            )
            self.assertEqual(
                r.returncode, 0,
                f"regen mode must not fail on stale hand refs: {r.stdout}\n{r.stderr}",
            )
            self.assertIn("STALE HAND SECTION", r.stderr)
            # regen preserved the stale hand block verbatim (by design)
            self.assertIn("hand:Stale Probe 2", INDEX.read_text(encoding="utf-8"))
        finally:
            INDEX.write_text(original, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
