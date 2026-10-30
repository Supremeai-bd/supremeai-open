#!/usr/bin/env python3
"""Offline contract tests for the event-driven role rotation (#3573) + empty-board helpers.

#3573 regime: scheduled roles are condition-driven (one per idle cycle,
re-armed by work events) — the 12h/24h `cadences_hours` clock gates and the
local 30-minute dispatch lease are REMOVED. These tests pin the new contract
so the artificial-timer class cannot silently return (Zero-Recurrence U6).
"""

from __future__ import annotations

import ast
import inspect
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
            self.assertEqual(cfg["scheduled_roles"], list(cal.DEFAULT_SCHEDULED_ROLES))

    def test_loads_v2_config(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "c.json"
            p.write_text(
                json.dumps(
                    {
                        "scheduled_roles": ["auditor", "ecosystem-scout"],
                        "merged_roles": {"x": "auditor"},
                    }
                )
            )
            cfg = cal.load_cadence_config(p)
            self.assertEqual(cfg["scheduled_roles"], ["auditor", "ecosystem-scout"])
            self.assertEqual(cfg["merged_roles"]["x"], "auditor")

    def test_legacy_cadences_hours_keys_become_order_and_hours_ignored(self):
        # #3573 legacy regime: the hour VALUES are dead — keys survive as order.
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "legacy.json"
            p.write_text(json.dumps({"cadences_hours": {"auditor": 9999, "ecosystem-scout": 1}}))
            cfg = cal.load_cadence_config(p)
            self.assertEqual(cfg["scheduled_roles"], ["auditor", "ecosystem-scout"])

    def test_invalid_config_falls_back(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "bad.json"
            p.write_text("{not json")
            cfg = cal.load_cadence_config(p)
            self.assertEqual(cfg["scheduled_roles"], list(cal.DEFAULT_SCHEDULED_ROLES))

    def test_canonical_role_merge(self):
        cfg = {
            "scheduled_roles": list(cal.DEFAULT_SCHEDULED_ROLES),
            "merged_roles": {"federation-auditor": "auditor"},
        }
        self.assertEqual(cal.canonical_role("federation-auditor", cfg), "auditor")
        self.assertEqual(cal.canonical_role("ecosystem-scout", cfg), "ecosystem-scout")

    def test_shipped_config_is_v2(self):
        # The tracked config itself must carry the event-driven schema (no
        # hour values that a future refactor could silently re-arm).
        cfg = cal.load_cadence_config()  # default CADENCE_FILE = shipped config
        self.assertNotIn("cadences_hours", cfg)
        self.assertEqual(cfg["scheduled_roles"], list(cal.DEFAULT_SCHEDULED_ROLES))


class TestRoleEpisodeRotation(unittest.TestCase):
    """#3573 episode semantics: due ⟺ not yet run this episode. No clock."""

    CFG = {
        "scheduled_roles": ["ecosystem-scout", "auditor"],
        "merged_roles": {},
    }

    def test_never_run_is_due(self):
        self.assertTrue(cal.role_is_due("ecosystem-scout", None, self.CFG))

    def test_run_this_episode_not_due_regardless_of_age(self):
        # Ran 1 second ago: not due. Ran "long" ago (same episode): STILL not
        # due — the timestamp is a marker, never a duration input.
        now = time.time()
        self.assertFalse(cal.role_is_due("ecosystem-scout", now - 1, self.CFG))
        self.assertFalse(cal.role_is_due("ecosystem-scout", now - 999 * 3600, self.CFG))

    def test_non_scheduled_role_not_due(self):
        self.assertFalse(cal.role_is_due("not-a-role", None, self.CFG))

    def test_due_roles_respects_config_order(self):
        self.assertEqual(cal.due_roles({}, self.CFG), ["ecosystem-scout", "auditor"])

    def test_due_roles_empty_when_all_ran_this_episode(self):
        now = time.time()
        store = {"ecosystem-scout": now, "auditor": now}
        self.assertEqual(cal.due_roles(store, self.CFG), [])

    def test_due_roles_partial_episode(self):
        now = time.time()
        store = {"ecosystem-scout": now}
        self.assertEqual(cal.due_roles(store, self.CFG), ["auditor"])

    def test_due_roles_ignores_legacy_hour_values(self):
        # Legacy configs are normalized by load_cadence_config (keys -> order,
        # hours dead); due_roles consumes the normalized shape.
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "legacy.json"
            p.write_text(json.dumps({"cadences_hours": {"ecosystem-scout": 1, "auditor": 9999}}))
            cfg = cal.load_cadence_config(p)
        self.assertEqual(cal.due_roles({}, cfg), ["ecosystem-scout", "auditor"])

    def test_due_roles_canonical_key_read(self):
        # #1569 lineage: mark writes the canonical key, read must use it too.
        now = time.time()
        store = {"auditor": now}
        cfg = {"scheduled_roles": ["task-auditor"], "merged_roles": {"task-auditor": "auditor"}}
        self.assertEqual(cal.due_roles(store, cfg), [])

    def test_mark_role_run(self):
        store = {}
        now = 1000.0
        cal.mark_role_run("ecosystem-scout", store, now)
        self.assertEqual(store["ecosystem-scout"], now)


class TestEventDrivenContract(unittest.TestCase):
    """U6 source pins: the artificial-timer class cannot silently return."""

    def test_module_has_no_hour_gate_constant(self):
        self.assertFalse(hasattr(cal, "DEFAULT_CADENCE_HOURS"))
        self.assertTrue(hasattr(cal, "DEFAULT_SCHEDULED_ROLES"))

    def test_role_is_due_has_no_duration_comparison(self):
        src = inspect.getsource(cal.role_is_due)
        tree = ast.parse(src)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
        self.assertNotIn("hours", names | attrs)
        self.assertNotIn("cadences_hours", names | attrs)

    def test_pick_has_no_dispatch_time_gate(self):
        # #3573: the 30-minute local lease exclusion is gone from the
        # claimability gate (nested is_claimable — AST name scan, comment-immune).
        # #3738 reconciliation: pick_next_issue legitimately carries the
        # lease_store/ISSUE_LEASE_SECONDS names ONLY as the born-duplicate twin
        # demotion's in-flight input (demotion-only — removes a duplicate
        # dispatch, never gates or delays a candidate); the old candidate-skip
        # pattern (leased_at) stays forbidden.
        src = inspect.getsource(cal.pick_next_issue)
        tree = ast.parse(src)
        gates = [
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "is_claimable"
        ]
        self.assertEqual(len(gates), 1)
        gate_tokens = set()
        for node in ast.walk(gates[0]):
            if isinstance(node, ast.Name):
                gate_tokens.add(node.id)
            elif isinstance(node, ast.Attribute):
                gate_tokens.add(node.attr)
        for tok in gate_tokens:
            self.assertNotIn("LEASE", tok.upper())
        self.assertNotIn("leased_at", src)
        # The #3738 twin wiring stays honest: the twin scan must actually be fed
        # this runner's journal in-flight input.
        self.assertIn("_duplicate_twin_note(", src)
        self.assertIn("lease_store", src)

    def test_dispatch_rearms_rotation_on_work_event(self):
        # The work event (claimable issue assigned) must reset the rotation
        # store on BOTH assignment paths (dispatch + envelope).
        src = inspect.getsource(cal.run_dispatch_cycle)
        self.assertGreaterEqual(src.count("save_last_run_store({})"), 2)

    def test_no_reset_on_empty_board_timer_loop(self):
        # The old reset (`not raw and state -> {}` on every clean cycle) is
        # gone — an idle board must reach the clean+sleep state, not re-arm
        # the rotation forever (founder mandate 2).
        self.assertNotIn("cadence timers reset", inspect.getsource(cal.run_dispatch_cycle))


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
