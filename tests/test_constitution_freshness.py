#!/usr/bin/env python3
"""Offline contract tests for the Constitution Freshness Invariant (#567).

Covers the agent-loop slice of the 3-tier enforcement:

  * Tier 1 — `scripts/agents/continuous_agent_loop.py` step_2_rules():
    - RULE_FRESHNESS_FILES SSOT (AGENTS.md,
      .github/PULL_REQUEST_TEMPLATE.md — AGENT_RULES.md was deleted by #1526);
    - pure divergence classifier `diff_rule_freshness()`;
    - fail-closed matrix: git missing (rc 127), fetch failure (network down),
      unverifiable worktree blob, missing-local-with-self-heal-failure;
    - honest-skip semantics (#1539): a file deleted/renamed UPSTREAM is
      skipped for the run with an honest notice — never a permanent fail,
      never auto-synced via checkout (the AGENT_RULES.md self-defeat class);
    - auto-sync: divergence triggers 'git checkout origin/main -- <files>',
      checkout failure fail-closes, all-fresh runs NO checkout;
    - report-only mode (--verify-only boot smoke): drift is reported, the
      result stays True, and the tree is NEVER mutated (governance PRs
      intentionally carry constitution changes);
    - offline escape hatch: --offline flag / SUPREMEAI_OFFLINE=1 short-circuits
      the network gate (every git call would fail — the gate still passes);
    - mandatory invariant checklist SSOT (reflection evidence, P7 sizing,
      claim gate, boundary guard, stale-base guard);
    - #67 parity marker: CONTRACT_VERSION string and its print format are
      byte-stable (the final stdout line of --verify-only, emitted exactly
      once from run_verify() since #1551).

Pure stdlib, fully offline (git interactions are simulated via scripted
run_cmd doubles and a hermetic REPO_ROOT tempdir — no network, no repo
mutation). Dual-mode: unittest and pytest.
Run: python3 -m unittest tests.test_constitution_freshness -v
"""

from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal


def _blob_sha(tag: str) -> str:
    """Deterministic 40-hex fixture from a short tag (stable across runs)."""
    base = format(sum(ord(c) for c in tag) % 16, "x")
    return base * 40


def _install_hermetic_repo(files: dict[str, str]) -> tempfile.TemporaryDirectory:
    """Create a temp REPO_ROOT pre-seeded with the given constitution files."""
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return tmp


class _GateHarness(unittest.TestCase):
    """Shared harness: hermetic REPO_ROOT + scripted run_cmd + silent log."""

    def setUp(self) -> None:
        self._original_repo_root = cal.REPO_ROOT
        self._original_run_cmd = cal.run_cmd
        self._original_log = cal.log
        self._original_env = {k: os.environ.pop(k, None) for k in cal.OFFLINE_ENV_VARS}
        cal.log = lambda *a, **k: None  # silence gate chatter
        self.seen: list[str] = []
        self._tmp = None

    def tearDown(self) -> None:
        cal.REPO_ROOT = self._original_repo_root
        cal.run_cmd = self._original_run_cmd
        cal.log = self._original_log
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    # -- helpers ----------------------------------------------------------
    def seed_repo(self, files: dict[str, str] | None = None) -> None:
        payload = {
            "AGENTS.md": "# agents\n",
            "AGENT_RULES.md": "# rules\n",
            ".github/PULL_REQUEST_TEMPLATE.md": "# template\n",
        }
        if files:
            payload.update(files)
        self._tmp = _install_hermetic_repo(payload)
        cal.REPO_ROOT = Path(self._tmp.name)

    def script(self, script):
        """Install a scripted run_cmd double keyed by command prefix."""

        def fake_run(cmd, cwd=None, check=False):
            text = " ".join(cmd)
            self.seen.append(text)
            for prefix, outcome in script:
                if text.startswith(prefix):
                    return outcome
            return (0, "", "")

        cal.run_cmd = fake_run


