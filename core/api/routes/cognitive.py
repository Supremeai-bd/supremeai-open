from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import get_current_user_token
from brain.cognitive_router import get_cognitive_router
from brain.economic_optimizer import BudgetContext, get_economic_optimizer

# AUDIT-FIX (#1704 P0): আগে এই router-এ কোনো auth dependency ছিল না — ফলে
# /cognitive/route যে কেউ কল করতে পারত। এছাড়া request body থেকে user_id
# গ্রহণ করত, যা IDOR-এর সমান — caller অন্য user-এর ভান করে budget bypass
# করতে পারত। এখন authenticated user_token দিয়ে বাধ্যতামূলক করা হয়েছে,
# এবং request-এর user_id-কে সর্বদা token-এর sub দিয়ে override করা হয়।
router = APIRouter(
    prefix="/cognitive",
    tags=["cognitive"],
    dependencies=[Depends(get_current_user_token)],
)


class CognitiveRouteRequest(BaseModel):
    prompt: str
    monthly_limit: float = 10.0
    spent_this_month: float = 0.0
    cost_sensitivity: float = 0.5


@router.post("/route")
async def route_cognitive(
    req: CognitiveRouteRequest,
    token_payload: dict = Depends(get_current_user_token),
):
    # AUDIT-FIX (#1704 P0): user_id এখন request body থেকে নেওয়া হয় না —
    # সর্বদা authenticated token-এর "sub" ব্যবহার করা হয়। এতে IDOR ও
    # billing bypass উভয়ই বন্ধ হয়ে যায়।
    user_id = token_payload.get("sub")
    if not user_id:
        # নিরাপত্তা সর্বদা fail-closed — কোনো silent fallback নয়।
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid token: missing subject")

    economic_optimizer = await get_economic_optimizer()
    cognitive_router_instance = get_cognitive_router(economic_optimizer=economic_optimizer)
    budget_context = BudgetContext(
        user_id=user_id,
        monthly_limit=req.monthly_limit,
        spent_this_month=req.spent_this_month,
        cost_sensitivity=req.cost_sensitivity,
    )
    result = await cognitive_router_instance.route(
        prompt=req.prompt, user_id=user_id, budget_context=budget_context
    )
    return result
