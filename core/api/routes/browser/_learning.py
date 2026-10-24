"""System-learning toggle endpoints (in-memory compat state).

Split out of the former single-module api/routes/browser.py verbatim.

Issue #1657 (P1 security audit): ``toggle_learning`` used to accept
``body: dict[str, bool]`` — a bare dict whose ``enabled`` value was trusted
as truthy without type validation (so ``"false"`` — a non-empty string —
would have been treated as enabled=True). The request is now a strict
Pydantic model: ``enabled`` must be a real bool and unknown keys are 422.
"""

from typing import Any

from fastapi import Depends
from pydantic import BaseModel, ConfigDict, StrictBool

from api.routes.admin_dashboard import require_admin_token
from api.routes.browser import router

SYSTEM_LEARNING: dict[str, Any] = {"enabled": True}


class ToggleLearningRequest(BaseModel):
    """Body for POST /system-learning/toggle.

    ``enabled`` defaults to True (the previous ``body.get("enabled", True)``
    behaviour). ``extra="forbid"`` rejects unexpected payload keys outright.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: StrictBool = True


@router.get("/system-learning")
def get_system_learning():
    return SYSTEM_LEARNING


@router.post("/system-learning/toggle", dependencies=[Depends(require_admin_token)])
def toggle_learning(body: ToggleLearningRequest):
    SYSTEM_LEARNING["enabled"] = body.enabled
    return {"success": True}
