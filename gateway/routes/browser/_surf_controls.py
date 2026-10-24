"""Legacy manual-pause surf controls (admin-guarded).

Split out of the former single-module api/routes/browser.py verbatim.

Issue #1657 (P1 security audit): the three POST endpoints here used to accept
``body: dict[str, str]`` — an unvalidated bare-dict body with no Pydantic
model, so arbitrary payloads were accepted and silently discarded. Each
endpoint now takes a strict Pydantic model so malformed requests are rejected
with 422 at the validation layer instead of being swallowed.
"""

from typing import Any

from fastapi import Depends
from pydantic import BaseModel, ConfigDict

from api.routes.admin_dashboard import require_admin_token
from api.routes.browser import router

PAUSED_STATE: dict[str, Any] = {"paused": False}


class SurfControlRequest(BaseModel):
    """Strict body for /surf/resume, /surf/skip-auth and /surf/pause-manual.

    The handlers perform no per-request computation from the body (they only
    flip :data:`PAUSED_STATE`), so the model intentionally declares zero
    fields. ``extra="forbid"`` turns any unexpected payload key into a 422 —
    previously anything was accepted and silently ignored.
    """

    model_config = ConfigDict(extra="forbid")


@router.post("/surf/resume", dependencies=[Depends(require_admin_token)])
def resume_surf(body: SurfControlRequest):
    PAUSED_STATE["paused"] = False
    return {"status": "resumed"}


@router.post("/surf/skip-auth", dependencies=[Depends(require_admin_token)])
def skip_auth(body: SurfControlRequest):
    PAUSED_STATE["paused"] = False
    return {"status": "auth_skipped"}


@router.post("/surf/pause-manual", dependencies=[Depends(require_admin_token)])
def pause_manual(body: SurfControlRequest):
    PAUSED_STATE["paused"] = True
    return {"status": "paused_for_manual"}


@router.get("/surf/paused-state")
def get_paused_state():
    return PAUSED_STATE
