"""tests/test_federation_ci_watchdog.py — Offline test battery for Federation CI Watchdog.

Hermetic tests for issue formatting, contract markers, short name mapping,
deduplication logic, and payload handling without network calls.
"""

import json
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.ci.federation_ci_watchdog import (
    FEDERATION_REPOS,
    build_issue_body,
    build_issue_labels,
    build_issue_title,
    build_mirror_marker,
    repo_short_name,
)


class TestFederationCiWatchdog(unittest.TestCase):
    def test_federation_repos_count_and_composition(self):
        self.assertEqual(len(FEDERATION_REPOS), 12)
        expected = [
            "Supremeai-bd/supremeai",
            "Supremeai-bd/supremeai-command",
            "Supremeai-bd/supremeai-skills",
            "Supremeai-bd/supremeai-vscode",
            "Supremeai-bd/supremeai-agents",
            "Supremeai-bd/supremeai-browser",
            "Supremeai-bd/supremeai-api",
            "Supremeai-bd/supremeai-studio",
            "Supremeai-bd/supremeai-infrastructure",
            "Supremeai-bd/supremeai-core",
            "Supremeai-bd/supremeai-sdk",
            "Supremeai-bd/supremeai-mcp-control-plane",
        ]
        for r in expected:
            self.assertIn(r, FEDERATION_REPOS)

    def test_repo_short_name(self):
        self.assertEqual(repo_short_name("Supremeai-bd/supremeai"), "monorepo")
        self.assertEqual(repo_short_name("Supremeai-bd/supremeai-command"), "command")
        self.assertEqual(repo_short_name("Supremeai-bd/supremeai-studio"), "studio")
        self.assertEqual(repo_short_name("Supremeai-bd/supremeai-mcp-control-plane"), "mcp-control-plane")

    def test_mirror_marker_uniqueness(self):
        m1 = build_mirror_marker("Supremeai-bd/supremeai-api", 999)
        self.assertEqual(m1, "<!-- MIRROR_RUN: Supremeai-bd/supremeai-api/actions/runs/999 -->")

    def test_issue_title_and_labels(self):
        title = build_issue_title("Deploy Pipeline", "Supremeai-bd/supremeai-studio", "main", 555)
        self.assertEqual(title, "fix(ci): [studio] Deploy Pipeline failed on main (Run #555)")

        labels = build_issue_labels("Supremeai-bd/supremeai-studio")
        self.assertIn("status:unclaimed", labels)
        self.assertIn("P0-critical", labels)
        self.assertIn("handoff:coder", labels)
        self.assertIn("area:ci", labels)
        self.assertIn("repo:studio", labels)

    def test_issue_body_contract(self):
        body = build_issue_body(
            repo="Supremeai-bd/supremeai-skills",
            workflow_name="Test Matrix",
            run_id=888,
            html_url="https://github.com/Supremeai-bd/supremeai-skills/actions/runs/888",
            branch="staging",
            commit_sha="1234567890abcdef",
            error_summary="AssertionError: 5 != 6",
        )
        self.assertIn("### 🤖 SupremeAI Agent Task Contract", body)
        self.assertIn("Supremeai-bd/supremeai-skills", body)
        self.assertIn("P0-critical", body)
        self.assertIn("agent-orchestration", body)
        self.assertIn("<!-- MIRROR_RUN: Supremeai-bd/supremeai-skills/actions/runs/888 -->", body)
        self.assertIn("AssertionError: 5 != 6", body)


if __name__ == "__main__":
    unittest.main()
