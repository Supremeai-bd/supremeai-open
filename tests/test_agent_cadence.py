#!/usr/bin/env python3
"""Offline contract tests for role-cadence + empty-board issue creation helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal


class TestCadenceConfig(unittest.TestCase):
    def test_defaults_when_missing(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nope.json"
            cfg = cal.load_cadence_config(p)
            self.assertEqual(cfg["cadences_hours"], cal.DEFAULT_CADENCE_HOURS)

    def test_loads_valid_config(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            p.write_text(
                json.dumps(
                    {
                        "cadences_hours": {"ecosystem-scout": 6},
                        "merged_roles": {"x": "auditor"},
                    }
                )
            )
            cfg = cal.load_cadence_config(p)
            self.assertEqual(cfg["cadences_hours"]["ecosystem-scout"], 6)
            self.assertEqual(cfg["merged_roles"]["x"], "auditor")

    def test_invalid_config_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text("{not json")
            cfg = cal.load_cadence_config(p)
            self.assertEqual(cfg["cadences_hours"], cal.DEFAULT_CADENCE_HOURS)

    def test_canonical_role_merge(self):
        cfg = {
            "cadences_hours": cal.DEFAULT_CADENCE_HOURS,
            "merged_roles": {"federation-auditor": "auditor"},
        }
        self.assertEqual(cal.canonical_role("federation-auditor", cfg), "auditor")
        self.assertEqual(cal.canonical_role("ecosystem-scout", cfg), "ecosystem-scout")


class TestRoleDue(unittest.TestCase):
    def test_never_run_is_due(self):
        cfg = {"cadences_hours": {"ecosystem-scout": 12}, "merged_roles": {}}
        self.assertTrue(cal.role_is_due("ecosystem-scout", None, time.time(), cfg))

    def test_recently_run_not_due(self):
        cfg = {"cadences_hours": {"ecosystem-scout": 12}, "merged_roles": {}}
        now = time.time()
        self.assertFalse(cal.role_is_due("ecosystem-scout", now - 3600, now, cfg))

    def test_overdue_is_due(self):
        cfg = {"cadences_hours": {"ecosystem-scout": 12}, "merged_roles": {}}
        now = time.time()
        self.assertTrue(cal.role_is_due("ecosystem-scout", now - 13 * 3600, now, cfg))

    def test_due_roles_list(self):
        cfg = {"cadences_hours": {"a": 1, "b": 100}, "merged_roles": {}}
        now = time.time()
        store = {"a": now - 2 * 3600, "b": now - 100}
        due = cal.due_roles(store, now, cfg)
        self.assertIn("a", due)
        self.assertNotIn("b", due)

    def test_mark_role_run(self):
        store = {}
        now = 1000.0
        cal.mark_role_run("ecosystem-scout", store, now)
        self.assertEqual(store["ecosystem-scout"], now)


class TestLastRunStore(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "store.json"
            store = {"auditor": 123.0}
            self.assertTrue(cal.save_last_run_store(store, p))
            loaded = cal.load_last_run_store(p)
            self.assertEqual(loaded["auditor"], 123.0)

    def test_missing_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nope.json"
            self.assertEqual(cal.load_last_run_store(p), {})


class TestP0Drainage(unittest.TestCase):
    def test_has_open_p0_blocker_positive(self):
        issues = [
            {"number": 101, "labels": [{"name": "P1-high"}]},
            {"number": 102, "labels": [{"name": "P0-critical"}]},
        ]
        self.assertTrue(cal.has_open_p0_blocker(issues))

    def test_has_open_p0_blocker_negative(self):
        issues = [
            {"number": 101, "labels": [{"name": "P1-high"}]},
            {"number": 103, "labels": [{"name": "P2-medium"}]},
        ]
        self.assertFalse(cal.has_open_p0_blocker(issues))

    def test_has_open_p0_blocker_blocked_by_upstream_excluded(self):
        # বাংলা: লেনে-অ্যাকশনেবল-নয় P0 ব্লকার-গণনা থেকে বাদ (docstring চুক্তি)।
        issues = [
            {"number": 104, "labels": [{"name": "P0-critical"}, {"name": "blocked-by-upstream"}]},
        ]
        self.assertFalse(cal.has_open_p0_blocker(issues))

    def test_has_open_p0_blocker_admin_only_excluded(self):
        # বাংলা: admin-only P0 এই লেনে কখনোই pickযোগ্য নয় (EXCLUDED_LABELS) —
        # এটিকে ব্লকার গুনলে cadence চিরকাল অবরুদ্ধ (starvation) হত।
        issues = [
            {"number": 105, "labels": [{"name": "P0-critical"}, {"name": "admin-only"}]},
        ]
        self.assertFalse(cal.has_open_p0_blocker(issues))

    def test_has_open_p0_blocker_mirror_private_excluded(self):
        # বাংলা: mirror:private P0-ও একই স্থায়ী লেন-সীমা — ব্লকার-গণনা থেকে বাদ।
        issues = [
            {"number": 106, "labels": [{"name": "p0"}, {"name": "mirror:private"}]},
        ]
        self.assertFalse(cal.has_open_p0_blocker(issues))

    def test_has_open_p0_blocker_claimed_still_blocks(self):
        # বাংলা: claimed P0 সাময়িক বাধা (সক্রিয় কাজ চলছে) — ব্লক করবেই (নিয়ম ৫)।
        issues = [
            {"number": 107, "labels": [{"name": "P0-critical"}, {"name": "status:claimed"}]},
        ]
        self.assertTrue(cal.has_open_p0_blocker(issues))

    def test_label_names_extraction(self):
        item = {"labels": [{"name": "P0-critical"}, {"name": "Status:Unclaimed"}]}
        self.assertEqual(cal.label_names(item), ["p0-critical", "status:unclaimed"])


if __name__ == "__main__":
    unittest.main()
