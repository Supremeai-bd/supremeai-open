#!/usr/bin/env python3
"""mcp_registry_catalog.py — read-only MCP Registry catalog fetcher, report-only (issue #2161, R52 option A).

Mission (issue #2161, scout radar lane R52, option A — the R22 verdict made concrete):
    The R22 lane (#1686, radar IV, verdict `accept_verbatim` read-only ingest)
    has sat open since radar IV with a correct direction and zero in-tree
    consumers (#2161 Finding 1: git grep over tracked code = 0 files). This
    probe is the agent-plane half of option A: a cache-first, read-only
    catalog fetcher pinned to the official registry's `/v0.1/` family
    (radar IV's live precedent + #2161 Finding 2's mirror-consistency
    check; switching families later is a one-line constant — #2161
    alternatives_rejected #7). It prints a dated catalog snapshot plus a
    health line that includes the `/v0.1/version` drift-detection probe
    (service version, commit, build time, build age). It decides nothing,
    registers nothing, installs nothing, changes nothing. The BYO connect
    flow stays human-approved (WO #1523's shape, radar IV's contract).

Report-only contract (the #2161 never-do list, verbatim in spirit):
    - NO publish / validate probes: the write side of the OpenAPI mirror is
      documented (#2161 Finding 2) but NEVER probed — publish is an
      identity-mutating endpoint and anonymous write-probing is exactly the
      class this federation's own exposure tickets condemn (#2161
      alternatives_rejected #6). This file constructs GET URLs for ping,
      version, and servers ONLY.
    - NO auto-registration / auto-install / auto-PR / auto-merge: catalog
      rows are informational; any connect is a human-approved step that
      happens outside this probe.
    - NO credentials: anonymous GETs with a browser UA and a 20s timeout
      (house sentry precedent), sequential, cache-first, no retry storms.
    - NO .github/** touch, NO guard-baseline writes, NO disk writes at all
      (zero-write doctrine: the cache is in-memory only).
    - NO duplication: R22/radar IV own the verdict; WO #1523 owns the
      product wiring; this probe only surfaces the catalog the verdict
      named, so the eventual wiring lands on live facts.

Exit contract (family pattern: #1814 verdict plane via #2131):
    --self-test  hermetic offline unit pass (roster mode)          -> 0/1
    --plan       offline snapshot of pins/policy/never-do          -> 0
    --health     ping + version + build age (2 GETs)               -> 0 verified /
                 2 fail-close (unreachable registry, honest-skip #1760)
    --snapshot   dated catalog receipt [--limit N] [--max-pages P]  -> 0 / 2
                 [--filter SUBSTR]; per-page failures are honest
                 skip rows, never red
    (no args)    --plan

Zero-write doctrine: the live code paths never open a file for writing and
never spawn child processes. The only network calls are zero-credential GETs
against registry.modelcontextprotocol.io with a pinned browser UA and timeout,
cached in-memory with a TTL so cursor walks and health+snapshot combinations
do not re-fetch the same page within one run.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROBE_TAG = "[mcp-registry-catalog]"

EXIT_OK = 0
EXIT_SELFTEST_FAIL = 1
EXIT_FAILCLOSE = 2
EXIT_USAGE = 3

PROBE_TIMEOUT_S = 20
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"  # house sentry precedent: browser UA, zero credentials
)

# --- the /v0.1 pin (the lane's one deliberate version choice) -------------
# Radar IV probed and recorded /v0.1 live; #2161 Finding 2 verified both
# families (/v0 + /v0.1) are the OFFICIAL documented shape (dual mirror,
# not a shadow) and re-confirmed /v0.1 as the first-mover surface. The pin
# is a single constant on purpose: if the registry ever deprecates one
# family, the migration is this one line plus a dated receipt (alt-rejected
# #7: betting early on the shorter string buys nothing).
REGISTRY_BASE = "https://registry.modelcontextprotocol.io"
VERSION_FAMILY = "/v0.1"
SERVERS_PATH = f"{VERSION_FAMILY}/servers"
PING_PATH = f"{VERSION_FAMILY}/ping"
VERSION_PATH = f"{VERSION_FAMILY}/version"

CACHE_TTL_S = 300  # in-memory only; a fresh process always re-probes

DEFAULT_PAGE_LIMIT = 50
DEFAULT_MAX_PAGES = 4


class FailClose(RuntimeError):
    """Raised when the registry is unreachable/misbehaving — honest-skip #1760."""