class FreshnessSurfaceSSOT(unittest.TestCase):
    """The invariant's declared surface must stay exactly the constitution."""

    def test_01_freshness_file_surface_is_verbatim(self):
        # SSOT sync (#1526 follow-up): AGENT_RULES.md was deleted by #1526 —
        # the freshness surface is now the Single Door double (AGENTS.md +
        # PR template). The old triple expectation kept the suite red.
        self.assertEqual(
            cal.RULE_FRESHNESS_FILES,
            ("AGENTS.md", ".github/PULL_REQUEST_TEMPLATE.md"),
        )

    def test_02_checklist_covers_all_fail_closed_guards(self):
        checklist = cal.mandatory_invariant_checklist()
        ids = [entry["id"] for entry in checklist]
        self.assertEqual(len(ids), len(set(ids)), "checklist ids must be unique")
        for required in (
            "zero-admin-budget",
            "claim-gate",
            "reflection-evidence",
            "p7-cohesive-sizing",
            "boundary-guard",
            "stale-base-guard",
        ):
            self.assertIn(required, ids)

    def test_03_checklist_names_the_pr_template_fields(self):
        reflection = next(
            e
            for e in cal.mandatory_invariant_checklist()
            if e["id"] == "reflection-evidence"
        )
        self.assertIn("**why:**", reflection["rule"])
        self.assertIn("**alternatives_rejected:**", reflection["rule"])
        self.assertIn("Reflection Evidence", reflection["rule"])

    def test_04_p7_entry_states_the_ingestion_ceiling(self):
        p7 = next(
            e
            for e in cal.mandatory_invariant_checklist()
            if e["id"] == "p7-cohesive-sizing"
        )
        self.assertIn("30 files", p7["rule"])
        self.assertIn("200 KB", p7["rule"])


class DiffRuleFreshness(unittest.TestCase):
    """Pure classifier — no git, no filesystem."""

    def test_05_identical_shas_are_fresh(self):
        shas = {p: _blob_sha(p) for p in cal.RULE_FRESHNESS_FILES}
        self.assertEqual(cal.diff_rule_freshness(shas, dict(shas)), [])

    def test_06_content_drift_is_divergence(self):
        local = {p: _blob_sha(p) for p in cal.RULE_FRESHNESS_FILES}
        remote = dict(local)
        remote["AGENT_RULES.md"] = _blob_sha("drifted")
        self.assertEqual(cal.diff_rule_freshness(local, remote), ["AGENT_RULES.md"])

    def test_07_remote_absent_is_divergence_not_crash(self):
        local = {p: _blob_sha(p) for p in cal.RULE_FRESHNESS_FILES}
        remote = {p: None for p in cal.RULE_FRESHNESS_FILES}
        self.assertEqual(
            cal.diff_rule_freshness(local, remote), list(cal.RULE_FRESHNESS_FILES)
        )

    def test_08_absent_both_sides_is_fresh(self):
        shas = {p: None for p in cal.RULE_FRESHNESS_FILES}
        self.assertEqual(cal.diff_rule_freshness(shas, dict(shas)), [])

    def test_09_partial_dictionary_inputs_do_not_crash(self):
        self.assertEqual(cal.diff_rule_freshness({}, {}), [])
        self.assertEqual(
            cal.diff_rule_freshness({"AGENTS.md": "a" * 40}, {"AGENTS.md": None}),
            ["AGENTS.md"],
        )


