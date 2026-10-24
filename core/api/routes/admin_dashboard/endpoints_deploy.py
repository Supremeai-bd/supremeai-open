"""Deployment trigger endpoint (POST /admin-api/deploy)."""

from fastapi import HTTPException, status

from api.routes.admin_dashboard import router


@router.post("/deploy")
def trigger_deploy():
    """Fail closed until a real deployment provider is configured."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Deployment orchestration is not configured for this environment.",
    )
