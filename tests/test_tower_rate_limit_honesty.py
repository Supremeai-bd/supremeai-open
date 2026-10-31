#!/usr/bin/env python3
"""Pin + behavior: 429 rate-limit honesty — the tower is UP when it throttles.

Live anatomy (GLM Agent 26, Job 486824, 2026-10-31T10:26Z): the fleet's hourly
cron fires for every agent inside the same :26 window, so the tower answers the
hour with HTTP 429 while perfectly alive — a 3-window probe saw w1
bridge_work_queue OK rows=0 and w2/w3 HTTP 429. Both transport layers surfaced
that state as a generic connection failure: the sibling client raised
McpTowerConnectionError and the loop's floor/board probes printed only
type(exc).__name__, so every agent in that window read "plane dark" as
tower-down (r17 #4346's dark-cycle datum) — a false diagnosis that invites
retry storms precisely when backing off is the right move.

Root fix pinned here (zero network — fake responses and patched fakes):
  1. Client: 429 raises McpTowerRateLimitedError — a SUBCLASS of
     McpTowerConnectionError, so every existing except-clause keeps catching
     (zero-collateral contract); 500/502/503 stay plain connection errors.
  2. Floor probe: a 429-shaped exception yields the honest "tower rate-limited
     ... not tower-down" note, not the tower-down note.
  3. Board fallback: the same classification appends "rate-limited, not
     tower-down" to the failure note (consumed verbatim by the PR-audit dark
     line), and non-429 failures keep the legacy note shape.
  4. Classifier purity: string-based so it works even when the sibling client
     cannot be imported; matches the client class name and urllib's
     "HTTP Error 429" spelling, never a bare tool-payload digit.

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import io
import sys
import unittest
import unittest.mock
import urllib.error
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal  # noqa: E402

try:
    import mcp_tower_client as mtc  # noqa: E402

    HAVE_SIBLING = True
except ImportError:  # pragma: no cover — documented degraded runtime
    HAVE_SIBLING = False


def _http_error_429() -> urllib.error.HTTPError:
    """urllib's real-world 429 shape (live: HTTP Error 429: Too Many Requests)."""
    return urllib.error.HTTPError(
        "https://tower.example/mcp", 429, "Too Many Requests", {}, io.BytesIO(b"")
    )


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class TestClassifierPurity(unittest.TestCase):
    """The classifier is the honesty keystone — pin both its hits and misses."""

    def test_urllib_429_shape_hits(self):
        self.assertTrue(cal._tower_rate_limited(_http_error_429()))

    def test_client_class_name_hits_without_message(self):
        class McpTowerRateLimitedError(Exception):
            pass

        self.assertTrue(cal._tower_rate_limited(McpTowerRateLimitedError("HTTP 429")))

    def test_other_connection_errors_miss(self):
        self.assertFalse(cal._tower_rate_limited(RuntimeError("tower exploded")))
        self.assertFalse(cal._tower_rate_limited(urllib.error.URLError("dns dead")))
        if HAVE_SIBLING:
            self.assertFalse(
                cal._tower_rate_limited(mtc.McpTowerConnectionError("HTTP 503"))
            )
            self.assertFalse(
                cal._tower_rate_limited(mtc.McpTowerTimeoutError("Timeout: tools/call"))
            )

    def test_bare_digit_payload_never_false_positives(self):
        # An issue number or row count riding an error message must not classify
        # as a rate limit (e.g. "row 4290 malformed" contains no HTTP-429 shape).
        self.assertFalse(cal._tower_rate_limited(RuntimeError("row 4290 malformed")))
        self.assertFalse(cal._tower_rate_limited(RuntimeError("totalOpen=429")))


