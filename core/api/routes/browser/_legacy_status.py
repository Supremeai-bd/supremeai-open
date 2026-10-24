"""Legacy surf status/activity endpoints (in-memory compat state).

Split out of the former single-module api/routes/browser.py verbatim.
"""

from fastapi import Depends, HTTPException

from api.deps import get_current_user_token
from api.routes.browser import router
from api.routes.browser._state import BROWSER_STATUS, RECENT_ACTIVITIES


@router.get("/surf/status")
def get_status(user: dict = Depends(get_current_user_token)):
    if not user.get("sub") or not user.get("tenant_id"):
        raise HTTPException(status_code=401, detail="Authenticated tenant required")
    return BROWSER_STATUS


@router.post("/surf/start")
def start_surf(user: dict = Depends(get_current_user_token)):
    if not user.get("sub") or not user.get("tenant_id"):
        raise HTTPException(status_code=401, detail="Authenticated tenant required")
    BROWSER_STATUS["browsing"] = True
    return {"status": "started"}


@router.post("/surf/stop")
def stop_surf(user: dict = Depends(get_current_user_token)):
    if not user.get("sub") or not user.get("tenant_id"):
        raise HTTPException(status_code=401, detail="Authenticated tenant required")
    BROWSER_STATUS["browsing"] = False
    return {"status": "stopped"}


@router.get("/activity/recent")
def get_recent_activity(user: dict = Depends(get_current_user_token)):
    if not user.get("sub") or not user.get("tenant_id"):
        raise HTTPException(status_code=401, detail="Authenticated tenant required")
    return {"activities": RECENT_ACTIVITIES}
