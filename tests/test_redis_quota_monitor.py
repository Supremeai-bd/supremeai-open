#!/usr/bin/env python3
"""Contract & Unit Tests for the Redis quota monitor pure logic (#1522 / Q1)."""

import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
MONITOR_PATH = REPO_ROOT / "scripts" / "ops" / "redis_quota_monitor.py"

_spec = importlib.util.spec_from_file_location("redis_quota_monitor", MONITOR_PATH)
rqm = importlib.util.module_from_spec(_spec)
if MONITOR_PATH.parent not in sys.path:
    sys.path.insert(0, str(MONITOR_PATH.parent))
_spec.loader.exec_module(rqm)


class TestQuotaMath(unittest.TestCase):
    def test_compute_pct_basic(self):
        self.assertEqual(rqm.compute_pct(400000, 500000), 80.0)

    def test_compute_pct_rounding(self):
        self.assertEqual(rqm.compute_pct(1, 3), 33.33)

    def test_compute_pct_zero_limit_is_none(self):
        """A zero/unknown limit must be None — never a fabricated 0% or crash."""
        self.assertIsNone(rqm.compute_pct(10, 0))
        self.assertIsNone(rqm.compute_pct(10, None))
        self.assertIsNone(rqm.compute_pct("x", "y"))

    def test_tier_boundaries(self):
        self.assertIsNone(rqm.tier_for(79.99))
        self.assertEqual(rqm.tier_for(80.0), "warn")
        self.assertEqual(rqm.tier_for(94.9), "warn")
        self.assertEqual(rqm.tier_for(95.0), "crit")
        self.assertIsNone(rqm.tier_for(None))


class TestEvaluateAccounts(unittest.TestCase):
    def test_chain_evaluation(self):
        chain = [
            {"label": "primary", "usage": {"estimatedCommands": 412500, "limit": 500000}},
            {"label": "secondary", "usage": {"estimatedCommands": 480001, "limit": 500000}},
            {"label": "tertiary", "usage": {"estimatedCommands": 50000, "limit": 500000}},
            {"label": "broken", "usage": None},
        ]
        alerts = rqm.evaluate_accounts(chain)
        self.assertEqual([a["label"] for a in alerts], ["primary", "secondary"])
        self.assertEqual(alerts[0]["tier"], "warn")
        self.assertEqual(alerts[1]["tier"], "crit")
        self.assertAlmostEqual(alerts[0]["pct"], 82.5)

    def test_empty_chain_is_quiet(self):
        self.assertEqual(rqm.evaluate_accounts([]), [])
        self.assertEqual(rqm.evaluate_accounts(None), [])


class TestDedupStateMachine(unittest.TestCase):
    def test_one_alert_per_label_tier_window(self):
        state = {}
        self.assertTrue(rqm.should_alert(state, "primary", "warn", "W1"))
        rqm.record_alert(state, "primary", "warn", "W1", "2026-10-27T19:00:00Z")
        self.assertFalse(rqm.should_alert(state, "primary", "warn", "W1"))
        # independent per tier and per window
        self.assertTrue(rqm.should_alert(state, "primary", "crit", "W1"))
        self.assertTrue(rqm.should_alert(state, "primary", "warn", "W2"))

    def test_state_roundtrip(self):
        import os
        import tempfile

        state = {"primary:warn": {"window": "W1", "sentAt": "t"}}
        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            self.assertTrue(rqm.save_state(path, state))
            self.assertEqual(rqm.load_state(path), state)
        finally:
            os.unlink(path)

    def test_corrupt_state_is_empty(self):
        import os
        import tempfile

        fd, path = tempfile.mkstemp()
        os.close(fd)
        try:
            with open(path, "w") as fh:
                fh.write("{not json")
            self.assertEqual(rqm.load_state(path), {})
        finally:
            os.unlink(path)


class TestMessageComposition(unittest.TestCase):
    def test_message_contains_facts(self):
        alerts = [
            {"label": "primary", "pct": 82.5, "tier": "warn", "used": 412500, "limit": 500000, "cooldownUntil": None},
            {"label": "secondary", "pct": 96.0, "tier": "crit", "used": 480001, "limit": 500000, "cooldownUntil": None},
        ]
        msg = rqm.compose_message(alerts, active_primary="secondary", next_reset="2026-11-01T00:00:00Z")
        self.assertIn("[WARN]", msg)
        self.assertIn("[CRITICAL]", msg)
        self.assertIn("82.50%", msg)
        self.assertIn("96.00%", msg)
        self.assertIn("2026-11-01T00:00:00Z", msg)
        self.assertIn("secondary", msg)  # active primary reported

    def test_quiet_chain_message_is_none(self):
        self.assertIsNone(rqm.compose_message([]))


class TestSseParser(unittest.TestCase):
    def test_parse_sse_tool_response(self):
        canned = (
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":2,"result":{"content":'
            '[{"type":"text","text":"{\\"chain\\": [], \\"autoRotateEnabled\\": true}"}]}}\n'
        )
        text = rqm.parse_tool_response_text(canned)
        self.assertTrue(json.loads(text)["autoRotateEnabled"])

    def test_parse_plain_json_response(self):
        canned = '{"jsonrpc":"2.0","id":2,"result":{"content":[{"type":"text","text":"{\\"ok\\": 1}"}]}}'
        text = rqm.parse_tool_response_text(canned)
        self.assertEqual(json.loads(text)["ok"], 1)

    def test_parse_error_raises(self):
        canned = 'data: {"jsonrpc":"2.0","id":2,"error":{"code":-32602,"message":"bad"}}'
        with self.assertRaises(RuntimeError):
            rqm.parse_tool_response_text(canned)


if __name__ == "__main__":
    unittest.main()
