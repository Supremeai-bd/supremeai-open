#!/usr/bin/env python3
"""tests/test_federation_anchors.py — Unit tests for Federation Anchor Hubs SSOT Registry."""

import unittest
from scripts.ci.federation_anchors import (
    ANCHOR_HUBS,
    ANCHOR_ALIASES,
    CI_FAILURE_ANCHOR,
    BRIDGE_ORDER_ANCHOR,
    get_anchor_issue_number,
    normalize_repo_key,
    self_test,
)


class TestFederationAnchors(unittest.TestCase):
    def test_anchor_counts(self):
        """Must have exactly 14 persistent anchor hubs."""
        self.assertEqual(len(ANCHOR_HUBS), 14)
        unique_numbers = set(ANCHOR_HUBS.values())
        self.assertEqual(len(unique_numbers), 14)

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


if __name__ == "__main__":
    unittest.main()
