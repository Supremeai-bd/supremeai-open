"""sdk/tests/test_python_sdk.py — pytest harness for the packaged Python SDK.

Issue #338 acceptance criterion 3 (test harness asserting SSE parsing, tool
serialization, and error translation green) + packaging contract (AC1:
pyproject metadata, typed exports, zero unnecessary dependencies).

Drives the SAME stdlib mock-MCP server surface the reference implementation
embeds, but from OUTSIDE the package — proving the packaged import surface
(`supremeai_sdk`) is what consumers get.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tomllib import TOMLDecodeError, loads as toml_loads

import pytest

SDK_DIR = Path(__file__).resolve().parent.parent / "python"
PKG = SDK_DIR / "supremeai_sdk"


# ---------------------------------------------------------------------------
# Import the PACKAGED module (not the examples/ copy) — path-pinned, dual
# python -m pytest and plain pytest friendly.
# ---------------------------------------------------------------------------

def _load_package():
    if str(SDK_DIR) not in sys.path:
        sys.path.insert(0, str(SDK_DIR))
    import supremeai_sdk  # noqa: WPS433 (test scope)

    importlib.reload(supremeai_sdk)
    return supremeai_sdk


supremeai_sdk = _load_package()


# ---------------------------------------------------------------------------
# Mock tower (same surface as the embedded harness; localhost only)
# ---------------------------------------------------------------------------

class _MockMcpHandler(BaseHTTPRequestHandler):
    server_version = "MockTower/1.0"

    def log_message(self, *args):  # silence request logging
        pass

    def _send_json(self, status: int, payload: dict, headers: dict | None = None):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.startswith("/health"):
            self._send_json(200, {"status": "ok", "mock": True})
        elif self.path.startswith("/sse"):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()
            frames = [
                {"frame_type": "event", "seq": 1, "timestamp": "2026-02-14T09:30:00Z",
                 "event": "agent:started", "task_id": "task-338", "agent_id": "agent-1",
                 "payload": {"goal": "harness"}},
                {"frame_type": "heartbeat", "seq": 2, "timestamp": "2026-02-14T09:30:05Z",
                 "heartbeat": {"kind": "ping", "interval_seconds": 30}},
                {"frame_type": "event", "seq": 3, "timestamp": "2026-02-14T09:30:10Z",
                 "event": "agent:done", "task_id": "task-338", "agent_id": "agent-1",
                 "payload": {"summary": "harness complete"}},
            ]
            for f in frames:
                self.wfile.write(f"data: {json.dumps(f)}\n\n".encode())
        elif self.path.startswith("/private"):
            self._send_json(401, {"error": "unauthorized"})
        elif self.path.startswith("/gated"):
            self._send_json(403, {"error": "forbidden"})
        elif self.path.startswith("/gone"):
            self._send_json(404, {"error": "not found"})
        else:
            self._send_json(429, {"error": "rate limit exceeded"}, {"Retry-After": "2"})
        self.close_connection = True

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path.startswith("/tasks/dispatch"):
            req = json.loads(body)
            self._send_json(200, {
                "task_id": req["task_id"],
                "tier": "coding_reasoning",
                "route": [{"provider": "anthropic", "model": "claude-sonnet-4-5"}],
                "accepted": True,
            })
        elif self.path.startswith("/mcp"):
            req = json.loads(body)
            if req["params"]["name"] == "boom":
                self._send_json(200, {
                    "jsonrpc": "2.0", "id": req.get("id"),
                    "error": {"code": -32601, "message": "unknown tool: boom"},
                })
            else:
                self._send_json(200, {
                    "jsonrpc": "2.0", "id": req.get("id"),
                    "result": {"tool": req["params"]["name"],
                               "echo": req["params"]["arguments"]},
                })
        else:
            self._send_json(404, {"error": "not found"})
        self.close_connection = True


@pytest.fixture(scope="module")
def tower():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _MockMcpHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


# ---------------------------------------------------------------------------
# SSE parsing (AC3)
# ---------------------------------------------------------------------------

def test_sse_stream_parses_three_frames(tower):
    client = supremeai_sdk.SupremeAIClient(tower, "pytest-harness")

    async def run():
        return [f async for f in client.stream_sse("task-338")]

    frames = asyncio.run(run())
    assert len(frames) == 3
    assert [f.seq for f in frames] == [1, 2, 3]
    assert frames[0].event == "agent:started"
    assert frames[0].frame_type == "event"
    assert frames[1].frame_type == "heartbeat"
    assert frames[1].heartbeat["kind"] == "ping"
    assert frames[2].event == "agent:done"


def test_sse_terminal_frame_ends_stream(tower):
    client = supremeai_sdk.SupremeAIClient(tower, "pytest-harness")

    async def run():
        seen = 0
        async for _ in client.stream_sse("task-338"):
            seen += 1
        return seen

    # stream terminates exactly at the terminal frame (no hang, no extra reads)
    assert asyncio.run(run()) == 3


# ---------------------------------------------------------------------------
# Tool serialization (AC3)
# ---------------------------------------------------------------------------

def test_invoke_tool_serializes_jsonrpc_envelope(tower):
    client = supremeai_sdk.SupremeAIClient(tower, "pytest-harness")

    async def run():
        return await client.invoke_tool(
            supremeai_sdk.ToolInvocation(tool="repo_read", arguments={"path": "docs/"})
        )

    tr = asyncio.run(run())
    assert tr.status == "ok"
    assert tr.result["tool"] == "repo_read"
    assert tr.result["echo"]["path"] == "docs/"
    assert tr.invocation_id.startswith("inv-")
    assert isinstance(tr.duration_ms, int)


def test_invoke_tool_honors_caller_invocation_id(tower):
    client = supremeai_sdk.SupremeAIClient(tower, "pytest-harness")

    async def run():
        return await client.invoke_tool(
            supremeai_sdk.ToolInvocation(tool="x", arguments={}, invocation_id="inv-fixed-42")
        )

    assert asyncio.run(run()).invocation_id == "inv-fixed-42"


def test_jsonrpc_tool_error_translates_to_honest_envelope(tower):
    client = supremeai_sdk.SupremeAIClient(tower, "pytest-harness")

    async def run():
        return await client.invoke_tool(
            supremeai_sdk.ToolInvocation(tool="boom", arguments={})
        )

    tr = asyncio.run(run())
    assert tr.status == "error"
    assert tr.error["code"] == "tool_failed"
    assert tr.error["retryable"] is False
    assert "unknown tool: boom" in tr.error["message"]


def test_task_dispatch_round_trip(tower):
    client = supremeai_sdk.SupremeAIClient(tower, "pytest-harness")

    async def run():
        return await client.dispatch_task(supremeai_sdk.TaskDispatchRequest(
            task_id="task-338", issue="338", objective="pytest harness",
            touching_files=("sdk/python/supremeai_sdk/client.py",),
        ))

    res = asyncio.run(run())
    assert res.accepted is True
    assert res.tier == "coding_reasoning"
    assert res.route[0]["provider"] == "anthropic"


# ---------------------------------------------------------------------------
# Error translation (AC3: 401/403/404/429 → honest exception taxonomy)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("path", "exc_name"),
    [("/private", "SdkAuthError"), ("/gated", "SdkForbidden"), ("/gone", "SdkNotFound")],
)
def test_http_error_translation(tower, path, exc_name):
    async def run():
        from supremeai_sdk.client import _raise_for_status, _request

        status, headers, body = await _request("GET", f"{tower}{path}")
        try:
            _raise_for_status(status, headers, body)
        except supremeai_sdk.SdkError as exc:
            return type(exc).__name__, exc.status_code
        return None, None

    name, code = asyncio.run(run())
    assert name == exc_name
    assert code in (401, 403, 404)


def test_429_carries_retry_after(tower):
    async def run():
        from supremeai_sdk.client import _raise_for_status, _request

        status, headers, body = await _request("GET", f"{tower}/throttled")
        try:
            _raise_for_status(status, headers, body)
        except supremeai_sdk.SdkRateLimited as exc:
            return exc.retry_after_s
        return None

    assert asyncio.run(run()) == 2.0


def test_transport_failure_is_retryable_envelope():
    client = supremeai_sdk.SupremeAIClient("http://127.0.0.1:1", "pytest-harness")

    async def run():
        return await client.invoke_tool(
            supremeai_sdk.ToolInvocation(tool="x", arguments={})
        )

    tr = asyncio.run(run())
    assert tr.status == "error"
    assert tr.error["code"] == "transport_error"
    assert tr.error["retryable"] is True


# ---------------------------------------------------------------------------
# Packaging contract (AC1: pyproject, typed exports, zero unnecessary deps)
# ---------------------------------------------------------------------------

def _pyproject() -> dict:
    raw = (SDK_DIR / "pyproject.toml").read_text(encoding="utf-8")
    try:
        return toml_loads(raw)
    except TOMLDecodeError as exc:  # pragma: no cover - guard the guard
        raise AssertionError(f"pyproject.toml is not valid TOML: {exc}") from exc


def test_pyproject_name_and_zero_runtime_deps():
    cfg = _pyproject()
    assert cfg["project"]["name"] == "supremeai-sdk-py"
    assert cfg["project"]["dependencies"] == []  # AC1: zero unnecessary deps
    assert cfg["project"]["requires-python"] == ">=3.11"


def test_py_typed_marker_shipped():
    assert (PKG / "py.typed").is_file(), "PEP 561 py.typed must exist"


def test_public_exports_complete_and_importable():
    expected = {
        "DEFAULT_BASE_URL", "DEFAULT_CLIENT_NAME", "MCP_ACCEPT",
        "SdkAuthError", "SdkError", "SdkForbidden", "SdkNotFound",
        "SdkRateLimited", "StatusFrame", "SupremeAIClient",
        "TaskDispatchRequest", "TaskDispatchResult", "ToolInvocation",
        "ToolResult", "__version__",
    }
    assert set(supremeai_sdk.__all__) == expected
    for name in expected:
        assert getattr(supremeai_sdk, name, None) is not None, f"export {name} missing"


def test_client_is_frozen_slots_dataclasses():
    import dataclasses

    for cls in (
        supremeai_sdk.TaskDispatchRequest,
        supremeai_sdk.TaskDispatchResult,
        supremeai_sdk.ToolInvocation,
        supremeai_sdk.ToolResult,
        supremeai_sdk.StatusFrame,
    ):
        assert dataclasses.is_dataclass(cls)
        assert cls.__dataclass_params__.frozen and cls.__dataclass_params__.slots


def test_offline_self_test_harness_passes():
    """The packaged module's embedded harness must stay green (issue #33 parity)."""
    from supremeai_sdk.client import _self_test

    assert _self_test() == 0
