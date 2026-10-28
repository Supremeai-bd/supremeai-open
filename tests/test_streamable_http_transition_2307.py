"""Streamable HTTP client transition — #2307 (R61 lane, R60 option A).

MCP spec revision 2025-06-18 replaces HTTP+SSE and prescribes the client
transition algorithm: POST the InitializeRequest to the server URL first;
only when that attempt fails fall back to the legacy GET+SSE transport.
The tower already serves both transports, so the client plane was the last
holdout. These tests pin the contract offline (no network): POST-first,
session-header capture + propagation, spec Accept header, protocol revision
2025-03-26 on the streamable path, 2024-11-05 untouched on the SSE path,
and the fallback preserving every currently-working configuration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "agents"))

import mcp_tower_client as mtc  # noqa: E402

ORIGIN = "https://supremeai-mcp-tower.example"


class FakeResp:
    def __init__(self, status=200, headers=None, body=None, sse_lines=None,
                 content_type="application/json"):
        self.status_code = status
        self.headers = {"Content-Type": content_type}
        self.headers.update(headers or {})
        self._body = body
        self._sse = sse_lines

    @property
    def text(self):
        return json.dumps(self._body) if self._body is not None else ""

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body

    def iter_lines(self, decode_unicode=True):
        return iter(self._sse or [])


class FakeHTTP:
    """Records POST/GET calls, replays scripted responses."""

    def __init__(self):
        self.posts: list[tuple[str, dict]] = []
        self.gets: list[str] = []
        self.post_responses: list[FakeResp] = []
        self.get_responses: list[FakeResp] = []

    def post(self, url, **kw):
        self.posts.append((url, kw))
        if not self.post_responses:
            raise AssertionError("unexpected POST — no scripted response")
        return self.post_responses.pop(0)

    def get(self, url, **kw):
        self.gets.append(url)
        if not self.get_responses:
            raise AssertionError("unexpected GET — SSE fallback must not fire")
        return self.get_responses.pop(0)

    def close(self):
        pass


def _client(http):
    c = mtc.McpTowerClient(server_url=ORIGIN)
    c._http = http
    return c


@pytest.fixture(autouse=True)
def _fixed_request_id(monkeypatch):
    # the client generates its own JSON-RPC ids; pin them so scripted
    # response bodies can carry the matching id
    monkeypatch.setattr(mtc.uuid, "uuid4", lambda: "fixed-id")


def _init_result_body(init_id):
    return {"jsonrpc": "2.0", "id": init_id,
            "result": {"serverInfo": {"name": "tower", "version": "1.0"}}}


@pytest.fixture(autouse=True)
def _fast_wait(monkeypatch):
    monkeypatch.setattr(mtc, "RESPONSE_WAIT", 0.2)
    monkeypatch.setattr(mtc, "REQUEST_TIMEOUT", 1)


def test_streamable_happy_path_post_first_json_body():
    http = FakeHTTP()
    http.post_responses = [
        FakeResp(200, headers={"mcp-session-id": "sess-123"},
                 body=_init_result_body("id-1")),
        FakeResp(202),  # notifications/initialized
        FakeResp(200, body={"jsonrpc": "2.0", "id": "id-2",
                            "result": {"tools": []}}),  # tools/list
    ]
    c = _client(http)
    c.connect()
    assert c._transport == "streamable"
    assert c._session_id == "sess-123"
    result = c.list_tools()  # third POST
    # POST-first: exactly the streamable endpoint, zero GETs
    assert [u for u, _ in http.posts] == [ORIGIN + "/mcp"] * 3
    assert http.gets == []
    init_kw = http.posts[0][1]
    # spec Accept header: both transports offered on every POST
    assert init_kw["headers"]["Accept"] == "application/json, text/event-stream"
    assert init_kw["headers"]["Content-Type"] == "application/json"
    payload = init_kw["json"]
    assert payload["method"] == "initialize"
    assert payload["params"]["protocolVersion"] == "2025-03-26"
    # session header propagates to follow-up requests
    assert http.posts[1][1]["headers"]["mcp-session-id"] == "sess-123"
    assert http.posts[2][1]["headers"]["mcp-session-id"] == "sess-123"
    # MCP-Protocol-Version header on post-initialize requests
    assert http.posts[2][1]["headers"]["MCP-Protocol-Version"] == "2025-03-26"
    # notifications carry no id
    assert "id" not in http.posts[1][1]["json"]
    assert result == []  # list_tools() unwraps .get("tools") internally
    c.close()


def test_streamable_sse_response_body_parsed():
    http = FakeHTTP()
    http.post_responses = [
        FakeResp(200, headers={"mcp-session-id": "sess-sse"},
                 content_type="text/event-stream",
                 sse_lines=[
                     "event: message",
                     f"data: {json.dumps(_init_result_body('fixed-id'))}",
                     "",
                 ]),
        FakeResp(202),
    ]
    c = _client(http)
    c.connect()
    assert c._transport == "streamable"
    assert c._session_id == "sess-sse"
    c.close()


def test_fallback_on_404_preserves_legacy_transport():
    """Spec transition: POST fails HTTP 4xx → legacy GET+SSE transport."""
    http = FakeHTTP()
    http.post_responses = [FakeResp(404, body={"error": "not found"})]
    c = _client(http)
    calls = {}

    def fake_sse():
        calls["sse"] = True
        c._transport = "sse"

    c._connect_sse = fake_sse  # type: ignore[method-assign]
    c.connect()
    assert calls.get("sse") is True
    assert c._transport == "sse"
    # the POST attempt happened first and hit the streamable endpoint
    assert [u for u, _ in http.posts] == [ORIGIN + "/mcp"]
    c.close()


@pytest.mark.parametrize("status", [404, 500, 503])
def test_fallback_on_any_http_error(status):
    """4xx is the spec's trigger; 5xx also falls back so a cold-start can
    never break a configuration that works today (zero-downtime guarantee)."""
    http = FakeHTTP()
    http.post_responses = [FakeResp(status)]
    c = _client(http)
    c._connect_sse = lambda: setattr(c, "_transport", "sse")  # type: ignore[method-assign]
    c.connect()
    assert c._transport == "sse"
    c.close()


def test_fallback_on_connection_error():
    http = FakeHTTP()

    def boom(*a, **kw):
        raise requests.ConnectionError("refused")

    http.post = boom  # type: ignore[method-assign]
    c = _client(http)
    c._connect_sse = lambda: setattr(c, "_transport", "sse")  # type: ignore[method-assign]
    c.connect()
    assert c._transport == "sse"
    c.close()


def test_rpc_error_in_streamable_body_raises_mcp_error():
    http = FakeHTTP()
    http.post_responses = [
        FakeResp(200, body={"jsonrpc": "2.0", "id": "fixed-id",
                            "error": {"code": -32601, "message": "no such tool"}}),
    ]
    c = _client(http)
    c._transport = "streamable"
    with pytest.raises(mtc.McpTowerError, match="-32601"):
        c.call_tool("nope", {})
    c.close()


def test_legacy_sse_revision_constant_untouched():
    assert mtc.PROTOCOL_VERSION_SSE == "2024-11-05"
    assert mtc.PROTOCOL_VERSION_STREAMABLE == "2025-03-26"


def test_transport_reset_on_close():
    http = FakeHTTP()
    http.post_responses = [
        FakeResp(200, headers={"mcp-session-id": "s"},
                 body=_init_result_body("x")),
        FakeResp(202),
    ]
    c = _client(http)
    c.connect()
    assert c._transport == "streamable"
    c.close()
    assert c._transport is None
    assert c._initialized is False
