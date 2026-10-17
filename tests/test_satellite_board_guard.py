#!/usr/bin/env python3
"""Offline test battery for scripts/ci/satellite_board_guard.py (#626).

Hermetic by construction: every test injects a fake fetcher (or hits the
module's own zero-network --self-test fixtures). No real GitHub call is ever
made from this battery; no credentials are read (the token path is exercised
only as an inert argument).

Covers the three-tier contract:
  Tier 1 (reflection): the audited registry matches the #626 doctrine SSOT.
  Tier 2 (smoke): verdict logic, classification, exit-code mapping, output
          shapes behave per the module contract.
  Tier 3 (tests): this battery itself — 100% offline, sub-second.
"""

from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))

import satellite_board_guard as sbg  # noqa: E402


def fake_fetch(items):
    def _fetch(org, repo, token=None):
        return items

    return _fetch


def fetch_404(org, repo, token=None):
    raise sbg.UnreachableError("HTTP 404 — repository absent or private plane")


def fetch_rate_limited(org, repo, token=None):
    raise sbg.RateLimitError("HTTP 403 — rate limit exhausted")


class RegistryDoctrineTest(unittest.TestCase):
    """Tier 1 — the audited registry IS the #626 doctrine, pinned."""

    EXPECTED = {
        "studio", "api", "vscode", "browser", "core", "command",
        "skills", "agents", "sdk", "archive", "infrastructure", "mcp-control-plane",
    }

    def test_01_registry_matches_issue_626_doctrine(self):
        self.assertEqual(set(sbg.SATELLITES), self.EXPECTED)

    def test_02_registry_has_exactly_twelve_satellites(self):
        self.assertEqual(len(sbg.SATELLITES), 12)

    def test_03_private_monorepo_is_out_of_scope(self):
        self.assertNotIn("supremeai", sbg.SATELLITES)
        self.assertNotIn("supremeai-open", sbg.SATELLITES)


class VerdictLogicTest(unittest.TestCase):
    """Tier 2 — verdict determination per satellite."""

    def test_04_clean_satellite_zero_open_items(self):
        r = sbg.audit_satellite("studio", fetch=fake_fetch([]))
        self.assertEqual(r.verdict, sbg.VERDICT_CLEAN)
        self.assertEqual((r.open_issues, r.open_prs), (0, 0))
        self.assertEqual(r.violating, [])

    def test_05_violation_counts_issues_and_prs_separately(self):
        items = [
            {"number": 1, "title": "stray issue one"},
            {"number": 2, "title": "stray issue two"},
            {"number": 10, "title": "stray pr", "pull_request": {"url": "x"}},
        ]
        r = sbg.audit_satellite("api", fetch=fake_fetch(items))
        self.assertEqual(r.verdict, sbg.VERDICT_VIOLATION)
        self.assertEqual(r.open_issues, 2)
        self.assertEqual(r.open_prs, 1)
        self.assertEqual(len(r.violating), 3)

    def test_06_pr_classification_requires_pull_request_key(self):
        issues, prs, _ = sbg.classify_items(
            [{"number": 7, "title": "plain issue"}]
        )
        self.assertEqual((issues, prs), (1, 0))
        issues, prs, _ = sbg.classify_items(
            [{"number": 8, "title": "pr", "pull_request": {"url": "y"}}]
        )
        self.assertEqual((issues, prs), (0, 1))

    def test_07_violation_details_carry_number_and_title(self):
        r = sbg.audit_satellite(
            "sdk", fetch=fake_fetch([{"number": 42, "title": "orphaned epic"}])
        )
        self.assertTrue(any("#42" in d and "orphaned epic" in d for d in r.violating))

    def test_08_malformed_items_are_ignored_not_fatal(self):
        r = sbg.audit_satellite("core", fetch=fake_fetch(["garbage", None, 17]))
        self.assertEqual(r.verdict, sbg.VERDICT_CLEAN)

    def test_09_non_list_payload_treated_as_empty(self):
        r = sbg.audit_satellite("core", fetch=fake_fetch(None))
        self.assertEqual(r.verdict, sbg.VERDICT_CLEAN)


