"""MCP Circle Center — external tools, connector health, tool schemas.

Owns (per FCC plan): external tools, connector health, tool schemas.
Domain adapters: MCP server config (read-only) + ``brain.mcp_client.MCPClient``
for post-approval tool invocation. Blocking subprocess work runs in a worker
thread. ``mcp.invoke`` is HIGH risk + approval-gated (governed path).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from core.circles.centers.base import CircleCenter, ExecutionEnvelope, LocalCapability
from core.circles.contracts import CircleName, RiskLevel
from core.logging_config import logger

_DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[4]
    / "infrastructure"
    / "mcp-control-plane"
    / "mcp_config.local.json"
)


def _config_path() -> Path:
    return Path(os.environ.get("MCP_CONFIG_PATH", str(_DEFAULT_CONFIG)))


def _load_servers() -> dict[str, dict[str, Any]]:
    path = _config_path()
    if not path.exists():
        raise FileNotFoundError("mcp_config_not_found")
    raw = json.loads(path.read_text(encoding="utf-8"))
    servers = raw.get("mcpServers", raw) if isinstance(raw, dict) else {}
    return {name: cfg for name, cfg in servers.items() if isinstance(cfg, dict)}


class MCPCenter(CircleCenter):
    circle = CircleName.MCP
    display_name = "MCP external tools"
    owner = "infrastructure/mcp-control-plane"

    def __init__(self) -> None:
        super().__init__()
        self.register(
            LocalCapability(
                name="mcp.server.status",
                description="List configured MCP servers (connector health view)",
                risk_level=RiskLevel.LOW,
                timeout_ms=5_000,
                cache_ttl_ms=10_000,
            ),
            self._server_status,
        )
        self.register(
            LocalCapability(
                name="mcp.tools.list",
                description="Discover tool schemas from a configured MCP server",
                risk_level=RiskLevel.MEDIUM,
                timeout_ms=45_000,
            ),
            self._tools_list,
        )
        self.register(
            LocalCapability(
                name="mcp.invoke",
                description="Invoke an MCP tool (approval-gated governed path)",
                risk_level=RiskLevel.HIGH,
                approval_required=True,
                timeout_ms=60_000,
            ),
            self._invoke,
        )

    def local_permission(self, envelope: ExecutionEnvelope) -> str | None:
        if envelope.capability in {"mcp.tools.list", "mcp.invoke"}:
            if not str(envelope.payload.get("server", "")).strip():
                return f"server is required for {envelope.capability}"
        if (
            envelope.capability == "mcp.invoke"
            and not str(envelope.payload.get("tool", "")).strip()
        ):
            return "tool is required for mcp.invoke"
        return None

    def resolve_adapter(self, envelope: ExecutionEnvelope):  # noqa: ANN201
        if envelope.capability == "mcp.server.status":
            return _load_servers
        return None  # subprocess adapters are built per call

    async def _server_status(self, request) -> dict:
        try:
            servers = await asyncio.to_thread(_load_servers)
        except FileNotFoundError:
            return {"configured": False, "servers": []}
        return {
            "configured": True,
            "servers": [
                {
                    "name": name,
                    "command": cfg.get("command", [])[:1],  # binary name only
                    "args_count": len(cfg.get("args", []) or []),
                }
                for name, cfg in sorted(servers.items())
            ],
        }

    def _resolve_command(self, server: str) -> list[str]:
        servers = _load_servers()
        cfg = servers.get(server)
        if cfg is None:
            raise LookupError(f"mcp_server_unknown:{server}")
        command = cfg.get("command") or []
        if not command:
            raise ValueError(f"mcp_server_without_command:{server}")
        return [*command, *(cfg.get("args", []) or [])]

    async def _tools_list(self, request) -> dict:
        server = str(request.payload.get("server", ""))
        return await asyncio.to_thread(self._blocking_tools_list, server)

    def _blocking_tools_list(self, server: str) -> dict:
        from brain.mcp_client import MCPClient

        client = MCPClient(server, self._resolve_command(server))
        try:
            tools = client.list_tools()
        finally:
            client.disconnect()
        return {"server": server, "tools": tools, "count": len(tools)}

    async def _invoke(self, request) -> dict:
        server = str(request.payload.get("server", ""))
        tool = str(request.payload.get("tool", ""))
        arguments = dict(request.payload.get("arguments", {}))
        logger.info(f"[MCPCenter] invoking tool={tool} server={server}")
        return await asyncio.to_thread(self._blocking_invoke, server, tool, arguments)

    def _blocking_invoke(self, server: str, tool: str, arguments: dict) -> dict:
        from brain.mcp_client import MCPClient

        client = MCPClient(server, self._resolve_command(server))
        try:
            return client.call_tool(tool, arguments)
        finally:
            client.disconnect()


__all__ = ["MCPCenter"]
