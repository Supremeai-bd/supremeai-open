#!/usr/bin/env python3
"""Universal agent-slot heartbeat pinger (issue #1402).

Any agent tool that can run a subprocess can announce real-time liveness for
its assigned slot with this dependency-free script (stdlib only):

    # loop mode (default) — pings every 45s while the tool runs:
    python3 scripts/agents/heartbeat_ping.py --slot agent-1 --agent-id Antigravity

    # single ping (cron, CI job, session-start hook):
    python3 scripts/agents/heartbeat_ping.py --slot agent-2 --agent-id "Claude Code" --once

Transports (--mode):
    rest   Upstash REST (default). Env: UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN.
           This is the same Redis account the MCP tower, backend and dashboard use,
           so pings are visible on the /api/agents dashboard immediately.
    mcp    Ping via the MCP control tower `agent_heartbeat` tool (full inline
           handshake). Env: MCP_URL + MCP_API_KEY (+ optional client label).
           Use this when the tool is already MCP-connected but has no Redis creds.

Storage contract (must stay in sync with infrastructure/mcp-control-plane
src/registry/agent_heartbeat.ts and backend/core/agent_heartbeat.py):
    Key   supremeai:agent-heartbeat:<slot>      (slot = "agent-N")
    Value JSON {slot, agentId, source, clientId?, updatedAtMs, updatedAt}
    TTL   300s   (dashboard: ≤90s online, 90–300s stale, key gone → assigned)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

SLOT_RULES = "slot must match agent-N (e.g. agent-4)"
TTL_SECONDS = 300

# Multi-account failover chain (labels mirror the tower/dashboard contract).
# The canonical Upstash PRIMARY repeatedly hits its 500k/day ceiling — walkers
# try each configured account in order until one accepts the write.
_REST_CHAIN: list[tuple[str, str, str]] = [
    ("primary", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"),
    ("secondary", "UPSTASH_REDIS_SECONDARY_REST_URL", "UPSTASH_REDIS_SECONDARY_REST_TOKEN"),
    ("tertiary", "UPSTASH_REDIS_TERTIARY_REST_URL", "UPSTASH_REDIS_TERTIARY_REST_TOKEN"),
    ("quaternary", "UPSTASH_REDIS_QUATERNARY_REST_URL", "UPSTASH_REDIS_QUATERNARY_REST_TOKEN"),
    ("quinary", "UPSTASH_REDIS_QUINARY_REST_URL", "UPSTASH_REDIS_QUINARY_REST_TOKEN"),
]


def valid_slot(slot: str) -> bool:
    if not slot.startswith("agent-"):
        return False
    suffix = slot[len("agent-") :]
    return suffix.isdigit()


def build_payload(slot: str, agent_id: str, source: str, client_id: str | None) -> str:
    now_ms = int(time.time() * 1000)
    payload: dict = {
        "slot": slot,
        "agentId": agent_id,
        "source": source,
        "updatedAtMs": now_ms,
        "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now_ms / 1000)),
    }
    if client_id:
        payload["clientId"] = client_id
    return json.dumps(payload)


def ping_rest(slot: str, payload: str, url: str | None, token: str | None) -> str:
    """Write the heartbeat via the first reachable Upstash REST account.

    An explicit --url/--token pair (or the primary env vars) is tried FIRST,
    then the remaining configured chain — a quota-dead account never breaks
    the ping as long as any other account is configured.
    """
    attempts: list[tuple[str, str, str]] = []
    if url and token:
        attempts.append(("primary", url, token))
    seen = {u for _, u, _ in attempts}
    for label, url_key, token_key in _REST_CHAIN:
        u, t = os.environ.get(url_key, ""), os.environ.get(token_key, "")
        if u and t and u not in seen:
            attempts.append((label, u, t))
            seen.add(u)
    if not attempts:
        raise RuntimeError(
            "rest mode requires UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN "
            "(env or --url/--token); use --mode mcp if you only have tower creds"
        )

    key = f"supremeai:agent-heartbeat:{slot}"
    failures: list[str] = []
    for label, u, t in attempts:
        req = urllib.request.Request(
            u,
            data=json.dumps(["SET", key, payload, "EX", str(TTL_SECONDS)]).encode(),
            headers={"Authorization": f"Bearer {t}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                body = json.loads(res.read().decode())
            if body.get("error"):
                raise RuntimeError(body["error"])
            return label
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:120]
            failures.append(f"{label}: HTTP {exc.code} {detail}")
        except Exception as exc:  # noqa: BLE001 — failover must keep walking
            failures.append(f"{label}: {exc}")
    raise RuntimeError(f"all {len(attempts)} Redis account(s) rejected the ping: {' | '.join(failures)}")


def ping_mcp(slot: str, agent_id: str, mcp_url: str, api_key: str, client_label: str) -> str:
    """Full inline MCP handshake (initialize → initialized → tools/call)."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "MCP-Protocol-Version": "2025-03-26",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    endpoint = mcp_url.rstrip("/") + "/mcp"

    def post(body: dict, session: str | None = None):
        hdrs = dict(headers)
        if session:
            hdrs["Mcp-Session-Id"] = session
        req = urllib.request.Request(
            endpoint, data=json.dumps(body).encode(), headers=hdrs, method="POST"
        )
        return urllib.request.urlopen(req, timeout=30)

    init = post(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": client_label, "version": "1.0.0"},
            },
        }
    )
    session = init.headers.get("Mcp-Session-Id")
    init.read()

    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session).read()

    call = post(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "agent_heartbeat",
                "arguments": {"slot": slot, **({"agentId": agent_id} if agent_id else {})},
            },
        },
        session,
    )
    call.read()
    return "mcp"


