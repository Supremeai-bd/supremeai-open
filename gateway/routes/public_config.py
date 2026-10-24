from fastapi import APIRouter
from pydantic import BaseModel

from core.config import settings
from utils.branding import MODEL_DISPLAY, PROVIDER_DISPLAY

router = APIRouter(
    prefix="/config/public",
    tags=["public_config"],
)


class PublicConfigResponse(BaseModel):
    maxConcurrency: int  # -- camelCase required to match frontend JSON API contract
    features: dict[str, bool]
    version: str
    models: dict[str, str]
    adminEmail: str = ""  # -- empty to prevent administrative email disclosure


@router.get("", response_model=PublicConfigResponse)
async def get_public_config():
    # Safe defaults without leaking internal administrative emails
    return PublicConfigResponse(
        adminEmail="",
        maxConcurrency=3,
        features={"selfHealing": True, "costGuard": True},
        version="2.0.0",
        models={
            "chat": settings.model_chat,
            "general": settings.model_general,
            "multilingual": settings.model_multilingual,
        },
    )


@router.get("/branding")
async def get_public_branding():
    """Return the canonical SupremeAI model/provider branding maps.

    Public (no auth) so the customer dashboard can brand model names without
    an admin token. The frontend uses this as the single source of truth,
    falling back to its local copy when offline.
    """
    return {
        "models": {k: v["label"] for k, v in MODEL_DISPLAY.items()},
        "providers": PROVIDER_DISPLAY,
    }
