from typing import Any

from .base import BasePlugin


class SlackPlugin(BasePlugin):
    """Slack plugin — experimental, not yet implemented.

    Lifecycle: IDEA. No real tool coverage.
    Returns graceful 'unavailable' rather than crashing.
    """

    @property
    def plugin_id(self) -> str:
        return "slack"

    @property
    def lifecycle(self) -> str:
        return "IDEA"

    async def execute_tool(
        self, tool_name: str, params: dict[str, Any], context: dict[str, Any]
    ) -> Any:
        raise NotImplementedError(
            "Slack plugin is experimental and not yet implemented. Please check back later."
        )
