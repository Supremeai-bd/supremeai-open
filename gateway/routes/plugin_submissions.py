import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, HttpUrl

from core.plugins.mcp_security import MCPSecurityGuard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/plugins/community", tags=["community_plugins"])


class PluginSubmission(BaseModel):
    name: str
    description: str
    mcp_url: HttpUrl
    author: str


@router.post("/submit")
async def submit_community_plugin(req: PluginSubmission):
    """
    Accepts community plugin submissions.
    Only allows declarative/MCP plugins for V1 (no executable code).
    """
    logger.info(f"Received community plugin submission: {req.name}")

    # 1. Basic URL Security Check
    mcp_url_str = str(req.mcp_url)
    if not MCPSecurityGuard.is_safe_url(mcp_url_str, enforce_https=True):
        raise HTTPException(
            status_code=400,
            detail="Invalid or unsafe MCP URL. Must be HTTPS and cannot point to internal/private networks.",
        )

    # 2. In a real scenario, this would push to a review queue or run the security scanner.
    # For now we'll just acknowledge receipt.
    return {
        "status": "pending_review",
        "message": f"Plugin '{req.name}' has been submitted for security review.",
        "tracking_id": "PRJ-9938-V1",
    }
