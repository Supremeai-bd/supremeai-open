from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    """
    Abstract base class for all official native plugins in SupremeAI.
    """

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier for this plugin."""
        pass

    @abstractmethod
    async def execute_tool(
        self, tool_name: str, params: dict[str, Any], context: dict[str, Any]
    ) -> Any:
        """
        Executes a specific tool provided by this plugin.
        :param tool_name: The name of the tool to execute.
        :param params: Arguments for the tool.
        :param context: Execution context (e.g., auth tokens, user info).
        """
        pass
