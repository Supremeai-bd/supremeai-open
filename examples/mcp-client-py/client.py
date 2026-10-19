"""SupremeAI MCP Tower — zero-dependency client (SSE + Streamable HTTP).

Spec companion: docs/MCP_CONNECT.md (issue #31).

House style (mirrors examples/gateway_client.py):
- no third-party dependencies; stdlib only
- honest errors: every failure class carries its status code
- network I/O happens ONLY on explicit CLI action (offline-safe import)
- credentials never appear in URLs or logs (SECRETS_MODEL.md)

Transports (verified against infrastructure/mcp-control-plane/src/index.ts):
- POST/GET/DELETE /mcp   — Streamable HTTP, stateful via Mcp-Session-Id
- GET /sse               — Server-Sent Events (text/event-stream)
- GET /health            — public smoke probe
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = os.getenv(
    "SUPREMEAI_MCP_TOWER_URL", "https://supremeai-mcp-tower.onrender.com"
)
DEFAULT_CLIENT_NAME = os.getenv("SUPREMEAI_CLIENT_NAME", "demo-py-client")
MCP_ACCEPT = "application/json, text/event-stream"


class TowerError(RuntimeError):
    """সব Tower-ত্রুটির মূল — status_code বহন করে (honest failure)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class TowerRateLimited(TowerError):
    """429 — per-IP সীমা; Retry-After সম্মান করুন, কখনো হট-লুপ নয়।"""


class TowerForbidden(TowerError):
    """403 — default-deny RBAC: role যথেষ্ট নয় (docs/MCP_CONNECT.md §1)."""


class TowerSessionLost(TowerError):
    """404 -32001 — stale Mcp-Session-Id; fresh initialize দিন।"""


# ---------------------------------------------------------------------------
# HTTP core
# ---------------------------------------------------------------------------


