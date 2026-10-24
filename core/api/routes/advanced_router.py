# SupremeAI 2.0 — Advanced Model Router API Router
# বাংলা মন্তব্য: এটি স্মার্ট প্রম্পট এনালাইসিস এবং মডেল ডাইনামিক রাউটিং এর FastAPI এন্ডপয়েন্ট সরবরাহ করে।

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.llm.advanced_model_router import AdvancedModelRouter
from core.security.authentication.rbac import get_current_user_token

router = APIRouter(
    prefix="/api/v1/router",
    tags=["Advanced Model Router"],
    dependencies=[Depends(get_current_user_token)],
)

global_router = AdvancedModelRouter()


class RouteRequest(BaseModel):
    prompt: str
    task_type: str | None = "general"
    user_id: str | None = None
    budget_constraint: float | None = None


@router.post("/route")
async def route_model(req: RouteRequest):
    """
    Route an LLM request to the optimal model based on task type, complexity, and budget constraints.
    """
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Prompt cannot be empty")

    decision = await global_router.route_request(
        prompt=req.prompt,
        task_type=req.task_type or "general",
        user_id=req.user_id,
        budget_constraint=req.budget_constraint,
    )

    complexity = global_router.analyze_prompt_complexity(req.prompt)

    return {
        "status": "success",
        "task_type": req.task_type,
        "prompt_complexity": complexity,
        "decision": {
            "provider": decision.provider,
            "model": decision.model,
            "priority_score": decision.priority_score,
            "expected_cost": decision.expected_cost,
            "expected_latency": decision.expected_latency,
        },
    }
