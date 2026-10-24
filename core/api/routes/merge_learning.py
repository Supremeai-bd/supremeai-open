"""Merge-Learning webhook + query API (issue #1929).

Founder directive: every merge into main gets a learning report saved to the
database — why it was allowed as an improvement, what it did, and its held
history — so SupremeAI learns from every change (mistakes included).
Auth mirrors the CI webhook: shared X-CI-Webhook-Secret header.
"""

import hmac

from fastapi import APIRouter, Header, HTTPException, Query

from core.config import settings
from models.merge_learning_report import (
    MergeLearningPayload,
    list_merge_learning,
    upsert_merge_learning,
)

router = APIRouter(prefix="/api/merge-learning", tags=["merge-learning"])


def _verify_secret(secret: str) -> None:
    # বাংলা মন্তব্য: সিআই ওয়েবহুকের মতোই শেয়ার্ড সিক্রেট ভেরিফিকেশন
    if not settings.ci_webhook_secret:
        raise HTTPException(status_code=500, detail="CI Webhook Secret not configured on server")
    if not hmac.compare_digest(secret, settings.ci_webhook_secret):
        raise HTTPException(status_code=401, detail="Unauthorized webhook request")


@router.post("/webhook")
async def merge_learning_webhook(
    payload: MergeLearningPayload,
    x_ci_webhook_secret: str = Header(..., alias="X-CI-Webhook-Secret"),
) -> dict:
    """PR-helper recorder lands merge learning reports here (idempotent upsert)."""
    _verify_secret(x_ci_webhook_secret)
    row = await upsert_merge_learning(payload)
    if not row:
        raise HTTPException(status_code=500, detail="Failed to store merge learning report")
    return {"status": "success", "report_id": row["id"], "pr_number": row["pr_number"]}


@router.get("/reports")
async def get_merge_learning_reports(
    x_ci_webhook_secret: str = Header(..., alias="X-CI-Webhook-Secret"),
    lane: str | None = Query(default=None, description="Filter by agent lane"),
    risk_class: str | None = Query(default=None, description="Filter by gate risk class"),
    held_only: bool = Query(
        default=False, description="Only merges that were held (mistake trail)"
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Teach-back: query the learning base (agents + evolution module read here)."""
    _verify_secret(x_ci_webhook_secret)
    rows = await list_merge_learning(
        lane=lane, risk_class=risk_class, held_only=held_only, limit=limit, offset=offset
    )
    return {"status": "success", "count": len(rows), "reports": rows}
