from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import get_current_user_token
from core.llm.llm_gateway import llm_gateway
from core.llm.llm_gateway.context import InferenceContext
from core.logging_config import logger

router = APIRouter(prefix="/workspace/task", tags=["Supreme Workspace Tasks"])


# ==========================================
# ⚙️ PYDANTIC MODELS (Payload & Response Validation)
# ==========================================
class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the speaker (user/assistant)")
    content: str = Field(..., min_length=1, max_length=20000, description="Message content")


class TaskPayload(BaseModel):
    task: str = Field(..., min_length=1, max_length=10000, description="Task prompt description")
    task_type: str = Field("general", description="Category or type of task")
    messages: list[ChatMessage] = Field(
        default_factory=list, description="Recent conversation history"
    )


class TaskExecuteResponse(BaseModel):
    result: str = Field(..., description="Generated execution output or answer")
    status: str = Field("success", description="Status of the task execution")


class TaskQuotaResponse(BaseModel):
    remaining: int = Field(..., description="Remaining token quota for tenant")


# ==========================================
# 🚀 ROUTE: /task/execute
# ==========================================
@router.post("/execute", response_model=TaskExecuteResponse)
async def execute_task(
    payload: TaskPayload,
    background_tasks: BackgroundTasks,
    token_payload: dict = Depends(get_current_user_token),
):
    """
    Handles user prompts from the Vanilla JS Customer Dashboard.
    Integrates Redis rate limiting, RAM conversation history, and Supabase persistent storage.
    """
    _tenant_id = token_payload.get("sub")
    if not _tenant_id:
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        # বাংলা মন্তব্য: মেসেজ হিস্ট্রি এবং নতুন টাস্ক প্রম্পটকে গেটওয়ের উপযোগী মেসেজ লিস্ট স্কিমায় কনভার্ট করা হচ্ছে
        messages_payload = []
        for msg in payload.messages[-5:]:
            messages_payload.append(
                {
                    "role": "user" if msg.role.lower() == "user" else "assistant",
                    "content": msg.content,
                }
            )

        messages_payload.append(
            {
                "role": "user",
                "content": f"Current Task ({payload.task_type}): {payload.task}",
            }
        )

        # ৩. Generate AI Response
        # বাংলা মন্তব্য: সরাসরি গুগল নেটিভ ক্লায়েন্ট কল না করে ইউনিভার্সাল llm_gateway ব্যবহার করে এপিআই কল করা হচ্ছে
        response = await llm_gateway.acompletion(
            prompt=messages_payload,
            # M03 P0-পূর্ণাংশ: InferenceContext বাধ্যতামূলক — token 'sub' টেন্যান্ট
            # অ্যাট্রিবিউশন (আগে কোনো tenant_id যেত না → CostGuard বাইপাসড)।
            context=InferenceContext(
                tenant_id=str(_tenant_id),
                task_type=payload.task_type,
                stream=False,
            ),
        )
        result_text = response.get("text", "") if isinstance(response, dict) else str(response)

        # ৫. Save to Supabase (Database - Long Term) - Background Task
        # রেসপন্স যেন ফাস্ট হয়, তাই ডাটাবেসে সেভ করার কাজটি ব্যাকগ্রাউন্ডে দেওয়া হলো
        def save_to_supabase(task, result):
            try:
                from database.supabase_client import db

                if db.client:
                    db.client.table("task_history").insert(
                        {"task": task, "result": result}
                    ).execute()
            except Exception as e:
                logger.warning(f"Failed to save task history to Supabase: {e}")

        background_tasks.add_task(save_to_supabase, payload.task, result_text)

        return {"result": result_text, "status": "success"}

    except Exception as e:
        logger.info(f"❌ Neural Pipeline Error: {e!s}")
        raise HTTPException(status_code=500, detail="Neural connection pipeline error.") from e


# ==========================================
# 📊 ROUTE: /task/quota
# ==========================================
@router.get("/quota", response_model=TaskQuotaResponse)
async def get_quota(token_payload: dict = Depends(get_current_user_token)):
    """
    Fetch the current token quota from Redis for the UI.
    """
    _tenant_id = token_payload.get("sub")
    if not _tenant_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        from core.cache.redis_manager import redis_manager

        remaining = await redis_manager.client.get(f"quota:{_tenant_id}:remaining")
    except Exception as e:
        # Ripple-Effect Guard: do NOT report 0 here — that is indistinguishable
        # from "quota genuinely exhausted" and will silently block legitimate
        # users during a Redis outage. Surface a distinct error state instead.
        logger.error(f"Quota lookup failed for tenant={_tenant_id}: {e}")
        raise HTTPException(
            status_code=503,
            detail="Quota service temporarily unavailable. Please retry shortly.",
        ) from e

    if remaining is not None:
        return {"remaining": int(remaining)}
    # Key genuinely absent (e.g. new tenant, quota not yet provisioned) — this
    # is a real "0" state, not a masked failure.
    return {"remaining": 0}
