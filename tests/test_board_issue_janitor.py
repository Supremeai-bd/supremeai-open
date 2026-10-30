import unittest
from scripts.agents.pr_lifecycle_guard import (
    find_superseded_sentry_passes,
    find_duplicate_issues,
)


class TestBoardIssueJanitor(unittest.TestCase):
    def test_superseded_sentry_passes_evidence_based(self):
        # Multiple sentry passes on the board
        issues = [
            {"number": 2902, "title": "guard(platform): sentry pass 22:44Z — 7/8 alive"},
            {"number": 3049, "title": "guard(platform): provider sentry pass 04:45Z — 7/8 alive"},
            {"number": 3111, "title": "guard(platform): sentry pass 08:45Z — 7/8 alive"},
            {"number": 3200, "title": "fix: auth token expiration bug"},
        ]
        superseded = find_superseded_sentry_passes(issues)
        # 2902 and 3049 should be superseded by 3111
        self.assertEqual(superseded, [(2902, 3111), (3049, 3111)])
        # The newest (3111) is never closed — sentinel evidence is continuously preserved!
        self.assertNotIn((3111, 3111), superseded)
        # Non-sentry bug (3200) is never closed
        self.assertFalse(any(old == 3200 for old, _ in superseded))

    def test_single_sentry_pass_never_closed(self):
        # A single sentry pass on the board is never closed by timer
        issues = [
            {"number": 3111, "title": "guard(platform): sentry pass 08:45Z — 7/8 alive"},
        ]
        superseded = find_superseded_sentry_passes(issues)
        self.assertEqual(superseded, [])

    def test_duplicate_issues(self):
        issues = [
            {"number": 3011, "title": "dispatch(labels): #1668 has empty labels", "labels": []},
            {"number": 3012, "title": "dispatch(labels): #1668 has empty labels", "labels": []},
            {"number": 762, "title": "Anchor Hub", "labels": ["anchor-hub"]},
            {"number": 763, "title": "Anchor Hub", "labels": ["anchor-hub"]},
        ]
        dups = find_duplicate_issues(issues)
        self.assertEqual(dups, [(3012, 3011)])


if __name__ == "__main__":
    unittest.main()