class OfflineEscapeHatch(_GateHarness):
    """--offline / SUPREMEAI_OFFLINE=1 = explicit stale-context risk."""

    def test_10_flag_short_circuits_every_git_call(self):
        self.seed_repo()
        # Every git command fails — proves the offline path never touches git.
        self.script([("git", (127, "", "Binary not found"))])
        self.assertTrue(cal.step_2_rules(offline=True))

    def test_11_env_var_truthy_values_enable_offline(self):
        self.seed_repo()
        self.script([("git", (127, "", "network down"))])
        for value in ("1", "true", "yes", "TRUE", "Yes"):
            os.environ["SUPREMEAI_OFFLINE"] = value
            self.assertTrue(cal._offline_requested(False), msg=value)
            self.assertTrue(cal.step_2_rules(), msg=value)

    def test_12_no_flag_no_env_means_online(self):
        for key in cal.OFFLINE_ENV_VARS:
            os.environ.pop(key, None)
        self.assertFalse(cal._offline_requested(False))
        self.assertTrue(cal._offline_requested(True))

    def test_13_missing_local_constitution_fails_even_offline(self):
        self.seed_repo()
        (cal.REPO_ROOT / ".github/PULL_REQUEST_TEMPLATE.md").unlink()
        self.script([("git", (127, "", "unused — must not be reached"))])
        self.assertFalse(cal.step_2_rules(offline=True))


class Step2FailClosed(_GateHarness):
    """Non-offline gate fails closed on every unverifiable origin state."""

    def test_14_git_binary_missing_fails_closed(self):
        self.seed_repo()
        self.script([("git fetch", (127, "", "Binary not found: 'git'"))])
        self.assertFalse(cal.step_2_rules())

    def test_15_fetch_network_failure_fails_closed(self):
        self.seed_repo()
        self.script([("git fetch", (128, "", "Could not resolve host"))])
        self.assertFalse(cal.step_2_rules())

    def test_16_unverifiable_worktree_blob_fails_closed(self):
        self.seed_repo()
        self.script(
            [
                ("git fetch", (0, "", "")),
                ("git hash-object", (128, "", "fatal: unable to hash")),
            ]
        )
        self.assertFalse(cal.step_2_rules())

    def test_17_origin_constitution_deletion_is_honest_skip(self):
        # #1539 landed semantics (synced 2026-10-28): a file deleted/renamed
        # UPSTREAM must not fail-closed the gate forever — preconditioning the
        # gate on the repo's own deleted file is the loop's self-defeat class
        # (AGENT_RULES.md #1526 froze the loop exactly this way). The run now
        # honestly skips that file and still passes; deletion is never
        # auto-synced via checkout.
        self.seed_repo()
        captured: list[str] = []
        cal.log = lambda icon, msg, **k: captured.append(f"{icon} {msg}")
        shas = {p: _blob_sha(p) for p in cal.RULE_FRESHNESS_FILES}
        script: list[tuple[str, tuple[int, str, str]]] = [("git fetch", (0, "", ""))]
        for path in cal.RULE_FRESHNESS_FILES:
            script.append(("git hash-object -- " + path, (0, shas[path] + "\n", "")))
            # origin/main dropped .github/PULL_REQUEST_TEMPLATE.md — rev-parse fails.
            if path == ".github/PULL_REQUEST_TEMPLATE.md":
                script.append(
                    ("git rev-parse --verify --quiet origin/main:" + path, (1, "", ""))
                )
            else:
                script.append(
                    (
                        "git rev-parse --verify --quiet origin/main:" + path,
                        (0, shas[path] + "\n", ""),
                    )
                )
        self.script(script)
        self.assertTrue(
            cal.step_2_rules(),
            "upstream deletion is an honest skip, not a permanent fail",
        )
        self.assertTrue(
            any("deleted upstream" in m for m in captured),
            "the skip must be announced honestly (log notice)",
        )
        self.assertFalse(
            any("git checkout" in t for t in self.seen),
            "deletion must never be auto-synced via checkout",
        )


