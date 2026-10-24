"""Universal Zero-Complexity Interface — Access API (Phase 1).

বাংলা: execution-mode self-service endpoint। নিয়ম (Correction 2):
- User শুধু নিজের মোড বদলাতে পারবে — অন্য user-এর নয়।
- Mode enum backend-এ validate হয় — client যা পাঠাক, ভাঙবে না।
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.routes.connections import SetModeRequest, SetModeResponse, set_execution_mode
from core.security.authentication.rbac import get_current_user_token

router = APIRouter(prefix="/api/v1/access", tags=["access"])


@router.post("/set-mode", response_model=SetModeResponse)
async def set_mode(
    payload: SetModeRequest, current_user: dict = Depends(get_current_user_token)
) -> SetModeResponse:
    return await set_execution_mode(payload, current_user)
