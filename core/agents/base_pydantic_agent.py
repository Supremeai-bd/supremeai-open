from typing import Any

from pydantic import BaseModel
from pydantic_ai import Agent

from core.llm.llm_gateway import get_llm_gateway
from core.logging_config import logger
from core.mcp_client import MCPRegistryClient


class BasePydanticAgent:
    """
    বাংলা মন্তব্ব: PydanticAI-এর উপর তৈরি Base Agent Class.
    এটি SupremeAI-এর LiteLLM Gateway এবং MCP (Master Control Program) টুলগুলোর
    সাথে PydanticAI-কে সংযুক্ত করে।
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        model_name: str = "openai:gpt-4o",  # Defaulting to an OpenAI compatible model for PydanticAI
        result_type: type[BaseModel] | type[str] = str,
    ):
        self.name = name
        self.system_prompt = system_prompt
        self.model_name = model_name
        self.result_type = result_type

        # PydanticAI Agent
        self.agent = Agent(  # type: ignore[call-overload]
            self.model_name,
            system_prompt=self.system_prompt,
            result_type=self.result_type,
        )

        self.mcp_client = MCPRegistryClient()
        self.gateway = get_llm_gateway()

    async def register_mcp_tools(self, domain: str) -> None:
        """
        Dynamically fetches tools from MCP server based on domain
        and registers them into the PydanticAI agent.
        """
        tools = await self.mcp_client.discover_tools(domain)
        logger.info(f"[{self.name}] Registering MCP tools: {tools}")

        # In a full implementation, we would dynamically generate
        # python functions that call the MCP server endpoints and
        # register them via `self.agent.tool()` decorator.

        for tool_name in tools:
            # Create a dynamic function closure
            async def mcp_tool_wrapper(query: str, __tool_name=tool_name) -> str:
                """Dynamically dispatched tool to MCP backend."""
                logger.debug(f"[{self.name}] Calling MCP tool: {__tool_name} with args: {query}")
                return f"Executed {__tool_name} with {query}"

            # Pydantic AI uses decorators to register tools or the tool() function
            self.agent.tool(name=tool_name)(mcp_tool_wrapper)

    async def run(self, user_input: str) -> Any:
        """
        Execute the PydanticAI agent with the given user input.
        """
        logger.info(f"[{self.name}] Executing agent run...")

        # PydanticAI handles the orchestration
        try:
            result = await self.agent.run(user_input)
            return result.data
        except Exception as e:
            logger.error(f"[{self.name}] Agent execution failed: {e}")
            raise
