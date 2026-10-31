#!/usr/bin/env python3
"""Pin + behavior: scan-B transport resilience — tower fallback for the merged-landing fetch.

Live anatomy (GLM Agent 22, Job 486813, 2026-10-30): one session, same board
state, 15 minutes apart — pick run 1 demoted #2792 (merged #3209 cites
"for #2792"), pick run 2 SERVED #2792 again because the single unauthenticated
api.github.com fetch had gone dark (shared cloud-egress IP, 60 req/h budget
split across many concurrent agents), and the fail-open contract served the
premise-delivered row a second time — a whole agent cycle burned on manual
re-verification. The board query solved this exact defect class with the
zero-credential tower fallback (_tower_board_rows); scan B now carries the
same fallback (REST first, tower second).

Contract preserved (test_premise_delivered_demotion.py pins untouched):
  - fail-open: REST dark + tower dark ⇒ the row is served (the filter can
    only REMOVE a dispatch, never block one — the #3050-family contract);
  - merged-only signal: the tower fallback maps mergedAt→merged_at and adds
    no new demotion class; closed-unmerged rows still never demote;
  - one fetch per pick run: the process-level cache still absorbs both the
    success and the failure (later candidates never re-network).

Pins here (zero network — transport functions are patched fakes):
  1. REST dark + tower rows ⇒ demotion note names the citing PR (fallback
     actually revives scan B).
  2. REST dark + tower dark ⇒ serve (fail-open preserved end-to-end).
  3. Cache: the fetch path runs at most once per process across candidates —
     success path and failure path both cached.
  4. Mapper purity: mergedAt→merged_at, body defaults "", malformed and
     number-less rows dropped, non-list payload ⇒ [].
  5. Parse purity: SSE data-line and plain-JSON tower bodies both parse;
     id-mismatched and error envelopes ignored; garbage text ⇒ [].
  6. The tower probe is capped by the hard join: a stuck transport raises
     TimeoutError (which the fail-open layer serves) instead of hanging the
     pick path — skipped automatically where the sibling client cannot be
     imported (the probe's first step).
  7. AST pin: _fetch_merged_landing_prs still wired as the live fetcher —
     _probe_premise_delivered keeps handing it to the note unchanged.

Dual-mode: runs under both `python3 -m unittest` and `pytest`.
"""

from __future__ import annotations

import ast
import json
import sys
import unittest
import unittest.mock
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal


def _row(number: int, body: str = "Evidence-only note. No promised artifact here.") -> dict:
    return {
        "number": number,
        "title": f"row {number}",
        "labels": [{"name": "status:unclaimed"}],
        "body": body,
    }


def _pr(number: int, title: str, merged_at: str | None = "2026-10-30T09:00:00Z", body: str | None = None) -> dict:
    return {"number": number, "title": title, "merged_at": merged_at, "body": body}


def _reset_landing_cache() -> None:
    cal._LANDING_FETCH_DONE = False
    cal._LANDING_ROWS = []


class _LandingCacheIsolated(unittest.TestCase):
    def setUp(self):
        _reset_landing_cache()
        self.addCleanup(_reset_landing_cache)


