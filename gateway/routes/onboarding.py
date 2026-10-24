"""
Onboarding API — POST /api/onboarding/complete
Validates user's initial setup: API keys, preferred model, first chat confirmation.
"""

from __future__ import annotations

import pathlib
import time
from typing import Any

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from core.logging_config import logger

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

SUPPORTED_PROVIDERS = {
    "openai": "https://api.openai.com/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "gemini": "https://generativelanguage.googleapis.com/v1/models?key={key}",
    "groq": "https://api.groq.com/openai/v1/models",
    "deepseek": "https://api.deepseek.com/v1/models",
}


class OnboardingPayload(BaseModel):
    user_id: str
    provider: str = "openrouter"
    api_key: str
    default_model: str | None = "gpt-4o-mini"
    theme: str | None = "dark"
    language: str | None = "en"
    first_chat_sent: bool = False


class OnboardingResponse(BaseModel):
    status: str
    user_id: str
    provider_valid: bool
    model_ready: bool
    message: str
    setup_complete: bool


async def _validate_api_key(provider: str, api_key: str) -> bool:
    """Quick validation — hits the provider's /models endpoint."""
    if provider not in SUPPORTED_PROVIDERS:
        return True  # Unknown provider — assume valid
    url = SUPPORTED_PROVIDERS[provider].format(key=api_key)
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url, headers=headers)
            return resp.status_code in (200, 206)
    except Exception as exc:
        logger.debug(f"API key validation request failed: {exc}")
        return False


def _save_user_preferences(payload: OnboardingPayload) -> bool:
    """Save preferences to Supabase or local fallback."""
    prefs = {
        "user_id": payload.user_id,
        "theme": payload.theme,
        "default_model": payload.default_model,
        "auto_save": True,
        "custom_shortcuts": {
            "provider": payload.provider,
            "language": payload.language,
            "onboarding_completed_at": time.time(),
        },
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        from database.supabase_client import db

        if db.client:
            db.client.table("user_preferences").upsert(prefs).execute()
            logger.info(f"Onboarding prefs saved to Supabase for {payload.user_id}")
            return True
    except Exception as exc:
        logger.debug(f"Supabase preference save failed: {exc}")

    # Local fallback
    try:
        import json

        p = pathlib.Path("data/user_prefs")
        p.mkdir(parents=True, exist_ok=True)
        safe = payload.user_id.replace("/", "_")[:40]
        (p / f"{safe}.json").write_text(json.dumps(prefs, indent=2))
        return True
    except Exception as exc:
        logger.warning(f"Local preference save failed: {exc}")
        return False


@router.post("/complete", response_model=OnboardingResponse)
async def complete_onboarding(payload: OnboardingPayload):
    """
    Complete user onboarding:
    1. Validate API key against provider
    2. Save user preferences (theme, model, language)
    3. Return readiness status
    """
    logger.info(
        f"Onboarding completion request for user={payload.user_id} provider={payload.provider}"
    )

    # 1. Validate API key
    provider_valid = await _validate_api_key(payload.provider, payload.api_key)
    if not provider_valid:
        logger.warning(f"API key validation failed for {payload.provider}")

    # 2. Save preferences (even if key invalid — user can fix later)
    _save_user_preferences(payload)

    # 3. Optionally store encrypted key in secure_credential_store
    if provider_valid and payload.api_key:
        try:
            from core.security.secure_credential_store import SecureCredentialStore

            store = SecureCredentialStore()
            store.set(f"{payload.user_id}:{payload.provider}_api_key", payload.api_key)
        except Exception as exc:
            logger.debug(f"Credential store failed: {exc}")

    model_ready = provider_valid and bool(payload.default_model)

    if not provider_valid:
        message = (
            f"⚠️ API key validation for '{payload.provider}' failed. "
            "You can still explore SupremeAI with free-tier models. "
            "Update your key in Settings anytime."
        )
    elif model_ready:
        message = f"🚀 You're all set! {payload.default_model} is ready. Start chatting or explore the Studio."
    else:
        message = "✅ Preferences saved. Select a model to complete setup."

    return OnboardingResponse(
        status="success",
        user_id=payload.user_id,
        provider_valid=provider_valid,
        model_ready=model_ready,
        message=message,
        setup_complete=model_ready and payload.first_chat_sent,
    )


@router.get("/status/{user_id}")
async def get_onboarding_status(user_id: str) -> dict[str, Any]:
    """Check if a user has completed onboarding."""
    try:
        from database.supabase_client import db

        if db.client:
            res = (
                await db.client.table("user_preferences")
                .select("*")
                .eq("user_id", user_id)
                .execute()
            )
            if res.data:
                prefs = res.data[0]
                completed_at = prefs.get("custom_shortcuts", {}).get("onboarding_completed_at")
                return {
                    "user_id": user_id,
                    "onboarding_complete": bool(completed_at),
                    "completed_at": completed_at,
                    "preferences": {
                        "theme": prefs.get("theme", "dark"),
                        "default_model": prefs.get("default_model", ""),
                        "language": prefs.get("custom_shortcuts", {}).get("language", "en"),
                    },
                }
    except Exception as exc:
        logger.debug(f"Status check DB error: {exc}")

    return {"user_id": user_id, "onboarding_complete": False}


@router.delete("/reset/{user_id}")
async def reset_onboarding(user_id: str) -> dict[str, str]:
    """Reset onboarding state (for testing/support)."""
    try:
        from database.supabase_client import db

        if db.client:
            await db.client.table("user_preferences").delete().eq("user_id", user_id).execute()
    except Exception as exc:
        logger.warning(f"Failed to reset onboarding state for {user_id}: {exc}")
    return {"status": "reset", "user_id": user_id}


class OnboardingPlanRequest(BaseModel):
    locale: str = "en"
    source: str = "mobile"
    declared_goal: str | None = None
    persona: str = "developer"
    experience_level: str = "intermediate"


class OnboardingSignalRequest(BaseModel):
    user_id: str = "default"
    step_id: str
    signal: dict[str, Any] = {}


@router.post("/plan")
async def build_onboarding_plan(req: OnboardingPlanRequest):
    """ADVANCED: Generates a personalized onboarding DAG based on user intent and persona."""
    try:
        from adaptive_engine.learning_loop import LearningLoop

        loop = LearningLoop.get_instance()
        steps = await loop.personalize_flow(
            persona=req.persona,
            experience_level=req.experience_level,
        )
        return {"status": "success", "steps": steps, "persona": req.persona}
    except Exception as e:
        logger.warning(f"[Onboarding] Plan generation fallback: {e}")
        return {
            "status": "fallback",
            "steps": [
                {"id": "welcome", "title": "Welcome to SupremeAI", "required": True},
                {"id": "ready", "title": "Get Started", "required": True},
            ],
        }


@router.post("/signal")
async def record_onboarding_signal(sig: OnboardingSignalRequest):
    """ADVANCED: Records real-time user interaction signals to train the AdaptiveEngine."""
    try:
        from adaptive_engine.learning_loop import LearningLoop

        loop = LearningLoop.get_instance()
        await loop.record_signal(
            user_id=sig.user_id,
            signal_type="onboarding_interaction",
            payload={"step_id": sig.step_id, **sig.signal},
        )
        reorder = await loop.suggest(user_id=sig.user_id)
        return {"status": "recorded", "reorder": reorder}
    except Exception as e:
        logger.debug(f"[Onboarding] Signal recording skipped: {e}")
        return {"status": "skipped", "error": str(e)}
