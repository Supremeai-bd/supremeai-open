from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from agents.syncguard.syncguard_agent import SyncGuardAgent
from api.dependencies import get_current_admin

router = APIRouter(
    prefix="/syncguard",
    tags=["SyncGuard"],
    dependencies=[Depends(get_current_admin)],
    responses={404: {"description": "Not found"}},
)


@router.post("/audit", response_model=dict[str, Any])
async def trigger_audit() -> dict[str, Any]:
    """
    Manually trigger a full infrastructure and configuration audit.
    Can be called via the 'Recheck Safeguard' button on Web, Mobile, or VS Code.
    """
    try:
        agent = SyncGuardAgent()
        report = await agent.run_full_audit()
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Audit execution failed: {e!s}") from e
