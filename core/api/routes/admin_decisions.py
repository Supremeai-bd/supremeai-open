"""Admin decisions API (#4052) — query agent decision metadata.

বাংলা: `GET /api/admin/decisions` — agent/task_type/outcome/since ফিল্টারসহ
decision metadata তালিকা (acceptance #6)। পড়া-শুধু (read-only) — সিদ্ধান্ত
রেকর্ডিং store API (core.learning.decision_store) দিয়েই হয়, admin API-র
মাধ্যমে নয় (provenance অখণ্ড রাখতে)।
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from api.dependencies import get_current_admin
from core.learning.decision_store import get_decision, query_decisions

router = APIRouter(prefix="/api/admin/decisions", tags=["Admin Learning"])


class DecisionRecord(BaseModel):
    id: str
    agent_type: str
    task_type: str
    decision: str
    why: str
    outcome: str
    status: str


class DecisionsResponse(BaseModel):
    count: int
    filters: dict[str, str | None]
    decisions: list[dict]


@router.get("", response_model=DecisionsResponse)
async def list_decisions(
    agent: str | None = Query(None, description="agent_type filter"),
    task_type: str | None = Query(None, description="task_type filter"),
    outcome: str | None = Query(None, description="success|fail|partial|pending"),
    since: datetime | None = Query(None, description="created_at >= since (ISO-8601)"),
    include_deprecated: bool = Query(False, description="include superseded decisions"),
    limit: int = Query(100, ge=1, le=500),
    _admin: dict = Depends(get_current_admin),
) -> DecisionsResponse:
    """Decision metadata তালিকা — ফিল্টার সাপোর্ট (acceptance #6)।"""
    rows = await query_decisions(
        agent_type=agent,
        task_type=task_type,
        outcome=outcome,
        since=since,
        status=None if include_deprecated else "active",
        limit=limit,
    )
    return DecisionsResponse(
        count=len(rows),
        filters={
            "agent": agent,
            "task_type": task_type,
            "outcome": outcome,
            "since": since.isoformat() if since else None,
            "include_deprecated": str(include_deprecated),
        },
        decisions=rows,
    )


@router.get("/{decision_id}", response_model=dict)
async def get_one_decision(
    decision_id: str,
    _admin: dict = Depends(get_current_admin),
) -> dict:
    """এক সিদ্ধান্ত + provenance chain entry-point (supersedes রেফারেন্সসহ)।"""
    row = await get_decision(decision_id)
    if row is None:
        return {"error": "decision not found", "id": decision_id}
    return row
