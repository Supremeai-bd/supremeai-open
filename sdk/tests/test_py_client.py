"""Unit tests for the SupremeAI Python SDK against an in-process mock gateway.

Stdlib only (unittest + http.server) per bridge test doctrine. Covers:
header signing, run submission, 503 retry/backoff recovery, terminal
GatewayError surfacing, SSE chunk re-assembly (sync), and the async
streaming iterator.
"""

import asyncio
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "python"))

from supremeai import AsyncSupremeAIClient, GatewayError, SupremeAIClient
from supremeai.sse_listener import SSEListener

SSE_BODY = (
    "event: token\n"
    'data: {"type":"token","text":"He"}\n'
    "\n"
    "event: token\n"
    'data: {"type":"token","text":"llo"}\n'
    "\n"
    "event: tool_call_delta\n"
    'data: {"type":"tool_call_delta","delta":{"index":0,"id":"call_1","name":"get_weather"}}\n'
    "\n"
    "event: tool_call_delta\n"
    'data: {"type":"tool_call_delta","delta":{"index":0,"argumentsFragment":"{\\"city\\":"}}\n'
    "\n"
    "event: tool_call_delta\n"
    'data: {"type":"tool_call_delta","delta":{"index":0,"argumentsFragment":"\\"Dhaka\\"}"}}\n'
    "\n"
    "event: done\n"
    'data: {"type":"done","finishReason":"stop"}\n'
    "\n"
    "data: [DONE]\n"
    "\n"
)


class MockGateway(BaseHTTPRequestHandler):
    """Deterministic mock of the Unified Gateway surface."""

    server_version = "SupremeAIMock/1"

    def log_message(self, *args):  # silence request logging
        pass

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        state = self.server.state  # type: ignore[attr-defined]
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        state["last_auth"] = self.headers.get("Authorization")
        state["last_body"] = json.loads(raw.decode("utf-8") or "{}")
        if self.path == "/v1/runs":
            self._send_json(
                201,
                {
                    "id": "run_123",
                    "status": "queued",
                    "task": state["last_body"].get("task", ""),
                },
            )
        else:
            self._send_json(
                404, {"error": {"code": "NOT_FOUND", "message": "unknown path"}}
            )

    def do_GET(self):
        state = self.server.state  # type: ignore[attr-defined]
        if self.path == "/v1/health":
            self._send_json(200, {"ok": True})
        elif self.path == "/v1/flaky":
            with state["lock"]:
                state["flaky_hits"] += 1
                should_fail = state["flaky_hits"] <= 2
            if should_fail:
                self._send_json(
                    503, {"error": {"code": "UPSTREAM_BUSY", "message": "try again"}}
                )
            else:
                self._send_json(200, {"ok": True, "attempts": state["flaky_hits"]})
        elif self.path == "/v1/always-503":
            self._send_json(
                503, {"error": {"code": "UPSTREAM_BUSY", "message": "never recovers"}}
            )
        elif self.path.endswith("/stream"):
            body = SSE_BODY.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send_json(
                404, {"error": {"code": "NOT_FOUND", "message": "unknown path"}}
            )


class MockGatewayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), MockGateway)
        self.state = {
            "lock": threading.Lock(),
            "flaky_hits": 0,
            "last_auth": None,
            "last_body": None,
        }

    @property
    def base_url(self):
        host, port = self.server_address[:2]
        return "http://%s:%d" % (host, port)


class TestSupremeAISDK(unittest.TestCase):
    def setUp(self):
        self.gateway = MockGatewayServer()
        self.thread = threading.Thread(target=self.gateway.serve_forever, daemon=True)
        self.thread.start()
        self.client = SupremeAIClient(
            base_url=self.gateway.base_url,
            api_key="test-key-123",
            max_retries=3,
            backoff_floor=0.01,
            timeout=5.0,
        )

    def tearDown(self):
        self.gateway.shutdown()
        self.gateway.server_close()

    def test_header_signing_and_run_submission(self):
        response = self.client.run_task(
            "summarize", {"text": "hello"}, idempotency_key="abc"
        )
        self.assertEqual(response["id"], "run_123")
        self.assertEqual(response["status"], "queued")
        self.assertEqual(self.gateway.state["last_auth"], "Bearer test-key-123")
        self.assertEqual(self.gateway.state["last_body"]["task"], "summarize")
        self.assertEqual(self.gateway.state["last_body"]["idempotencyKey"], "abc")

    def test_retry_backoff_succeeds_on_third_attempt(self):
        response = self.client.request("GET", "/v1/flaky")
        self.assertTrue(response["ok"])
        self.assertEqual(response["attempts"], 3)
        self.assertEqual(self.gateway.state["flaky_hits"], 3)

    def test_gateway_error_after_max_retries(self):
        with self.assertRaises(GatewayError) as ctx:
            self.client.request("GET", "/v1/always-503")
        error = ctx.exception
        self.assertEqual(error.status, 503)
        self.assertTrue(error.retryable)
        self.assertEqual(error.code, "UPSTREAM_BUSY")

    def test_sse_reassembly_sync(self):
        tokens, done = [], None
        tool = {"id": "", "name": "", "arguments": ""}
        for event in self.client.stream_run("run_123"):
            parsed = event.parsed or {}
            if parsed.get("type") == "token":
                tokens.append(parsed["text"])
            elif parsed.get("type") == "tool_call_delta":
                delta = parsed["delta"]
                tool["id"] = delta.get("id") or tool["id"]
                tool["name"] = delta.get("name") or tool["name"]
                tool["arguments"] += delta.get("argumentsFragment", "")
            elif parsed.get("type") == "done":
                done = True
                break
        self.assertEqual("".join(tokens), "Hello")
        self.assertEqual(tool["id"], "call_1")
        self.assertEqual(tool["name"], "get_weather")
        self.assertEqual(json.loads(tool["arguments"]), {"city": "Dhaka"})
        self.assertTrue(done)

    def test_sse_listener_multiline_and_finish(self):
        listener = SSEListener()
        events = listener.feed("event: message\nid: 42\ndata: line-one\n")
        self.assertEqual(events, [])
        events = listener.feed("data: line-two\n\n")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].data, "line-one\nline-two")
        self.assertEqual(events[0].id, "42")
        self.assertEqual(listener.finish(), [])

    def test_async_streaming_iterator(self):
        async def collect():
            async_client = AsyncSupremeAIClient(
                base_url=self.gateway.base_url,
                api_key="test-key-123",
                timeout=5.0,
            )
            tokens = []
            async for event in async_client.stream_run("run_123"):
                parsed = event.parsed or {}
                if parsed.get("type") == "token":
                    tokens.append(parsed["text"])
            return "".join(tokens)

        self.assertEqual(asyncio.run(collect()), "Hello")


if __name__ == "__main__":
    unittest.main(verbosity=2)