class Step2AutoSync(_GateHarness):
    """Divergence triggers the issue-prescribed automatic checkout."""

    def _shas_script(self, diverged: set[str]) -> None:
        script: list[tuple[str, tuple[int, str, str]]] = [("git fetch", (0, "", ""))]
        for path in cal.RULE_FRESHNESS_FILES:
            local = _blob_sha("local-" + path)
            remote = _blob_sha("drift-" + path) if path in diverged else local
            script.append(("git hash-object -- " + path, (0, local + "\n", "")))
            script.append(
                (
                    "git rev-parse --verify --quiet origin/main:" + path,
                    (0, remote + "\n", ""),
                )
            )
        script.append(("git checkout", (0, "", "")))
        self.script(script)

    def test_18_divergence_auto_checkouts_only_diverged_files(self):
        self.seed_repo()
        self._shas_script({".github/PULL_REQUEST_TEMPLATE.md"})
        self.assertTrue(cal.step_2_rules())
        checkouts = [t for t in self.seen if t.startswith("git checkout")]
        self.assertEqual(len(checkouts), 1)
        self.assertEqual(checkouts[0], "git checkout origin/main -- .github/PULL_REQUEST_TEMPLATE.md")

    def test_19_failed_auto_checkout_fails_closed(self):
        self.seed_repo()
        self._shas_script({"AGENTS.md"})
        # Override: the checkout itself fails.
        self.script(
            [
                ("git fetch", (0, "", "")),
                ("git hash-object", (0, "a" * 40 + "\n", "")),
                ("git rev-parse", (0, "b" * 40 + "\n", "")),
                ("git checkout", (1, "", "error: pathspec did not match")),
            ]
        )
        self.assertFalse(cal.step_2_rules())

    def test_20_all_fresh_runs_no_checkout(self):
        self.seed_repo()
        shas = {p: _blob_sha(p) for p in cal.RULE_FRESHNESS_FILES}
        script: list[tuple[str, tuple[int, str, str]]] = [("git fetch", (0, "", ""))]
        for path in cal.RULE_FRESHNESS_FILES:
            script.append(("git hash-object -- " + path, (0, shas[path] + "\n", "")))
            script.append(
                (
                    "git rev-parse --verify --quiet origin/main:" + path,
                    (0, shas[path] + "\n", ""),
                )
            )
        self.script(script)
        self.assertTrue(cal.step_2_rules())
        self.assertFalse(
            any("git checkout" in t for t in self.seen),
            "fresh constitution must not be touched",
        )


class VerifyOnlyReportOnlyMode(_GateHarness):
    """Boot smoke proves the machinery without mutating governance PRs."""

    def test_21_drift_is_reported_not_reverted_and_result_stays_true(self):
        self.seed_repo()
        self._shas_script_all_diverged()
        self.assertTrue(cal.step_2_rules(auto_sync=False))
        self.assertFalse(
            any("git checkout" in t for t in self.seen),
            "report-only mode must never mutate the tree",
        )

    def _shas_script_all_diverged(self) -> None:
        script: list[tuple[str, tuple[int, str, str]]] = [("git fetch", (0, "", ""))]
        for path in cal.RULE_FRESHNESS_FILES:
            script.append(
                ("git hash-object -- " + path, (0, _blob_sha("local") + "\n", ""))
            )
            script.append(
                (
                    "git rev-parse --verify --quiet origin/main:" + path,
                    (0, _blob_sha("remote") + "\n", ""),
                )
            )
        self.script(script)

    def test_22_infra_failure_still_fails_closed_in_report_mode(self):
        self.seed_repo()
        self.script([("git fetch", (128, "", "network down"))])
        self.assertFalse(cal.step_2_rules(auto_sync=False))

    def test_23_parity_marker_contract_is_byte_stable(self):
        # #67: the FINAL stdout line of --verify-only is a cross-repo parity
        # grep target — the format string and version must not drift silently.
        # #1551 moved the single emission into run_verify() (main()'s duplicate
        # print removed); the pin follows the emission, exactly once.
        self.assertEqual(cal.CONTRACT_VERSION, "agent-loop-contract/1")
        self.assertIn(
            "CONTRACT_VERSION={CONTRACT_VERSION}",
            inspect.getsource(cal.run_verify),
        )
        self.assertNotIn(
            "CONTRACT_VERSION={CONTRACT_VERSION}",
            inspect.getsource(cal.main),
            "marker must be emitted exactly once (run_verify owns the final line)",
        )