def _request(
    method: str,
    url: str,
    *,
    body: dict | None = None,
    headers: dict | None = None,
    timeout: float = 30.0,
) -> tuple[int, dict, bytes]:
    """One honest HTTP round-trip; raises typed errors on 4xx/5xx."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Accept", MCP_ACCEPT)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        detail = payload.decode(errors="replace")[:300]
        if exc.code == 429:
            retry_after = exc.headers.get("Retry-After", "unknown")
            raise TowerRateLimited(
                f"429 rate limited (Retry-After: {retry_after}s) — {detail}",
                status_code=429,
            ) from exc
        if exc.code == 403:
            raise TowerForbidden(
                f"403 default-deny RBAC — register or present verified credentials: {detail}",
                status_code=403,
            ) from exc
        if exc.code == 404 and "-32001" in detail:
            raise TowerSessionLost(
                "404 -32001 session not found — re-initialize a fresh session",
                status_code=404,
            ) from exc
        raise TowerError(f"HTTP {exc.code} — {detail}", status_code=exc.code) from exc
    except urllib.error.URLError as exc:
        raise TowerError(f"network unreachable: {exc.reason}") from exc


# ---------------------------------------------------------------------------
# Streamable HTTP transport (/mcp)
# ---------------------------------------------------------------------------


class McpHttpClient:
    """Stateful MCP client: initialize → tools/list → tools/call → delete."""

    def __init__(
        self, base_url: str = DEFAULT_BASE_URL, client_name: str = DEFAULT_CLIENT_NAME
    ):
        self.base_url = base_url.rstrip("/")
        self.client_name = client_name
        self.session_id: str | None = None
        self._next_id = 1

    def _url(self) -> str:
        return f"{self.base_url}/mcp?client={self.client_name}"

    def _rpc(self, method: str, params: dict | None = None) -> dict:
        if self.session_id is None and method != "initialize":
            raise TowerSessionLost("no active session — call initialize() first")
        payload: dict = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        self._next_id += 1
        if params is not None:
            payload["params"] = params
        headers: dict = {}
        if self.session_id is not None:
            headers["Mcp-Session-Id"] = self.session_id
        _, resp_headers, raw = _request(
            "POST", self._url(), body=payload, headers=headers
        )
        sid = resp_headers.get("Mcp-Session-Id") or resp_headers.get("mcp-session-id")
        if sid:
            self.session_id = sid
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TowerError(f"non-JSON response from /mcp: {raw[:200]!r}") from exc
        if isinstance(parsed, dict) and "error" in parsed:
            err = parsed["error"]
            raise TowerError(f"JSON-RPC error {err.get('code')}: {err.get('message')}")
        return parsed

    def initialize(self) -> dict:
        """Fresh `initialize` (no session header) mints a new per-session transport."""
        self.session_id = None
        result = self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": self.client_name, "version": "1.0.0"},
            },
        )
        # notifications/initialized handshake completes the MCP init sequence.
        try:
            headers = {"Mcp-Session-Id": self.session_id} if self.session_id else {}
            _request(
                "POST",
                self._url(),
                body={"jsonrpc": "2.0", "method": "notifications/initialized"},
                headers=headers,
            )
        except TowerError:
            pass  # notification is best-effort per spec tolerance
        return result

    def list_tools(self) -> list:
        envelope = self._rpc("tools/list")
        result = envelope.get("result") if isinstance(envelope, dict) else None
        return result.get("tools", []) if isinstance(result, dict) else []

    def call_tool(self, name: str, arguments: dict | None = None) -> dict:
        envelope = self._rpc("tools/call", {"name": name, "arguments": arguments or {}})
        result = envelope.get("result") if isinstance(envelope, dict) else None
        return result if isinstance(result, dict) else envelope

    def close(self) -> None:
        """DELETE /mcp — always release the session on shutdown (etiquette §5)."""
        if self.session_id is None:
            return
        try:
            _request(
                "DELETE",
                self._url(),
                headers={"Mcp-Session-Id": self.session_id},
                timeout=10.0,
            )
        except TowerError:
            pass  # best-effort; server TTL cleans up regardless
        finally:
            self.session_id = None


# ---------------------------------------------------------------------------
# SSE transport (/sse)
# ---------------------------------------------------------------------------


def sse_read(
    base_url: str = DEFAULT_BASE_URL,
    client_name: str = DEFAULT_CLIENT_NAME,
    max_frames: int = 5,
    timeout: float = 30.0,
) -> list:
    """Read the first SSE frames from /sse (text/event-stream).

    Returns a list of {"event": ..., "data": ...} frames. NOTE: this call
    blocks on the open stream — bounded here by max_frames for demo use.
    Real clients: reconnect on ConnectionError with exponential backoff.
    """
    url = f"{base_url.rstrip('/')}/sse?client={client_name}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "text/event-stream")
    frames: list = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            event_name = None
            data_lines: list = []
            while len(frames) < max_frames:
                line = resp.readline()
                if not line:
                    break  # stream closed by server
                text = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if text == "":
                    if data_lines:
                        frames.append(
                            {"event": event_name, "data": "\n".join(data_lines)}
                        )
                    event_name, data_lines = None, []
                elif text.startswith("event:"):
                    event_name = text.split(":", 1)[1].strip()
                elif text.startswith("data:"):
                    data_lines.append(text.split(":", 1)[1].lstrip())
    except urllib.error.HTTPError as exc:
        if exc.code == 503:
            raise TowerError(
                "503 SSE session table full — back off and reconnect later",
                status_code=503,
            ) from exc
        raise TowerError(f"HTTP {exc.code} on /sse", status_code=exc.code) from exc
    return frames


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


def health(base_url: str = DEFAULT_BASE_URL) -> dict:
    """GET /health — public, credential-free smoke probe."""
    _, _, raw = _request("GET", f"{base_url.rstrip('/')}/health", timeout=15.0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw.decode(errors="replace")[:200]}


# ---------------------------------------------------------------------------
# CLI (network only on explicit action)
# ---------------------------------------------------------------------------


def main(argv: list) -> int:
    actions = {
        "health": "GET /health smoke probe (no credentials)",
        "sse": "read first SSE frames from /sse",
        "tools": "initialize + tools/list over Streamable HTTP",
        "call": "initialize + tools/call <name> [json-args]",
    }
    if not argv or argv[0] not in actions:
        print(__doc__.strip())
        print("\nUsage: client.py <action> [args]")
        for name, desc in actions.items():
            print(f"  {name:6s} — {desc}")
        return 0 if not argv else 2

    action = argv[0]
    if action == "health":
        print(json.dumps(health(), indent=2))
        return 0
    if action == "sse":
        for frame in sse_read(max_frames=3):
            print(f"[{frame['event'] or 'message'}] {frame['data']}")
        return 0

    client = McpHttpClient()
    try:
        init = client.initialize()
        server_info = (init.get("result") or {}).get("serverInfo", {})
        print(
            f"# connected as '{client.client_name}' — server: "
            f"{server_info.get('name', '?')} {server_info.get('version', '')}"
        )
        print(f"# session: {client.session_id}")
        if action == "tools":
            for tool in client.list_tools():
                print(f"- {tool.get('name')}: {tool.get('description', '')[:80]}")
        elif action == "call":
            if len(argv) < 2:
                print(
                    "usage: client.py call <tool-name> [json-arguments]",
                    file=sys.stderr,
                )
                return 2
            args = json.loads(argv[2]) if len(argv) > 2 else {}
            result = client.call_tool(argv[1], args)
            print(json.dumps(result, indent=2))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except TowerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
