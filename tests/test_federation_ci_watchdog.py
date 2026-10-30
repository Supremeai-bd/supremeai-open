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
    classify_failure_lane,
    find_loose_mirrors,
    find_mirror_in_items,
    is_fresh_run,
    pr_number_from_merge_ref,
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
        # PR-lane branch ("staging" is not the tracked branch): the incident
        # must file as PR-lane P2-medium — claiming P0-critical Production for
        # a non-main red run is the #1764 misclassification class.
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
        self.assertIn("P2-medium (PR-lane CI failure", body)
        self.assertNotIn("P0-critical", body)
        self.assertIn("Lane Classification (PR-lane)", body)
        self.assertIn("agent-orchestration", body)
        self.assertIn(
            "<!-- MIRROR_RUN: Supremeai-bd/supremeai-skills/actions/runs/888 -->", body
        )
        self.assertIn("AssertionError: 5 != 6", body)
        # #2512: protected-path routing note ships on every lane — workflow-
        # internal root causes are admin-only regardless of lane scope.
        self.assertIn("Protected-Path Routing Note (#2512)", body)
        self.assertIn("admin-only", body)


class TestLaneClassification(unittest.TestCase):
    """#1764: priority must describe the failure's lane scope.

    Live incident class (2026-10-28): PR merge-ref runs (`1763/merge` etc.)
    failing the U4 Anti-Duplicate PR Guard were mirrored as "P0-critical
    (Production CI failure / blocker)" while `main` was green — the loop's
    P0 Drainage Invariant then held routine work for noise, and solvers were
    dispatched onto PR lanes they cannot push to.
    """

    def test_production_lane_is_main_only(self):
        self.assertEqual(classify_failure_lane("main"), "production")
        self.assertEqual(classify_failure_lane("  main "), "production")

    def test_pr_lanes_never_classify_production(self):
        self.assertEqual(classify_failure_lane("1763/merge"), "pr-lane")
        self.assertEqual(classify_failure_lane("1787/merge"), "pr-lane")
        self.assertEqual(classify_failure_lane("feature/some-work"), "pr-lane")
        self.assertEqual(classify_failure_lane("bridge/bridge-20261028-x"), "pr-lane")

    def test_unknown_branch_fails_safe_to_pr_lane(self):
        # Fail-safe direction: never cry wolf — an unknown/empty branch is
        # NOT promoted to production.
        self.assertEqual(classify_failure_lane(""), "pr-lane")
        self.assertEqual(classify_failure_lane("   "), "pr-lane")
        self.assertEqual(classify_failure_lane(None), "pr-lane")

    def test_pr_number_from_merge_ref(self):
        self.assertEqual(pr_number_from_merge_ref("1763/merge"), 1763)
        self.assertIsNone(pr_number_from_merge_ref("feature/x"))
        self.assertIsNone(pr_number_from_merge_ref("main"))
        self.assertIsNone(pr_number_from_merge_ref(""))
        self.assertIsNone(pr_number_from_merge_ref("1763/MERGE"))  # exact ref only
        self.assertIsNone(pr_number_from_merge_ref("1763/merges"))

    def test_production_labels_keep_legacy_p0_contract(self):
        # Default branch param preserves the pre-#1764 behavior for main.
        labels = build_issue_labels("Supremeai-bd/supremeai-studio")
        self.assertIn("P0-critical", labels)
        self.assertNotIn("P2-medium", labels)
        self.assertIn("status:runway", labels)

    def test_pr_lane_labels_file_honestly_as_p2(self):
        labels = build_issue_labels(
            "Supremeai-bd/supremeai-open", branch="1763/merge"
        )
        self.assertIn("P2-medium", labels)
        self.assertNotIn("P0-critical", labels)
        # ci-fixer triage routing (S09 label-bridge) must survive the lane fix.
        self.assertIn("status:runway", labels)
        self.assertIn("status:unclaimed", labels)
        self.assertIn("area:ci", labels)
        self.assertIn("repo:open", labels)

    def test_production_body_has_no_lane_note(self):
        body = build_issue_body(
            repo="Supremeai-bd/supremeai-command",
            workflow_name="CI Pipeline",
            run_id=1,
            html_url="u",
            branch="main",
            commit_sha="a",
        )
        self.assertIn("P0-critical (Production CI failure / blocker)", body)
        self.assertNotIn("Lane Classification (PR-lane)", body)
        # #2512: production-lane incidents carry the admin-only routing note —
        # the exact lane where the #2511 claim+TTL burn happened.
        self.assertIn("Protected-Path Routing Note (#2512)", body)
        self.assertIn("structurally blocked patch", body)

    def test_pr_lane_body_names_pr_and_disclaims_production(self):
        body = build_issue_body(
            repo="Supremeai-bd/supremeai-open",
            workflow_name="CI — Open Unified Pipeline",
            run_id=40595046266,
            html_url="u",
            branch="1763/merge",
            commit_sha="554e5015734f",
        )
        self.assertIn("P2-medium (PR-lane CI failure", body)
        self.assertNotIn("P0-critical", body)
        self.assertIn("PR #1763", body)
        self.assertIn("not a tracked-branch production blocker", body)
        # Honesty boundary: lane scope, no fabricated claim about main.
        self.assertIn("makes no claim about `main` status", body)

    def test_feature_branch_body_uses_branch_subject(self):
        body = build_issue_body(
            repo="Supremeai-bd/supremeai-api",
            workflow_name="Test Matrix",
            run_id=2,
            html_url="u",
            branch="feature/some-work",
            commit_sha="b",
        )
        self.assertIn("P2-medium (PR-lane CI failure", body)
        self.assertIn("branch `feature/some-work`", body)

    def test_mirror_failure_passes_branch_to_labels(self):
        # Wiring pin: mirror_failure must thread the run's branch into the
        # label builder, or every event-driven mirror regresses to P0.
        import inspect

        import scripts.ci.federation_ci_watchdog as wd

        source = inspect.getsource(wd.mirror_failure)
        self.assertIn("build_issue_labels(repo, branch=branch)", source)

    def test_pr_lane_failure_handled_inplace(self):
        from unittest.mock import patch
        import scripts.ci.federation_ci_watchdog as wd

        with patch("scripts.ci.federation_ci_watchdog.label_pr_lane_failure", return_value=True) as mock_label:
            result = wd.mirror_failure(
                repo="Supremeai-bd/supremeai-open",
                workflow_name="CI — Open Unified Pipeline",
                run_id=999999,
                html_url="https://github.com/runs/999999",
                branch="3921/merge",
            )
            self.assertTrue(result)
            mock_label.assert_called_once_with(
                "Supremeai-bd/supremeai-open", 3921, 999999, "https://github.com/runs/999999", token=None
            )


if __name__ == "__main__":
    unittest.main()