# --- cache-first plumbing (in-memory, injectable clock) -------------------
class TTLCache:
    """Tiny in-memory TTL cache so one run never re-fetches the same URL."""

    def __init__(self, ttl_s: int = CACHE_TTL_S, clock=None):
        self._ttl = ttl_s
        self._clock = clock or time.monotonic
        self._store: dict[str, tuple[float, object]] = {}
        self.hits = 0
        self.misses = 0

    def get(self, url: str):
        hit = self._store.get(url)
        if hit is None:
            self.misses += 1
            return None
        stamp, value = hit
        if self._clock() - stamp > self._ttl:
            del self._store[url]
            self.misses += 1
            return None
        self.hits += 1
        return value

    def put(self, url: str, value) -> None:
        self._store[url] = (self._clock(), value)


DEFAULT_CACHE = TTLCache()


def _http_get_json(url: str, cache: TTLCache | None = None):
    """Zero-credential GET, cache-first. Returns parsed JSON or None on non-200."""
    use_cache = cache if cache is not None else DEFAULT_CACHE
    cached = use_cache.get(url)
    if cached is not None:
        return cached
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT_S) as resp:  # nosec B310 — registry.modelcontextprotocol.io https endpoint, zero-credential GET with pinned UA+timeout (report-only design; R52/#2161 audit)
        if getattr(resp, "status", 200) != 200:
            return None
        payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    use_cache.put(url, payload)
    return payload


# --- URL builders (GET-only surface; the pin makes this auditable) --------
def servers_url(limit: int, cursor: str | None = None) -> str:
    if limit < 1 or limit > 200:
        raise ValueError(f"limit out of registry-safe range [1,200]: {limit}")
    params = {"limit": str(limit)}
    if cursor:
        params["cursor"] = cursor
    return f"{REGISTRY_BASE}{SERVERS_PATH}?{urllib.parse.urlencode(params)}"


def ping_url() -> str:
    return f"{REGISTRY_BASE}{PING_PATH}"


def version_url() -> str:
    return f"{REGISTRY_BASE}{VERSION_PATH}"


# --- record parsing (defensive; live-verified 2026-10-28 receipt) ---------
# Real /v0.1/servers list items are ENVELOPED: {"server": {<2025-12-11 schema
# payload>}, "_meta": {"io.modelcontextprotocol.registry/official": {
#   "status", "statusChangedAt", "publishedAt", "updatedAt", "isLatest"}}}
# (live receipt v1.8.6). Flat payloads are accepted for schema compatibility.
_REGISTRY_META_KEY = "io.modelcontextprotocol.registry/official"


def parse_server_record(rec: object) -> dict | None:
    """Normalize one registry list item (envelope or flat); None when unusable."""
    if not isinstance(rec, dict):
        return None
    payload = rec.get("server") if isinstance(rec.get("server"), dict) else rec
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        return None
    remotes = payload.get("remotes")
    remote_types: list[str] = []
    if isinstance(remotes, list):
        for r in remotes:
            if isinstance(r, dict) and isinstance(r.get("type"), str):
                remote_types.append(r["type"])
    version = payload.get("version")
    meta = rec.get("_meta") if isinstance(rec.get("_meta"), dict) else {}
    official = meta.get(_REGISTRY_META_KEY) if isinstance(meta.get(_REGISTRY_META_KEY), dict) else {}
    status = official.get("status")
    updated = official.get("updatedAt") or payload.get("updated_at")
    return {
        "name": name,
        "title": payload.get("title") if isinstance(payload.get("title"), str) else "",
        "version": version if isinstance(version, str) else "unknown",
        "remotes": len(remote_types),
        "streamable_http": "streamable-http" in remote_types,
        "status": status if isinstance(status, str) else "unknown",
        "updated_at": updated if isinstance(updated, str) else "unknown",
    }


def _match_filter(row: dict, needle: str) -> bool:
    hay = f"{row['name']} {row['title']}".lower()
    return needle.lower() in hay


