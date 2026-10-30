import unittest
from datetime import datetime, timezone, timedelta
from scripts.agents.pr_lifecycle_guard import (
    is_historical_sentry,
    is_completed_receipt,
    find_duplicate_issues,
)

class TestBoardIssueJanitor(unittest.TestCase):
    def test_sentry_pass_older_than_12h(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=14)).isoformat()
        recent_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        
        self.assertTrue(is_historical_sentry("guard(platform): sentry pass 22:44Z — 7/8 alive", old_time))
        self.assertFalse(is_historical_sentry("guard(platform): sentry pass 22:44Z — 7/8 alive", recent_time))
        self.assertFalse(is_historical_sentry("fix: something else", old_time))

    def test_completed_receipt(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
        self.assertTrue(is_completed_receipt("🌉 Bridge Work Order — Identity registration receipt", ["report", "bridge:receipt"], old_time))
        self.assertFalse(is_completed_receipt("[Anchor Hub] Core Embassy", ["anchor-hub"], old_time))

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
