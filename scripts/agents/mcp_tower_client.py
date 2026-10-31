#!/usr/bin/env python3
"""MCP Tower Client — connects to SupremeAI Control Tower (no auth, public URL).

This is a PERMANENT solution: the MCP server URL is public (viewer mode only).
No credentials are stored in this file. Role can be elevated later from the
admin dashboard or database.

Usage:
    # Connect + register + heartbeat
    python scripts/agents/mcp_tower_client.py connect --name z.ai-1 --slot agent-3

    # One-shot heartbeat
    python scripts/agents/mcp_tower_client.py heartbeat --slot agent-3 --name z.ai-1

    # List all agents in the tower
    python scripts/agents/mcp_tower_client.py status

    # List available tools
    python scripts/agents/mcp_tower_client.py tools

    # Inspect a tool's argument contract WITHOUT probing it live (#GLM09-486738)
    python scripts/agents/mcp_tower_client.py schema bridge_submit_patch

    # Call any tool
    python scripts/agents/mcp_tower_client.py call system_summary

This file is committed to the repo (no secrets). Per-agent identity (name, slot)
is stored in a local gitignored file: .z-ai-config/agent-identity.json
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
from queue import Empty, Queue
from typing import Any

import requests

# ── Configuration ────────────────────────────────────────────────────────────

# AUDIT-FIX (CI fixer): removed hardcoded deployment URL from default value.
# The URL must be set via MCP_TOWER_URL env var. AGENTS.md Rule #19 references
# the URL in documentation — the actual code reads it from env.
def strip_endpoint_suffixes(url: str) -> str:
    """Return the Tower base origin from any documented URL form.

    #2317 (R60 lane, #2300 option A): the documented setup carries the /mcp
    endpoint suffix (dispatch mandate export form, repo-root mcp.json) while
    connect() appends MCP_SSE_PATH itself — the /mcp suffix must be stripped
    here or the join produces the dead path GET /mcp/sse (live 404) instead of
    GET /sse (200). Order-tolerant: /mcp, /sse, /mcp/sse and bare all resolve
    to the base origin; exact-suffix matching cannot corrupt /mcp-server.
    """
    return url.rstrip("/").removesuffix("/sse").removesuffix("/mcp")


def resolve_mcp_server_url() -> str:
    """Resolve MCP Control Tower URL from env or workspace mcp.json."""
    url = os.environ.get("MCP_TOWER_URL", os.environ.get("MCP_SERVER_URL", ""))
    if url:
        return strip_endpoint_suffixes(url)
    mcp_file = Path(__file__).resolve().parents[2] / "mcp.json"
    if mcp_file.exists():
        try:
            with open(mcp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                tower = data.get("mcpServers", {}).get("supremeai-control-tower", {})
                server_url = tower.get("url", "")
                if server_url:
                    return strip_endpoint_suffixes(server_url)
        except Exception:
            pass
    return "https://supremeai-mcp-tower.onrender.com"


MCP_SERVER_URL = resolve_mcp_server_url()
MCP_SSE_PATH = "/sse"
MCP_STREAMABLE_PATH = "/mcp"
# Protocol revisions: 2025-03-26 introduced Streamable HTTP; the streamable
# floor tracks the tower's verified max (2025-11-25, live ladder probe R68/#2530).
# The legacy SSE transport keeps negotiating the revision the old path always used.
PROTOCOL_VERSION_STREAMABLE = "2025-11-25"
PROTOCOL_VERSION_SSE = "2024-11-05"
REQUEST_TIMEOUT = 30
SSE_READ_TIMEOUT = 600
RESPONSE_WAIT = 15
HEARTBEAT_INTERVAL = 45  # seconds

# Per-agent identity file (gitignored)
IDENTITY_FILE = Path(os.environ.get("AGENT_IDENTITY_FILE", ".z-ai-config/agent-identity.json"))

# ── Errors ───────────────────────────────────────────────────────────────────


class McpTowerError(Exception):
    pass


class McpTowerConnectionError(McpTowerError):
    pass


class McpTowerRateLimitedError(McpTowerConnectionError):
    """HTTP 429 from the tower — the tower is UP and throttling, not down.

    বাংলা (GLM Agent 26, Job 486824, live প্রমাণ 2026-10-31T10:26Z): fleet-এর
    hourly cron সবাই একই :26 উইন্ডোতে tower প্রোব করে — tower জীবিত অবস্থাতেই
    429 দেয় (৩-উইন্ডো প্রোব: w1 bridge_work_queue OK rows=0, w2/w3 HTTP 429),
    কিন্তু এই শ্রেণি ছাড়া সেটা সাধারণ connection-error হয়ে যেত এবং লুপ মিথ্যা
    "tower-down/plane-dark" পাঠ দিত (r17 #4346 dark-cycle datum-এর আসল কারণ)।
    Subclass রাখার চুক্তি: প্রতিটি বিদ্যমান ``except McpTowerConnectionError``
    কল-সাইট অক্ষত থাকে (zero collateral), অথচ নোট-স্তর এখন 429-কে সৎভাবে
    "rate-limited, not tower-down" হিসেবে শ্রেণিবদ্ধ করতে পারে। 503 ইচ্ছাকৃতভাবে
    এই শ্রেণির বাইরে — সেটা সত্যিই cold-boot/unavailable হতে পারে।
    """

    pass


class McpTowerTimeoutError(McpTowerError):
    pass


class _LegacyFallback(Exception):
    """Internal signal: the Streamable HTTP attempt failed in a way the spec's
    transition algorithm answers with the legacy GET+SSE transport (#2307).
    Never escapes connect() — callers only ever see McpTowerError."""


# ── Identity management ────────────────────────────────────────────────────


def load_identity() -> dict[str, str]:
    """Load agent identity from local gitignored file."""
    if IDENTITY_FILE.exists():
        with open(IDENTITY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_identity(identity: dict[str, str]) -> None:
    """Save agent identity to local gitignored file."""
    IDENTITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(IDENTITY_FILE, "w", encoding="utf-8") as f:
        json.dump(identity, f, indent=2)
        f.write("\n")


def resolve_name(preferred: str | None = None) -> str:
    """Resolve agent name — use preferred, or from identity file, or generate."""
    identity = load_identity()
    if preferred:
        return preferred
    if identity.get("agent_name"):
        return identity["agent_name"]
    # Auto-generate based on environment
    env_type = os.environ.get("AGENT_TYPE", "z.ai")
    return f"{env_type}-1"


# ── MCP Tower SSE Client ────────────────────────────────────────────────────


class McpTowerClient:
    """Synchronous MCP client (no auth) — Streamable HTTP first, SSE fallback.

    Transport selection follows the MCP spec 2025-06-18 client transition
    algorithm (#2307): POST-first to the server's single endpoint; the legacy
    GET+SSE transport is the automatic fallback so no working configuration
    breaks during the fleet transition.
    """

    def __init__(
        self,
        server_url: str = MCP_SERVER_URL,
        sse_path: str = MCP_SSE_PATH,
        verbose: bool = False,
    ) -> None:
        self.server_url = server_url.rstrip("/")
        self.sse_path = sse_path if sse_path.startswith("/") else "/" + sse_path
        self.verbose = verbose
        self._session_id: str | None = None
        self._transport: str | None = None  # "streamable" | "sse" once connected
        self._message_endpoint: str | None = None
        self._sse_thread: threading.Thread | None = None
        self._sse_stop = threading.Event()
        self._http = requests.Session()
        self._response_queues: dict[str, Queue] = {}
        self._response_lock = threading.Lock()
        self._initialized = False
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(f"[mcp] {msg}", file=sys.stderr, flush=True)

    def connect(self) -> None:
        """Connect using the MCP spec 2025-06-18 client transition algorithm.

        #2307 (R61 lane, R60 option A): POST the InitializeRequest to the
        server URL first; only when that attempt fails (HTTP >= 400 or the
        request cannot be delivered) fall back to the legacy GET+SSE
        transport. A server that already speaks Streamable HTTP is used via
        its single endpoint; every configuration that works today keeps
        working through the fallback — the old transport is spec-blessed
        for exactly this transition posture.
        """
        if self._initialized:
            return
        try:
            self._connect_streamable()
        except _LegacyFallback as e:
            self._log(f"streamable unsupported ({e}); falling back to SSE")
            self._connect_sse()
        self._initialized = True

    def _connect_streamable(self) -> None:
        url = self.server_url + MCP_STREAMABLE_PATH
        init_id = str(uuid.uuid4())
        payload = {
            "jsonrpc": "2.0",
            "id": init_id,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION_STREAMABLE,
                "capabilities": {},
                "clientInfo": {"name": "supremeai-agent", "version": "1.0.0"},
            },
        }
        self._log(f"POST initialize (streamable): {url}")
        try:
            resp = self._http.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
        except requests.RequestException as e:
            raise _LegacyFallback(str(e)) from e
        if not (200 <= resp.status_code < 300):
            # Spec: HTTP 4xx → legacy transport. >=400 also covers 5xx here on
            # purpose: the fallback preserves every currently-working setup.
            raise _LegacyFallback(f"HTTP {resp.status_code}")
        sid = resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        self._transport = "streamable"
        try:
            result = self._parse_streamable_response(resp, expect_id=init_id)
        except Exception:
            self._transport = None
            self._session_id = None
            raise
        self._log(f"Server: {result.get('serverInfo', {})}" if isinstance(result, dict) else "Server: <streamable>")
        self._send_notification("notifications/initialized", {})

    def _connect_sse(self) -> None:
        sse_url = self.server_url + self.sse_path
        self._log(f"Opening SSE: {sse_url}")
        resp = self._http.get(
            sse_url,
            stream=True,
            timeout=(REQUEST_TIMEOUT, SSE_READ_TIMEOUT),
            headers={"Accept": "text/event-stream"},
        )
        if resp.status_code != 200:
            if resp.status_code == 429:
                raise McpTowerRateLimitedError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            raise McpTowerConnectionError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        self._sse_thread = threading.Thread(
            target=self._sse_reader, args=(resp,), daemon=True, name="mcp-sse"
        )
        self._sse_thread.start()
        deadline = time.time() + RESPONSE_WAIT
        while self._message_endpoint is None and time.time() < deadline:
            time.sleep(0.1)
        if self._message_endpoint is None:
            raise McpTowerConnectionError("No endpoint event received")
        self._log(f"Session: {self._session_id}")
        init = self._send_request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION_SSE,
                "capabilities": {},
                "clientInfo": {"name": "supremeai-agent", "version": "1.0.0"},
            },
        )
        self._log(f"Server: {init.get('serverInfo', {})}")
        self._send_notification("notifications/initialized", {})
        self._transport = "sse"

    def _parse_streamable_response(self, resp: requests.Response, expect_id: str | None) -> Any:
        """Parse a Streamable HTTP response body: JSON object or SSE stream."""
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "text/event-stream" in ctype:
            for raw in resp.iter_lines(decode_unicode=True):
                line = (raw or "").rstrip("\r")
                if not line.startswith("data:"):
                    continue
                data = line[5:].lstrip()
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict) or obj.get("id") != expect_id:
                    continue
                if "error" in obj:
                    err = obj["error"]
                    raise McpTowerError(f"RPC error {err.get('code')}: {err.get('message')}")
                return obj.get("result")
            raise McpTowerTimeoutError("streamable SSE body carried no matching response")
        try:
            obj = resp.json()
        except ValueError:
            return None  # empty body (e.g. bare 202) — nothing to parse
        if isinstance(obj, dict) and obj.get("id") == expect_id and "error" in obj:
            err = obj["error"]
            raise McpTowerError(f"RPC error {err.get('code')}: {err.get('message')}")
        return obj.get("result") if isinstance(obj, dict) else None

    def list_tools(self) -> list[dict[str, Any]]:
        return self._send_request("tools/list", {}).get("tools", [])

    def call_tool(self, name: str, arguments: dict | None = None) -> Any:
        return self._send_request("tools/call", {"name": name, "arguments": arguments or {}})

    def ping(self) -> bool:
        try:
            self._send_request("ping", {})
            return True
        except McpTowerError:
            return False

    def start_heartbeat(self, slot: str, agent_id: str) -> None:
        """Start background heartbeat loop (every 45s)."""
        def _loop():
            while not self._heartbeat_stop.is_set():
                try:
                    self.call_tool("agent_heartbeat", {"slot": slot, "agentId": agent_id})
                    self._log(f"heartbeat sent: {slot} / {agent_id}")
                except Exception as e:
                    self._log(f"heartbeat failed: {e}")
                self._heartbeat_stop.wait(HEARTBEAT_INTERVAL)

        self._heartbeat_thread = threading.Thread(
            target=_loop, daemon=True, name="mcp-heartbeat"
        )
        self._heartbeat_thread.start()

    def stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()

    def close(self) -> None:
        self.stop_heartbeat()
        self._sse_stop.set()
        self._initialized = False
        self._transport = None
        try:
            self._http.close()
        except Exception:
            pass

    def __enter__(self) -> "McpTowerClient":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _sse_reader(self, resp: requests.Response) -> None:
        event_type = None
        data_lines: list[str] = []
        try:
            for raw in resp.iter_lines(decode_unicode=True):
                if self._sse_stop.is_set():
                    break
                if raw is None:
                    continue
                line = raw.rstrip("\r")
                if line == "":
                    if event_type and data_lines:
                        self._dispatch(event_type, "\n".join(data_lines))
                    event_type = None
                    data_lines = []
                    continue
                if line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
        except Exception as e:
            if not self._sse_stop.is_set():
                self._log(f"SSE error: {e}")

    def _dispatch(self, event_type: str, data: str) -> None:
        if event_type == "endpoint":
            self._message_endpoint = self.server_url + data
            if "sessionId=" in data:
                self._session_id = data.split("sessionId=", 1)[1].split("&", 1)[0]
            self._log(f"endpoint: {self._message_endpoint}")
            return
        if event_type == "message":
            try:
                payload = json.loads(data)
            except json.JSONDecodeError:
                return
            mid = payload.get("id")
            if mid is None:
                return
            with self._response_lock:
                q = self._response_queues.get(mid)
            if q:
                q.put(payload)

    def _post_streamable(self, method: str, params: dict[str, Any], expect_response: bool) -> Any:
        url = self.server_url + MCP_STREAMABLE_PATH
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL_VERSION_STREAMABLE,
        }
        if self._session_id:
            headers["mcp-session-id"] = self._session_id
        if expect_response:
            mid = str(uuid.uuid4())
            payload = {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}
        else:
            mid = None
            payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self._log(f"-> {method} (streamable)")
        try:
            resp = self._http.post(url, json=payload, timeout=REQUEST_TIMEOUT, headers=headers)
        except requests.RequestException as e:
            raise McpTowerConnectionError(str(e)) from e
        if resp.status_code not in (200, 202):
            if resp.status_code == 429:
                raise McpTowerRateLimitedError(f"HTTP {resp.status_code}")
            raise McpTowerConnectionError(f"HTTP {resp.status_code}")
        if not expect_response:
            return None
        return self._parse_streamable_response(resp, expect_id=mid)

    def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        if self._transport == "streamable":
            return self._post_streamable(method, params, expect_response=True)
        if not self._message_endpoint:
            raise McpTowerConnectionError("Not connected")
        mid = str(uuid.uuid4())
        payload = {"jsonrpc": "2.0", "id": mid, "method": method, "params": params}
        q: Queue = Queue()
        with self._response_lock:
            self._response_queues[mid] = q
        self._log(f"-> {method}")
        try:
            r = self._http.post(
                self._message_endpoint,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
            if r.status_code not in (200, 202):
                with self._response_lock:
                    self._response_queues.pop(mid, None)
                if r.status_code == 429:
                    raise McpTowerRateLimitedError(f"HTTP {r.status_code}")
                raise McpTowerConnectionError(f"HTTP {r.status_code}")
        except requests.RequestException as e:
            with self._response_lock:
                self._response_queues.pop(mid, None)
            raise McpTowerConnectionError(str(e))
        try:
            rpc = q.get(timeout=RESPONSE_WAIT)
        except Empty:
            with self._response_lock:
                self._response_queues.pop(mid, None)
            raise McpTowerTimeoutError(f"Timeout: {method}")
        finally:
            with self._response_lock:
                self._response_queues.pop(mid, None)
        if "error" in rpc:
            err = rpc["error"]
            raise McpTowerError(f"RPC error {err.get('code')}: {err.get('message')}")
        return rpc.get("result")

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if self._transport == "streamable":
            self._post_streamable(method, params, expect_response=False)
            return
        if not self._message_endpoint:
            return
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        try:
            self._http.post(
                self._message_endpoint,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
        except Exception:
            pass


# ── CLI ──────────────────────────────────────────────────────────────────────


def _cli_main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="MCP Tower client — connect, heartbeat, call tools (no auth)"
    )
    parser.add_argument("--server", default=MCP_SERVER_URL)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ping", help="Check server connectivity")
    sub.add_parser("status", help="List all agents in the tower")
    sub.add_parser("tools", help="List available tools")

    # Root-cause fix (GLM Agent 09, Job 486738, incident PR bridge-20261030-test-x):
    # the tower ships a full JSON inputSchema for every tool via tools/list, but this
    # client never surfaced it — so agents learned argument shapes by calling live
    # tools with junk payloads. On state-mutating tools (bridge_submit_patch,
    # work_claim, ...) that files real work orders/PRs. `schema` reads the
    # declared contract offline: zero mutations, zero probe artifacts, ever.
    sch = sub.add_parser(
        "schema",
        help="Print a tool's full inputSchema from tools/list (use this, never junk-payload probing)",
    )
    sch.add_argument("tool_name")

    c = sub.add_parser("connect", help="Connect + register + start heartbeat")
    c.add_argument("--name", default=None, help="Agent name (default: from identity file)")
    c.add_argument("--slot", default=None, help="Agent slot (default: from identity file)")
    c.add_argument("--auto-register", action="store_true", default=False,
                   help="Auto-register: connect, send heartbeat, save identity, start loop (Rule #19)")

    hb = sub.add_parser("heartbeat", help="Send one heartbeat")
    hb.add_argument("--slot", required=True)
    hb.add_argument("--name", required=True)

    call_p = sub.add_parser("call", help="Call a tool")
    call_p.add_argument("tool_name")
    call_p.add_argument("arguments", nargs="?", default="{}")

    args = parser.parse_args()

    try:
        arguments = json.loads(args.arguments) if args.cmd == "call" else {}
    except json.JSONDecodeError as e:
        print(f"ERROR: invalid JSON arguments: {e}", file=sys.stderr)
        return 2

    client = McpTowerClient(server_url=args.server, verbose=args.verbose)
    try:
        client.connect()
    except McpTowerError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    try:
        if args.cmd == "ping":
            ok = client.ping()
            print(json.dumps({"ok": ok}, indent=2))
            return 0 if ok else 1

        if args.cmd == "status":
            result = client.call_tool("agent_status", {})
            text = result["content"][0]["text"] if isinstance(result, dict) and "content" in result else str(result)
            try:
                data = json.loads(text)
                slots = data.get("slots", [])
                print(f"Agents in tower: {len(slots)}")
                for s in slots:
                    print(f"  {s.get('slot','?'):<15} state={s.get('state','?'):<10} agentId={s.get('agentId','?')}")
            except json.JSONDecodeError:
                print(text)
            return 0

        if args.cmd == "tools":
            tools = client.list_tools()
            print(f"Total tools: {len(tools)}")
            for t in tools:
                print(f"  {t.get('name','?'):<40} {(t.get('description') or '')[:60]}")
            return 0

        if args.cmd == "schema":
            tools = client.list_tools()
            match = next((t for t in tools if t.get("name") == args.tool_name), None)
            if match is None:
                close = ", ".join(
                    t.get("name", "") for t in tools if args.tool_name in t.get("name", "")
                )
                print(f"ERROR: unknown tool: {args.tool_name}" + (f" (close: {close})" if close else ""), file=sys.stderr)
                return 1
            print(json.dumps(match.get("inputSchema", {}), indent=2, ensure_ascii=False))
            return 0

        if args.cmd == "connect":
            name = resolve_name(args.name)
            identity = load_identity()
            slot = args.slot or identity.get("slot", "agent-3")

            # AUDIT-FIX (#2030): --auto-register sends initial heartbeat immediately
            # and saves the response (which may contain auto-incremented name from server)
            if args.auto_register:
                print(f"Auto-registering with MCP Tower (Rule #19)...")
                try:
                    result = client.call_tool("agent_heartbeat", {"slot": slot, "agentId": name})
                    text = result["content"][0]["text"] if isinstance(result, dict) and "content" in result else str(result)
                    # Parse response — server may return auto-incremented name
                    try:
                        hb_data = json.loads(text)
                        if hb_data.get("ok"):
                            print(f"✅ Registered: slot={slot}, name={name}")
                            print(f"   TTL: {hb_data.get('ttlSeconds', 300)}s")
                            print(f"   Redis: {hb_data.get('redisAccount', 'default')}")
                    except json.JSONDecodeError:
                        print(f"Heartbeat response: {text[:200]}")
                except McpTowerError as e:
                    print(f"⚠️ Heartbeat failed (server may not support new slot format yet): {e}")
                    print("   Server needs redeploy after PR merge. Continuing with heartbeat loop...")

            print(f"Connecting as: {name} (slot: {slot})")
            client.start_heartbeat(slot, name)
            save_identity({"agent_name": name, "slot": slot, "mcp_server": args.server})
            print(f"Identity saved to {IDENTITY_FILE}")
            print("Heartbeat running. Press Ctrl+C to stop.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nStopping...")
            return 0

        if args.cmd == "heartbeat":
            result = client.call_tool("agent_heartbeat", {"slot": args.slot, "agentId": args.name})
            text = result["content"][0]["text"] if isinstance(result, dict) and "content" in result else str(result)
            print(text)
            return 0

        if args.cmd == "call":
            result = client.call_tool(args.tool_name, arguments)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0

    except McpTowerError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()

    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
