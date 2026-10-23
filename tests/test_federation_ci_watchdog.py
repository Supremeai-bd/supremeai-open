"""tests/test_federation_ci_watchdog.py — Offline test battery for Federation CI Watchdog.

Hermetic tests for issue formatting, contract markers, short name mapping,
deduplication logic, and payload handling without network calls.
"""

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
    find_loose_mirrors,
    find_mirror_in_items,
    is_fresh_run,
    relink_loose_mirrors,
    repo_short_name,
)


class TestLooseMirrorRelink(unittest.TestCase):
    """8-anchor SSOT backfill: mirrored incidents must never drift loose.

    Live incident class: #910-#918 were mirrored as root issues because
    link_sub_issue's REST fallback POSTed to /sub-issues (404) instead of
    /sub_issues, and the failure was swallowed. These tests pin the repair.
    """

    def _board(self) -> list[dict]:
        marker = build_mirror_marker("Supremeai-bd/supremeai-api", 424242)
        return [
            {"number": 910, "id": 7770001, "body": f"incident body\n{marker}"},
            {"number": 911, "id": 7770002, "body": "regular non-mirror issue"},
            {
                "number": 912,
                "id": 7770003,
                "pull_request": {"url": "x"},
                "body": marker,
            },
            {"number": 913, "id": 7770004, "body": None},
            {
                "number": 914,
                "id": 7770005,
                "body": build_mirror_marker(
                    "Supremeai-bd/supremeai-studio", 424243
                ),
            },
        ]

    def test_find_loose_mirrors_detects_only_loose_issue_mirrors(self):
        loose = find_loose_mirrors(self._board(), set())
        self.assertEqual(loose, [910, 914])

    def test_find_loose_mirrors_excludes_already_linked_by_db_id(self):
        # db ids are opaque GitHub database ids compared item-id to linked-id.
        loose = find_loose_mirrors(self._board(), {7770001})
        self.assertEqual(loose, [914])

    def test_find_loose_mirrors_handles_none_and_empty(self):
        self.assertEqual(find_loose_mirrors(None, None), [])
        self.assertEqual(find_loose_mirrors([], set()), [])

    def test_find_loose_mirrors_never_counts_prs(self):
        items = [
            {
                "number": 999,
                "pull_request": {"url": "x"},
                "body": build_mirror_marker("Supremeai-bd/supremeai-core", 1),
            }
        ]
        self.assertEqual(find_loose_mirrors(items, set()), [])

    def test_relink_helpers_available(self):
        # The relink pass depends on the anchors helpers; if the import
        # chain breaks, relink must degrade to an explicit failure, not a
        # silent zero-action success.
        import scripts.ci.federation_ci_watchdog as wd

        if wd.link_sub_issue is None:  # pragma: no cover - degraded env only
            self.fail("federation_anchors.link_sub_issue import chain broken")

    def test_sub_issue_endpoint_is_snake_case(self):
        # Live-verified 2026-10-24: GET .../issues/761/sub_issues -> 200;
        # GET .../issues/761/sub-issues -> 404 Not Found. A regression to
        # the hyphenated path re-opens the loose-incident failure mode.
        import scripts.ci.federation_anchors as anchors

        self.assertEqual(anchors.SUB_ISSUES_PATH, "sub_issues")
        self.assertNotIn("sub-issues", anchors.SUB_ISSUES_PATH)

    def test_relink_returns_failure_tuple_when_helpers_missing(self):
        # Degraded-import contract: (0, 1) so callers exit non-zero.
        import scripts.ci.federation_ci_watchdog as wd

        original = wd.link_sub_issue
        original_list = wd.list_sub_issue_ids
        try:
            wd.link_sub_issue = None
            wd.list_sub_issue_ids = None
            self.assertEqual(relink_loose_mirrors(token=""), (0, 1))
        finally:
            wd.link_sub_issue = original
            wd.list_sub_issue_ids = original_list


class TestFederationCiWatchdog(unittest.TestCase):
    def test_federation_repos_count_and_composition(self):
        self.assertEqual(len(FEDERATION_REPOS), 12)
        expected = [
            "Supremeai-bd/supremeai-open",
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
        self.assertEqual(
            repo_short_name("Supremeai-bd/supremeai-mcp-control-plane"),
            "mcp-control-plane",
        )

    def test_mirror_marker_uniqueness(self):
        m1 = build_mirror_marker("Supremeai-bd/supremeai-api", 999)
        self.assertEqual(
            m1, "<!-- MIRROR_RUN: Supremeai-bd/supremeai-api/actions/runs/999 -->"
        )

    def test_issue_title_and_labels(self):
        title = build_issue_title(
            "Deploy Pipeline", "Supremeai-bd/supremeai-studio", "main", 555
        )
        self.assertEqual(
            title, "fix(ci): [studio] Deploy Pipeline failed on main (Run #555)"
        )

        labels = build_issue_labels("Supremeai-bd/supremeai-studio")
        self.assertIn("status:unclaimed", labels)
        self.assertIn("P0-critical", labels)
        # S09 label-bridge: status:runway is LABEL_PRIORITY[0] -> ci-fixer.
        # Without it the mirrored issue matched no matrix trigger and the
        # loop silently fell through to coder — ci-fixer could never fire.
        self.assertIn("status:runway", labels)
        self.assertIn("handoff:coder", labels)
        self.assertIn("area:ci", labels)
        self.assertIn("repo:studio", labels)

    def test_find_mirror_in_items_excludes_prs_and_finds_real_mirror(self):
        marker = build_mirror_marker("Supremeai-bd/supremeai-api", 999)
        items = [
            # A PR carrying the marker text in its body must be IGNORED —
            # /issues mixes PRs into the list; mirrors live only on issues.
            {"number": 900, "pull_request": {"url": "x"}, "body": f"noise {marker}"},
            {"number": 901, "body": f"contract\n{marker}\nend"},
            {"number": 902, "body": "no marker here"},
            {"number": 903, "body": None},
        ]
        self.assertEqual(
            find_mirror_in_items(items, "Supremeai-bd/supremeai-api", 999), 901
        )
        self.assertIsNone(
            find_mirror_in_items(items, "Supremeai-bd/supremeai-api", 404)
        )
        self.assertIsNone(find_mirror_in_items([], "Supremeai-bd/supremeai-api", 999))
        self.assertIsNone(find_mirror_in_items(None, "Supremeai-bd/supremeai-api", 999))

    def test_is_fresh_run_recency_gate(self):
        from datetime import datetime, timezone

        now = datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)
        # Fresh: inside the 24h window.
        self.assertTrue(is_fresh_run("2026-10-18T11:59:59Z", now, 24))
        self.assertTrue(is_fresh_run("2026-10-17T12:00:00Z", now, 24))  # boundary
        # Stale: week-old dead runs must not resurface as fresh P0 incidents.
        self.assertFalse(is_fresh_run("2026-10-11T12:00:00Z", now, 24))
        # Fail-closed: missing/malformed timestamps are never fresh.
        self.assertFalse(is_fresh_run("", now, 24))
        self.assertFalse(is_fresh_run("garbage", now, 24))
        self.assertFalse(is_fresh_run("2026-10-18T11:00:00Z", now, -1))

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
        self.assertIn(
            "<!-- MIRROR_RUN: Supremeai-bd/supremeai-skills/actions/runs/888 -->", body
        )
        self.assertIn("AssertionError: 5 != 6", body)


if __name__ == "__main__":
    unittest.main()