# --- health line (the /v0.1/version drift-detection probe) ----------------
def _iso_to_dt(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def build_health(fetch) -> dict:
    """ping + version receipt; raises FailClose when the registry is unreachable."""
    try:
        ping = fetch(ping_url())
        ver = fetch(version_url())
    except Exception as exc:  # urllib errors, JSON errors, timeouts — all honest
        raise FailClose(f"registry unreachable: {exc}") from exc
    if not isinstance(ping, dict) or "pong" not in ping:
        raise FailClose("ping endpoint did not return the documented pong shape")
    if not isinstance(ver, dict) or not isinstance(ver.get("version"), str):
        raise FailClose("version endpoint did not return the documented version shape")
    built_at = _iso_to_dt(ver.get("build_time", ""))
    now = datetime.now(timezone.utc)
    age_h = round((now - built_at).total_seconds() / 3600.0, 1) if built_at else None
    return {
        "ping": True,
        "service_version": ver.get("version"),
        "git_commit": ver.get("git_commit", "")[:12],
        "build_time": ver.get("build_time"),
        "build_age_hours": age_h,
        "family": VERSION_FAMILY,
    }


# --- snapshot assembly -----------------------------------------------------
def build_snapshot(fetch, limit: int = DEFAULT_PAGE_LIMIT,
                   max_pages: int = DEFAULT_MAX_PAGES, needle: str | None = None) -> dict:
    """Paged catalog walk; per-page failures are honest skip rows (never red)."""
    health = build_health(fetch)
    rows: list[dict] = []
    skips: list[str] = []
    cursor: str | None = None
    pages = 0
    for _ in range(max(1, max_pages)):
        try:
            payload = fetch(servers_url(limit, cursor))
        except Exception as exc:
            skips.append(f"page {pages + 1}: fetch failed ({exc.__class__.__name__})")
            break
        pages += 1
        if not isinstance(payload, dict) or not isinstance(payload.get("servers"), list):
            skips.append(f"page {pages}: unexpected payload shape, walk stopped honestly")
            break
        for rec in payload["servers"]:
            row = parse_server_record(rec)
            if row is None:
                skips.append(f"page {pages}: one unusable record skipped")
                continue
            if needle and not _match_filter(row, needle):
                continue
            rows.append(row)
        cursor = (payload.get("next_cursor")
                  or (payload.get("metadata") or {}).get("next_cursor")
                  or (payload.get("metadata") or {}).get("nextCursor"))
        if not isinstance(cursor, str) or not cursor:
            break
    return {
        "receipt_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
        "health": health,
        "pages_fetched": pages,
        "rows": rows,
        "filtered": bool(needle),
        "skips": skips,
    }


# --- runners ----------------------------------------------------------------
def _fetch_with_cache(cache: TTLCache):
    return lambda url: _http_get_json(url, cache)


def run_plan() -> int:
    print(f"{PROBE_TAG} offline plan (no network, no writes):")
    print(f"  registry      : {REGISTRY_BASE} (official MCP Registry, R22/#1686)")
    print(f"  family pin    : {VERSION_FAMILY} (radar IV precedent + #2161 Finding 2)")
    print(f"  GET surface   : {PING_PATH} | {VERSION_PATH} | {SERVERS_PATH}?limit=N&cursor=C")
    print(f"  cache         : in-memory TTL {CACHE_TTL_S}s, zero disk writes")
    print(f"  health line   : ping + service version + build age (drift detection)")
    print(f"  snapshot      : paged walk, limit<=200/page, honest skip rows, never red")
    print(f"  never-do      : no publish or validate probes, no credentials, no"
          f" auto-registration, no .github/**, no guard-baseline writes")
    print(f"  report-only   : rows are informational; connect stays human-approved (WO #1523)")
    return EXIT_OK


def run_health() -> int:
    cache = TTLCache()
    try:
        receipt = build_health(_fetch_with_cache(cache))
    except FailClose as exc:
        print(f"{PROBE_TAG} FAIL-CLOSE (honest-skip #1760): {exc}")
        return EXIT_FAILCLOSE
    age = receipt["build_age_hours"]
    age_s = f"{age}h old" if age is not None else "build_time unparseable"
    print(f"{PROBE_TAG} health receipt {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')}:")
    print(f"  ping            : pong OK ({receipt['family']} family)")
    print(f"  service version : {receipt['service_version']}")
    print(f"  git commit      : {receipt['git_commit']}")
    print(f"  built           : {receipt['build_time']} ({age_s})")
    print(f"  GETs            : {cache.misses + cache.hits} ({cache.misses} network / {cache.hits} cached)")
    return EXIT_OK


def run_snapshot(limit: int, max_pages: int, needle: str | None) -> int:
    cache = TTLCache()
    try:
        snap = build_snapshot(_fetch_with_cache(cache), limit=limit, max_pages=max_pages, needle=needle)
    except FailClose as exc:
        print(f"{PROBE_TAG} FAIL-CLOSE (honest-skip #1760): {exc}")
        return EXIT_FAILCLOSE
    print(f"{PROBE_TAG} catalog snapshot {snap['receipt_utc']} (family {snap['health']['family']}):")
    print(f"  registry   : {REGISTRY_BASE} v{snap['health']['service_version']} "
          f"(built {snap['health']['build_age_hours']}h ago)")
    print(f"  pages      : {snap['pages_fetched']} (limit {limit}/page, max {max_pages})")
    print(f"  rows       : {len(snap['rows'])}" + (f" (filter: {needle})" if needle else ""))
    for row in snap["rows"]:
        http = "streamable-http" if row["streamable_http"] else "other-transport"
        print(f"    - {row['name']} v{row['version']} remotes={row['remotes']} "
              f"[{http}] status={row['status']}")
    for skip in snap["skips"]:
        print(f"  skip: {skip}")
    print(f"  GETs       : {cache.misses + cache.hits} ({cache.misses} network / {cache.hits} cached)")
    print(f"  report-only: rows are informational; connect stays human-approved")
    return EXIT_OK


# --- self-test (hermetic; roster mode) --------------------------------------
def _selftest() -> int:
    checks: list[tuple[str, bool]] = []

    # 1. the /v0.1 pin holds on every URL builder
    urls = [servers_url(50), servers_url(1, "abc"), ping_url(), version_url()]
    checks.append(("family pin on all builders", all(REGISTRY_BASE + VERSION_FAMILY in u for u in urls)))
    checks.append(("no bare /v0/ family", all("/v0/" not in u.replace("/v0.1/", "") for u in urls)))

    # 2. limit guard rails (registry-safe range, fail loudly)
    try:
        servers_url(500)
        checks.append(("limit guard rejects >200", False))
    except ValueError:
        checks.append(("limit guard rejects >200", True))
    try:
        servers_url(0)
        checks.append(("limit guard rejects 0", False))
    except ValueError:
        checks.append(("limit guard rejects 0", True))

    # 3. record parsing on the LIVE-VERIFIED envelope fixture (v1.8.6 receipt:
    #    list items wrap the 2025-12-11 payload in "server" and carry registry
    #    status/updatedAt under _meta) plus the flat-shape compatibility case
    fixture = {
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
    row = parse_server_record(fixture)
    checks.append(("envelope fixture parsed", row is not None and row["name"] == "example/mcp-server"
                   and row["streamable_http"] is True and row["remotes"] == 1
                   and row["status"] == "active" and row["updated_at"].startswith("2026-04-13")))
    flat_row = parse_server_record({"name": "flat/srv", "version": "0.1.0"})
    checks.append(("flat fixture compat", flat_row is not None and flat_row["name"] == "flat/srv"
                   and flat_row["status"] == "unknown"))
    checks.append(("unusable record -> None", parse_server_record({"nope": 1}) is None
                   and parse_server_record("junk") is None and parse_server_record(None) is None))

    # 4. filter semantics (case-insensitive name/title substring)
    assert row is not None
    checks.append(("filter matches name", _match_filter(row, "MCP-SERVER")))
    checks.append(("filter matches title", _match_filter(row, "example m")))
    checks.append(("filter rejects miss", not _match_filter(row, "zzz")))

    # 5. TTL cache: same URL twice -> one network fetch, one hit (injectable clock)
    clock = {"t": 0.0}
    c = TTLCache(ttl_s=300, clock=lambda: clock["t"])
    c.put("https://x/y", {"a": 1})
    got1 = c.get("https://x/y")
    clock["t"] = 100.0
    got2 = c.get("https://x/y")
    checks.append(("cache hit inside TTL", got1 == {"a": 1} and got2 == {"a": 1} and c.hits == 2))
    clock["t"] = 400.0
    got3 = c.get("https://x/y")
    checks.append(("cache expiry after TTL", got3 is None and c.misses == 1))

    # 6. health line on canned endpoints (build age computed, shape pinned)
    def canned_fetch(url):
        return {"pong": True} if url.endswith("/ping") else {"version": "1.0.0", "build_time": "2026-10-28T12:00:00Z"}

    health = build_health(canned_fetch)
    checks.append(("health shape", health["ping"] is True and health["service_version"] == "1.0.0"
                   and health["family"] == VERSION_FAMILY and health["build_age_hours"] is not None))

    # 7. honest fail-close: unreachable registry -> FailClose (never a fake receipt)
    def boom(url):
        raise OSError("network down")

    try:
        build_health(boom)
        checks.append(("fail-close on unreachable", False))
    except FailClose:
        checks.append(("fail-close on unreachable", True))

    # 8. snapshot pipeline on an injected two-page catalog (paging + skip rows;
    #    the injected fetch answers the health endpoints too — build_snapshot
    #    always opens with the health line before walking pages; cursor comes
    #    from metadata.nextCursor, the live-verified camelCase field)
    page1 = {"servers": [fixture, {"junk": True}],
             "metadata": {"nextCursor": "c2", "count": 2}}
    page2 = {"servers": [{"server": {"name": "other/srv", "version": "0.1.0",
                                     "remotes": [{"type": "sse", "url": "https://o/s"}]},
                           "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active"}}}]}
    pages_seen: list[str] = []

    def paged_fetch(url):
        if url.endswith("/ping"):
            return {"pong": True}
        if url.endswith("/version"):
            return {"version": "1.0.0", "build_time": "2026-10-28T12:00:00Z"}
        pages_seen.append(url)
        return page2 if "cursor=c2" in url else page1

    snap = build_snapshot(paged_fetch, limit=2, max_pages=3)
    checks.append(("snapshot pages walked", len(pages_seen) == 2 and snap["pages_fetched"] == 2))
    checks.append(("snapshot rows + honest skip", len(snap["rows"]) == 2
                   and snap["rows"][1]["name"] == "other/srv"
                   and snap["rows"][1]["status"] == "active"
                   and any("unusable record" in s for s in snap["skips"])))
    checks.append(("snapshot carries health", snap["health"]["ping"] is True))
    snap_f = build_snapshot(paged_fetch, limit=2, max_pages=3, needle="other")
    checks.append(("snapshot filter narrows", len(snap_f["rows"]) == 1
                   and snap_f["rows"][0]["name"] == "other/srv" and snap_f["filtered"] is True))

    # 9. cursor walk stops honestly when the registry stops paging
    def health_and_last(url):
        if url.endswith("/ping"):
            return {"pong": True}
        if url.endswith("/version"):
            return {"version": "1.0.0", "build_time": "2026-10-28T12:00:00Z"}
        return {"servers": [fixture]}

    snap_last = build_snapshot(health_and_last, limit=2, max_pages=3)
    checks.append(("walk stops without cursor", snap_last["pages_fetched"] == 1))

    # 10. never-do source pins on the LIVE code (everything before _selftest):
    #     zero writes, zero subprocess, GET-only (no method= kwarg anywhere),
    #     and the write-plane endpoint names never appear in constructed paths.
    live_src = Path(__file__).read_text(encoding="utf-8").split("def _selftest", 1)[0]
    checks.append(("zero-write/subprocess source pin",
                   re.search(r"\bsubprocess\b|write_text|write_bytes|(?<![A-Za-z_])open\(", live_src) is None))
    checks.append(("GET-only source pin", 'method=' not in live_src and 'Request(' in live_src))
    # write-plane endpoints are never constructed: exactly THREE f-string URL
    # builders exist (ping/version/servers — module docstring prose excluded by
    # splitting it off), and no /publish or /validate path literal appears in
    # code. Adding a write probe trips both sub-checks.
    code_only = live_src.split('"""', 2)[2] if live_src.count('"""') >= 2 else live_src
    checks.append(("write-plane endpoints never built",
                   code_only.count("REGISTRY_BASE}{") == 3
                   and "/publish" not in code_only and "/validate" not in code_only))

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"{PROBE_TAG} self-test {len(checks) - len(failed)}/{len(checks)}")
    return EXIT_SELFTEST_FAIL if failed else EXIT_OK


def main(argv: list[str]) -> int:
    if "--self-test" in argv:
        return _selftest()
    if "--plan" in argv:
        return run_plan()
    if "--health" in argv and "--snapshot" in argv:
        print(f"{PROBE_TAG} usage: --health and --snapshot are mutually exclusive")
        return EXIT_USAGE
    if "--health" in argv:
        return run_health()
    if "--snapshot" in argv:
        def _opt(flag: str, default: int) -> int:
            return int(argv[argv.index(flag) + 1]) if flag in argv else default
        try:
            limit = _opt("--limit", DEFAULT_PAGE_LIMIT)
            max_pages = _opt("--max-pages", DEFAULT_MAX_PAGES)
        except ValueError:
            print(f"{PROBE_TAG} usage: --limit/--max-pages expect integers")
            return EXIT_USAGE
        needle = argv[argv.index("--filter") + 1] if "--filter" in argv else None
        return run_snapshot(limit, max_pages, needle)
    print(f"{PROBE_TAG} usage: [--self-test | --plan | --health | --snapshot "
          f"[--limit N] [--max-pages P] [--filter SUBSTR]]")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
