from typing import Any

from .base import BasePlugin


class GitHubPlugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "github"

    async def execute_tool(
        self, tool_name: str, params: dict[str, Any], context: dict[str, Any]
    ) -> Any:
        access_token = context.get("access_token")
        if not access_token:
            raise ValueError("Missing GitHub access token in context")

        if tool_name == "create_pr":
            return {"status": "success", "message": "PR created (mock)", "params": params}
        elif tool_name == "list_issues":
            return {"status": "success", "issues": []}
        else:
            raise NotImplementedError(f"Tool {tool_name} is not implemented for GitHubPlugin")
