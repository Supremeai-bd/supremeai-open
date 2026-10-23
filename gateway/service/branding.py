"""SupremeAI reply branding — single source of truth for the chat badge.

Label format: ``SupremeAI <channel>.<engine> <Tier>``
  channel: ``w`` = webhook/cookie relay, ``a`` = API-key squad
  engine : short hint of the model that actually answered (ge, gr, gp ...)
Example: ``SupremeAI w.ge Turbo`` / ``SupremeAI a.gr Free``
"""
from __future__ import annotations

from typing import Optional

ENGINE_HINTS = {
    "gemini": "ge", "google": "ge", "ghost_gemini": "ge",
    "grok": "gr", "xai": "gr",
    "openai": "gp", "chatgpt": "gp", "gpt": "gp",
    "claude": "cl", "anthropic": "cl",
    "perplexity": "px",
    "deepseek": "ds",
    "groq": "lm", "llama": "lm",
    "mistral": "mi",
}
ULTRA_MARKERS = ("pro", "opus", "ultra", "reasoning", "o1", "o3")
CHANNELS = {"w", "a"}


def engine_hint(*candidates: Optional[str]) -> str:
    """Return the first matching engine hint from provider/model strings, else ``xx``."""
    for cand in candidates:
        low = (cand or "").lower()
        for key, hint in ENGINE_HINTS.items():
            if key in low:
                return hint
    return "xx"


def tier_for(channel: str, model: Optional[str] = None, paid: bool = False) -> str:
    low = (model or "").lower()
    if channel == "a" and any(m in low for m in ULTRA_MARKERS):
        return "Ultra"
    if channel == "w":
        return "Turbo"
    return "Pro" if paid else "Free"


def build_brand(channel: str, provider: Optional[str] = None,
                model: Optional[str] = None, paid: bool = False) -> dict:
    ch = channel if channel in CHANNELS else "w"
    eng = engine_hint(provider, model)
    tier = tier_for(ch, model, paid)
    return {
        "channel": ch,
        "engine": eng,
        "tier": tier,
        "label": f"SupremeAI {ch}.{eng} {tier}",
    }