class UnreachablePathsTest(unittest.TestCase):
    """Tier 2 — fail-honest skip-with-warning contract."""

    def test_10_private_or_absent_repo_is_unreachable(self):
        r = sbg.audit_satellite("sdk", fetch=fetch_404)
        self.assertEqual(r.verdict, sbg.VERDICT_UNREACHABLE)
        self.assertIn("404", r.reason)

    def test_11_rate_limit_is_unreachable_never_violation(self):
        r = sbg.audit_satellite("archive", fetch=fetch_rate_limited)
        self.assertEqual(r.verdict, sbg.VERDICT_UNREACHABLE)
        self.assertIn("403", r.reason)


class ExitCodeAndOutputTest(unittest.TestCase):
    """Tier 2 — CI-facing contract (exit codes, JSON, report)."""

    def test_12_exit_code_all_clean_is_zero(self):
        reports = sbg.audit_all(fetch=fake_fetch([]))
        self.assertEqual(sbg.decide_exit_code(reports), 0)

    def test_13_exit_code_any_violation_is_one(self):
        def mixed(org, repo, token=None):
            return [] if repo == "studio" else [
                {"number": 1, "title": "stray", "pull_request": {"url": "x"}}
            ]

        reports = sbg.audit_all(fetch=mixed)
        self.assertEqual(sbg.decide_exit_code(reports), 1)

    def test_14_exit_code_all_unreachable_is_two(self):
        reports = sbg.audit_all(fetch=fetch_404)
        self.assertEqual(sbg.decide_exit_code(reports), 2)
        self.assertEqual(len(reports), 12)

    def test_15_json_output_shape_and_totals(self):
        reports = sbg.audit_all(fetch=fake_fetch([]))
        payload = sbg.build_json(reports, "Supremeai-bd")
        self.assertEqual(payload["org"], "Supremeai-bd")
        self.assertEqual(payload["issue"], 626)
        self.assertEqual(payload["doctrine"], "zero-issue-satellite-mandate")
        self.assertEqual(payload["clean"], 12)
        self.assertEqual(payload["violations"], 0)
        self.assertEqual(payload["unreachable"], 0)
        self.assertEqual(len(payload["satellites"]), 12)

    def test_16_json_serializable(self):
        reports = sbg.audit_all(fetch=fetch_rate_limited)
        payload = sbg.build_json(reports, "Supremeai-bd")
        roundtrip = json.loads(json.dumps(payload))
        self.assertEqual(roundtrip["unreachable"], 12)

    def test_17_report_mode_prints_matrix_and_totals(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            reports = sbg.audit_all(fetch=fake_fetch([]))
            for r in reports:
                print(r.summary())
        out = buf.getvalue()
        self.assertIn("studio", out)
        self.assertIn("CLEAN", out)
        self.assertIn("mcp-control-plane", out)

    def test_18_summary_line_format(self):
        r = sbg.SatelliteReport("api", sbg.VERDICT_CLEAN)
        self.assertIn("api", r.summary())
        self.assertIn("CLEAN", r.summary())


class BuiltinSelfTestAndPolicyTest(unittest.TestCase):
    """Tier 2/3 — built-in offline self-test + credential policy."""

    def test_19_builtin_self_test_passes(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            ok = sbg.self_test()
        self.assertTrue(ok)
        self.assertIn("self-test: 5/5 checks PASS", buf.getvalue())

    def test_20_default_fetch_uses_unauthenticated_plane_when_no_token(self):
        # The default fetcher accepts token=None; the endpoint it hits is the
        # unauthenticated REST combined listing (verified structurally — no
        # network performed, no secret material involved).
        url = sbg._issues_url("Supremeai-bd", "studio")
        self.assertTrue(url.startswith("https://api.github.com/repos/"))
        self.assertIn("/issues?state=open", url)
        self.assertNotIn("token", url)
        # signature tolerates the inert token argument
        import inspect

        params = list(inspect.signature(sbg.default_fetch_open_items).parameters)
        self.assertEqual(params, ["org", "repo", "token"])

    def test_21_env_token_lookup_prefers_gh_then_github(self):
        import os

        original = {k: os.environ.get(k) for k in ("GH_TOKEN", "GITHUB_TOKEN")}
        try:
            for k in original:
                os.environ.pop(k, None)
            self.assertIsNone(sbg._env_token())
            os.environ["GITHUB_TOKEN"] = "b-token"
            self.assertEqual(sbg._env_token(), "b-token")
            os.environ["GH_TOKEN"] = "a-token"
            self.assertEqual(sbg._env_token(), "a-token")
        finally:
            for k, v in original.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main(verbosity=2)