class TaskCycleWiring(unittest.TestCase):
    """The dispatch path must route the offline escape hatch honestly.

    run_cycle() was removed as dead code (#1551: its only job was calling
    step_2_rules, and no dispatch path ever invoked it). The #1560 wheel
    refactor moved the board query verbatim from main() into
    run_dispatch_cycle() — the offline routing pin follows that home.
    """

    def test_24_dispatch_cycle_honors_offline_escape_hatch(self):
        source = inspect.getsource(cal.run_dispatch_cycle)
        self.assertIn('getattr(args, "offline", False)', source)
        self.assertIn("_offline_requested(", source)

    def test_25_argparser_exposes_offline_escape_hatch(self):
        source = inspect.getsource(cal.main)
        self.assertIn('"--offline"', source)
        self.assertIn("SUPREMEAI_OFFLINE", inspect.getsource(cal))


class VerifyOnlyExitContract(unittest.TestCase):
    """#1551 landed contract: --verify-only is fail-closed, marker exactly once.

    Behavioral guard (real subprocess, fully offline) — this contract was
    silently lost twice before (#1541 -> #1544 rebase) and re-landed by
    #1551; the pin makes the next silent loss loud.
    """

    def test_26_verify_only_passes_with_single_final_marker(self):
        env = dict(os.environ)
        env["SUPREMEAI_OFFLINE"] = "1"
        proc = subprocess.run(
            [
                sys.executable,
                str(_ROOT / "scripts" / "agents" / "continuous_agent_loop.py"),
                "--verify-only",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
        lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
        self.assertTrue(lines, "--verify-only must emit tier evidence")
        self.assertEqual(
            lines[-1],
            f"CONTRACT_VERSION={cal.CONTRACT_VERSION}",
            "marker must be the final stdout line (SPEC §4b)",
        )
        self.assertEqual(
            sum(1 for ln in lines if ln.startswith("CONTRACT_VERSION=")),
            1,
            "marker must print exactly once",
        )

    def test_27_verify_only_boot_smoke_wiring_pin(self):
        # বাংলা: #567 Tier-1 গেটের শেষ কলার #1551-এ dead-cluster removal-এ হারিয়ে
        # গিয়েছিল — গেট নির্মিত ও ২৬-টেস্ট যাচাইকৃত হয়েও কেউই ডাকত না (ড্রিফটেড
        # AGENTS.md-সহ --verify-only নিঁখোচ পাস করত, live main-এ প্রমাণিত)।
        # VerifyOnlyExitContract-এর নিজের ভয় ("silently lost twice before") এখানেও
        # প্রযোজ্য — এই সোর্স-পিন পরের নীরব হারিয়ে-যাওয়া জোরে চিৎকার করায়।
        # চুক্তি: report-only (auto_sync=False — গাছ কখনো মিউটেট হয় না) এবং
        # _offline_requested-রুটেড (offline escape hatch সৎ)।
        source = inspect.getsource(cal.main)
        self.assertIn("step_2_rules(", source)
        self.assertIn("auto_sync=False", source)
        self.assertIn("_offline_requested(", source)
        # dispatch-পথ অস্পৃষ্ট থাকবে (owner-level সিদ্ধান্ত, #1551) — AST-স্তরের
        # পিন (কমেন্ট-ইমিউন; run_dispatch_cycle-এর বাংলা কমেন্টে step_2_rules-এর
        # উল্লেখ থাকলেও কোনো কল নেই — string-grep সেখানে মিথ্যা পজিটিভ দেয়)।
        calls = {
            node.func.id
            for node in ast.walk(ast.parse(inspect.getsource(cal.run_dispatch_cycle)))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertNotIn("step_2_rules", calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
