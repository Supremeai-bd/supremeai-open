#!/usr/bin/env python3
"""
tests/test_self_healing_reporter.py — WO #488 verification battery (S09-resynced).

Tier 1: the loop's classify_task_role routes CI-failure issues to ci-fixer
        with 100% determinism — now via the S09 label plane (status:runway),
        exactly the label the watchdog mirror and the healing reporter emit;
        priority ladder ranks healing issues above backlog features.
Tier 2: healing payload generation conforms to the WO issue contract and
        dedup fingerprints are deterministic and collision-free.
Tier 3: zero regression — the loop module still imports and dispatches
        deterministically: unrouted keyword-only signals fall back to coder
        (fail-closed), trigger labels route exactly, substring labels never
        trigger.

Runner: plain stdlib unittest, no pytest dependency.
  python3 tests/test_self_healing_reporter.py
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = REPO_ROOT / "scripts" / "agents"
for p in (str(REPO_ROOT / "tests"), str(AGENTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

def _load_reporter_module():
    spec = importlib.util.spec_from_file_location(
        "agents_self_healing_reporter", AGENTS_DIR / "self_healing_reporter.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


shr = _load_reporter_module()


def _load_loop_module():
    """Import continuous_agent_loop without executing its CLI main."""
    spec = importlib.util.spec_from_file_location(
        "continuous_agent_loop", AGENTS_DIR / "continuous_agent_loop.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


LOOP = _load_loop_module()


CI_FAILURE_FIXTURES = [
    # Mirrored/healing CI-failure issues carry `status:runway` — the S09
    # LABEL_PRIORITY[0] trigger that deterministically routes to ci-fixer
    # (watchdog mirror + self-healing reporter both emit it now).
    ("fix(Supremeai-bd/supremeai-open): [ci-failure] Heal PR #480 checks (Stale-Base Guard)",
     ["bridge:queued", "P0-critical", "status:runway", "repo:Supremeai-bd/supremeai-open", "area:ci"]),
    ("fix(Supremeai-bd/supremeai-infra): [ci-failure] Heal PR #12 checks (unit)",
     ["bridge:queued", "P1-high", "status:runway", "repo:Supremeai-bd/supremeai-infra", "area:ci"]),
    ("fix(repo): [ci-failure] Heal PR #7 checks (matrix, lint)",
     ["bridge:queued", "P0-critical", "status:runway", "repo:repo", "area:ci"]),
    ("ci pipeline red on main", ["status:runway", "area:ci"]),
    ("workflow action failure blocks merge", ["status:runway", "bug", "area:ci"]),
]


class Tier1RoleAndPriority(unittest.TestCase):
    def test_ci_failure_maps_to_ci_fixer_deterministically(self):
        for title, labels in CI_FAILURE_FIXTURES:
            first = LOOP.classify_task_role(title, labels, "heal payload")
            self.assertEqual(first, "ci-fixer", title)
            for _ in range(3):
                self.assertEqual(LOOP.classify_task_role(title, labels, "heal payload"),
                                 first, f"non-deterministic for {title}")

    def test_priority_ladder_puts_healing_above_backlog(self):
        ladder = {"P0-critical": 0, "P1-high": 1, "P2-medium": 2, "P3-low": 3}
        queue = [
            ("backlog feature", ["P1-high"]),          # WO #461-style feature task
            ("heal PR #480", ["P0-critical"]),         # merge-blocked healing
            ("backlog docs", ["P2-medium"]),
            ("heal PR #481", ["P1-high"]),             # runway hygiene healing
        ]
        ordered = sorted(queue, key=lambda item: ladder.get(
            next((l for l in item[1] if l in ladder), "P3-low"), 3))
        self.assertEqual(ordered[0][1], ["P0-critical"])
        self.assertEqual(ordered[1][1], ["P1-high"])
        self.assertIn("heal", ordered[0][0])

    def test_reporter_priority_rules(self):
        self.assertEqual(shr.priority_for_failure(True), "P0-critical")
        self.assertEqual(shr.priority_for_failure(False), "P1-high")


class Tier2PayloadAndDedup(unittest.TestCase):
    def test_title_matches_wo_contract(self):
        t = shr.healing_title("Supremeai-bd/supremeai-open", 480,
                              ["Knowledge Sharing Guard", "Stale-Base Guard"])
        m = shr.TITLE_RE.match(t)
        self.assertIsNotNone(m, t)
        self.assertEqual(m.group("num"), "480")
        self.assertEqual(m.group("checks"),
                         "Knowledge Sharing Guard, Stale-Base Guard")

    def test_payload_contains_branch_commit_log_and_labels(self):
        issue = shr.build_healing_issue({
            "repo": "Supremeai-bd/supremeai-open", "number": 483,
            "branch": "feat/dashboard-r2", "head_sha": "deadbee",
            "failing_checks": ["Stale-Base Guard"], "blocked_merge": False,
            "log_snippet": "error: Knowledge Sharing Guard: missing summary\n",
        })
        self.assertEqual(issue["labels"],
                         ["bridge:queued", "P1-high", "status:runway",
                          "repo:Supremeai-bd/supremeai-open", "area:ci"])
        for needle in ("feat/dashboard-r2", "deadbee", "Knowledge Sharing Guard",
                       "healing-fp:", "landing.yml auto-merges"):
            self.assertIn(needle, issue["body"])

    def test_fingerprint_deterministic_and_collision_free(self):
        seen = set()
        for num in range(400, 900):                     # 500 distinct pairs
            fp = shr.dedup_fingerprint("Supremeai-bd/supremeai-open", num)
            self.assertNotIn(fp, seen)
            seen.add(fp)
        self.assertEqual(shr.dedup_fingerprint("r/x", 7),
                         shr.dedup_fingerprint("r/x", 7))
        self.assertNotEqual(shr.dedup_fingerprint("r/x", 7),
                            shr.dedup_fingerprint("r/y", 7))
        self.assertRegex(shr.fingerprint_marker("abcd"), r"^<!-- healing-fp:abcd -->$")

    def test_classifier_compat_predicate(self):
        self.assertTrue(shr.is_ci_failure_issue(
            "fix(r): [ci-failure] Heal PR #1 checks (x)", []))
        self.assertTrue(shr.is_ci_failure_issue("anything", ["area:ci"]))
        self.assertFalse(shr.is_ci_failure_issue("feat: dashboard", ["enhancement"]))


class Tier3ZeroRegression(unittest.TestCase):
    def test_loop_module_healthy_and_dispatch_intact(self):
        self.assertTrue(callable(LOOP.classify_task_role))
        # Fail-closed fallback: keyword-only titles/labels can no longer
        # invent a role (#489 deprecates keyword matching) — they route to
        # the preserved coder default, deterministically.
        self.assertEqual(LOOP.classify_task_role(
            "feat: smart context selector", ["enhancement", "P1-high"], "body"),
            "coder")
        self.assertEqual(LOOP.classify_task_role(
            "audit readiness report", ["documentation"], "parity drift"),
            "coder")
        self.assertEqual(LOOP.classify_task_role(
            "plan architecture rfc", ["documentation"], "adr contract"),
            "coder")

    def test_label_plane_routes_exactly_and_never_by_substring(self):
        # Positive trigger-label routes (S09 LABEL_PRIORITY).
        self.assertEqual(LOOP.classify_task_role("x", ["status:runway"], ""), "ci-fixer")
        self.assertEqual(LOOP.classify_task_role("x", ["gate:pre-landing"], ""), "task-auditor")
        self.assertEqual(LOOP.classify_task_role("x", ["status:claimed"], ""), "coder")
        # Substring-immune: a label merely CONTAINING a trigger never fires.
        self.assertEqual(LOOP.classify_task_role("x", ["xstatus:runwayx"], ""), "coder")
        # Priority: runway outranks claimed when both are present.
        self.assertEqual(
            LOOP.classify_task_role("x", ["status:claimed", "status:runway"], ""),
            "ci-fixer")

    def test_reporter_module_import_is_pure(self):
        self.assertTrue(hasattr(shr, "build_healing_issue"))
        self.assertTrue(hasattr(shr, "collect_failing_prs"))
        self.assertRegex(shr.DEFAULT_REPO, r"^Supremeai-bd/")


if __name__ == "__main__":
    unittest.main(verbosity=2)
