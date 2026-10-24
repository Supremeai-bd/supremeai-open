from typing import Any

from .base import BasePlugin


class TelegramPlugin(BasePlugin):
    """Telegram plugin — experimental, not yet implemented.

    Lifecycle: IDEA. No real tool coverage.
    Returns graceful 'unavailable' rather than crashing.
    """

    @property
    def plugin_id(self) -> str:
        return "telegram"

    @property
    def lifecycle(self) -> str:
        return "IDEA"

    async def execute_tool(
        self, tool_name: str, params: dict[str, Any], context: dict[str, Any]
    ) -> Any:
        raise NotImplementedError(
            "Telegram plugin is experimental and not yet implemented. Please check back later."
        )
