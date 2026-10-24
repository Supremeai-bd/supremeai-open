# backend/api/routes/admin_librarian.py

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from agents.skill_librarian import SkillLibrarian
from api.routes.admin import get_current_admin

# 🔄 প্রিফিক্স ডুপ্লিকেশন ফিক্স (/api/api/admin... থেকে /api/admin...)
router = APIRouter(
    prefix="/api/admin/librarian",
    tags=["Admin Librarian"],
    dependencies=[Depends(get_current_admin)],
)
librarian = SkillLibrarian()


class ApprovalRequest(BaseModel):
    skill_id: str
    action: str  # APPROVE, APPROVE_AS_EPHEMERAL, REJECT
    ai_patch_code: str | None = None


@router.get("/queue", response_model=list[dict])
async def get_quarantine_queue():
    """কোয়ারেন্টাইনে থাকা পেন্ডিং স্কিলগুলোর লিস্ট ড্যাশবোর্ডে পাঠায়"""
    try:
        return librarian.list_quarantine_queue()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch queue: {e!s}") from e


@router.post("/process")
async def process_skill_action(payload: ApprovalRequest, background_tasks: BackgroundTasks):
    """
    Admin এর অ্যাকশন রিকোয়েস্ট গ্রহণ করে সাথে সাথে ২০০ OK রেসপন্স দেয়।
    ভারী ফাইল অপারেশন এবং ডিস্ক রাইট ব্যাকগ্রাউন্ডে প্রসেস হয়।
    """
    if payload.action not in ["APPROVE", "APPROVE_AS_EPHEMERAL", "REJECT"]:
        raise HTTPException(status_code=400, detail="Invalid action provided.")

    # 🚀 ভারী কাজগুলো ব্যাকগ্রাউন্ড টাস্কে পুশ করা হলো
    background_tasks.add_task(
        librarian.process_approval,
        skill_id=payload.skill_id,
        action=payload.action,
        ai_patch_code=payload.ai_patch_code,
    )

    # ইউজার ইন্টারফেস সাথে সাথে ফ্রি (Instant UI Response)
    return {
        "success": True,
        "detail": "Action queued successfully for asynchronous processing.",
    }
