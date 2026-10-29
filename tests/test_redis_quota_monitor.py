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

    # ── #1839: persistent default state contract ─────────────────────────────

    def test_default_state_path_is_persistent_not_tmp(self):
        """The /tmp default starved [BURN] history; default must be home-relative (#1839)."""
        p = rqm.default_state_path()
        self.assertEqual(p.name, "redis_quota_alert_state.json")
        self.assertTrue(str(p).startswith(str(rqm.Path.home())))
        self.assertNotIn(str(rqm.tempfile.gettempdir()), str(p))

    def test_env_override_wins_over_default(self):
        """REDIS_QUOTA_STATE_FILE must keep precedence over the new home default (#1839)."""
        import os as _os
        from unittest import mock

        with mock.patch.dict("os.environ", {"REDIS_QUOTA_STATE_FILE": "/x/y/state.json"}):
            self.assertEqual(
                _os.environ.get(rqm.STATE_ENV, str(rqm.default_state_path())),
                "/x/y/state.json",
            )

    def test_save_state_creates_missing_parent_dirs(self):
        """~/.supremeai may not exist on a fresh host; save_state must not fail silently (#1839)."""
        import os
        import tempfile

        base = tempfile.mkdtemp()
        nested = os.path.join(base, "lv1", "lv2", "state.json")
        try:
            self.assertFalse(os.path.isdir(os.path.dirname(nested)))
            self.assertTrue(rqm.save_state(nested, {"k": 1}))
            self.assertEqual(rqm.load_state(nested), {"k": 1})
        finally:
            import shutil

            shutil.rmtree(base, ignore_errors=True)


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


class TestIsoParsing(unittest.TestCase):
    def test_z_suffix_and_garbage(self):
        self.assertIsNotNone(rqm.parse_iso_ts("2026-11-01T00:01:00Z"))
        self.assertIsNone(rqm.parse_iso_ts("not-a-date"))
        self.assertIsNone(rqm.parse_iso_ts(None))
        self.assertIsNone(rqm.parse_iso_ts(12345))


class TestBurnProjection(unittest.TestCase):
    """#1698 D1: the active link's burn rate must be projected, never guessed."""

    PRIOR = {"used": 50000, "ts": "2026-10-28T00:00:00Z"}
    CURRENT = {"used": 98000, "ts": "2026-10-28T01:00:00Z"}  # 48000 cmds/h

    def test_honest_skips(self):
        cases = [
            (None, self.CURRENT, 500000),                     # no history
            (self.CURRENT, {"used": 98001, "ts": "2026-10-28T01:00:10Z"}, 500000),  # dt < 600s
            (self.CURRENT, {"used": 10, "ts": "2026-10-28T03:00:00Z"}, 500000),     # counter reset
            (self.PRIOR, self.CURRENT, 0),                    # invalid limit
            ({"used": 1000, "ts": "garbage"}, self.CURRENT, 500000),                # bad ts
        ]
        for prior, current, limit in cases:
            result = rqm.project_burn(prior, current, limit, None, "2026-11-01T00:01:00Z")
            self.assertIsNotNone(result["skip"], "case must skip honestly: %r" % (prior,))

    def test_projection_math(self):
        proj = rqm.project_burn(self.PRIOR, self.CURRENT, 500000, 480000, "2026-11-01T00:01:00Z")
        self.assertIsNone(proj["skip"])
        self.assertEqual(proj["burn_per_hour"], 48000)
        self.assertAlmostEqual(proj["projected_pct"], 931.76, places=2)
        self.assertIsNotNone(proj["soft_crossed_at"])

    def test_under_soft_projection_is_quiet(self):
        calm = rqm.project_burn(
            {"used": 96000, "ts": "2026-10-28T00:00:00Z"},
            self.CURRENT, 500000, 480000, "2026-11-01T00:01:00Z",
        )
        self.assertIsNone(calm["skip"])
        self.assertIsNone(rqm.compose_burn_line(calm, "tertiary", "2026-11-01T00:01:00Z"))

    def test_burn_line_fires_when_crossing_soft(self):
        proj = rqm.project_burn(self.PRIOR, self.CURRENT, 500000, 480000, "2026-11-01T00:01:00Z")
        line = rqm.compose_burn_line(proj, "tertiary", "2026-11-01T00:01:00Z")
        self.assertIn("[BURN]", line)
        self.assertIn("tertiary", line)
        self.assertIn("#1698", line)

    def test_snapshots_are_window_scoped(self):
        state = {}
        self.assertIsNone(rqm.prior_usage_snapshot(state, "tertiary", "W1"))
        rqm.record_usage_snapshot(state, "tertiary", "W1", 55000, "2026-10-28T00:00:00Z")
        self.assertEqual(rqm.prior_usage_snapshot(state, "tertiary", "W1")["used"], 55000)
        self.assertIsNone(rqm.prior_usage_snapshot(state, "tertiary", "W2"))


