#!/usr/bin/env python3
"""tests/test_tower_tool_capability_gate.py — U6 zero-recurrence guard for the
tower tool-roster gate (GLM Agent 09, Job 486738, cycle 6, 2026-10-31).

Failure class being locked out (roster-purge blind-call debt):

  The MCP tower purges tool families in waves (snake_case github_* → dotted
  github.* → whole github.* family gone from the anonymous/viewer roster,
  live-verified 2026-10-31: tools/list shows no ``github.*`` names). The loop's
  tower PR probes (_tower_open_prs, _tower_merged_landing_prs) kept burning a
  full initialize→notifications/initialized→tools/call cycle per probe on
  every zero-credential boot, dying deterministically with
  "MCP error -32602: Tool github.list_prs not found" — a PERMANENT tool-surface
  state that the old classifier mis-reported as "viewer RBAC" (a false
  cause-diagnosis that sent later agents hunting for credentials/roles that
  cannot fix a missing tool). Root cause: no capability check between the
  caller and the wire.

Fix pinned here:
  1. `_tower_tool_roster_gate(tool)` reads the live tools/list roster ONCE per
     process; a confirmed absence returns a truthful note and CACHES it;
     present tool / unreadable roster / transport failure → None (fail-open:
     the probe keeps its previous behavior; transient outages never block work).
  2. Both PR probes consult the gate before ANY network call; a missing-tool
     note ⇒ zero urllib calls (no wasted init/call cycle, no -32602 noise).
  3. The -32602 / "Tool ... not found" error shape classifies as permanent
     tool-absence (NOT RBAC) — closing the false "viewer RBAC" cause class.
  4. The report dark-line prefix is note-truthful: roster notes render
     "tool-absent (tower roster purge)"; RBAC-shaped notes keep the pinned
     "viewer RBAC" prefix (byte-compat with test_failed_pr_audit_board_assurance).

All tests are offline and deterministic: urllib.request.urlopen is stubbed at
the module boundary; no network, no gh, no tower.

বাংলা সারসংক্ষেপ:
------------------
টাওয়ার থেকে github.list_prs টুল সরে যাওয়ার পরও লুপ প্রতি বুটে অন্ধ টুল-কল করে
নিশ্চিত -32602-এ মরত এবং মিথ্যা "viewer RBAC" কারণ দেখাত। এই guard পিন করে:
রোস্টার-গেট আগে চলবে (অনুপস্থিত টুল = শূন্য নেটওয়ার্ক কল, সৎ নোট, প্রক্রিয়া-স্তরের
ক্যাশ), -32602 শেপ স্থায়ী টুল-অনুপস্থিতি হিসেবেই শ্রেণিবদ্ধ হবে — ভুল RBAC
নির্ণয় শ্রেণি আর কখনো ফিরবে না।

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import inspect
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402

GATE_NOTE_FRAGMENT = "roster does not carry"


def _sse(payload: dict) -> bytes:
    """Tower-shaped SSE body: event/data lines (raw-urllib transport reads it)."""
    return ("event: message\ndata: " + json.dumps(payload) + "\n").encode("utf-8")


def _roster_response(tool_names: list[str]) -> bytes:
    """tools/list result carrying the given tool-name roster."""
    return _sse(
        {
            "jsonrpc": "2.0",
            "id": "cal-roster-gate-2",
            "result": {"tools": [{"name": n} for n in tool_names]},
        }
    )


_INIT_RESPONSE = _sse(
    {
        "jsonrpc": "2.0",
        "id": "cal-roster-gate-1",
        "result": {"protocolVersion": "2024-11-05", "capabilities": {}},
    }
)


class _FakeResponse(io.BytesIO):
    """Minimal urlopen stand-in: context-manager + dict headers."""

    def __init__(self, body: bytes):
        super().__init__(body)
        self.headers = {"mcp-session-id": "sid-gate-test"}


class TestClassifierToolAbsenceShape(unittest.TestCase):
    """The -32602 / "Tool ... not found" shape is permanent tool-absence, not RBAC."""

    def test_32602_shape_gets_truthful_tool_absent_note(self) -> None:
        note = cal._classify_tower_pr_failure(
            "MCP error -32602: Tool github.list_prs not found"
        )
        self.assertIn("tool-absent", note)
        self.assertIn("permanent", note)
        self.assertIn("-32602", note)

    def test_not_found_shape_without_code_also_matches(self) -> None:
        note = cal._classify_tower_pr_failure("Tool github.list_prs not found")
        self.assertIn("tool-absent", note)

    def test_rbac_shape_still_classified_as_rbac(self) -> None:
        note = cal._classify_tower_pr_failure(
            "Forbidden: role 'viewer' has no repository read access for 'github.list_prs'."
        )
        self.assertIn("RBAC-forbidden", note)
        self.assertNotIn("tool-absent", note)

    def test_generic_error_stays_generic(self) -> None:
        note = cal._classify_tower_pr_failure("connection reset by peer")
        self.assertIn("tower PR tool-call error", note)
        self.assertNotIn("tool-absent", note)


class TestRosterGateBlocksProbe(unittest.TestCase):
    """A confirmed missing tool ⇒ zero network calls, truthful note, cached."""

    def setUp(self) -> None:
        cal._TOWER_ROSTER_GATE_CACHE.clear()

    def test_open_prs_probe_makes_zero_calls_on_missing_tool(self) -> None:
        calls = []

        def _counting_urlopen(req, timeout=0):  # pragma: no cover — must NOT run
            calls.append(req)
            raise AssertionError("urlopen must not be called when the gate says absent")

        with mock.patch.object(
            cal, "_tower_tool_roster_gate", return_value="tower tools/list roster does not carry 'github.list_prs' (roster-purge state) — probe skipped"
        ), mock.patch.object(cal.urllib.request, "urlopen", side_effect=_counting_urlopen):
            rows, note = cal._tower_open_prs()
        self.assertIsNone(rows)
        self.assertIn(GATE_NOTE_FRAGMENT, note)
        self.assertEqual(calls, [])

    def test_landing_probe_makes_zero_calls_on_missing_tool(self) -> None:
        calls = []

        def _counting_urlopen(req, timeout=0):  # pragma: no cover — must NOT run
            calls.append(req)
            raise AssertionError("urlopen must not be called when the gate says absent")

        with mock.patch.object(
            cal, "_tower_tool_roster_gate", return_value="tower tools/list roster does not carry 'github.list_prs' (roster-purge state) — probe skipped"
        ), mock.patch.object(cal.urllib.request, "urlopen", side_effect=_counting_urlopen):
            # বাংলা: সরাসরি tower-পরিবহণ ডাক — REST-প্লেন এই টেস্টের বিষয় নয়
            # (_fetch_merged_landing_prs-এর REST চেষ্টা আলাদা নেটওয়ার্ক কল করে)।
            with self.assertRaises(RuntimeError) as ctx:
                cal._tower_merged_landing_prs(20)
        self.assertIn(GATE_NOTE_FRAGMENT, str(ctx.exception))
        self.assertEqual(calls, [])


class TestRosterGateFailOpen(unittest.TestCase):
    """Unverifiable roster / present tool ⇒ None ⇒ previous probe behavior."""

    def setUp(self) -> None:
        cal._TOWER_ROSTER_GATE_CACHE.clear()

    def test_transport_failure_means_none_not_missing(self) -> None:
        with mock.patch.object(
            cal.urllib.request, "urlopen", side_effect=OSError("network dark")
        ):
            self.assertIsNone(cal._tower_tool_roster_gate("github.list_prs"))
        # বাংলা: যাচাই-ব্যর্থতা "অনুপস্থিতি" প্রমাণ নয় — ক্যাশ খালি থাকবে।
        self.assertEqual(cal._TOWER_ROSTER_GATE_CACHE, {})

    def test_unreadable_roster_means_none_not_missing(self) -> None:
        garbage = b"not-json-at-all"
        with mock.patch.object(
            cal.urllib.request, "urlopen", side_effect=lambda req, timeout=0: _FakeResponse(garbage)
        ):
            self.assertIsNone(cal._tower_tool_roster_gate("github.list_prs"))
        self.assertEqual(cal._TOWER_ROSTER_GATE_CACHE, {})

    def test_present_tool_returns_none(self) -> None:
        bodies = [
            _INIT_RESPONSE,
            _sse({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            _roster_response(["status", "bridge_guide", "github.list_prs"]),
        ]

        def _fake_urlopen(req, timeout=0):
            return _FakeResponse(bodies.pop(0))

        with mock.patch.object(cal.urllib.request, "urlopen", side_effect=_fake_urlopen):
            self.assertIsNone(cal._tower_tool_roster_gate("github.list_prs"))
        self.assertEqual(cal._TOWER_ROSTER_GATE_CACHE, {})

    def test_gate_none_lets_probe_attempt_network(self) -> None:
        calls = []

        def _counting_urlopen(req, timeout=0):
            calls.append(req)
            raise OSError("transport dark — probe attempted as contracted")

        with mock.patch.object(
            cal, "_tower_tool_roster_gate", return_value=None
        ), mock.patch.object(cal.urllib.request, "urlopen", side_effect=_counting_urlopen):
            rows, note = cal._tower_open_prs()
        self.assertIsNone(rows)
        self.assertTrue(len(calls) >= 1, "gate=None must preserve the live probe path")
        self.assertIn("failed", note.lower())


class TestRosterGateCaching(unittest.TestCase):
    """Confirmed absence is cached: one roster read per process."""

    def setUp(self) -> None:
        cal._TOWER_ROSTER_GATE_CACHE.clear()

    def test_missing_note_cached_and_second_call_is_free(self) -> None:
        # বাংলা: গেটের ৩টি পোস্ট — initialize, notifications/initialized, tools/list।
        bodies = [
            _INIT_RESPONSE,
            _sse({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            _roster_response(["status", "bridge_guide", "bridge_work_queue"]),
        ]

        def _fake_urlopen(req, timeout=0):
            if bodies:
                return _FakeResponse(bodies.pop(0))
            raise AssertionError("roster must be read once per process, not per call")

        with mock.patch.object(cal.urllib.request, "urlopen", side_effect=_fake_urlopen):
            first = cal._tower_tool_roster_gate("github.list_prs")
            second = cal._tower_tool_roster_gate("github.list_prs")
        self.assertIsInstance(first, str)
        self.assertIn(GATE_NOTE_FRAGMENT, first)
        self.assertEqual(first, second)
        self.assertIn("github.list_prs", cal._TOWER_ROSTER_GATE_CACHE)

    def test_probe_consumes_cache_without_extra_roster_read(self) -> None:
        bodies = [
            _INIT_RESPONSE,
            _sse({"jsonrpc": "2.0", "method": "notifications/initialized"}),
            _roster_response(["status", "bridge_guide"]),
        ]

        def _fake_urlopen(req, timeout=0):
            return _FakeResponse(bodies.pop(0))

        with mock.patch.object(cal.urllib.request, "urlopen", side_effect=_fake_urlopen):
            cal._tower_tool_roster_gate("github.list_prs")  # warms the cache
            rows, note = cal._tower_open_prs()
        self.assertIsNone(rows)
        self.assertIn(GATE_NOTE_FRAGMENT, note)
        self.assertEqual(bodies, [], "no extra roster fetch may happen after cache warm")


class TestProbeWiringPins(unittest.TestCase):
    """Both PR probes consult the roster gate before any network work (source pin)."""

    def test_open_prs_probe_wires_the_gate(self) -> None:
        src = inspect.getsource(cal._tower_open_prs)
        self.assertIn("_tower_tool_roster_gate", src)
        self.assertIn("github.list_prs", src)

    def test_landing_probe_wires_the_gate(self) -> None:
        src = inspect.getsource(cal._tower_merged_landing_prs)
        self.assertIn("_tower_tool_roster_gate", src)
        self.assertIn("github.list_prs", src)

    def test_dark_line_prefix_is_note_truthful(self) -> None:
        src = inspect.getsource(cal.report_failed_open_prs)
        self.assertIn("plane_cause", src)
        self.assertIn("roster", src)
        self.assertIn("viewer RBAC", src)  # RBAC-notes keep the pinned prefix


if __name__ == "__main__":
    unittest.main(verbosity=2)
