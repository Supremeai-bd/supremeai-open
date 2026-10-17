#!/usr/bin/env python3
"""Dual-mode contract tests for S0.1 work.claim (task #456).

Two layers, same file:
  UNIT      - decision matrix, marker round-trip, atomic rollback: runs
              TODAY with zero network against scripts/tower/work_claim_reference.py.
  CONTRACT  - live tower checks: skip-until-landed. They activate only when
              the tower advertises work.claim; otherwise they SKIP cleanly,
              never fail the suite.

Run modes (dual-mode doctrine):
  pytest tests/test_s01_atomic_claim_contract.py
  python3 tests/test_s01_atomic_claim_contract.py   (stdlib unittest, no deps)

Extraction SSOT: TTL and marker constants are imported from the reference
implementation, never duplicated here.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

IN_PYTEST = "PYTEST_CURRENT_TEST" in os.environ
HERE = Path(__file__).resolve().parent
REF_DIR = HERE.parent / "scripts" / "tower"
if str(REF_DIR) not in sys.path:
    sys.path.insert(0, str(REF_DIR))

import work_claim_reference as ref  # noqa: E402

T0 = datetime(2026, 10, 17, 2, 40, 52, tzinfo=timezone.utc)


def minutes(n: int) -> datetime:
    return T0 + timedelta(minutes=n)


class UnitDecisionMatrix(unittest.TestCase):
    """Spec section 3 table, cell by cell (pure, offline)."""

    def test_01_unclaimed_grants_new(self):
        self.assertEqual(ref.evaluate_claim(None, 456, "zai", T0), ref.GRANT_NEW)

    def test_02_same_agent_live_is_noop(self):
        cur = ref.parse_marker(ref.build_marker(456, "zai", T0))
        self.assertEqual(ref.evaluate_claim(cur, 456, "zai", minutes(10)), ref.NOOP_SELF)

    def test_03_same_agent_expired_renews(self):
        cur = ref.parse_marker(ref.build_marker(456, "zai", T0))
        self.assertEqual(ref.evaluate_claim(cur, 456, "zai", minutes(31)), ref.GRANT_RENEW)

    def test_04_other_agent_live_conflicts(self):
        cur = ref.parse_marker(ref.build_marker(456, "zai", T0))
        self.assertEqual(ref.evaluate_claim(cur, 456, "other", minutes(10)), ref.CONFLICT_OTHER)

    def test_05_other_agent_expired_takes_over(self):
        cur = ref.parse_marker(ref.build_marker(456, "zai", T0))
        self.assertEqual(ref.evaluate_claim(cur, 456, "other", minutes(31)), ref.GRANT_TAKEOVER)

    def test_06_ttl_is_thirty_minutes_by_reference(self):
        self.assertEqual(ref.TTL_MINUTES, 30)  # transit doctrine constant

    def test_07_boundary_minute_is_live(self):
        cur = ref.parse_marker(ref.build_marker(456, "zai", T0))
        self.assertEqual(ref.evaluate_claim(cur, 456, "other", minutes(29)), ref.CONFLICT_OTHER)
        self.assertEqual(ref.evaluate_claim(cur, 456, "other", minutes(30)), ref.GRANT_TAKEOVER)


class UnitMarkerFormat(unittest.TestCase):
    """Marker is the ledger: round-trip + fail-closed parsing."""

    def test_08_round_trip(self):
        m = ref.build_marker(456, "zai-agent", T0)
        c = ref.parse_marker(m)
        self.assertIsNotNone(c)
        self.assertEqual(c.issue, 456)  # type: ignore[union-attr]
        self.assertEqual(c.agent, "zai-agent")  # type: ignore[union-attr]
        self.assertEqual(c.ts, T0)
        self.assertEqual(c.ttl_minutes, ref.TTL_MINUTES)

    def test_09_garbage_never_parses(self):
        for junk in ("", "atomic-claim:issue=1", "<!-- not-a-marker -->",
                     "<!-- atomic-claim:issue=x,agent=y,ts=z,ttl=1m -->"):
            self.assertIsNone(ref.parse_marker(junk), junk)

    def test_10_latest_marker_wins(self):
        old = ref.build_marker(456, "a", T0)
        new = ref.build_marker(456, "b", minutes(5))
        c = ref.latest_claim(["noise", old, "more noise", new])
        self.assertEqual(c.agent, "b")  # type: ignore[union-attr]

    def test_11_bad_agent_rejected(self):
        with self.assertRaises(ref.ClaimError):
            ref.build_marker(456, "", T0)
        with self.assertRaises(ref.ClaimError):
            ref.build_marker(456, "bad agent; rm -rf", T0)

    def test_12_bad_issue_rejected(self):
        with self.assertRaises(ref.ClaimError):
            ref.build_marker(0, "zai", T0)


class UnitAtomicTransaction(unittest.TestCase):
    """All-or-nothing semantics on the simulated tower."""

    def setUp(self):
        self.ad = ref.SimulatedAdapter()
        self.ad.issues[456] = {"state": "open", "labels": ["status:unclaimed"]}

    def test_13_full_claim_writes_both_planes(self):
        d = ref.work_claim(self.ad, 456, "zai", T0)
        self.assertEqual(d, ref.GRANT_NEW)
        self.assertIn("status:claimed", self.ad.issues[456]["labels"])
        self.assertNotIn("status:unclaimed", self.ad.issues[456]["labels"])
        self.assertEqual(len(self.ad.list_comments(456)), 1)
        self.assertTrue(self.ad.list_comments(456)[0].startswith(ref.MARKER_PREFIX))
        self.assertEqual(len(self.ad.audit), 1)

    def test_14_label_failure_means_no_comment(self):
        self.ad.fail_label = True
        with self.assertRaises(ref.ClaimError):
            ref.work_claim(self.ad, 456, "zai", T0)
        self.assertEqual(self.ad.list_comments(456), [])
        self.assertIn("status:unclaimed", self.ad.issues[456]["labels"])

    def test_15_comment_failure_rolls_back_label(self):
        self.ad.fail_comment = True
        with self.assertRaises(ref.ClaimError):
            ref.work_claim(self.ad, 456, "zai", T0)
        self.assertNotIn("status:claimed", self.ad.issues[456]["labels"])
        self.assertEqual(self.ad.list_comments(456), [])

    def test_16_closed_issue_is_terminal(self):
        self.ad.issues[456] = {"state": "closed", "labels": []}
        with self.assertRaises(ref.ClaimError) as ctx:
            ref.work_claim(self.ad, 456, "zai", T0)
        self.assertEqual(ctx.exception.code, "ISSUE_CLOSED")

    def test_17_missing_issue_is_terminal(self):
        with self.assertRaises(ref.ClaimError) as ctx:
            ref.work_claim(self.ad, 40404, "zai", T0)
        self.assertEqual(ctx.exception.code, "ISSUE_NOT_FOUND")

    def test_18_conflict_leaves_state_untouched(self):
        ref.work_claim(self.ad, 456, "zai", T0)
        before_comments = list(self.ad.list_comments(456))
        with self.assertRaises(ref.ClaimError) as ctx:
            ref.work_claim(self.ad, 456, "other", minutes(10))
        self.assertEqual(ctx.exception.code, "CLAIM_CONFLICT_OTHER")
        self.assertEqual(self.ad.list_comments(456), before_comments)
        self.assertEqual(len(self.ad.audit), 1)

    def test_19_renew_replaces_with_fresh_marker(self):
        ref.work_claim(self.ad, 456, "zai", T0)
        d = ref.work_claim(self.ad, 456, "zai", minutes(31))
        self.assertEqual(d, ref.GRANT_RENEW)
        live = ref.latest_claim(self.ad.list_comments(456))
        self.assertEqual(live.agent, "zai")  # type: ignore[union-attr]
        self.assertEqual(live.ts, minutes(31))  # type: ignore[union-attr]

    def test_20_takeover_by_other_after_expiry(self):
        ref.work_claim(self.ad, 456, "zai", T0)
        d = ref.work_claim(self.ad, 456, "other", minutes(31))
        self.assertEqual(d, ref.GRANT_TAKEOVER)
        self.assertEqual(ref.latest_claim(self.ad.list_comments(456)).agent, "other")  # type: ignore[union-attr]


TOWER_URL = os.environ.get("SUPREMEAI_TOWER_URL", "https://supremeai-mcp-tower.onrender.com/mcp")


def tower_tools(timeout: int = 20):
    """Minimal MCP initialize + tools/list over HTTP (no SDK deps)."""
    def rpc(session, req_id, method, params):
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params is not None:
            payload["params"] = params
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream"}
        if session:
            headers["mcp-session-id"] = session
        req = urllib.request.Request(TOWER_URL, data=json.dumps(payload).encode(),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            sid = resp.headers.get("mcp-session-id") or session
            body = resp.read().decode("utf-8", errors="replace")
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip()), sid
                except json.JSONDecodeError:
                    continue
        return (json.loads(body) if body.strip() else {}), sid

    resp, sid = rpc(None, 1, "initialize", {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "s01-contract-test", "version": "1.0.0"}})
    if not resp.get("result"):
        raise ConnectionError("tower initialize failed")
    rpc(sid, 0, "notifications/initialized", {}, )
    resp, _ = rpc(sid, 2, "tools/list", {})
    return [t.get("name") for t in resp.get("result", {}).get("tools", [])]


class LiveTowerContract(unittest.TestCase):
    """skip-until-landed: silent until work.claim ships, then strict."""

    def tools(self):
        return tower_tools()

    @unittest.skipUnless(os.environ.get("S01_LIVE") == "1",
                         "skip-until-landed (set S01_LIVE=1 to attempt live checks)")
    def test_21_tool_advertised(self):
        try:
            names = self.tools()
        except Exception as exc:  # network variance must skip, not fail
            self.skipTest(f"tower unreachable: {exc}")
        self.assertIn("work_claim", [n.replace(".", "_") for n in names])

    def test_22_reference_matches_spec_shape(self):
        # Fail-closed materialize: the shipped reference must construct a
        # valid marker for the task issue right now, or the suite is broken.
        m = ref.build_marker(456, "contract-check", T0)
        self.assertTrue(m.startswith("<!-- atomic-claim:issue=456,"))


def load_and_run():
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(load_and_run())