@unittest.skipUnless(HAVE_SIBLING, "sibling mcp_tower_client unavailable")
class TestClientRateLimitClass(unittest.TestCase):
    def test_rate_limited_subclass_zero_collateral_contract(self):
        """Existing except-clauses keep catching: subclass of ConnectionError."""
        self.assertTrue(issubclass(mtc.McpTowerRateLimitedError, mtc.McpTowerConnectionError))
        self.assertTrue(issubclass(mtc.McpTowerRateLimitedError, mtc.McpTowerError))

    def test_post_streamable_429_raises_rate_limited_class(self):
        client = mtc.McpTowerClient(server_url="https://tower.example")
        fake_session = unittest.mock.Mock()
        fake_session.post.return_value = _FakeResponse(429)
        client._http = fake_session
        with self.assertRaises(mtc.McpTowerRateLimitedError):
            client._post_streamable("tools/call", {}, expect_response=True)
        # বাংলা: একই কল সাধারণ connection-error-ও ধরতে পারে — subclass চুক্তি।
        try:
            client._post_streamable("tools/call", {}, expect_response=True)
        except mtc.McpTowerConnectionError:
            pass  # caught as the parent class: the zero-collateral contract
        else:
            self.fail("429 must still be catchable as McpTowerConnectionError")

    def test_post_streamable_503_stays_plain_connection_error(self):
        client = mtc.McpTowerClient(server_url="https://tower.example")
        fake_session = unittest.mock.Mock()
        fake_session.post.return_value = _FakeResponse(503)
        client._http = fake_session
        with self.assertRaises(mtc.McpTowerConnectionError) as ctx:
            client._post_streamable("tools/call", {}, expect_response=True)
        self.assertNotIsInstance(ctx.exception, mtc.McpTowerRateLimitedError)


class _FakeFloorClient:
    """Offline stand-in for the sibling client the floor probe drives.

    বাংলা: ফ্লোর-প্রোবের ট্রান্সপোর্ট হলো sibling ক্লায়েন্ট (requests.Session),
    cal.urllib.request.urlopen নয় — তাই প্যাচ পয়েন্ট ক্লায়েন্ট ক্লাস। ভুল
    প্যাচ-পয়েন্টে টেস্ট চালালে প্রোব আসল নেটওয়ার্কে যায় (live প্রমাণ
    2026-10-31: সত্যিকারের 429 Cloudflare 'Just a moment...' HTML চ্যালেঞ্জ
    বডি সহ ফেরত এসেছিল — throttling CDN-edge-এ বসে আছে)।
    """

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def connect(self) -> None:
        pass

    def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        raise self._exc


class TestFloorProbeRateLimitNote(unittest.TestCase):
    """Floor probe: 429-shaped failure ⇒ honest rate-limit note, not tower-down."""

    def _floor_note_with(self, exc: Exception) -> str:
        fake = lambda *a, **k: _FakeFloorClient(exc)  # noqa: E731
        with unittest.mock.patch.object(mtc, "McpTowerClient", fake):
            return cal._tower_queue_floor(timeout_s=6.0)

    def test_client_429_yields_rate_limited_note(self):
        note = self._floor_note_with(mtc.McpTowerRateLimitedError("HTTP 429"))
        self.assertIn("tower rate-limited", note)
        self.assertIn("429", note)
        self.assertIn("not tower-down", note)
        self.assertIn("P0-drainage gate (Invariant 5)", note)

    def test_client_503_keeps_legacy_tower_down_note(self):
        note = self._floor_note_with(mtc.McpTowerConnectionError("HTTP 503"))
        self.assertIn("tower board probe failed (McpTowerConnectionError)", note)
        self.assertNotIn("rate-limited", note)


class TestBoardFallbackRateLimitNote(unittest.TestCase):
    """Board fallback: 429 failure note carries the cause and the honest suffix."""

    def _board_note_with(self, exc: Exception) -> str:
        with unittest.mock.patch.object(cal.urllib.request, "urlopen", side_effect=exc):
            rows, note = cal._tower_board_rows(timeout_s=6.0)
        self.assertEqual(rows, [])
        return note

    def test_urllib_429_note_names_status_and_classification(self):
        note = self._board_note_with(_http_error_429())
        self.assertIn("tower board fallback failed", note)
        self.assertIn("429", note)
        self.assertIn("rate-limited, not tower-down", note)

    def test_non_429_note_carries_message_but_no_rate_limit_suffix(self):
        note = self._board_note_with(urllib.error.URLError("dns dead"))
        self.assertIn("tower board fallback failed (URLError: ", note)
        self.assertIn("dns dead", note)
        self.assertNotIn("rate-limited", note)


if __name__ == "__main__":
    unittest.main()