class TestFallbackRevivesScanB(_LandingCacheIsolated):
    def test_rest_dark_tower_rows_demote(self):
        """REST 403 + tower closed-PR window ⇒ scan B demotes on the title citation."""
        raw_tower_rows = [
            {"number": 3209, "title": "feat(bridge): Identity registration + run worklog for #2792", "state": "closed", "mergedAt": "2026-10-30T10:54:00Z"},
        ]
        with unittest.mock.patch.object(
            cal, "_rest_merged_landing_prs", side_effect=RuntimeError("HTTP Error 403: rate limit")
        ), unittest.mock.patch.object(
            cal, "_tower_merged_landing_prs", return_value=cal._map_tower_landing_rows(raw_tower_rows)
        ) as tower:
            note = cal._premise_delivered_note(_row(2792), tree_root=Path("/nonexistent"))
        self.assertIsNotNone(note)
        self.assertIn("premise-delivered", note)
        self.assertIn("#3209", note)
        self.assertIn("for #2792", note)
        tower.assert_called_once_with(cal.MERGED_LANDING_WINDOW)

    def test_rest_dark_tower_dark_serves_fail_open(self):
        """Both transports dark ⇒ the exception reaches the note's fail-open layer ⇒ serve."""

        def boom(per_page):
            raise RuntimeError("rate limited")

        with unittest.mock.patch.object(cal, "_rest_merged_landing_prs", side_effect=RuntimeError("403")), unittest.mock.patch.object(
            cal, "_tower_merged_landing_prs", side_effect=RuntimeError("tower dark")
        ):
            self.assertIsNone(cal._premise_delivered_note(_row(2792), tree_root=Path("/nonexistent")))

    def test_rest_green_tower_never_called(self):
        """REST healthy ⇒ the fallback transport is not spent (latency + quota guard)."""
        with unittest.mock.patch.object(
            cal, "_rest_merged_landing_prs", return_value=[_pr(1, "receipt #2792 landing")]
        ) as rest, unittest.mock.patch.object(
            cal, "_tower_merged_landing_prs", side_effect=AssertionError("tower must not run when REST is green")
        ):
            note = cal._premise_delivered_note(_row(2792), tree_root=Path("/nonexistent"))
        rest.assert_called_once_with(cal.MERGED_LANDING_WINDOW)
        self.assertIsNotNone(note)

    def test_tower_closed_unmerged_still_serves(self):
        """The fallback adds no new demotion class: closed-unmerged tower rows never demote."""
        raw_tower_rows = [
            {"number": 3170, "title": "Recovery correction (report-only) for #2792", "state": "closed", "mergedAt": None},
        ]
        with unittest.mock.patch.object(cal, "_rest_merged_landing_prs", side_effect=RuntimeError("403")), unittest.mock.patch.object(
            cal, "_tower_merged_landing_prs", return_value=cal._map_tower_landing_rows(raw_tower_rows)
        ):
            self.assertIsNone(cal._premise_delivered_note(_row(2792), tree_root=Path("/nonexistent")))


class TestLandingCacheOnce(_LandingCacheIsolated):
    def test_success_path_cached_across_candidates(self):
        calls = []

        def rest(per_page):
            calls.append(per_page)
            return [_pr(3158, "R62 disposition — live-verified by receipt #2395")]

        with unittest.mock.patch.object(cal, "_rest_merged_landing_prs", side_effect=rest), unittest.mock.patch.object(
            cal, "_tower_merged_landing_prs", side_effect=AssertionError("tower must not run when REST is green")
        ):
            first = cal._fetch_merged_landing_prs(80)
            second = cal._fetch_merged_landing_prs(80)
        self.assertEqual(len(calls), 1)
        self.assertIs(first, second)

    def test_failure_path_cached_across_candidates(self):
        rest_calls, tower_calls = [], []

        def rest(per_page):
            rest_calls.append(per_page)
            raise RuntimeError("403")

        def tower(per_page):
            tower_calls.append(per_page)
            raise RuntimeError("tower dark")

        with unittest.mock.patch.object(cal, "_rest_merged_landing_prs", side_effect=rest), unittest.mock.patch.object(
            cal, "_tower_merged_landing_prs", side_effect=tower
        ):
            # বাংলা: প্রথম প্রার্থী দুই ট্রান্সপোর্টের ব্যর্থতা দেখে সৎ raise করে
            # (উপরের fail-open স্তর সেটাকে serve-এ নামায়)।
            with self.assertRaises(RuntimeError):
                cal._fetch_merged_landing_prs(80)
        self.assertEqual(len(rest_calls), 1)
        self.assertEqual(len(tower_calls), 1)
        # বাংলা: ব্যর্থতাও ক্যাশ হয় — পরের প্রার্থীরা নেটওয়ার্কে যায় না, খালি তালিকা পায়।
        self.assertEqual(cal._fetch_merged_landing_prs(80), [])
        self.assertEqual(len(rest_calls), 1)
        self.assertEqual(len(tower_calls), 1)


class TestTowerRowMapping(unittest.TestCase):
    def test_merged_at_camel_case_mapped(self):
        rows = cal._map_tower_landing_rows(
            [{"number": 3209, "title": "t", "state": "closed", "mergedAt": "2026-10-30T10:54:00Z"}]
        )
        self.assertEqual(rows[0]["merged_at"], "2026-10-30T10:54:00Z")

    def test_body_defaults_empty_and_state_defaults_closed(self):
        rows = cal._map_tower_landing_rows([{"number": 1, "title": "t"}])
        self.assertEqual(rows[0]["body"], "")
        self.assertEqual(rows[0]["state"], "closed")

    def test_malformed_and_numberless_rows_dropped(self):
        rows = cal._map_tower_landing_rows(
            [None, "garbage", {"title": "no number"}, {"number": 2, "title": "ok", "mergedAt": None}, 42]
        )
        self.assertEqual([r["number"] for r in rows], [2])

    def test_non_list_payload_maps_empty(self):
        self.assertEqual(cal._map_tower_landing_rows(None), [])
        self.assertEqual(cal._map_tower_landing_rows({"error": "x"}), [])
        self.assertEqual(cal._map_tower_landing_rows("nope"), [])


