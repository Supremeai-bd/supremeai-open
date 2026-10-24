"""Provides the MCPRegistryClient for connecting to external MCP servers using the Official SDK (V2.1)."""

import json
from typing import Any, Optional

import httpx

from core.config import settings
from core.logging_config import logger
from core.plugins.mcp_security import MCPSecurityGuard


class MCPRegistryClient:
    """
    MCP-Hub: The Real-World Connector.
    Connects to external MCP servers securely.
    """

    def __init__(self):
        # We would typically initialize the official mcp sdk client here
        self.enforce_https = getattr(settings, "env", "development") == "production"

    async def connect_and_discover(self, mcp_url: str) -> list[dict[str, Any]]:
        """
        Connects to an MCP server URL, validates it for SSRF, and discovers tools.
        Uses SSE/HTTP standard as defined by Model Context Protocol.
        """
        logger.info(f"MCP Client: Attempting to connect to {mcp_url}")

        if not MCPSecurityGuard.is_safe_url(mcp_url, enforce_https=self.enforce_https):
            logger.error(f"MCP Security blocked connection to {mcp_url}")
            raise ValueError("URL blocked by SSRF / Security policy")

        # Mocking official MCP SDK v2 behavior
        # In production this would be:
        # async with mcp.ClientSession(mcp_url) as session:
        #    return await session.list_tools()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Assuming the MCP server exposes standard /mcp/tools endpoint
                response = await client.get(f"{mcp_url}/mcp/tools")
                if response.status_code == 200:
                    data = response.json()
                    return data.get("tools", [])
                else:
                    logger.warning(
                        f"Failed to fetch tools from {mcp_url}. Status: {response.status_code}"
                    )
                    return []
        except Exception as e:
            logger.error(f"MCP connection error to {mcp_url}: {e}")
            raise

    async def execute_tool(
        self,
        mcp_url: str,
        tool_name: str,
        params: dict[str, Any],
        user: dict[str, Any] | None = None,
    ) -> Any:
        """
        Executes a tool on a remote MCP server.

        AUD-3.2/3.4 (P0): MCP tool invocations now pass the canonical tool
        policy gateway (identity/tenant/role/risk + audit), and ``params``
        must be a JSON-serializable mapping of scalar/list/dict values
        (validated before the network call).
        """
        if not MCPSecurityGuard.is_safe_url(mcp_url, enforce_https=self.enforce_https):
            raise ValueError("URL blocked by SSRF / Security policy")

        # AUD-3.4: basic argument validation — reject non-mapping payloads and
        # values that cannot be serialized (prevents ambiguous/abusive calls).
        if not isinstance(params, dict):
            raise ValueError("MCP tool params must be a JSON object (dict)")
        try:
            import json as _json

            _json.dumps(params)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"MCP tool params are not JSON-serializable: {exc}") from exc

        # AUD-3.2/3.3: canonical policy decision before any side effect.
        from core.security.tool_gateway import tool_policy_gateway

        await tool_policy_gateway.enforce(
            tool_name=f"mcp.{tool_name}",
            user=user,
            risk="medium",  # remote tools default to medium; unregistered callers require identity
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{mcp_url}/mcp/tools/{tool_name}/execute", json={"params": params}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to execute MCP tool {tool_name} at {mcp_url}: {e}")
            raise

    async def discover_tools(self, domain: str) -> list[str]:
        """
        Discovers tools across all configured MCP servers that match the given domain (tag).
        Falls back to default tools if discovery fails.
        """
        discovered = []
        for url in getattr(settings, "mcp_server_urls", []):
            try:
                tools = await self.connect_and_discover(url)
                for t in tools:
                    if domain in t.get("tags", []):
                        discovered.append(t.get("name"))
            except Exception as e:
                logger.warning(f"Error discovering tools from {url}: {e}")

        if not discovered:
            if domain == "research_analysis":
                discovered = ["web_search"]
            elif domain == "code_generation":
                discovered = ["code_generator"]

        return discovered


class ControlTowerClient:
    """Client for the SupremeAI MCP Control Tower (Native MCP SDK)."""

    def __init__(self, use_sse: bool = False):
        self.use_sse = use_sse
        self._session = None
        self._exit_stack = None
        self._client_ctx = None

    async def connect(self):
        """Connect to the MCP Control Tower."""
        import contextlib
        import os

        from mcp import StdioServerParameters
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client
        from mcp.client.stdio import stdio_client

        self._exit_stack = contextlib.AsyncExitStack()

        if self.use_sse:
            url = os.environ.get("RENDER_MCP_URL")
            if not url:
                from core.config import settings

                if settings.env == "local":
                    url = "http://localhost:3771"  # is_local()
                else:
                    raise ValueError("RENDER_MCP_URL must be set in production environments.")
            sse_url = f"{url}/mcp"
            # Optional API Key if control tower is secured
            api_key = os.environ.get("MCP_API_KEY", "")
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

            logger.info(f"Connecting to MCP Control Tower (SSE) at {sse_url}")
            self._client_ctx = sse_client(sse_url, headers=headers)
        else:
            # Local Stdio Connection (Assumes running in the same codebase)
            script_path = os.path.join(
                os.path.dirname(__file__), "../../infrastructure/mcp-control-plane/src/index.ts"
            )
            logger.info(f"Connecting to MCP Control Tower (STDIO) via tsx {script_path}")

            server_params = StdioServerParameters(
                command="npx", args=["tsx", script_path], env=os.environ.copy()
            )
            self._client_ctx = stdio_client(server_params)

        # Enter the client context and initialize session
        read, write = await self._exit_stack.enter_async_context(self._client_ctx)
        self._session = await self._exit_stack.enter_async_context(ClientSession(read, write))

        await self._session.initialize()
        logger.info("✅ MCP Control Tower Connected & Initialized")

    async def disconnect(self):
        """Disconnect from the MCP Control Tower."""
        if self._exit_stack:
            await self._exit_stack.aclose()
            logger.info("🔌 MCP Control Tower Disconnected")

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """Call a specific tool on the Control Tower.

        বাংলা (M06 P-A ৮/৮ RunType adoption): প্রতিটি MCP কল ক্যানোনিকাল
        ``run_type="mcp"`` রান হিসেবেও পর্যবেক্ষিত (flag-gated, best-effort)।
        connection-অনুপস্থিতির RuntimeError আগের মতোই ছড়ায় — রান সেটাকেই
        FAILED-হিসেবে রেকর্ড করে (সত্য প্রতিফলন)।
        """
        from runs.run_scope import observe_run

        async with observe_run(
            run_type="mcp",
            title=f"mcp:{name}",
            source_type="mcp",
            source_ref=name,
        ):
            if not self._session:
                raise RuntimeError("Not connected to MCP Control Tower")

            logger.info(f"Calling MCP Tool '{name}' with args: {arguments}")
            result = await self._session.call_tool(name, arguments)
            return result


# Global singleton instance (can be used throughout the backend)
control_tower = ControlTowerClient(use_sse=True)  # Use SSE by default for cross-service
