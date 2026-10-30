#!/usr/bin/env python3
"""tests/test_federation_anchors.py — Unit tests for Federation Anchor Hubs SSOT Registry."""

import json
import unittest
import unittest.mock

from scripts.ci.federation_anchors import (
    ANCHOR_HUBS,
    BRIDGE_ORDER_ANCHOR,
    CI_FAILURE_ANCHOR,
    get_anchor_issue_number,
    self_test,
)


class TestFederationAnchors(unittest.TestCase):
    def test_anchor_counts(self):
        """Must have valid registry with active and retired subsets."""
        from scripts.ci.federation_anchors import ACTIVE_ANCHOR_HUBS, RETIRED_ANCHOR_HUBS
        self.assertTrue(set(ACTIVE_ANCHOR_HUBS.keys()).issubset(set(ANCHOR_HUBS.keys())))
        self.assertTrue(set(RETIRED_ANCHOR_HUBS.keys()).issubset(set(ANCHOR_HUBS.keys())))
        unique_numbers = set(ANCHOR_HUBS.values())
        self.assertEqual(len(unique_numbers), len(ANCHOR_HUBS))

    def test_sequential_anchor_range(self):
        """Anchor issue numbers must span 749 through 762."""
        expected = set(range(749, 763))
        self.assertEqual(set(ANCHOR_HUBS.values()), expected)

    def test_specialized_hub_constants(self):
        """CI failure hub and Bridge order hub must be mapped to #761 and #760."""
        self.assertEqual(BRIDGE_ORDER_ANCHOR, 760)
        self.assertEqual(CI_FAILURE_ANCHOR, 761)

    def test_domain_satellite_resolution(self):
        """All 12 domain repos must resolve accurately."""
        satellites = [
            ("Supremeai-bd/supremeai-studio", 749),
            ("Supremeai-bd/supremeai-api", 750),
            ("Supremeai-bd/supremeai-core", 751),
            ("Supremeai-bd/supremeai-command", 752),
            ("Supremeai-bd/supremeai-skills", 753),
            ("Supremeai-bd/supremeai-vscode", 754),
            ("Supremeai-bd/supremeai-agents", 755),
            ("Supremeai-bd/supremeai-browser", 756),
            ("Supremeai-bd/supremeai-sdk", 757),
            ("Supremeai-bd/supremeai-infrastructure", 758),
            ("Supremeai-bd/supremeai-mcp-control-plane", 759),
            ("Supremeai-bd/supremeai-open", 762),
        ]
        for repo, expected_num in satellites:
            with self.subTest(repo=repo):
                self.assertEqual(get_anchor_issue_number(repo), expected_num)

    def test_alias_resolution(self):
        """Short aliases must resolve to the identical anchor hub numbers."""
        self.assertEqual(get_anchor_issue_number("studio"), 749)
        self.assertEqual(get_anchor_issue_number("api"), 750)
        self.assertEqual(get_anchor_issue_number("core"), 751)
        self.assertEqual(get_anchor_issue_number("command"), 752)
        self.assertEqual(get_anchor_issue_number("skills"), 753)
        self.assertEqual(get_anchor_issue_number("vscode"), 754)
        self.assertEqual(get_anchor_issue_number("agents"), 755)
        self.assertEqual(get_anchor_issue_number("browser"), 756)
        self.assertEqual(get_anchor_issue_number("sdk"), 757)
        self.assertEqual(get_anchor_issue_number("infra"), 758)
        self.assertEqual(get_anchor_issue_number("infrastructure"), 758)
        self.assertEqual(get_anchor_issue_number("mcp"), 759)
        self.assertEqual(get_anchor_issue_number("bridge"), 760)
        self.assertEqual(get_anchor_issue_number("ci"), 761)
        self.assertEqual(get_anchor_issue_number("open"), 762)

    def test_self_test_passes(self):
        """Hermetic self_test function must return 0."""
        self.assertEqual(self_test(), 0)