def ping_once(args: argparse.Namespace) -> str:
    if not valid_slot(args.slot):
        raise ValueError(f"invalid {SLOT_RULES}: '{args.slot}'")
    payload = build_payload(args.slot, args.agent_id or args.slot, "cli", args.client_id)
    if args.mode == "mcp":
        mcp_url = args.mcp_url or os.environ.get("MCP_URL", "")
        api_key = args.api_key or os.environ.get("MCP_API_KEY", "")
        if not (mcp_url and api_key):
            raise RuntimeError("mcp mode requires MCP_URL + MCP_API_KEY (env or flags)")
        return ping_mcp(
            args.slot, args.agent_id or args.slot, mcp_url, api_key, args.client_label
        )
    url = args.url or os.environ.get("UPSTASH_REDIS_REST_URL", "")
    token = args.token or os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
    if not (url and token):
        raise RuntimeError(
            "rest mode requires UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN "
            "(env or --url/--token); use --mode mcp if you only have tower creds"
        )
    return ping_rest(args.slot, payload, url, token)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--slot", required=True, help="assigned slot id, e.g. agent-4")
    parser.add_argument("--agent-id", default=None, help="human-readable label, e.g. 'Cline'")
    parser.add_argument("--mode", choices=["rest", "mcp"], default="rest")
    parser.add_argument("--once", action="store_true", help="single ping then exit (default: loop)")
    parser.add_argument("--interval", type=int, default=45, help="seconds between pings (loop mode)")
    parser.add_argument("--url", default=None, help="Upstash REST URL (rest mode)")
    parser.add_argument("--token", default=None, help="Upstash REST token (rest mode)")
    parser.add_argument("--mcp-url", default=None, help="tower base URL (mcp mode)")
    parser.add_argument("--api-key", default=None, help="tower API key (mcp mode)")
    parser.add_argument("--client-id", default=None, help="optional audit attribution")
    parser.add_argument("--client-label", default="supremeai-heartbeat-pinger")
    args = parser.parse_args()

    if args.once:
        transport = ping_once(args)
        print(f"💓 heartbeat sent via {transport}: {args.slot} ({args.agent_id or args.slot})")
        return 0

    print(f"💓 pinging {args.slot} every {args.interval}s (Ctrl-C to stop)…", flush=True)
    while True:
        try:
            transport = ping_once(args)
            print(f"  ✅ {time.strftime('%H:%M:%S')} via {transport}", flush=True)
        except KeyboardInterrupt:
            print("👋 stopped — slot will degrade to 'assigned' within 90s", flush=True)
            return 0
        except (urllib.error.URLError, RuntimeError, ValueError) as exc:
            print(f"  ⚠️ {time.strftime('%H:%M:%S')} ping failed: {exc}", flush=True)
        time.sleep(max(15, args.interval))


if __name__ == "__main__":
    sys.exit(main())
