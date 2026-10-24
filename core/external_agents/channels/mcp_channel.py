"""
backend/external_agents/channels/mcp_channel.py
===============================================
ISSUE-1574 (Part 5): expose core SupremeAI tools to external workers
(ZCode et al.) over the standard MCP JSON-RPC 2.0 protocol.

Exposed tools (read/scope-guarded):
    supremeai_file_inspect  — inspect a file inside the repo root
    supremeai_git_diff      — git diff/stat inside the repo root
    supremeai_test_run      — run pytest on scoped targets (collect-only fast mode)
    supremeai_memory_search — search long-term memory (best-effort, honest)

The :class:`McpChannelServer` speaks JSON-RPC 2.0 (``initialize`` /
``tools/list`` / ``tools/call``) so ANY standard MCP transport (stdio pipe,
HTTP handler, SSE bridge) can serve it without re-wiring.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.logging_config import logger

__all__ = ["McpChannelServer", "SupremeAiWorkerTools", "TOOL_DEFINITIONS"]

SERVER_INFO = {"name": "supremeai-worker-tools", "version": "1.0.0"}
PROTOCOL_VERSION = "2024-11-05"
MAX_INSPECT_BYTES = 256 * 1024


def _repo_root() -> Path:
    root = Path(os.getenv("SUPREMEAI_REPO_ROOT", Path.cwd())).resolve()
    return root


def _safe_repo_path(path: str) -> Path:
    """Resolve ``path`` inside the repo root — path traversal fails closed."""
    root = _repo_root()
    candidate = (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise PermissionError(f"path '{path}' escapes the repository root")
    return candidate


class SupremeAiWorkerTools:
    """The concrete tool implementations handed to external workers."""

    def file_inspect(self, path: str, max_bytes: int = MAX_INSPECT_BYTES) -> dict[str, Any]:
        try:
            resolved = _safe_repo_path(path)
        except PermissionError as exc:
            return {"ok": False, "error": str(exc)}
        if not resolved.is_file():
            return {"ok": False, "error": f"not a file: {path}"}
        data = resolved.read_bytes()[:max_bytes]
        return {
            "ok": True,
            "path": path,
            "bytes_read": len(data),
            "truncated": resolved.stat().st_size > len(data),
            "content": data.decode("utf-8", errors="replace"),
        }

    def git_diff(self, base: str = "HEAD", pathspec: str = "") -> dict[str, Any]:
        root = _repo_root()
        if not (root / ".git").exists():
            return {"ok": False, "error": f"no git repository at {root}"}
        try:
            stat = subprocess.run(
                ["git", "-C", str(root), "diff", "--stat", base],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            patch = subprocess.run(
                ["git", "-C", str(root), "diff", base, *(["--", pathspec] if pathspec else [])],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            return {
                "ok": True,
                "base": base,
                "stat": stat.stdout[-20_000:],
                "diff": patch.stdout[-200_000:],
            }
        except subprocess.SubprocessError as exc:
            return {"ok": False, "error": f"git diff failed: {exc}"}

    def test_run(
        self, targets: str = "", collect_only: bool = True, timeout: int = 300
    ) -> dict[str, Any]:
        """Run pytest on scoped targets. Defaults to collect-only (fast, side-effect free)."""
        resolved = _safe_repo_path(targets) if targets else _repo_root()
        args = [sys.executable, "-m", "pytest", "-q", "--no-cov", "-p", "no:cacheprovider"]
        if collect_only:
            args.append("--collect-only")
        args.append(str(resolved))
        try:
            proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
            return {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-40_000:],
                "stderr": proc.stderr[-10_000:],
                "collect_only": collect_only,
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"pytest timed out after {timeout}s"}

    def memory_search(self, query: str, top_k: int = 5) -> dict[str, Any]:
        if not query:
            return {"ok": False, "error": "memory_search requires a query"}
        try:
            from memory.long_term_memory import MemoryManager

            results = MemoryManager().search_memories(query, top_k=top_k)
            return {"ok": True, "query": query, "results": results or []}
        except Exception as exc:  # memory backend degraded — say so honestly
            logger.warning(f"[mcp_channel] memory_search degraded: {exc}")
            return {"ok": False, "error": f"memory backend unavailable: {exc}"}


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "supremeai_file_inspect",
        "description": "Inspect a file inside the SupremeAI repository (scope-guarded).",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "max_bytes": {"type": "integer"}},
            "required": ["path"],
        },
        "handler": lambda tools, args: tools.file_inspect(
            args.get("path", ""), int(args.get("max_bytes", MAX_INSPECT_BYTES))
        ),
    },
    {
        "name": "supremeai_git_diff",
        "description": "Git diff (stat + patch) inside the SupremeAI repository.",
        "inputSchema": {
            "type": "object",
            "properties": {"base": {"type": "string"}, "pathspec": {"type": "string"}},
        },
        "handler": lambda tools, args: tools.git_diff(
            args.get("base", "HEAD"), args.get("pathspec", "")
        ),
    },
    {
        "name": "supremeai_test_run",
        "description": "Run pytest on scoped targets (collect-only by default).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "targets": {"type": "string"},
                "collect_only": {"type": "boolean"},
                "timeout": {"type": "integer"},
            },
        },
        "handler": lambda tools, args: tools.test_run(
            args.get("targets", ""),
            bool(args.get("collect_only", True)),
            int(args.get("timeout", 300)),
        ),
    },
    {
        "name": "supremeai_memory_search",
        "description": "Search SupremeAI long-term memory.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
            "required": ["query"],
        },
        "handler": lambda tools, args: tools.memory_search(
            args.get("query", ""), int(args.get("top_k", 5))
        ),
    },
]


class McpChannelServer:
    """Standard MCP JSON-RPC 2.0 server core over the worker tools."""

    def __init__(self, tools: SupremeAiWorkerTools | None = None) -> None:
        self.tools = tools or SupremeAiWorkerTools()
        self._handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "initialize": self._on_initialize,
            "tools/list": self._on_tools_list,
            "tools/call": self._on_tools_call,
        }

    # ------------------------------------------------------------------
    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """JSON-RPC 2.0 single-request handler (transport-agnostic)."""
        method = request.get("method", "")
        request_id = request.get("id")
        handler = self._handlers.get(method)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"method not found: {method}"},
            }
        try:
            result = handler(request.get("params") or {})
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(exc)},
            }

    # ------------------------------------------------------------------
    def _on_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        }

    def _on_tools_list(self, _params: dict[str, Any]) -> dict[str, Any]:
        return {
            "tools": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "inputSchema": t["inputSchema"],
                }
                for t in TOOL_DEFINITIONS
            ]
        }

    def _on_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        definition = next((t for t in TOOL_DEFINITIONS if t["name"] == name), None)
        if definition is None:
            raise ValueError(f"unknown tool: {name}")
        content = definition["handler"](self.tools, arguments)
        return {
            "content": [{"type": "text", "text": json.dumps(content, ensure_ascii=False)}],
            "isError": bool(content.get("ok") is False),
        }
