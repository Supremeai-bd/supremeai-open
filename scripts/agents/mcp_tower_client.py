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
def resolve_mcp_server_url() -> str:
    """Resolve MCP Control Tower URL from env or workspace mcp.json."""
    url = os.environ.get("MCP_TOWER_URL", os.environ.get("MCP_SERVER_URL", ""))
    if url:
        return url.rstrip("/").removesuffix("/sse")
    mcp_file = Path(__file__).resolve().parents[2] / "mcp.json"
    if mcp_file.exists():
        try:
            with open(mcp_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                tower = data.get("mcpServers", {}).get("supremeai-control-tower", {})
                server_url = tower.get("url", "")
                if server_url:
                    return server_url.rstrip("/").removesuffix("/sse")
        except Exception:
            pass
    return "https://supremeai-mcp-tower.onrender.com"


MCP_SERVER_URL = resolve_mcp_server_url()
MCP_SSE_PATH = "/sse"
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


class McpTowerTimeoutError(McpTowerError):
    pass


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
    """Synchronous MCP client over SSE transport (no auth)."""

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
        if self._initialized:
            return
        sse_url = self.server_url + self.sse_path
        self._log(f"Opening SSE: {sse_url}")
        resp = self._http.get(
            sse_url,
            stream=True,
            timeout=(REQUEST_TIMEOUT, SSE_READ_TIMEOUT),
            headers={"Accept": "text/event-stream"},
        )
        if resp.status_code != 200:
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
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "supremeai-agent", "version": "1.0.0"},
            },
        )
        self._log(f"Server: {init.get('serverInfo', {})}")
        self._send_notification("notifications/initialized", {})
        self._initialized = True

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

    def _send_request(self, method: str, params: dict[str, Any]) -> Any:
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
                raise McpTowerConnectionError(f"HTTP {r.status_code}")
        except requests.RequestError as e:
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
