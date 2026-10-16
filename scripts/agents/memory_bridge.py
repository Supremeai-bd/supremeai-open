#!/usr/bin/env python3
"""Memory Bridge — G1 (audit 2026-10-16): loop <-> federation experience link.

The federation's memory infrastructure (memory.* MCP tools on the tower:
get_similar_tasks / record_task / build_context / ...) existed without a
single consumer in the agent loop, so every task started from zero even
though recall was one MCP hop away (audit G1, P1).

This module closes that loop WITHOUT making the loop stateful (AGENTS.md §2:
agents stay stateless by lifecycle; the *system* is the learner):

  recall related experience -> task_envelope.related_experience (optional)
  record task outcome       -> episodic memory (fire-and-forget)

Honesty contract (U2):
  - No endpoint configured  -> disabled: no calls, no envelope key (byte-compat
    with pre-G1 consumers), single honest degraded log.
  - Any failure (transport, malformed response, non-JSON body, timeout) is
    captured, logged loudly, and returned as None / False. It NEVER raises
    into the loop and NEVER blocks the task on memory problems.

Zero dependencies: JSON-RPC over Streamable HTTP via urllib, mirroring the
tower's public MCP endpoint contract (initialize -> notifications/initialized
-> tools/call, mcp-session-id maintained across the handshake).

Self-test: `python3 scripts/agents/memory_bridge.py --self-test`
(offline: the transport is an injectable callable; no network).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Callable

ENV_MEMORY_ENDPOINT = "SUPREME_MEMORY_MCP"
ENV_MEMORY_TIMEOUT_S = "SUPREME_MEMORY_TIMEOUT_S"
DEFAULT_TIMEOUT_S = 6.0
PROTOCOL_VERSION = "2025-03-26"
RECALL_TOOL = "memory.get_similar_tasks"
RECORD_TOOL = "memory.record_task"
DEFAULT_RECALL_LIMIT = 3
MAX_RECALL_LIMIT = 10
MAX_PAYLOAD_ITEMS = 10
MAX_TEXT_CHARS = 4000

LogFn = Callable[[str], None]


def _default_log(msg: str) -> None:
    print(f"[MEMORY_BRIDGE] {msg}", file=sys.stderr)


def _fake_jsonrpc_response(text: str) -> dict[str, Any]:
    """Shape a caller return value the way the real transport does."""
    return {"result": {"content": [{"type": "text", "text": text}]}}


class MemoryBridge:
    """Stateless client for the tower's memory.* MCP tools (fail-open)."""

    def __init__(
        self,
        endpoint: str | None,
        caller: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        log_fn: LogFn | None = None,
    ) -> None:
        self.endpoint = (endpoint or "").strip() or None
        self.enabled = self.endpoint is not None
        self.timeout_s = timeout_s
        self._caller = caller
        self.log = log_fn or _default_log
        self.last_error: str | None = None

    @classmethod
    def from_env(cls, log_fn: LogFn | None = None) -> "MemoryBridge":
        endpoint = os.environ.get(ENV_MEMORY_ENDPOINT, "")
        raw_timeout = os.environ.get(ENV_MEMORY_TIMEOUT_S, "")
        try:
            timeout_s = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT_S
        except ValueError:
            timeout_s = DEFAULT_TIMEOUT_S
        return cls(endpoint=endpoint, timeout_s=max(0.5, timeout_s), log_fn=log_fn)

    # ── transport ────────────────────────────────────────────────────────────

    def _http_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """JSON-RPC over Streamable HTTP with the session handshake."""
        assert self.endpoint is not None
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        body = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "continuous-agent-loop", "version": "1.1.0"},
        }}
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(body).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            session_id = resp.headers.get("mcp-session-id")
            init = json.loads(resp.read().decode())
        if "error" in init:
            raise RuntimeError(f"initialize failed: {init['error']}")
        if session_id:
            headers["mcp-session-id"] = session_id
        # initialized notification (fire-and-forget)
        notify = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(notify).encode(), headers=headers, method="POST"
        )
        try:
            urllib.request.urlopen(req, timeout=self.timeout_s).read()
        except Exception:
            pass  # notifications are best-effort by protocol
        call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": method, "arguments": params}}
        req = urllib.request.Request(
            self.endpoint, data=json.dumps(call).encode(), headers=headers, method="POST"
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode())

    def _call_tool(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if self._caller is not None:
            return self._caller(tool, args)
        return self._http_call(tool, args)

    # ── parsing ──────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_tasks(response: dict[str, Any]) -> list[dict[str, Any]]:
        content = (response.get("result") or {}).get("content") or []
        for item in content:
            if item.get("type") == "text":
                raw = item.get("text") or ""
                try:
                    parsed = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    raise ValueError("memory tool returned non-JSON body") from None
                if isinstance(parsed, list):
                    tasks = parsed
                elif isinstance(parsed, dict):
                    tasks = parsed.get("tasks") or parsed.get("results") or []
                else:
                    tasks = []
                out = [t for t in tasks if isinstance(t, dict)]
                for t in out:
                    for key in ("title", "summary", "outcome", "detail"):
                        if isinstance(t.get(key), str) and len(t[key]) > MAX_TEXT_CHARS:
                            t[key] = t[key][:MAX_TEXT_CHARS] + "…[truncated]"
                return out[:MAX_PAYLOAD_ITEMS]
        raise ValueError("memory tool response carried no text content")

    def _guarded_call(self, tool: str, args: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Run a memory tool call; capture every failure as an honest log."""
        self.last_error = None
        try:
            response = self._call_tool(tool, args)
            if "error" in response:
                raise RuntimeError(f"{tool} error: {response['error']}")
            return self._extract_tasks(response)
        except Exception as exc:  # noqa: BLE001 — fail-open by design (U2: captured, never silent)
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.log(f"memory {tool} failed (proceeding without experience): {self.last_error}")
            return None

    # ── public surface ───────────────────────────────────────────────────────

    def recall_related(self, task_title: str, limit: int = DEFAULT_RECALL_LIMIT) -> dict[str, Any] | None:
        """Fill the envelope's optional related_experience block.

        Returns None when disabled or on any failure (envelope key omitted,
        byte-compat with pre-G1 consumers). Never raises.
        """
        if not self.enabled:
            return None
        limit = max(1, min(int(limit), MAX_RECALL_LIMIT))
        tasks = self._guarded_call(RECALL_TOOL, {"query": task_title, "limit": limit})
        if tasks is None:
            return None
        return {
            "source": RECALL_TOOL,
            "endpoint_configured": True,
            "query": task_title,
            "tasks": tasks[:limit],
        }

    def record_outcome(self, task_id: str, title: str, outcome: str, detail: str = "") -> bool:
        """Record a completed task's outcome signature (fire-and-forget).

        Returns True when the record was accepted. Never raises.
        """
        if not self.enabled:
            return False
        tasks = self._guarded_call(RECORD_TOOL, {
            "task_id": str(task_id)[:128],
            "title": (title or "")[:512],
            "outcome": (outcome or "")[:64],
            "detail": (detail or "")[:MAX_TEXT_CHARS],
        })
        return tasks is not None


# ── offline self-test ────────────────────────────────────────────────────────

def _self_test() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        if not cond:
            failures.append(name)

    logs: list[str] = []
    capture = logs.append

    # 1. Disabled (no endpoint): no calls, no experience, honest log.
    calls: list[tuple[str, dict[str, Any]]] = []

    def spy(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool, args))
        return _fake_jsonrpc_response(json.dumps([
            {"task_id": "t-1", "title": "similar past task", "outcome": "landed"},
            {"task_id": "t-2", "title": "another", "outcome": "landed"},
        ]))

    bridge = MemoryBridge(endpoint=None, caller=spy, log_fn=capture)
    check("disabled.recall_none", bridge.recall_related("anything") is None)
    check("disabled.no_calls", len(calls) == 0)
    check("disabled.enabled_flag", bridge.enabled is False)
    check("disabled.record_false", bridge.record_outcome("t", "T", "done") is False)
    check("disabled.no_calls_after_record", len(calls) == 0)

    # 2. Enabled recall success: tool name + args shape + parsing + capping.
    bridge = MemoryBridge(endpoint="http://memory.test/mcp", caller=spy, log_fn=capture)
    exp = bridge.recall_related("fix the gateway", limit=3)
    check("enabled.experience_not_none", exp is not None)
    check("enabled.source_field", exp is not None and exp["source"] == RECALL_TOOL)
    check("enabled.query_field", exp is not None and exp["query"] == "fix the gateway")
    check("enabled.tasks_parsed", exp is not None and len(exp["tasks"]) == 2)
    check("enabled.tool_name", len(calls) == 1 and calls[0][0] == RECALL_TOOL)
    check("enabled.call_args", len(calls) == 1 and calls[0][1].get("query") == "fix the gateway" and calls[0][1].get("limit") == 3)

    # 3. Limit capping: 5 tasks in, limit 2 -> 2 out (payload cap respected).
    calls.clear()
    bridge = MemoryBridge(endpoint="http://memory.test/mcp", caller=spy, log_fn=capture)
    big = _fake_jsonrpc_response(json.dumps([{"task_id": f"t-{i}"} for i in range(5)]))

    def spy_big(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        calls.append((tool, args))
        return big

    bridge._caller = spy_big  # noqa: SLF001 — test harness injection
    exp = bridge.recall_related("q", limit=2)
    check("cap.limit2", exp is not None and len(exp["tasks"]) == 2)

    # 4. Fail-open on transport failure: None, no raise, error captured.
    def boom(tool: str, args: dict[str, Any]) -> dict[str, Any]:
        raise OSError("connection refused")

    bridge = MemoryBridge(endpoint="http://memory.test/mcp", caller=boom, log_fn=capture)
    check("failopen.recall_none", bridge.recall_related("q") is None)
    check("failopen.error_captured", bridge.last_error is not None and "OSError" in (bridge.last_error or ""))
    check("failopen.logged", any("failed" in m for m in logs))

    # 5. Fail-open on MCP-level error envelope.
    bridge = MemoryBridge(endpoint="http://memory.test/mcp", caller=lambda t, a: {"error": {"code": -32000}}, log_fn=capture)
    check("mcperror.recall_none", bridge.recall_related("q") is None)

    # 6. Fail-open on malformed responses (no content / non-JSON body).
    bridge = MemoryBridge(endpoint="http://memory.test/mcp", caller=lambda t, a: {"result": {"content": []}}, log_fn=capture)
    check("nocontent.recall_none", bridge.recall_related("q") is None)
    bridge = MemoryBridge(endpoint="http://memory.test/mcp", caller=lambda t, a: _fake_jsonrpc_response("not-json{"), log_fn=capture)
    check("nonjson.recall_none", bridge.recall_related("q") is None)

    # 7. Record path: success True; failure False; both never raise.
    calls.clear()
    bridge = MemoryBridge(endpoint="http://memory.test/mcp", caller=spy, log_fn=capture)
    check("record.success_true", bridge.record_outcome("t-9", "Title", "landed", "PR #1") is True)
    check("record.tool_name", len(calls) == 1 and calls[0][0] == RECORD_TOOL)
    check("record.args_shape", calls[0][1].get("task_id") == "t-9" and calls[0][1].get("outcome") == "landed")
    bridge = MemoryBridge(endpoint="http://memory.test/mcp", caller=boom, log_fn=capture)
    check("record.failure_false", bridge.record_outcome("t-9", "Title", "landed") is False)

    # 8. Text truncation guard: oversized titles never enter the payload verbatim.
    huge = _fake_jsonrpc_response(json.dumps([{"task_id": "t-x", "title": "x" * (MAX_TEXT_CHARS + 500)}]))
    bridge = MemoryBridge(endpoint="http://memory.test/mcp", caller=lambda t, a: huge, log_fn=capture)
    exp = bridge.recall_related("q")
    check("truncation.applied", exp is not None and len(exp["tasks"][0]["title"]) <= MAX_TEXT_CHARS + 20)

    if failures:
        print(f"❌ MEMORY BRIDGE SELF-TEST FAILED ({len(failures)}): {failures}")
        return 1
    n = 8
    print("✅ ALL MEMORY BRIDGE TESTS PASSED (8 scenario groups, fail-open + honesty contract verified)")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print("usage: memory_bridge.py --self-test (module is imported by continuous_agent_loop.py)")
    sys.exit(2)
