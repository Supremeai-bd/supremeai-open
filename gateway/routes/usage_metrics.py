from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import get_project_admin
from database.supabase_client import db

router = APIRouter(
    prefix="/metrics/usage",
    tags=["usage-metrics"],
    dependencies=[Depends(get_project_admin)],
)


class UsageMetricUpsert(BaseModel):
    metric_date: str
    total_requests: int
    total_tokens: int
    total_cost: float
    unique_users: int
    avg_latency_ms: int
    error_rate: float


@router.get("/")
async def get_usage_metrics(
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=30, le=365),
    user: dict = Depends(get_project_admin),
):
    if not db.client:
        return {"items": [], "total": 0}
    try:
        query = (
            await db.client.table("usage_metrics").select("*").eq("tenant_id", user["tenant_id"])
        )
        if start:
            query = query.gte("date", start)
        if end:
            query = query.lte("date", end)
        res = query.order("date", desc=True).limit(limit).execute()
        return {"items": res.data or [], "total": len(res.data or [])}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/")
async def upsert_usage_metric(
    payload: UsageMetricUpsert,
    user: dict = Depends(get_project_admin),
):
    if not db.client:
        raise HTTPException(status_code=503, detail="Database not configured")
    try:
        data = payload.dict()
        data["tenant_id"] = user["tenant_id"]
        res = await db.client.table("usage_metrics").upsert(data).execute()
        return {"status": "success", "metric": res.data[0] if res.data else data}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
