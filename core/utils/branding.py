"""SupremeAI model/provider branding.

Single backend source of truth for mapping raw provider model/provider IDs
to SupremeAI branded display names. The frontend keeps a parallel map in
`frontend/src/lib/modelBranding.ts`; this endpoint lets the UI stay in sync
via GET /api/admin/model-branding.
"""

from __future__ import annotations

import logging
from typing import Any

from services.config_service import ConfigService

logger = logging.getLogger(__name__)

# provider id (raw) -> SupremeAI branded display name
PROVIDER_DISPLAY: dict[str, str] = {
    "openai": "SupremeAI Core",
    "google": "SupremeAI Vision",
    "gemini": "SupremeAI Vision",
    "anthropic": "SupremeAI Reason",
    "claude": "SupremeAI Reason",
    "deepseek": "SupremeAI Deep",
    "groq": "SupremeAI Llama",
    "together": "SupremeAI Collective",
    "togetherai": "SupremeAI Collective",
    "ollama": "SupremeAI Local",
    "mistral": "SupremeAI Mistral",
    "meta": "SupremeAI Llama",
    "llama": "SupremeAI Llama",
}

# raw model id -> (SupremeAI display name, family)
MODEL_DISPLAY: dict[str, dict[str, str]] = {
    # OpenAI
    "gpt-4": {"label": "SupremeAI Core", "family": "core"},
    "gpt-4o": {"label": "SupremeAI Core", "family": "core"},
    "gpt-4o-mini": {"label": "SupremeAI Core Mini", "family": "core"},
    "gpt-4-turbo": {"label": "SupremeAI Core Turbo", "family": "core"},
    "gpt-3.5-turbo": {"label": "SupremeAI Spark", "family": "spark"},
    # Anthropic
    "claude-3.5": {"label": "SupremeAI Reason", "family": "reason"},
    "claude-3-5-sonnet": {"label": "SupremeAI Reason", "family": "reason"},
    "claude-3-5-haiku": {"label": "SupremeAI Spark", "family": "spark"},
    "claude-3-opus": {"label": "SupremeAI Reason Pro", "family": "reason"},
    "claude-3": {"label": "SupremeAI Reason", "family": "reason"},
    # Google
    "gemini-1.5-pro": {"label": "SupremeAI Vision", "family": "vision"},
    "gemini-2.0-flash": {"label": "SupremeAI Vision Flash", "family": "vision"},
    "gemini-pro": {"label": "SupremeAI Vision", "family": "vision"},
    "gemini": {"label": "SupremeAI Vision", "family": "vision"},
    # DeepSeek
    "deepseek-chat": {"label": "SupremeAI Deep", "family": "deep"},
    "deepseek-coder": {"label": "SupremeAI Deep Coder", "family": "deep"},
    # Meta / Groq
    "llama3-70b-groq": {"label": "SupremeAI Llama", "family": "llama"},
    "llama": {"label": "SupremeAI Llama", "family": "llama"},
    # Mistral
    "mistral": {"label": "SupremeAI Mistral", "family": "mistral"},
}


async def sync_from_db(db: Any) -> None:
    """Sync PROVIDER_DISPLAY and MODEL_DISPLAY from the database configuration."""
    global PROVIDER_DISPLAY, MODEL_DISPLAY
    try:
        default_config = {
            "provider_display": dict(PROVIDER_DISPLAY),
            "model_display": dict(MODEL_DISPLAY),
        }
        configs = await ConfigService.get_config(db, "model_branding_map", default_config)
        if configs:
            if "provider_display" in configs and configs["provider_display"]:
                PROVIDER_DISPLAY.clear()
                PROVIDER_DISPLAY.update(configs["provider_display"])
            if "model_display" in configs and configs["model_display"]:
                MODEL_DISPLAY.clear()
                MODEL_DISPLAY.update(configs["model_display"])
            logger.info("✅ Synced model_branding_map from DB.")
    except Exception as e:
        logger.error(f"❌ Failed to sync model_branding_map from DB: {e}")


def _normalize(raw: str | None) -> str:
    return (raw or "").strip().lower()


def get_model_display_name(raw: str | None) -> str:
    """Return SupremeAI branded model name for a raw provider model id."""
    if not raw:
        return "SupremeAI Core"
    key = _normalize(raw)
    if key in MODEL_DISPLAY:
        return MODEL_DISPLAY[key]["label"]
    # partial match (e.g. gpt-4o-2024-...)
    for k in MODEL_DISPLAY:
        if key.startswith(k) or k.startswith(key):
            return MODEL_DISPLAY[k]["label"]
    return "SupremeAI Core"


def get_provider_display_name(raw: str | None) -> str:
    """Return SupremeAI branded provider name for a raw provider id."""
    if not raw:
        return "SupremeAI"
    key = _normalize(raw)
    if key in PROVIDER_DISPLAY:
        return PROVIDER_DISPLAY[key]
    for k in PROVIDER_DISPLAY:
        if k in key:
            return PROVIDER_DISPLAY[k]
    return "SupremeAI"