class TestTowerPayloadParsing(unittest.TestCase):
    CALL_ID = "cal-landing-fallback-1"

    def _sse_body(self, rows, call_id=CALL_ID):
        inner = json.dumps({"jsonrpc": "2.0", "id": call_id, "result": {"content": [{"type": "text", "text": json.dumps(rows)}]}})
        return f"event: message\ndata: {inner}\n"

    def test_sse_shape_parses(self):
        body = self._sse_body([{"number": 7, "title": "x"}])
        self.assertEqual([r["number"] for r in cal._parse_tower_landing_payload(body, self.CALL_ID)], [7])

    def test_plain_json_shape_parses(self):
        payload = {"jsonrpc": "2.0", "id": self.CALL_ID, "result": {"content": [{"type": "text", "text": "[]"}]}}
        self.assertEqual(cal._parse_tower_landing_payload(json.dumps(payload), self.CALL_ID), [])

    def test_id_mismatch_and_error_envelopes_ignored(self):
        other = json.dumps({"jsonrpc": "2.0", "id": "nope", "result": {"content": [{"type": "text", "text": "[1]"}]}})
        err = json.dumps({"jsonrpc": "2.0", "id": self.CALL_ID, "error": {"code": -1, "message": "x"}})
        body = f"data: {other}\ndata: {err}\n"
        self.assertEqual(cal._parse_tower_landing_payload(body, self.CALL_ID), [])

    def test_garbage_text_maps_empty_never_raises(self):
        for bad in ("", "not json", "event: ping", "{broken", 42, None, b"bytes"):
            self.assertEqual(cal._parse_tower_landing_payload(bad, self.CALL_ID), [])


class TestTowerProbeHardCap(unittest.TestCase):
    def setUp(self):
        # Test-isolation guard: _TOWER_ROSTER_GATE_CACHE is a PROCESS-level cache
        # (#4132's U6 root fix — "permanent tool-absence" is cached for the whole
        # boot). In one pytest session that boot spans every simulated tower in
        # the suite, so a note primed by an earlier test (e.g. the -32602
        # simulations in test_failed_pr_audit_honesty) makes the probe below
        # early-return BEFORE any transport — no wedged urlopen, no TimeoutError,
        # red that only reproduces in the full suite (order-dependent, observed
        # 2026-10-31 at 35a72f6). This probe pins the TRANSPORT hard-join, so it
        # must start with a cold gate: reset the cache, don't weaken the pin.
        cal._TOWER_ROSTER_GATE_CACHE.clear()

    def test_stuck_transport_capped_by_hard_join(self):
        """A wedged tower probe must raise TimeoutError, never hang the pick path."""
        try:
            import mcp_tower_client  # noqa: F401 — the probe's first step
        except ImportError:
            self.skipTest("sibling mcp_tower_client unavailable in this environment")

        def _stuck(*args, **kwargs):
            import time

            time.sleep(5.0)

        with unittest.mock.patch.object(cal.urllib.request, "urlopen", side_effect=_stuck):
            with self.assertRaises(TimeoutError):
                cal._tower_merged_landing_prs(80, timeout_s=0.3)


class TestFetcherWiring(unittest.TestCase):
    def test_note_defaults_to_fetcher_and_fetcher_keeps_rest_first(self):
        """AST pin: _premise_delivered_note's default fetch path still lands on
        _fetch_merged_landing_prs, and that fetcher's first transport stays the
        REST call with the tower strictly as the second (order is the contract:
        REST green ⇒ tower never spent)."""
        src = Path(cal.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        note_source = ""
        fetcher_source = ""
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_premise_delivered_note":
                note_source = ast.unparse(node)
            if isinstance(node, ast.FunctionDef) and node.name == "_fetch_merged_landing_prs":
                fetcher_source = ast.unparse(node)
        self.assertIn("_fetch_merged_landing_prs", note_source)
        rest_pos = fetcher_source.find("_rest_merged_landing_prs(")
        tower_pos = fetcher_source.find("_tower_merged_landing_prs(")
        self.assertGreater(rest_pos, -1, "REST transport must stay present")
        self.assertGreater(tower_pos, rest_pos, "tower fallback must come after the REST attempt")


if __name__ == "__main__":
    unittest.main()
