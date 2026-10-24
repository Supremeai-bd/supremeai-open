from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.dependencies import get_current_admin

# #1656: typed payload replacing bare dict — budget must be non-negative
# to prevent invalid state (negative/infinite/wrong-type values).


class BudgetUpdatePayload(BaseModel):
    """Payload for POST /money/budget."""

    model_config = {"extra": "forbid"}

    tenant_id: str | None = Field(
        default=None, min_length=1, max_length=100, description="Tenant ID; None = default cap"
    )
    cap: float = Field(..., ge=0, description="Budget cap (must be non-negative)")
    period: str = Field(
        default="monthly", pattern="^(daily|weekly|monthly)$", description="Budget period"
    )


router = APIRouter(
    prefix="",
    tags=["Command Center"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/money/cost")
# Issue #1665: these handlers return static/aggregated data with no
# await — plain `def` routes (FastAPI runs them in the threadpool)
# instead of `async def` coroutines that never await. HTTP contract
# unchanged; only the event-loop scheduling semantics are corrected.

def get_cost():
    return {"report": "", "generated_at": ""}


@router.get("/money/usage")
def get_usage():
    return {"daily": [], "cost_projected_monthly": 0, "cost_per_hour": 0}


@router.get("/money/budget")
def get_budget():
    return {"default_cap": 0, "per_tenant": {}}


@router.post("/money/budget")
def update_budget(payload: BudgetUpdatePayload):
    return {"message": "updated"}


@router.get("/money/roi")
def get_roi():
    return {
        "semantic_cache_hits": 0,
        "estimated_usd_saved": 0,
        "duplicate_executions_prevented": 0,
        "api_cost_reduction_ratio": 0,
    }
