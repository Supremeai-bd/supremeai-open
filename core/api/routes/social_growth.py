from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from core.social_growth import DraftStatus, SocialDraft, SocialPlatform, social_growth_circle

router = APIRouter(prefix="/api/v1/social", tags=["social-growth"])


class DraftRequest(BaseModel):
    platform: SocialPlatform
    body: str = Field(min_length=1, max_length=10_000)
    media_urls: list[str] = Field(default_factory=list, max_length=10)
    scheduled_for: datetime | None = None


def _identity(user: dict) -> tuple[str, str]:
    actor_id = str(user.get("sub") or "")
    tenant_id = str(user.get("tenant_id") or actor_id)
    if not actor_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Authenticated tenant required")
    return actor_id, tenant_id


def _serialize(draft: SocialDraft) -> dict:
    return {
        "id": draft.id,
        "tenant_id": draft.tenant_id,
        "platform": draft.platform.value,
        "body": draft.body,
        "media_urls": list(draft.media_urls),
        "scheduled_for": draft.scheduled_for.isoformat() if draft.scheduled_for else None,
        "status": draft.status.value,
        "approved_by": draft.approved_by,
        "created_at": draft.created_at.isoformat(),
        "published_at": draft.published_at.isoformat() if draft.published_at else None,
        "audit": draft.audit,
    }


@router.get("/drafts")
async def list_drafts(user: dict = Depends(get_current_user_token)):
    _, tenant_id = _identity(user)
    return {"drafts": [_serialize(draft) for draft in social_growth_circle.list_drafts(tenant_id)]}


@router.post("/drafts")
async def create_draft(payload: DraftRequest, user: dict = Depends(get_current_user_token)):
    actor_id, tenant_id = _identity(user)
    try:
        draft = social_growth_circle.create_draft(
            SocialDraft(
                tenant_id=tenant_id,
                author_id=actor_id,
                platform=payload.platform,
                body=payload.body,
                media_urls=tuple(payload.media_urls),
                scheduled_for=payload.scheduled_for,
            )
        )
    except PermissionError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    return {"draft": _serialize(draft)}


@router.post("/drafts/{draft_id}/approve")
async def approve_draft(draft_id: str, user: dict = Depends(get_current_user_token)):
    actor_id, tenant_id = _identity(user)
    try:
        draft = social_growth_circle.approve(draft_id, tenant_id, actor_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"draft": _serialize(draft), "requires_browser_publish": True}


@router.post("/pause")
async def pause_social(user: dict = Depends(get_current_user_token)):
    _, tenant_id = _identity(user)
    social_growth_circle.pause(tenant_id)
    return {"status": DraftStatus.PAUSED.value}


@router.post("/resume")
async def resume_social(user: dict = Depends(get_current_user_token)):
    _, tenant_id = _identity(user)
    social_growth_circle.resume(tenant_id)
    return {"status": "active"}
