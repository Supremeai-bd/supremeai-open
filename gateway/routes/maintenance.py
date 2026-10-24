from fastapi import APIRouter, Depends

from api.dependencies import get_current_admin
from core.maintenance_pipeline import maintenance_pipeline

router = APIRouter(
    prefix="/maintenance",
    tags=["Maintenance"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/status")
async def get_maintenance_status():
    """
    Get the real-time status of the SupremeAI Immune System.
    """
    return await maintenance_pipeline.run_health_check()
