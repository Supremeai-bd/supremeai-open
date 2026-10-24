from typing import Any

from .base import BasePlugin


class NotionPlugin(BasePlugin):
    """Notion plugin — experimental, limited tool coverage.

    Lifecycle: IDEA. Moved from official/ after audit discovered
    NotImplementedError on first tool call.
    """

    @property
    def plugin_id(self) -> str:
        return "notion"

    @property
    def lifecycle(self) -> str:
        return "IDEA"

    async def execute_tool(
        self, tool_name: str, params: dict[str, Any], context: dict[str, Any]
    ) -> Any:
        raise NotImplementedError(
            "Notion plugin is experimental with limited tool coverage. "
            "No tools are implemented yet — check back later."
        )
