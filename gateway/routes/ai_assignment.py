"""
AI Surface Assignment API
=========================
Admin can see all AI providers + their API keys, and assign which AI
serves which surface (Web Chat, IDE, Telegram, API).

Endpoints:
    GET  /api/admin/ai/surfaces        — list all surfaces + assigned AI
    GET  /api/admin/ai/providers       — list all AI providers + key status
    POST /api/admin/ai/assign          — assign AI to a surface
    GET  /api/admin/ai/assignment      — get current assignment map
    POST /api/admin/ai/test/{provider} — test a provider's API key
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.dependencies import get_current_admin
from core.logging_config import logger

router = APIRouter(prefix="/api/admin/ai", tags=["AI Surface Assignment"])

# ── Surfaces ──────────────────────────────────────────────────────────
SURFACES = [
    {"id": "web_chat", "name": "Web Chat", "icon": "💬", "description": "Dashboard chat interface"},
    {"id": "ide", "name": "IDE (Trio)", "icon": "💻", "description": "IDE code assistant pipeline"},
    {
        "id": "telegram",
        "name": "Telegram Bot",
        "icon": "📱",
        "description": "Telegram AI responses",
    },
    {
        "id": "api",
        "name": "API (Direct)",
        "icon": "🔌",
        "description": "Direct API /v1/chat/completions",
    },
    {
        "id": "research",
        "name": "Deep Research",
        "icon": "🔍",
        "description": "Scout/deep research agent",
    },
    {
        "id": "automation",
        "name": "Automation",
        "icon": "🤖",
        "description": "Browser automation agent",
    },
]

# ── Provider definitions ──────────────────────────────────────────────
PROVIDERS = [
    {
        "id": "groq",
        "name": "Groq",
        "env_key": "GROQ_API_KEY",
        "tier": 1,
        "speed": "fastest",
        "cost": "free",
    },
    {
        "id": "gemini",
        "name": "Gemini Flash",
        "env_key": "GEMINI_API_KEY",
        "tier": 1,
        "speed": "fast",
        "cost": "free",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "env_key": "OPENROUTER_API_KEY",
        "tier": 2,
        "speed": "medium",
        "cost": "free",
    },
    {
        "id": "mistral",
        "name": "Mistral",
        "env_key": "MISTRAL_API_KEY",
        "tier": 2,
        "speed": "fast",
        "cost": "free",
    },
    {
        "id": "byna",
        "name": "Bynara",
        "env_key": "BYNARA_API_KEY",
        "tier": 2,
        "speed": "medium",
        "cost": "free",
    },
    {
        "id": "bai",
        "name": "BAI",
        "env_key": "BAI_API_KEY",
        "tier": 2,
        "speed": "medium",
        "cost": "free",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "tier": 3,
        "speed": "medium",
        "cost": "paid",
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "env_key": "ANTHROPIC_API_KEY",
        "tier": 3,
        "speed": "medium",
        "cost": "paid",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "tier": 2,
        "speed": "fast",
        "cost": "free",
    },
    {
        "id": "cerebras",
        "name": "Cerebras",
        "env_key": "CEREBRAS_API_KEY",
        "tier": 1,
        "speed": "fastest",
        "cost": "free",
    },
    {
        "id": "modal",
        "name": "Modal (Self-hosted)",
        "env_key": "MODAL_TOKEN_ID",
        "tier": 3,
        "speed": "variable",
        "cost": "free-tier",
    },
]

# ── Assignment storage (in-memory + Infisical fallback) ───────────────
# In production, this would be stored in Supabase. For now, in-memory + env.
_assignment_store: dict[str, str] = {
    "web_chat": "groq",
    "ide": "gemini",
    "telegram": "groq",
    "api": "gemini",
    "research": "openrouter",
    "automation": "gemini",
}


class AssignPayload(BaseModel):
    surface: str
    provider: str


@router.get("/surfaces")
async def list_surfaces(admin_user: dict = Depends(get_current_admin)) -> list[dict[str, Any]]:
    """List all AI surfaces with their currently assigned provider."""
    result = []
    for s in SURFACES:
        assigned = _assignment_store.get(s["id"], "auto")
        provider_info = next((p for p in PROVIDERS if p["id"] == assigned), None)
        result.append(
            {
                **s,
                "assigned_provider": assigned,
                "assigned_provider_name": provider_info["name"]
                if provider_info
                else "Auto (failover)",
                "assigned_provider_tier": provider_info["tier"] if provider_info else 0,
            }
        )
    return result


@router.get("/providers")
async def list_providers(admin_user: dict = Depends(get_current_admin)) -> list[dict[str, Any]]:
    """List all AI providers with API key status."""
    result = []
    for p in PROVIDERS:
        key = os.environ.get(p["env_key"], "")
        # Check LLM_PROVIDER_KEYS JSON for multi-key
        lpk = os.environ.get("LLM_PROVIDER_KEYS", "")
        has_key = bool(key) or (lpk and p["id"] in lpk)

        result.append(
            {
                **p,
                "has_api_key": has_key,
                "key_preview": f"{key[:6]}...{key[-4:]}"
                if len(key) > 10
                else ("✅ set" if key else "❌ missing"),
                "key_env_var": p["env_key"],
            }
        )
    return result


@router.get("/assignment")
async def get_assignment(admin_user: dict = Depends(get_current_admin)) -> dict[str, str]:
    """Get current surface → provider assignment map."""
    return _assignment_store


@router.post("/assign")
async def assign_ai(
    payload: AssignPayload, admin_user: dict = Depends(get_current_admin)
) -> dict[str, Any]:
    """Assign a specific AI provider to a surface."""
    surface_ids = [s["id"] for s in SURFACES]
    provider_ids = [p["id"] for p in PROVIDERS] + ["auto"]

    if payload.surface not in surface_ids:
        raise HTTPException(status_code=422, detail=f"Invalid surface: {payload.surface}")
    if payload.provider not in provider_ids:
        raise HTTPException(status_code=422, detail=f"Invalid provider: {payload.provider}")

    _assignment_store[payload.surface] = payload.provider
    logger.info(f"AI assignment: {payload.surface} → {payload.provider} (by admin)")

    return {
        "success": True,
        "surface": payload.surface,
        "provider": payload.provider,
        "message": f"✅ {payload.surface} এখন {payload.provider} ব্যবহার করবে",
    }


@router.post("/test/{provider_id}")
async def test_provider(
    provider_id: str, admin_user: dict = Depends(get_current_admin)
) -> dict[str, Any]:
    """Test a provider's API key by making a simple request."""
    provider = next((p for p in PROVIDERS if p["id"] == provider_id), None)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")

    key = os.environ.get(provider["env_key"], "")
    if not key:
        return {"provider": provider_id, "status": "❌ no API key", "working": False}

    # Quick test based on provider
    test_urls = {
        "groq": "https://api.groq.com/openai/v1/models",
        "gemini": f"https://generativelanguage.googleapis.com/v1beta/models?key={key}",
        "openai": "https://api.openai.com/v1/models",
        "mistral": "https://api.mistral.ai/v1/models",
        "openrouter": "https://openrouter.ai/api/v1/models",
        "deepseek": "https://api.deepseek.com/v1/models",
        "cerebras": "https://api.cerebras.ai/v1/models",
        "byna": "https://router.bynara.id/v1/models",
        "bai": "https://api.b.ai/v1/models",
    }

    url = test_urls.get(provider_id)
    if not url:
        return {"provider": provider_id, "status": "⚠️ no test endpoint", "working": None}

    try:
        import httpx

        headers = {"Authorization": f"Bearer {key}"} if provider_id != "gemini" else {}
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 200:
            return {"provider": provider_id, "status": "✅ working", "working": True, "code": 200}
        else:
            return {
                "provider": provider_id,
                "status": f"❌ HTTP {resp.status_code}",
                "working": False,
                "code": resp.status_code,
            }
    except Exception as e:
        return {"provider": provider_id, "status": f"❌ error: {str(e)[:60]}", "working": False}


@router.get("/overview")
async def get_overview(admin_user: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """Complete overview: surfaces + providers + assignment in one call."""
    surfaces_data = await list_surfaces(admin_user)
    providers_data = await list_providers(admin_user)

    working_providers = [p for p in providers_data if p["has_api_key"]]
    missing_providers = [p for p in providers_data if not p["has_api_key"]]

    return {
        "surfaces": surfaces_data,
        "providers": providers_data,
        "assignment": _assignment_store,
        "summary": {
            "total_surfaces": len(SURFACES),
            "total_providers": len(PROVIDERS),
            "working_providers": len(working_providers),
            "missing_providers": len(missing_providers),
            "working_provider_names": [p["name"] for p in working_providers],
            "missing_provider_names": [p["name"] for p in missing_providers],
        },
    }
