# backend/core/llm/llm_gateway/registry.py
"""Provider registry for the LLM Gateway package.

Task 4-a package split: code moved VERBATIM from core/llm/llm_gateway.py —
provider → settings-attribute mapping, the multi-key rotation pool and the
longest-prefix key resolver. `_provider_key_pool` is THE single shared
instance (kept in exactly this one module and re-exported by the package).
"""

import asyncio
import os
import time

# বাংলা মন্তব্ব: Provider → settings attribute mapping।
# এই dict update করলেই নতুন provider add হয় — no code duplication।
_MODEL_KEY_MAP: dict[str, str] = {
    "groq": "groq_api_key",
    "gemini": "gemini_api_key",
    "gpt": "openai_api_key",
    "openai": "openai_api_key",
    "deepseek": "deepseek_api_key",
    "openrouter": "openrouter_api_key",
    "hf": "hf_api_key",
    "huggingface": "hf_api_key",
    "nvidia": "nvidia_api_key",
    "moonshot": "MOONSHOT_API_KEY",
    "together": "TOGETHER_API_KEY",
    "ollama": "OLLAMA_API_KEY",
    "hf_space": "HF_API_KEY",
    # Zero-cost OpenAI-compatible routers (final-test audit 2026-09-13):
    # BYNARA_API_KEY / BAI_API_KEY were configured in the deployment env but
    # never consumed by any code path — the keys were orphaned while the
    # routing chain wasted 40-60s per call on dead providers.
    "bynara": "bynara_api_key",
    "bai": "bai_api_key",
    "v0": "v0_api_key",
    "mistral": "mistral_api_key",
}

# Provider → OpenAI-compatible base URL. When a model's provider appears here,
# the gateway routes it through litellm's `openai/<model>` adapter using the
# provider key (per-call) instead of a provider-native SDK.
_PROVIDER_API_BASES: dict[str, str] = {
    "bynara": "https://router.bynara.id/v1",
    "bai": "https://api.b.ai/v1",
    "v0": "https://api.v0.dev/v1",
}

# Models that are no longer served by their provider (verified 2026-09-13).
_RETIRED_MODELS = {
    "gemini/gemini-2.0-flash",
    "gemini/gemini-1.5-pro",
    "gemini/gemini-1.5-flash",
}