class TestVerifyLiveQuotaPreflight(unittest.TestCase):
    """verify-live must fail fast on thin quota, degrade on probe failure, and
    keep its fail-closed semantics — the #3851 false-green family, guarded."""

    @staticmethod
    def _fake_urlopen(responses):
        """Build a urlopen mock consuming a scripted response list in order."""
        calls = {"n": 0}

        def _call(req, timeout=10):
            item = responses[calls["n"]] if calls["n"] < len(responses) else responses[-1]
            calls["n"] += 1
            if isinstance(item, Exception):
                raise item
            resp = unittest.mock.MagicMock()
            resp.__enter__.return_value.read.return_value = json.dumps(item).encode()
            resp.__exit__.return_value = False
            return resp

        _call.calls = calls
        return _call

    ACTIVE_OK = {"state": "open", "title": "[Anchor Hub] ok"}
    RETIRED_OK = {"state": "closed", "title": "[Anchor Hub] consolidated"}

    @classmethod
    def scripted_happy_path(cls, first=None):
        """Responses for one full verify pass, counts DERIVED from the SSOT
        registry (not hardcoded) so topology re-definitions (8-satellite →
        6-domain, #3968) cannot stale-red these tests again."""
        from scripts.ci.federation_anchors import ACTIVE_ANCHOR_HUBS, RETIRED_ANCHOR_HUBS

        seq = list(first) if first else []
        seq += [cls.ACTIVE_OK] * len(ACTIVE_ANCHOR_HUBS)
        seq += [cls.RETIRED_OK] * len(RETIRED_ANCHOR_HUBS)
        return seq

    def run_verify(self, responses):
        import io
        import unittest.mock
        from contextlib import redirect_stdout

        from scripts.ci.federation_anchors import verify_live

        buf = io.StringIO()
        with unittest.mock.patch(
            "scripts.ci.federation_anchors.urllib.request.urlopen",
            self._fake_urlopen(responses),
        ):
            with redirect_stdout(buf):
                code = verify_live(token="test-token")
        return code, buf.getvalue()

    def test_preflight_blocks_when_quota_low(self):
        """remaining=5 < 14 anchors: exit 1 and do NOT fire the 14 issue queries."""
        rate_limit_body = {
            "resources": {"core": {"limit": 60, "remaining": 5, "reset": 1790000000}}
        }
        code, out = self.run_verify([rate_limit_body])
        self.assertEqual(code, 1)
        self.assertIn("remaining=5", out)
        self.assertIn("NOT a clean pass", out)

    def test_preflight_degrades_gracefully(self):
        """Probe failure (None,None) must NOT block a verification with budget."""
        rate_limit_body = {
            "resources": {"core": {"limit": 60, "remaining": 5000, "reset": 1790000000}}
        }
        # /rate_limit raises → degrade; then SSOT-derived happy path.
        code, out = self.run_verify(
            self.scripted_happy_path(first=[ConnectionError("probe down")])
        )
        self.assertEqual(code, 0)
        self.assertIn("All Active Anchor Hubs are OPEN", out)

    def test_403_diagnostic_includes_reset(self):
        """A mid-verification 403 must carry remaining + reset + token advice."""
        import email.message
        import urllib.error

        rate_limit_body = {
            "resources": {"core": {"limit": 60, "remaining": 5000, "reset": 1790000000}}
        }
        hdrs = email.message.Message()
        hdrs["X-RateLimit-Remaining"] = "0"
        hdrs["X-RateLimit-Reset"] = "1790000000"
        err403 = urllib.error.HTTPError(
            "https://api.github.com/repos/x/issues/1", 403, "rate limit exceeded", hdrs, None
        )
        code, out = self.run_verify(
            self.scripted_happy_path(first=[rate_limit_body, err403])
        )
        self.assertEqual(code, 1)
        self.assertIn("remaining=0", out)
        self.assertIn("resets 2026-09-21T", out)
        self.assertIn("GITHUB_TOKEN", out)

    def test_fail_closed_semantics_preserved(self):
        """A wrong anchor state must still exit 1 (pre-existing contract)."""
        from scripts.ci.federation_anchors import ACTIVE_ANCHOR_HUBS, RETIRED_ANCHOR_HUBS

        rate_limit_body = {
            "resources": {"core": {"limit": 60, "remaining": 5000, "reset": 1790000000}}
        }
        closed_active = {"state": "closed", "title": "[Anchor Hub] wrongly closed"}
        code, out = self.run_verify(
            [rate_limit_body]
            + [closed_active] * len(ACTIVE_ANCHOR_HUBS)
            + [self.RETIRED_OK] * len(RETIRED_ANCHOR_HUBS)
        )
        self.assertEqual(code, 1)
        self.assertIn("Must be OPEN", out)


if __name__ == "__main__":
    unittest.main()
