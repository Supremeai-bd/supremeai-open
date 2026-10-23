#!/usr/bin/env python3
"""
Unit tests for scripts/ci/pr_patch_recorder.py.
Offline, deterministic, stdlib-only.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.ci.pr_patch_recorder import (
    detect_domains,
    format_patch_content,
    sanitize_filename,
    self_test,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestPRPatchRecorder(unittest.TestCase):
    def test_sanitize_filename(self):
        slug = sanitize_filename("fix(studio): repair auth routes & guest chat! (Refs #749)")
        self.assertIn("fix_studio_repair_auth_routes", slug)
        self.assertNotIn(" ", slug)
        self.assertNotIn("!", slug)

    def test_detect_domains(self):
        files = ["studio/src/App.tsx", "studio/package.json"]
        self.assertEqual(detect_domains(files), ["studio"])

        multi = ["studio/src/App.tsx", "gateway/src/index.ts"]
        self.assertEqual(detect_domains(multi), ["api", "studio"])

        core_files = ["core/src/index.ts"]
        self.assertEqual(detect_domains(core_files), ["core"])

        root_files = ["README.md", "AGENTS.md"]
        self.assertEqual(detect_domains(root_files), ["root"])

    def test_format_patch_and_sanity_warnings(self):
        # Single domain, compliant diff
        meta_ok = {
            "number": 100,
            "title": "feat(studio): add new button (Refs #100)",
            "author": {"login": "antigravity"},
            "headRefName": "feat/studio-button",
            "baseRefName": "main",
            "state": "OPEN",
            "url": "https://github.com/Supremeai-bd/supremeai-open/pull/100",
            "files": [{"path": "studio/src/Button.tsx", "additions": 10, "deletions": 0}],
        }
        content, warnings = format_patch_content(meta_ok, "diff --git a/test b/test\n+content\n")
        self.assertIn("# SupremeAI PR Patch: #100", content)
        self.assertIn("# Target Domain(s): studio", content)
        self.assertEqual(len(warnings), 0)

        # Multi-domain violation & missing issue ref
        meta_bad = {
            "number": 101,
            "title": "feat: touch multiple targets without issue",
            "author": {"login": "antigravity"},
            "headRefName": "feat/wide",
            "baseRefName": "main",
            "state": "OPEN",
            "url": "https://github.com/Supremeai-bd/supremeai-open/pull/101",
            "files": [
                {"path": "studio/src/Button.tsx", "additions": 5, "deletions": 1},
                {"path": "gateway/src/index.ts", "additions": 5, "deletions": 1},
            ],
        }
        content_bad, warnings_bad = format_patch_content(meta_bad, "diff --git a/test b/test\n+content\n")
        self.assertTrue(any("Multi-domain violation" in w for w in warnings_bad))
        self.assertTrue(any("Missing issue reference" in w for w in warnings_bad))

    def test_self_test_contract(self):
        self.assertTrue(self_test())


if __name__ == "__main__":
    unittest.main()
