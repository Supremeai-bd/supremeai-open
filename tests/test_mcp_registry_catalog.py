#!/usr/bin/env python3
"""tests/test_mcp_registry_catalog.py — tests for scripts/ci/mcp_registry_catalog.py.

Issue #2161 R52 option A: the MCP Registry catalog fetcher is REPORT-ONLY.
These tests pin the four contracts that make that safe:

    1. Correctness  — URL builders (the /v0.1 pin, registry-safe limit range),
       record parsing (2025-12-11 schema shape), filter semantics, TTL cache
       behavior, health-line assembly, and the paged snapshot pipeline on
       injected fetchers (zero network in tests).
    2. Honesty      — unreachable registry fail-closes (exit 2, honest-skip
       #1760); per-page failures become explicit skip rows; unusable records
       are disclosed, never silently dropped, never fabricated.
    3. Never-do     — the live code never writes files, never spawns
       subprocesses, never issues anything but GETs, and never constructs
       the write-plane endpoints (/publish, /validate): exactly three
       f-string URL builders exist and no write-path literal appears in code.
    4. Exit contract — --plan is offline and exits 0; --self-test passes via
       the same process entry the roster invokes (subprocess parity).

Dual-mode: pytest AND stdlib plain runner (python3 tests/test_mcp_registry_catalog.py),
offline and deterministic — the house dual-mode doctrine (test_bump_candidate_probe pattern).
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "scripts" / "ci" / "mcp_registry_catalog.py"


def _load_probe():
    spec = importlib.util.spec_from_file_location("_registry_probe_under_test", PROBE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


P = _load_probe()

FIXTURE = {
    "server": {
        "name": "example/mcp-server",
        "title": "Example MCP Server",
        "version": "1.2.3",
        "remotes": [{"type": "streamable-http", "url": "https://example.com/mcp"}],
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
    },
    "_meta": {"io.modelcontextprotocol.registry/official": {
        "status": "active", "updatedAt": "2026-04-13T17:32:20.852269Z", "isLatest": True}},
}


def _health_fetch(url):
    return {"pong": True} if url.endswith("/ping") else {
        "version": "1.8.6", "git_commit": "5bfb0025deadbeef",
        "build_time": "2026-10-28T12:00:00Z"}


def _paged_fetch_factory(page1, page2=None):
    def fetch(url):
        if url.endswith("/ping"):
            return {"pong": True}
        if url.endswith("/version"):
            return {"version": "1.0.0", "build_time": "2026-10-28T12:00:00Z"}
        if page2 and "cursor=c2" in url:
            return page2
        return page1
    return fetch


class TestURLBuilders(unittest.TestCase):
    def test_family_pin_on_all_builders(self):
        urls = [P.servers_url(50), P.servers_url(1, "abc"), P.ping_url(), P.version_url()]
        for u in urls:
            self.assertTrue(u.startswith(P.REGISTRY_BASE + P.VERSION_FAMILY), u)

    def test_no_bare_v0_family(self):
        for u in (P.servers_url(5), P.ping_url(), P.version_url()):
            self.assertNotIn("/v0/", u.replace("/v0.1/", ""))

    def test_limit_guard_rejects_out_of_range(self):
        for bad in (0, -1, 201, 500):
            with self.assertRaises(ValueError):
                P.servers_url(bad)

    def test_cursor_encoding(self):
        u = P.servers_url(10, "abc 123/x?y")
        self.assertIn("limit=10", u)
        self.assertIn("cursor=abc+123%2Fx%3Fy", u)


class TestRecordParsing(unittest.TestCase):
    def test_envelope_fixture(self):
        row = P.parse_server_record(FIXTURE)
        self.assertEqual(row["name"], "example/mcp-server")
        self.assertEqual(row["version"], "1.2.3")
        self.assertTrue(row["streamable_http"])
        self.assertEqual(row["remotes"], 1)
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["updated_at"], "2026-04-13T17:32:20.852269Z")

    def test_flat_fixture_compat(self):
        row = P.parse_server_record({"name": "flat/srv", "version": "0.1.0"})
        self.assertEqual(row["name"], "flat/srv")
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["updated_at"], "unknown")

    def test_unusable_records_return_none(self):
        for junk in (None, "junk", 42, {}, {"nope": 1}, {"server": {"nope": 1}}, {"name": ""}):
            self.assertIsNone(P.parse_server_record(junk), repr(junk))

    def test_missing_optional_fields_defaulted(self):
        row = P.parse_server_record({"server": {"name": "bare/srv"}})
        self.assertEqual(row["version"], "unknown")
        self.assertEqual(row["remotes"], 0)
        self.assertFalse(row["streamable_http"])
        self.assertEqual(row["status"], "unknown")
        self.assertEqual(row["updated_at"], "unknown")

    def test_filter_semantics(self):
        row = P.parse_server_record(FIXTURE)
        self.assertTrue(P._match_filter(row, "MCP-SERVER"))
        self.assertTrue(P._match_filter(row, "example m"))
        self.assertFalse(P._match_filter(row, "zzz"))


class TestTTLCache(unittest.TestCase):
    def test_hit_inside_ttl_and_expiry_after(self):
        clock = {"t": 0.0}
        c = P.TTLCache(ttl_s=300, clock=lambda: clock["t"])
        c.put("k", {"a": 1})
        self.assertEqual(c.get("k"), {"a": 1})
        clock["t"] = 299.9
        self.assertEqual(c.get("k"), {"a": 1})
        self.assertEqual(c.hits, 2)
        clock["t"] = 300.1
        self.assertIsNone(c.get("k"))
        self.assertEqual(c.misses, 1)

    def test_unknown_key_is_miss(self):
        c = P.TTLCache()
        self.assertIsNone(c.get("never-put"))
        self.assertEqual(c.misses, 1)


class TestHealthLine(unittest.TestCase):
    def test_shape_and_age(self):
        h = P.build_health(_health_fetch)
        self.assertTrue(h["ping"])
        self.assertEqual(h["service_version"], "1.8.6")
        self.assertEqual(h["git_commit"], "5bfb0025deadbe"[:12])
        self.assertIsNotNone(h["build_age_hours"])
        self.assertEqual(h["family"], "/v0.1")

    def test_failclose_on_unreachable(self):
        def boom(url):
            raise OSError("network down")
        with self.assertRaises(P.FailClose):
            P.build_health(boom)

    def test_failclose_on_bad_pong_shape(self):
        with self.assertRaises(P.FailClose):
            P.build_health(lambda url: {"nope": 1})

    def test_failclose_on_bad_version_shape(self):
        def fetch(url):
            return {"pong": True} if url.endswith("/ping") else {"error": "x"}
        with self.assertRaises(P.FailClose):
            P.build_health(fetch)


class TestSnapshotPipeline(unittest.TestCase):
    PAGE1 = {"servers": [FIXTURE, {"junk": True}],
             "metadata": {"nextCursor": "c2", "count": 2}}
    PAGE2 = {"servers": [{"server": {"name": "other/srv", "version": "0.1.0",
                                     "remotes": [{"type": "sse", "url": "https://o/s"}]},
                           "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}}}]}

    def test_paging_walk_and_honest_skips(self):
        fetch = _paged_fetch_factory(self.PAGE1, self.PAGE2)
        snap = P.build_snapshot(fetch, limit=2, max_pages=3)
        self.assertEqual(snap["pages_fetched"], 2)
        self.assertEqual(len(snap["rows"]), 2)
        self.assertEqual(snap["rows"][1]["name"], "other/srv")
        self.assertEqual(snap["rows"][1]["status"], "active")
        self.assertTrue(any("unusable record" in s for s in snap["skips"]))
        self.assertTrue(snap["health"]["ping"])

    def test_filter_narrows_and_flags(self):
        fetch = _paged_fetch_factory(self.PAGE1, self.PAGE2)
        snap = P.build_snapshot(fetch, limit=2, max_pages=3, needle="other")
        self.assertEqual(len(snap["rows"]), 1)
        self.assertEqual(snap["rows"][0]["name"], "other/srv")
        self.assertTrue(snap["filtered"])

    def test_walk_stops_without_cursor(self):
        snap = P.build_snapshot(_paged_fetch_factory({"servers": [FIXTURE]}), limit=2, max_pages=3)
        self.assertEqual(snap["pages_fetched"], 1)

    def test_page_failure_is_honest_skip_not_exception(self):
        def fetch(url):
            if url.endswith("/ping"):
                return {"pong": True}
            if url.endswith("/version"):
                return {"version": "1.0.0", "build_time": "2026-10-28T12:00:00Z"}
            raise TimeoutError("slow registry")
        snap = P.build_snapshot(fetch, limit=2, max_pages=2)
        self.assertEqual(snap["pages_fetched"], 0)
        self.assertEqual(snap["rows"], [])
        self.assertTrue(any("fetch failed" in s for s in snap["skips"]))

    def test_bad_payload_shape_stops_walk_honestly(self):
        snap = P.build_snapshot(_paged_fetch_factory({"unexpected": 1}), limit=2, max_pages=2)
        self.assertTrue(any("unexpected payload shape" in s for s in snap["skips"]))

    def test_health_failclose_propagates(self):
        def fetch(url):
            raise OSError("registry down")
        with self.assertRaises(P.FailClose):
            P.build_snapshot(fetch, limit=2, max_pages=1)


class TestNeverDo(unittest.TestCase):
    def setUp(self):
        self.live_src = PROBE.read_text(encoding="utf-8").split("def _selftest", 1)[0]
        self.code_only = (self.live_src.split('"""', 2)[2]
                          if self.live_src.count('"""') >= 2 else self.live_src)

    def test_zero_write_and_no_subprocess(self):
        self.assertIsNone(re.search(
            r"\bsubprocess\b|write_text|write_bytes|(?<![A-Za-z_])open\(", self.live_src))

    def test_get_only_no_method_kwarg(self):
        self.assertNotIn("method=", self.live_src)
        self.assertIn("Request(", self.live_src)

    def test_exactly_three_url_builders(self):
        self.assertEqual(self.code_only.count("REGISTRY_BASE}{"), 3)

    def test_write_plane_paths_never_in_code(self):
        self.assertNotIn("/publish", self.code_only)
        self.assertNotIn("/validate", self.code_only)

    def test_family_pin_is_the_constant(self):
        self.assertEqual(P.VERSION_FAMILY, "/v0.1")


class TestExitContract(unittest.TestCase):
    def test_plan_is_offline_ok(self):
        self.assertEqual(P.main(["--plan"]), P.EXIT_OK)

    def test_usage_errors(self):
        self.assertEqual(P.main(["--health", "--snapshot"]), P.EXIT_USAGE)
        self.assertEqual(P.main(["--nonsense"]), P.EXIT_USAGE)

    def test_roster_parity_selftest_via_subprocess(self):
        r = subprocess.run([sys.executable, str(PROBE), "--self-test"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, P.EXIT_OK, r.stdout + r.stderr)
        self.assertIn("22/22", r.stdout)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
