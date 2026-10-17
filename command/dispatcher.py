"""src/dispatcher.py — MCP Control Tower relay + minimal persistent kill-switch.

dispatcher.TowerDispatcher
- Speaks JSON-RPC 2.0 to the MCP Control Tower (`/mcp`) with explicit timeouts
  on every call (guard doctrine: no IO without timeout).
- fetch_status(): a READ-ONLY tools/call used by /status and /runway.
- dispatch_issue(): relays an issue URL into the agent-loop intake lane.

MiniRedis (kill-switch persistence)
- A minimal RESP-protocol client supporting exactly SET (with EX ttl),
  GET and DEL — enough for the persistent emergency kill-switch contract
  without any third-party dependency.
- Fail-closed: without REDIS_URL configured the kill-switch refuses to arm
  (KillSwitchUnavailable) instead of pretending to persist.
"""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

MCP_PROTOCOL_VERSION = "2025-06-18"


class DispatcherError(Exception):
    """Raised when the Control Tower call fails or returns malformed data."""


class TowerDispatcher:
    def __init__(self, base_url: str, timeout_s: float = 30.0) -> None:
        if not base_url or not base_url.startswith("https://"):
            raise DispatcherError("tower base_url must be an https URL")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _rpc(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
        if params is not None:
            payload["params"] = params
        req = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8")
                if resp.status != 200:
                    raise DispatcherError("tower HTTP %d" % resp.status)
        except urllib.error.HTTPError as exc:
            raise DispatcherError("tower HTTP %d" % exc.code) from exc
        except urllib.error.URLError as exc:
            raise DispatcherError("tower unreachable: %s" % exc.reason) from exc
        try:
            data = json.loads(body)
        except ValueError as exc:
            raise DispatcherError("tower returned malformed JSON") from exc
        if data.get("error"):
            raise DispatcherError("tower RPC error: %s" % data["error"])
        return data.get("result", {})

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        result = self._rpc(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )
        chunks = [
            c.get("text", "")
            for c in result.get("content", [])
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        return "".join(chunks)

    def fetch_status(self) -> str:
        """Read-only runway snapshot: tower liveness + queued work orders."""
        tools = self._rpc("tools/list")
        names = sorted(t.get("name", "") for t in tools.get("tools", []))
        try:
            queue = self.call_tool(
                "bridge_list_work_orders", {"label": "bridge:queued"}
            )
        except DispatcherError as exc:
            queue = "(queue unavailable: %s)" % exc
        lines = [
            "🏰 Control Tower: reachable",
            "🧰 tools: %d (%s)" % (len(names), ", ".join(names[:6]) + ("…" if len(names) > 6 else "")),
            "🌉 queued work orders: %s" % (queue or "?"),
        ]
        return "\n".join(lines)

    def dispatch_issue(self, issue_url: str) -> str:
        """Relay a GitHub issue URL into the agent-loop intake lane."""
        if not issue_url.startswith("https://github.com/") or "/issues/" not in issue_url:
            raise DispatcherError("issue_url must be a github.com issue URL")
        out = self.call_tool(
            "bridge_dispatch_issue", {"issueUrl": issue_url}
        )
        return "🛰️ dispatch relayed: %s" % (out or issue_url)


# ---------------------------------------------------------------------------
# Minimal RESP (Redis) client — kill-switch persistence
# ---------------------------------------------------------------------------

CRLF = b"\r\n"


def encode_resp(*args: bytes) -> bytes:
    out = bytearray(b"*%d%s" % (len(args), CRLF))
    for a in args:
        out += b"$%d%s%s%s" % (len(a), CRLF, a, CRLF)
    return bytes(out)


def parse_resp_line(line: bytes) -> str:
    return line.decode("utf-8", errors="replace").strip()


class KillSwitchUnavailable(Exception):
    """Raised when no REDIS_URL is configured (feature explicitly off)."""


class MiniRedis:
    """Tiny RESP client: SET key val EX ttl / GET / DEL only."""

    def __init__(self, url: Optional[str], timeout_s: float = 5.0) -> None:
        if not url:
            raise KillSwitchUnavailable("REDIS_URL is not configured")
        parsed = urlparse(url)
        if parsed.scheme not in ("redis", "rediss") or not parsed.hostname:
            raise KillSwitchUnavailable("REDIS_URL must be a redis:// URL")
        self.host = parsed.hostname
        self.port = parsed.port or 6379
        self.timeout_s = timeout_s

    def _command(self, *args: bytes) -> str:
        with socket.create_connection((self.host, self.port), timeout=self.timeout_s) as sock:
            sock.sendall(encode_resp(*args))
            sock.settimeout(self.timeout_s)
            data = sock.recv(4096)
        if not data:
            raise DispatcherError("empty response from redis")
        return parse_resp_line(data.split(CRLF)[0])

    def set_ex(self, key: str, value: str, ttl_s: int) -> str:
        return self._command(b"SET", key.encode("utf-8"), value.encode("utf-8"),
                             b"EX", str(int(ttl_s)).encode("utf-8"))

    def get(self, key: str) -> Optional[str]:
        raw = self._command(b"GET", key.encode("utf-8"))
        if raw.startswith("$-1") or raw in ("(nil)", ""):
            return None
        return raw[1:] if raw.startswith("$") else raw

    def delete(self, key: str) -> str:
        return self._command(b"DEL", key.encode("utf-8"))


KILL_SWITCH_KEY = "supremeai:command:kill_switch"


class KillSwitch:
    """Persistent emergency kill-switch backed by MiniRedis."""

    def __init__(self, redis: Optional[MiniRedis], ttl_s: int = 86400) -> None:
        if redis is None:
            raise KillSwitchUnavailable(
                "kill-switch requires REDIS_URL; refusing to fake persistence"
            )
        self.redis = redis
        self.ttl_s = ttl_s

    def arm(self, reason: str = "superadmin /stop") -> str:
        reply = self.redis.set_ex(KILL_SWITCH_KEY, reason, self.ttl_s)
        return "🛑 kill-switch ARMED (persistent %ss, redis: %s)" % (self.ttl_s, reply)

    def armed(self) -> bool:
        return self.redis.get(KILL_SWITCH_KEY) is not None

    def clear(self) -> str:
        self.redis.delete(KILL_SWITCH_KEY)
        return "✅ kill-switch cleared"
