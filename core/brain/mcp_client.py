"""Spawned-process MCP client for external MCP servers (headless agent fleet).

#686: ``MCPClient.call_tool`` is the single execution choke point for tools
dispatched to spawned external MCP servers (``tools/parallel_agent_executor.py``
and ``core/circles/centers/mcp_center.py`` both go through it). Tool requests
against servers listed in ``core/mcp_allowlist.py`` are now checked against that
server's ``allowed_tools`` at EXECUTION time — the allowlist previously had no
runtime consumer at all (neither registration- nor execution-time enforcement).
"""

import json
import signal
import subprocess
import time
from typing import Any

from core.logging_config import logger
from core.mcp_allowlist import MCPAllowlist, get_mcp_servers

DEFAULT_TIMEOUT = 30


class MCPClient:
    """
    Model Context Protocol (MCP) Client.
    Discovers tools and prompts from registered MCP servers.
    """

    def __init__(self, server_name: str, command: list[str], startup_timeout: int = 10):
        self.server_name = server_name
        self.command = command
        self.startup_timeout = startup_timeout
        self.process: subprocess.Popen | None = None
        self.last_used: float = time.time()

    def _terminate(self) -> None:
        if not self.process:
            return
        try:
            self.process.send_signal(signal.SIGTERM)
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        except (OSError, RuntimeError) as exc:
            logger.debug(f"MCP server termination cleanup: {exc}")
        finally:
            self.process = None

    def connect(self) -> bool:
        if self.process and self.process.poll() is None:
            return True
        self._terminate()
        try:
            logger.info(
                f"Connecting to MCP Server '{self.server_name}' using command: {self.command}"
            )
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            deadline = time.time() + self.startup_timeout
            while time.time() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f"MCP server exited with code {self.process.returncode}")
                time.sleep(0.05)
            return True
        except (OSError, RuntimeError) as exc:
            logger.error(f"Failed to start MCP server {self.server_name}: {exc}")
            self._terminate()
            return False

    def _write_request(self, request: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise RuntimeError("MCP server is not connected")
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        self.last_used = time.time()

    def _read_response(self) -> dict[str, Any]:
        if not self.process or not self.process.stdout:
            return {}
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("No response from MCP server")
        self.last_used = time.time()
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid MCP response: {exc}") from exc

    def list_tools(self) -> list[dict[str, Any]]:
        if not self.connect():
            return []
        try:
            self._write_request({"jsonrpc": "2.0", "method": "tools/list", "id": 1})
            response = self._read_response()
            return response.get("result", {}).get("tools", [])
        except (RuntimeError, json.JSONDecodeError) as exc:
            logger.error(f"Error querying MCP tools: {exc}")
            return []

    def call_tool(
        self, name: str, arguments: dict[str, Any], timeout: int = DEFAULT_TIMEOUT
    ) -> dict[str, Any]:
        """Execute a tool on the spawned MCP server.

        #686: execution-time allowlist gate. For servers that ARE part of
        ``core/mcp_allowlist.py`` (github, slack, filesystem, gemini-cli, …),
        the requested tool must be in that server's ``allowed_tools`` list —
        checked here at dispatch time, fail-closed. Servers outside the
        allowlist (first-party stdio servers wired via
        ``core/circles/centers/mcp_center.py``) keep their own governance
        layers (approval-gated ``mcp.invoke``, ``tool_policy_gateway``,
        ``core/mcp_policy.py``) and are deliberately not blanket-denied here.
        """
        if self.server_name in get_mcp_servers():
            verdict = MCPAllowlist.allowed_tools(self.server_name, [name])
            if not verdict.get("allowed"):
                denied = verdict.get("denied", [name])
                logger.warning(
                    f"MCP allowlist denied tool '{name}' on server '{self.server_name}' "
                    f"(allowed tools: {verdict.get('allowed_tools', [])})"
                )
                return {
                    "error": (
                        f"Tool '{name}' is not in the MCP allowlist for server '{self.server_name}'"
                    ),
                    "denied": denied,
                    "allowlist_denied": True,
                }
        if not self.connect():
            return {"error": "Server not connected"}
        request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
            "id": 2,
        }
        try:
            self._write_request(request)
            try:
                response = self._read_response()
                return response.get("result", {})
            except (RuntimeError, json.JSONDecodeError) as exc:
                logger.error(f"Error executing MCP tool '{name}': {exc}")
                return {"error": str(exc)}
        finally:
            try:
                if time.time() - self.last_used > 300:
                    self._terminate()
            except (OSError, RuntimeError) as exc:
                logger.debug(f"MCP idle cleanup: {exc}")

    def disconnect(self) -> None:
        self._terminate()
        logger.info(f"Disconnected from MCP Server '{self.server_name}'")