class _ProviderKeyPool:
    """SECURITY/RELIABILITY FIX (P0, review 2026-09-12): multi-key rotation.

    Deployment .env keeps GEMINI_API_KEY/GROQ_API_KEY/OPENROUTER_API_KEY as
    comma-joined multi-key strings ("k1,k2,k3"). The old code sent the entire
    raw string as one API key, so every provider call failed with 401/403 and
    the whole zero-cost fallback chain was dead. This pool:
      1. splits on commas into individual keys,
      2. rotates round-robin (spreads quota evenly),
      3. puts a key on cooldown after 401/403/429 so the next call picks a
         healthy key instead of hammering the broken one.
    """

    # Cooldown for transient errors (429) — short by design.
    _COOLDOWN_RATE_LIMIT = 60.0
    # Issue #438: escalating cooldown for DEFINITIVE auth errors (401/403).
    # The old flat 300s cooldown meant a permanently-invalid key (observed:
    # OpenRouter key 401 Unauthorized on every probe) was retried every 5
    # minutes forever, producing an endless 401 log stream. Now each
    # consecutive auth failure per (provider, key) escalates:
    #   5min → 1h → 24h (cap). A successful call resets the escalation.
    _AUTH_COOLDOWN_ESCALATION = (300.0, 3600.0, 86400.0)

    def __init__(self) -> None:
        self._idx: dict[str, int] = {}
        self._cooldown_until: dict[tuple[str, str], float] = {}
        self._auth_fail_counts: dict[tuple[str, str], int] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _keys_for(raw: str | None, provider: str = "") -> list[str]:
        keys: list[str] = []
        if raw:
            keys.extend([k.strip() for k in str(raw).split(",") if k.strip()])

        # Issue #755 (MA-12): also discover numbered env vars ${PREFIX}_1, ${PREFIX}_2, ...
        # (e.g. GEMINI_API_KEY_1, GEMINI_API_KEY_2, OPENAI_API_KEY_1, V0_API_KEY_1, etc.)
        if provider:
            prefixes = [f"{provider.upper()}_API_KEY", f"{provider.upper()}_KEY", provider.upper()]
            for pfx in prefixes:
                for idx in range(1, 15):
                    val = os.getenv(f"{pfx}_{idx}")
                    if val and val.strip() and val.strip() not in keys:
                        keys.append(val.strip())

        return keys

    async def next_key(self, provider: str, raw: str | None) -> str | None:
        keys = self._keys_for(raw, provider=provider)
        if not keys:
            return None
        if len(keys) == 1:
            key = keys[0]
        else:
            async with self._lock:
                idx = self._idx.get(provider, 0) % len(keys)
                self._idx[provider] = idx + 1
                key = keys[idx]
        # best-effort: skip a cooling key if a healthy sibling exists
        if await self.is_cooling(provider, key):
            for alt in keys:
                if alt != key and not await self.is_cooling(provider, alt):
                    return alt
        return key

    async def is_cooling(self, provider: str, key: str) -> bool:
        until = self._cooldown_until.get((provider, key), 0.0)
        if until and time.monotonic() < until:
            return True
        if until:
            self._cooldown_until.pop((provider, key), None)
        return False

    async def mark_error(self, provider: str, key: str | None, status: int) -> None:
        if not key:
            return
        if status in (401, 403):
            # Definitive auth error — escalate the cooldown per consecutive failure
            pool_key = (provider, key)
            attempt = self._auth_fail_counts.get(pool_key, 0) + 1
            self._auth_fail_counts[pool_key] = attempt
            idx = min(attempt - 1, len(self._AUTH_COOLDOWN_ESCALATION) - 1)
            ttl = self._AUTH_COOLDOWN_ESCALATION[idx]
            self._cooldown_until[pool_key] = time.monotonic() + ttl
            return
        if status == 429:
            self._cooldown_until[(provider, key)] = time.monotonic() + self._COOLDOWN_RATE_LIMIT

    async def mark_success(self, provider: str, key: str | None) -> None:
        """Reset auth-failure escalation for a key after a successful call."""
        if not key:
            return
        self._auth_fail_counts.pop((provider, key), None)
        self._cooldown_until.pop((provider, key), None)


_provider_key_pool = _ProviderKeyPool()


def _resolve_key_attr(model: str) -> str | None:
    """FIX (P1, review 2026-09-12): longest-prefix provider matching.

    The old substring loop matched "openrouter/deepseek/..." against the
    "deepseek" prefix (and "openrouter/openai/gpt-*" against "gpt"), sending
    the WRONG provider's key. Longest matching prefix wins now, so
    "openrouter/..." always resolves to the openrouter key.
    """
    if not model:
        return None
    model_lower = model.lower()
    best_prefix = ""
    best_attr: str | None = None
    for prefix, attr_name in _MODEL_KEY_MAP.items():
        if prefix in model_lower and len(prefix) > len(best_prefix):
            best_prefix = prefix
            best_attr = attr_name
    return best_attr


def _resolve_litellm_target(model: str) -> tuple[str, str | None]:
    """Translate a routing-policy model id into a litellm-callable target.

    Returns (litellm_model, api_base).
    - Providers with an OpenAI-compatible router (BYNARA, BAI) are served via
      litellm's `openai/<model>` adapter pointing at their base URL, using the
      per-call key resolved through _resolve_key_attr.
    - Everything else passes through unchanged (litellm provider-native).
    Raises ValueError for models verified retired at their provider so the
    chain skips them instantly instead of burning a network round-trip.
    """
    if not model:
        return model, None
    if model.lower() in _RETIRED_MODELS:
        raise ValueError(f"Model {model} is retired at its provider (verified 2026-09-13)")
    # Normalize bare model names from env settings (e.g. GEMINI_MODEL="gemini-2.5-flash")
    # into litellm's provider-prefixed format.
    if "/" not in model:
        lowered = model.lower()
        if lowered.startswith("models/gemini-"):
            model = f"gemini/{model.removeprefix('models/')}"
        elif lowered.startswith("gemini-"):
            model = f"gemini/{model}"
        elif lowered.startswith(("gpt-", "o1", "o3")):
            model = f"openai/{model}"
    provider = model.split("/", 1)[0].lower() if "/" in model else ""
    base = _PROVIDER_API_BASES.get(provider)
    if base:
        bare_model = model.split("/", 1)[1] if "/" in model else model
        return f"openai/{bare_model}", base
    return model, None
