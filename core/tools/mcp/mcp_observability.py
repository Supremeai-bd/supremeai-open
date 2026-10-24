"""
MCP Server for Observability & Production Error Tracking in SupremeAI 2.0.

এই সার্ভারটি প্রোডাকশন এবং CI/CD এনভায়রনমেন্টের এরর লগ, স্ট্যাক ট্রেস এবং হেলথ অডিট
রিপোর্ট ফ্রিতে এক্সট্র্যাক্ট করে এজেন্টের কাছে উপস্থাপন করে।
"""

import json
import os
from pathlib import Path

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

mcp = FastMCP("observability_mcp")

_workspace_root = Path(__file__).parent.parent.parent
LOG_DIR = _workspace_root / "logs"


class SentryIssueInput(BaseModel):
    """Sentry এরর ইস্যু খোঁজার জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    query: str = Field(default="is:unresolved", description="Sentry ইস্যু সার্চ ক্যুরি")
    limit: int = Field(default=5, description="সর্বোচ্চ কতগুলো ইস্যু আনবে", ge=1, le=25)


class LocalLogInput(BaseModel):
    """লোকাল সিস্টেমে থাকা লগ ফাইল পড়ার জন্য ইনপুট।"""

    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True)

    log_filename: str = Field(
        default="app.log", description="লগ ফাইলের নাম (যেমন: app.log, error.log)"
    )
    lines: int = Field(default=50, description="ফাইলের শেষ থেকে কত লাইন আনবে", ge=5, le=200)


@mcp.tool(
    name="observability_fetch_sentry_issues",
    annotations={
        "title": "Fetch Unresolved Sentry Production Issues",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def observability_fetch_sentry_issues(params: SentryIssueInput) -> str:
    """
    Sentry API ব্যবহার করে প্রোডাকশনের অমিমাংসিত এরর ও স্ট্যাক ট্রেস পেচ করে আনে।

    Args:
        params (SentryIssueInput): query ও limit

    Returns:
        str: Sentry ইস্যুর তালিকা বা এরর JSON
    """
    sentry_token = os.environ.get("SENTRY_AUTH_TOKEN")
    org_slug = os.environ.get("SENTRY_ORG_SLUG", "supremeai")
    project_slug = os.environ.get("SENTRY_PROJECT_SLUG", "supremeai-backend")

    if not sentry_token:
        return json.dumps(
            {
                "status": "zero-cost-fallback",
                "message": "SENTRY_AUTH_TOKEN is missing. Returning local zero-cost fallback indicator.",
                "issues": [],
            },
            ensure_ascii=False,
        )

    url = f"https://sentry.io/api/0/projects/{org_slug}/{project_slug}/issues/"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {sentry_token}"},
                params={"query": params.query, "limit": params.limit},
            )
            response.raise_for_status()
            data = response.json()

            issues = []
            for issue in data:
                issues.append(
                    {
                        "id": issue.get("id"),
                        "title": issue.get("title"),
                        "culprit": issue.get("culprit"),
                        "permalink": issue.get("permalink"),
                        "count": issue.get("count"),
                        "userCount": issue.get("userCount"),
                        "lastSeen": issue.get("lastSeen"),
                    }
                )

            return json.dumps({"count": len(issues), "issues": issues}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Failed to fetch Sentry issues: {e}"}, ensure_ascii=False)


@mcp.tool(
    name="observability_tail_local_logs",
    annotations={
        "title": "Tail Local Application Log Files",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def observability_tail_local_logs(params: LocalLogInput) -> str:
    """
    লোকাল সার্ভারের Loguru লগ ফাইল থেকে সর্বশেষ লাইনসমূহ এক্সেস করে।

    Args:
        params (LocalLogInput): log_filename ও lines

    Returns:
        str: লগ ফাইলের লাইনসমূহ বা এরর JSON
    """
    target_log = LOG_DIR / params.log_filename
    if not target_log.exists():
        return json.dumps(
            {"error": f"Log file '{params.log_filename}' does not exist in logs directory."},
            ensure_ascii=False,
        )

    try:
        content_lines = target_log.read_text(encoding="utf-8", errors="replace").splitlines()
        tail_lines = content_lines[-params.lines :]

        return json.dumps(
            {"log_file": str(target_log), "total_lines": len(content_lines), "tail": tail_lines},
            ensure_ascii=False,
        )
    except Exception as e:
        return json.dumps({"error": f"Failed to read log file: {e}"}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