class TestChainCapacity(unittest.TestCase):
    """#1698 D1/D4: chain-depth must be visible; failover behavior itself untouched."""

    NOW = rqm.parse_iso_ts("2026-10-28T02:00:00Z")

    def test_incident_shape_is_one_deep(self):
        chain = [
            {"label": "primary", "usage": {"estimatedCommands": 480000, "limit": 500000},
             "cooldownUntil": "2026-11-01T00:01:00Z"},
            {"label": "secondary", "usage": {"estimatedCommands": 500001, "limit": 500000},
             "cooldownUntil": "2026-11-01T00:01:00Z"},
            {"label": "tertiary", "usage": {"estimatedCommands": 55, "limit": 500000},
             "cooldownUntil": None},
        ]
        cap = rqm.chain_capacity(chain, "tertiary", now_dt=self.NOW)
        self.assertTrue(cap["one_deep"])
        self.assertEqual(cap["blocked"], ["primary", "secondary"])
        self.assertEqual(cap["available"], [])
        self.assertIn("[DEPTH]", rqm.compose_depth_line(cap))

    def test_healthy_chain_is_quiet(self):
        chain = [
            {"label": "primary", "usage": {"estimatedCommands": 100, "limit": 500000}, "cooldownUntil": None},
            {"label": "tertiary", "usage": {"estimatedCommands": 55, "limit": 500000}, "cooldownUntil": None},
        ]
        cap = rqm.chain_capacity(chain, "tertiary", now_dt=self.NOW)
        self.assertFalse(cap["one_deep"])
        self.assertIsNone(rqm.compose_depth_line(cap))

    def test_blocked_active_link_is_not_usable(self):
        chain = [{"label": "primary", "usage": {"estimatedCommands": 500001, "limit": 500000},
                  "cooldownUntil": None}]
        cap = rqm.chain_capacity(chain, "primary", now_dt=self.NOW)
        self.assertTrue(cap["none_available"])
        self.assertFalse(cap["one_deep"])
        self.assertIn("[DEPTH-CRITICAL]", rqm.compose_depth_line(cap))

    def test_empty_chain_is_critical(self):
        cap = rqm.chain_capacity([], None, now_dt=self.NOW)
        self.assertTrue(cap["none_available"])

    def test_expired_cooldown_is_available(self):
        chain = [
            {"label": "primary", "usage": {"estimatedCommands": 480000, "limit": 500000},
             "cooldownUntil": "2026-01-01T00:00:00Z"},  # long expired
            {"label": "tertiary", "usage": {"estimatedCommands": 55, "limit": 500000},
             "cooldownUntil": None},
        ]
        cap = rqm.chain_capacity(chain, "tertiary", now_dt=self.NOW)
        self.assertIn("primary", cap["available"])
        self.assertFalse(cap["one_deep"])


class TestD1MessageComposition(unittest.TestCase):
    def test_extras_only_message_is_sent(self):
        """Burn/depth alerts must fire even when no pct threshold is crossed."""
        msg = rqm.compose_message(
            [], active_primary="tertiary", next_reset="2026-11-01T00:01:00Z",
            extra_lines=["[DEPTH] chain one deep"],
        )
        self.assertIsNotNone(msg)
        self.assertIn("[DEPTH]", msg)
        self.assertIn("tertiary", msg)

    def test_quiet_chain_with_no_extras_is_none(self):
        self.assertIsNone(rqm.compose_message([], extra_lines=[]))
        self.assertIsNone(rqm.compose_message([], extra_lines=None))


if __name__ == "__main__":
    unittest.main()
