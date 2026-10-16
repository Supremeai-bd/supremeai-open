"""Streamable-HTTP MCP endpoint for the stealth browser sandbox (issue #335).

A minimal, zero-dependency ``http.server``-based MCP transport that exposes
the four contracted browser tools (``navigate``, ``screenshot``,
``scrape_text``, ``evaluate_js``) with the same session semantics as the
SupremeAI Tower (``docs/MCP_CONNECT.md``):

- ``POST /mcp`` without a session header performs ``initialize`` and mints a
  fresh ``Mcp-Session-Id``;
- subsequent ``POST /mcp`` calls must carry that header
  (``tools/list``, ``tools/call``, ``ping``);
- ``DELETE /mcp`` terminates the session; stale sessions get the canonical
  ``404`` / ``-32001 Session not found`` answer;
- oversized bodies get ``413``; malformed JSON-RPC gets ``-32700``.

Honest scope: this endpoint answers every response as a single
``application/json`` document (it does not stream SSE). It binds loopback by
default and is intended as the reference wiring for whatever production
transport the private runtime uses.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, Optional, Tuple

from sandbox.browser_runtime import TOOL_CATALOG, BrowserRuntime, invoke_tool

MAX_REQUEST_BYTES = 1_000_000
SESSION_TTL_S = 3600.0
JSON_RPC_PARSE_ERROR = -32700
SESSION_NOT_FOUND = -32001

_TIME_FN = time.monotonic


class _SessionTable:
    """Thread-safe session store with TTL expiry (bounded by expiry, not size)."""

    def __init__(self, ttl_s: float = SESSION_TTL_S) -> None:
        self._ttl = float(ttl_s)
        self._lock = threading.Lock()
        self._sessions: Dict[str, float] = {}

    def mint(self) -> str:
        session_id = uuid.uuid4().hex
        with self._lock:
            self._sessions[session_id] = _TIME_FN() + self._ttl
        return session_id

    def validate(self, session_id: Optional[str]) -> bool:
        if not session_id:
            return False
        now = _TIME_FN()
        with self._lock:
            expires = self._sessions.get(session_id)
            if expires is None:
                return False
            if expires <= now:
                del self._sessions[session_id]
                return False
        return True

    def drop(self, session_id: Optional[str]) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)


def _jsonrpc_result(request_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _jsonrpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class BrowserMcpRequestHandler(BaseHTTPRequestHandler):
    """Request handler wired to a :class:`BrowserRuntime` (see ``make_server``)."""

    server_version = "supremeai-browser-sandbox/1.0"
    protocol_version = "HTTP/1.1"

    # Injected by make_server:
    runtime: BrowserRuntime = None  # type: ignore[assignment]
    sessions: _SessionTable = None  # type: ignore[assignment]

    # -- plumbing -----------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """Silence default stderr logging; never log URLs or query strings."""
        return

    def _read_body(self) -> Tuple[Optional[bytes], Optional[Tuple[int, str]]]:
        length_raw = self.headers.get("Content-Length")
        if length_raw is None:
            return None, (411, "Content-Length required")
        try:
            length = int(length_raw)
        except ValueError:
            return None, (400, "invalid Content-Length")
        if length > MAX_REQUEST_BYTES:
            # Drain bounded overshoots so the 413 response reaches the client
            # cleanly (no broken pipe); anything beyond the drain cap is abuse
            # and the connection is hard-closed instead.
            drain_cap = 8 * MAX_REQUEST_BYTES
            if length <= drain_cap:
                remaining = length
                while remaining > 0:
                    chunk = self.rfile.read(min(65536, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            else:
                self.close_connection = True
            return None, (413, f"request body exceeds {MAX_REQUEST_BYTES} bytes")
        body = self.rfile.read(length) if length > 0 else b""
        if len(body) != length:
            return None, (400, "truncated request body")
        return body, None

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    # -- routes -------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        if self.path.split("?", 1)[0] != "/mcp":
            self._send_json(404, _jsonrpc_error(None, -32601, "unknown route"))
            return
        body, failure = self._read_body()
        if failure is not None:
            status, message = failure
            self._send_json(status, _jsonrpc_error(None, -32700 if status == 400 else -32600, message))
            return
        try:
            request = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(400, _jsonrpc_error(None, JSON_RPC_PARSE_ERROR, "malformed JSON"))
            return
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or "method" not in request:
            self._send_json(400, _jsonrpc_error(request.get("id") if isinstance(request, dict) else None,
                                                -32600, "invalid JSON-RPC request"))
            return

        method = request["method"]
        request_id = request.get("id")
        session_header = self.headers.get("Mcp-Session-Id")

        if method == "initialize":
            session_id = self.sessions.mint()
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "supremeai-browser-sandbox", "version": "1.0.0"},
            }
            data = json.dumps(_jsonrpc_result(request_id, result)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Mcp-Session-Id", session_id)
            self.end_headers()
            self.wfile.write(data)
            return

        if not self.sessions.validate(session_header):
            self._send_json(
                404,
                _jsonrpc_error(request_id, SESSION_NOT_FOUND,
                               "Session not found (stale or missing Mcp-Session-Id; re-initialize)"),
            )
            return

        if method == "tools/list":
            self._send_json(200, _jsonrpc_result(request_id, {"tools": list(TOOL_CATALOG)}))
            return
        if method == "ping":
            self._send_json(200, _jsonrpc_result(request_id, {}))
            return
        if method == "tools/call":
            params = request.get("params") or {}
            if not isinstance(params, dict):
                self._send_json(200, _jsonrpc_result(
                    request_id, invoke_tool(self.runtime, "", None)))
                return
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                arguments = {}
            self._send_json(200, _jsonrpc_result(
                request_id, invoke_tool(self.runtime, name if isinstance(name, str) else "", arguments)))
            return

        self._send_json(200, _jsonrpc_error(request_id, -32601, f"method {method!r} not supported"))

    def do_DELETE(self) -> None:  # noqa: N802 (http.server API)
        if self.path.split("?", 1)[0] != "/mcp":
            self._send_json(404, _jsonrpc_error(None, -32601, "unknown route"))
            return
        self.sessions.drop(self.headers.get("Mcp-Session-Id"))
        self._send_json(200, _jsonrpc_result(None, {}))

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        self._send_json(404, _jsonrpc_error(None, -32601,
                                            "GET is not served; POST /mcp to initialize"))


def make_server(
    runtime: BrowserRuntime,
    host: str = "127.0.0.1",
    port: int = 0,
    *,
    session_ttl_s: float = SESSION_TTL_S,
) -> ThreadingHTTPServer:
    """Build (not start) the reference MCP endpoint.

    ``port=0`` picks an ephemeral port for tests; production deployments pass
    a fixed port explicitly. Loopback is the default bind so the sandbox can
    never be accidentally exposed.
    """
    handler = type(
        "WiredBrowserMcpHandler",
        (BrowserMcpRequestHandler,),
        {"runtime": runtime, "sessions": _SessionTable(session_ttl_s)},
    )
    return ThreadingHTTPServer((host, port), handler)
