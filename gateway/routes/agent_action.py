from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_current_user_token
from core.logging_config import logger
from core.security.security_vault import decrypt_token
from core.security.tool_gateway import ToolPolicyViolation, tool_policy_gateway
from core.zero_cost_architecture.swarm_orchestrator_integration import ZeroCostSwarmOrchestrator
from database.session import get_db_session
from models.integration import Integration

router = APIRouter(tags=["Agent Action"])


class ActionPayload(BaseModel):
    target_platform: str  # "slack", "notion", "github"
    content: str
    context: dict[str, Any] = {}


@router.post("/agent/action")
async def run_agent_action(
    payload: ActionPayload,
    token_payload: dict = Depends(get_current_user_token),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Unified endpoint for executing AI agent actions targeting external platforms.
    """
    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user token")

    platform = payload.target_platform.lower()

    # AUD-3.2/3.3 (P0): external side-effecting actions now pass through the
    # single canonical policy gateway (identity/tenant/role/risk/budget + audit).
    try:
        await tool_policy_gateway.enforce(
            tool_name=f"platform_action.{platform}",
            user=token_payload,
            risk="high",  # external side effects (Slack/Notion/GitHub writes)
        )
    except ToolPolicyViolation as violation:
        raise HTTPException(status_code=403, detail=violation.decision.reason) from violation

    # 1. Fetch encrypted token from database
    try:
        stmt = select(Integration).where(
            Integration.user_id == user_id,
            Integration.provider == platform,
        )
        result = await db.execute(stmt)
        integration = result.scalar_one_or_none()

        if not integration or not integration.encrypted_access_token:
            raise HTTPException(
                status_code=400,
                detail=f"Integration for {platform} not found. Please connect {platform} in your settings.",
            )

        # 2. Decrypt token securely in the API layer (Stateless injection)
        plain_token = decrypt_token(integration.encrypted_access_token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching integration for {platform}: {e}")
        raise HTTPException(status_code=500, detail="Database or Decryption error") from e

    # 3. Setup Intent and kwargs for the Orchestrator
    intent = f"sync_to_{platform}"
    kwargs = {
        f"{platform}_token": plain_token,
        "content": payload.content,
        "context": payload.context,
    }

    # 4. Trigger Morphic Orchestrator
    try:
        logger.info(f"Triggering ZeroCostSwarmOrchestrator for intent '{intent}'")
        orchestrator = ZeroCostSwarmOrchestrator()

        # বাংলা মন্তব্য: রিকোয়েস্টে ডাবল সোয়ার্ম এক্সিকিউশন ও ওপারেশনাল কস্ট এড়াতে সরাসরি কাস্টম ওয়ার্কস্পেস দিয়ে রান করানো হচ্ছে।
        import uuid

        from models.shared_workspace import SharedWorkspace

        custom_workspace = SharedWorkspace(
            task_id=str(uuid.uuid4()), original_prompt=payload.content, intent=intent
        )
        custom_workspace.kwargs = kwargs

        # বাংলা মন্তব্য: ডুপ্লিকেট এবং বাগি লোকাল DAG লুপ পরিহার করে সেন্ট্রাল run_dag_for_workspace রান করা হলো।
        custom_workspace = await orchestrator.run_dag_for_workspace(
            custom_workspace, user_id=user_id
        )

        result = custom_workspace.work_product.get("integration_result", {})
        if result.get("status") == "error":
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Integration Execution Failed"),
            )

        return {
            "status": "success",
            # Issue #1816: SharedWorkspace's field is execution_logs (there is
            # no .logs attribute — the old reference raised AttributeError and
            # 500'd every successful sync right at the response build).
            "workspace_logs": custom_workspace.execution_logs,
            "result": result,
        }

    except HTTPException:
        # বাংলা মন্তব্য: ফোর-হান্ড্রেড রেঞ্জের ভ্যালিডেশন এররগুলো যাতে ৫০০-তে কনভার্ট না হয় সেজন্য সরাসরি রি-রেইজ করা হলো।
        raise
    except Exception as e:
        logger.error(f"Failed to execute agent action: {e}")
        raise HTTPException(status_code=500, detail=f"Agent Execution Error: {e}") from e
