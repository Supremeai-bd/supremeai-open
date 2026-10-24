from typing import Any

import httpx

from core.logging_config import logger
from core.skills.base import BaseSkill
from models.shared_workspace import SharedWorkspace


class SlackIntegrationSkill(BaseSkill):
    """
    বাংলা মন্তব্য: Slack-এ মেসেজ বা ডেটা সিঙ্ক করার স্কিল।
    """

    @property
    def name(self) -> str:
        return "SlackIntegrationSkill"

    async def execute(self, workspace: SharedWorkspace, user_id: str, **kwargs: Any) -> Any:
        slack_token = kwargs.get("slack_token")
        if not slack_token:
            workspace.log(f"{self.name}: Failed to execute. Missing slack_token.")
            raise ValueError("Slack token is required to execute SlackIntegrationSkill.")

        content = kwargs.get("content", workspace.original_prompt)
        channel = kwargs.get("context", {}).get("channel", "#general")

        workspace.log(f"{self.name}: Sending message to Slack channel {channel}...")

        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {slack_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "channel": channel,
            "text": content,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                if not data.get("ok"):
                    error_msg = data.get("error", "Unknown Slack API error")
                    workspace.log(f"{self.name}: Slack API returned error: {error_msg}")
                    raise RuntimeError(f"Slack API error: {error_msg}")

                workspace.log(f"{self.name}: Successfully sent message to Slack.")
                return {"status": "success", "platform": "slack", "response": data}
            except httpx.HTTPStatusError as e:
                logger.error(f"Slack integration HTTP error: {e}")
                workspace.log(f"{self.name}: HTTP Error: {e}")
                raise RuntimeError(f"Failed to communicate with Slack: {e}") from e
            except Exception as e:
                logger.error(f"Slack integration unexpected error: {e}")
                workspace.log(f"{self.name}: Unexpected Error: {e}")
                raise RuntimeError(f"Unexpected error in Slack integration: {e}") from e


class NotionSyncSkill(BaseSkill):
    """
    বাংলা মন্তব্য: Notion-এ পেজ বা ব্লক তৈরি করার স্কিল।
    """

    @property
    def name(self) -> str:
        return "NotionSyncSkill"

    async def execute(self, workspace: SharedWorkspace, user_id: str, **kwargs: Any) -> Any:
        notion_token = kwargs.get("notion_token")
        if not notion_token:
            workspace.log(f"{self.name}: Failed to execute. Missing notion_token.")
            raise ValueError("Notion token is required to execute NotionSyncSkill.")

        content = kwargs.get("content", workspace.original_prompt)
        parent_page_id = kwargs.get("context", {}).get("parent_page_id")

        workspace.log(f"{self.name}: Syncing content to Notion...")

        if not parent_page_id:
            workspace.log(f"{self.name}: Missing parent_page_id in context.")
            raise ValueError("parent_page_id is required to create a Notion page.")

        url = "https://api.notion.com/v1/pages"
        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        }

        # A simple payload to create a page with a text block
        payload = {
            "parent": {"page_id": parent_page_id},
            "properties": {"title": [{"text": {"content": "AI Synced Document"}}]},
            "children": [
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {"content": content}}]},
                }
            ],
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                workspace.log(f"{self.name}: Successfully synced content to Notion.")
                return {"status": "success", "platform": "notion", "response": data}
            except httpx.HTTPStatusError as e:
                logger.error(f"Notion integration HTTP error: {e}")
                workspace.log(f"{self.name}: HTTP Error: {e}")
                raise RuntimeError(f"Failed to communicate with Notion: {e}") from e
            except Exception as e:
                logger.error(f"Notion integration unexpected error: {e}")
                workspace.log(f"{self.name}: Unexpected Error: {e}")
                raise RuntimeError(f"Unexpected error in Notion integration: {e}") from e


class GithubSyncSkill(BaseSkill):
    """
    বাংলা মন্তব্য: GitHub-এ Issue বা Gist তৈরি করার স্কিল। Action-Dock থেকে পাঠানো ডেটা সিঙ্ক করে।
    """

    @property
    def name(self) -> str:
        return "GithubSyncSkill"

    async def execute(self, workspace: SharedWorkspace, user_id: str, **kwargs: Any) -> Any:
        github_token = kwargs.get("github_token")
        if not github_token:
            workspace.log(f"{self.name}: Failed to execute. Missing github_token.")
            raise ValueError("GitHub token is required to execute GithubSyncSkill.")

        content = kwargs.get("content", workspace.original_prompt)
        repo_name = kwargs.get("context", {}).get("repo", "user/repo")

        workspace.log(f"{self.name}: Syncing content to GitHub repository {repo_name}...")

        url = f"https://api.github.com/repos/{repo_name}/issues"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        payload = {"title": "AI Synced Content", "body": content}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                workspace.log(f"{self.name}: Successfully created issue on GitHub.")
                return {"status": "success", "platform": "github", "response": data}
            except httpx.HTTPStatusError as e:
                logger.error(f"GitHub integration HTTP error: {e}")
                workspace.log(f"{self.name}: HTTP Error: {e}")
                raise RuntimeError(f"Failed to communicate with GitHub: {e}") from e
            except Exception as e:
                logger.error(f"GitHub integration unexpected error: {e}")
                workspace.log(f"{self.name}: Unexpected Error: {e}")
                raise RuntimeError(f"Unexpected error in GitHub integration: {e}") from e
