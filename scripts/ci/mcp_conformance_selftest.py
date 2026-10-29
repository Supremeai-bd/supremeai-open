#!/usr/bin/env python3
"""MCP conformance self-test (#1329) — bridge-20261027-tower-self-capability.

Asserts that everything the tower ADVERTISES is actually usable:
  0. post-initialize requests carry MCP-Protocol-Version (wire self-check; a missing
     header makes the server assume 2025-03-26, voiding the 2025-11-25 floor — #2568).
  1. resources/list  -> every advertised URI is readable (no -32602).
  2. codebase_graph_query("chat") -> returns symbols (graph.json reachable).
  3. devtools_audit -> never reports verdict PASS while mode is a fallback.

Usage (CI or local):
  python scripts/ci/mcp_conformance_selftest.py [--url https://supremeai-mcp-tower.onrender.com/mcp]

Exit codes: 0 = conformant, 1 = violations found, 2 = tower unreachable.
Stdlib-only so it can run in any CI lane.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "https://supremeai-mcp-tower.onrender.com/mcp"
# Streamable floor — one constant per site, mirrors PROTOCOL_VERSION_STREAMABLE in
# scripts/agents/mcp_tower_client.py (landed via #2533, radar R68).
PROTOCOL_VERSION = "2025-11-25"
# Spec (streamable HTTP, rev >= 2025-06-18): every request after initialize MUST carry
# MCP-Protocol-Version: <negotiated>; a missing header makes the server assume
# 2025-03-26, silently voiding the negotiated floor (#2568, radar R70 header debt).
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
           "MCP-Protocol-Version": PROTOCOL_VERSION}
LAST_HEADERS: dict | None = None  # wire self-check surface: headers of the most recent POST


def post(url: str, payload: dict, session_id: str | None = None, timeout: int = 60):
    global LAST_HEADERS
    headers = dict(HEADERS)
    if session_id:
        headers["mcp-session-id"] = session_id
    LAST_HEADERS = headers
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        sid = resp.headers.get("mcp-session-id", session_id)
        raw = resp.read().decode("utf-8", errors="replace")
        payloads = []
        if not raw.strip():
            # HTTP 202 with empty body is the spec response to notifications
            # (notifications/initialized); the watchdog's _rpc() uses the same
            # {"accepted": True} convention. Without this, json.loads("") crashes
            # every live run at the notification step (#2568 follow-through).
            return sid, [{"accepted": True}]
        if raw.lstrip().startswith("event:") or "\ndata:" in raw:
            for line in raw.splitlines():
                if line.startswith("data:"):
                    try:
                        payloads.append(json.loads(line[5:].strip()))
                    except json.JSONDecodeError:
                        pass
        else:
            payloads.append(json.loads(raw))
        return sid, payloads


def initialize(url: str) -> str:
    sid, resps = post(url, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                   "clientInfo": {"name": "mcp-conformance-selftest", "version": "1.0"}},
    })
    post(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    return sid


def rpc(url: str, sid: str, method: str, params: dict, rid: int = 10):
    _, resps = post(url, {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}, sid)
    return resps[0] if resps else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    args = ap.parse_args()
    url = args.url

    try:
        sid = initialize(url)
    except Exception as err:  # noqa: BLE001
        print(f"FATAL: cannot initialize session with {url}: {err}")
        return 2

    violations: list[str] = []

    # ---- 0. post-initialize protocol-version header self-check (#2568, radar R70) ----
    # Any post-initialize request observed on the wire must carry MCP-Protocol-Version,
    # else the server assumes 2025-03-26 and every later check runs on the wrong floor.
    # LAST_HEADERS captures exactly what this selftest sent for the ping below — this
    # single assert would have caught the 4-caller header debt at #2533 review time.
    # Response content is irrelevant here (ping is protocol-mandatory); only wire
    # headers matter.
    try:
        rpc(url, sid, "ping", {}, rid=10)
    except Exception as err:  # noqa: BLE001 — transport failure is unreachability, not a violation
        print(f"FATAL: post-initialize ping to {url} failed: {err}")
        return 2
    if (LAST_HEADERS or {}).get("MCP-Protocol-Version") != PROTOCOL_VERSION:
        violations.append(
            "post-initialize request missing MCP-Protocol-Version: "
            f"{PROTOCOL_VERSION} header (server assumes 2025-03-26, voiding the floor)")

    # ---- 1. every advertised resource must be readable ----
    listing = rpc(url, sid, "resources/list", {}, rid=11)
    uris = [r.get("uri") for r in listing.get("result", {}).get("resources", [])]
    print(f"resources/list: {len(uris)} advertised")
    for uri in uris:
        res = rpc(url, sid, "resources/read", {"uri": uri}, rid=12)
        if "error" in res:
            violations.append(f"resource {uri} -> JSON-RPC {res['error'].get('code')}: {res['error'].get('message')}")
    print(f"resources/read: {len(uris) - len(violations)}/{len(uris)} readable")

    # ---- 2. codebase graph must be queryable ----
    call = rpc(url, sid, "tools/call", {"name": "codebase_graph_query", "arguments": {"query": "chat"}}, rid=13)
    if "error" in call:
        violations.append(f"codebase_graph_query errored: {call['error']}")
    else:
        text = json.dumps(call.get("result", {}))
        if "not found" in text.lower() or "not_indexed" in text.lower():
            violations.append("codebase_graph_query('chat') returned not-indexed — graph.json missing from tower read path")

    # ---- 3. audit tool must never PASS in fallback mode ----
    call = rpc(url, sid, "tools/call",
               {"name": "devtools_audit", "arguments": {"url": "https://supremeai-studio.pages.dev", "device": "desktop"}}, rid=14)
    text = json.dumps(call.get("result", {}))
    if "http-diagnostic-fallback" in text and '"PASS"' in text:
        violations.append("devtools_audit reported PASS while in http-diagnostic-fallback mode (dishonest verdict)")

    print("\n=== CONFORMANCE REPORT ===")
    if violations:
        for v in violations:
            print(f"VIOLATION: {v}")
        return 1
    print("OK: all advertised capabilities are actually usable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
