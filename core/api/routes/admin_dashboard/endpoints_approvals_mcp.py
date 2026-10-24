"""MCP control-tower approvals bridge
(GET/POST /admin-api/approvals/mcp — M17 P-A route-ownership fix: আগে এই
জোড়া ক্যানোনিকাল pending-task pair-এর একই path দখল করে shadow করত
(import-order-এ আগে নিবন্ধিত হওয়ায় first-match জিতে যেত) — ফলে
MCP-unconfigured অবস্থায় admin-approvals GET নীরবে খালি [] ফেরত দিত
(fake-empty queue)। এখন এটি নিজস্ব distinct path-এ থাকে — ক্যানোনিকাল
pending-task view (endpoints_command) /admin-api/approvals-এর মালিক।
"""

import os

from fastapi import HTTPException

from api.routes.admin_dashboard import router
from api.routes.admin_dashboard._models import ApprovalActionPayload
from core.logging_config import logger


@router.get("/approvals/mcp")
async def get_commandcenter_approvals_mcp():
    """Fetches real-time pending & historical approvals from MCP Control Tower."""
    mcp_url = os.getenv("RENDER_MCP_URL") or os.getenv("MCP_URL")
    if not mcp_url:
        logger.warning("RENDER_MCP_URL/MCP_URL not configured; skipping MCP approvals fetch.")
        return []
    admin_key = os.getenv("MCP_ADMIN_KEY") or os.getenv("MCP_API_KEY")
    try:
        import httpx

        headers = {}
        if admin_key:
            headers["Authorization"] = f"Bearer {admin_key}"
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(f"{mcp_url.rstrip('/')}/approvals", headers=headers)
            if resp.status_code == 200:
                return resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch approvals from MCP control tower: {e}")

    # Fallback to local queue if MCP unreachable
    return []


@router.post("/approvals/mcp")
async def resolve_commandcenter_approval_mcp(payload: ApprovalActionPayload):
    """Approves or rejects a Human-In-The-Loop request directly from the Admin Dashboard."""
    mcp_url = os.getenv("RENDER_MCP_URL") or os.getenv("MCP_URL")
    if not mcp_url:
        raise HTTPException(
            status_code=503,
            detail="MCP Control Tower is not configured (RENDER_MCP_URL/MCP_URL missing).",
        )
    admin_key = os.getenv("MCP_ADMIN_KEY") or os.getenv("MCP_API_KEY")
    decision = "APPROVED" if payload.approve else "REJECTED"
    try:
        import httpx

        headers = {}
        if admin_key:
            headers["Authorization"] = f"Bearer {admin_key}"
        url = f"{mcp_url.rstrip('/')}/approve?id={payload.id}&decision={decision}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code in (200, 302):
                return {
                    "status": "success",
                    "message": f"Request {payload.id} marked as {decision}",
                }
            raise HTTPException(
                status_code=resp.status_code, detail="Control tower rejected approval"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving approval on MCP: {e}")
        raise HTTPException(status_code=502, detail=f"Approval resolution failed: {e}")
