"""tests/test_provider_registry_lanes.py — acceptance tests for the 4 live-verified
OpenAI-compatible provider lanes wired into the dynamic AI registry (#1685).

Criteria enforced here (data-only, no network):
- zai / dashscope / mistral / cerebras templates registered with the probed endpoints.
- mistral lane closes the model_horizon.json <-> registry drift (horizon already
  tracked mistral/mistral-large-latest; the registry can now route it).
- No priority inflation above the free-tier primaries (gemini, grok stay first).
- Fail-closed availability: a lane surfaces in get_available_providers() only when
  its env key is set; no key material anywhere in the registry (env names are data).

The refresh_status() live health probe (criterion 2 of #1685) is a runtime-lane
check: it needs provider keys and network access, so it is intentionally not
unit-tested here.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gateway.services.dynamic_ai.provider_registry import (  # noqa: E402
    ProviderRegistry,
    ProviderStatus,
)

NEW_LANES = ("zai", "dashscope", "mistral", "cerebras")
EXPECTED_BASE_URLS = {
    "zai": "https://api.z.ai/api/paas/v4",
    "dashscope": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "mistral": "https://api.mistral.ai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
}
EXPECTED_ENV_VARS = {
    "zai": "ZAI_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
}


def _fresh_registry() -> ProviderRegistry:
    reg = ProviderRegistry()
    asyncio.run(reg.initialize())
    return reg


def test_four_lanes_registered():
    reg = _fresh_registry()
    for lane in NEW_LANES:
        cfg = reg.get_provider(lane)
        assert cfg is not None, f"lane {lane} missing from registry"
        assert cfg.base_url == EXPECTED_BASE_URLS[lane]
        assert cfg.api_key_env_var == EXPECTED_ENV_VARS[lane]
        assert cfg.models, f"lane {lane} must ship at least one model"


def test_mistral_drift_closed_against_model_horizon():
    """model_horizon.json already tracks mistral/mistral-large-latest — the
    registry must now be able to route that exact model id."""
    horizon = (REPO_ROOT / "gateway" / "model_horizon.json").read_text(encoding="utf-8")
    assert "mistral/mistral-large-latest" in horizon
    reg = _fresh_registry()
    mistral_models = {m["id"] for m in reg.get_provider("mistral").models}
    assert "mistral-large-latest" in mistral_models


def test_no_priority_inflation_above_free_tier_primaries():
    reg = _fresh_registry()
    gemini_p = reg.get_provider("gemini").priority
    groq_p = reg.get_provider("groq").priority
    for lane in NEW_LANES:
        p = reg.get_provider(lane).priority
        assert p > gemini_p and p > groq_p, f"{lane} must not outrank free-tier primaries"


def test_cerebras_is_the_only_new_free_tier_lane():
    reg = _fresh_registry()
    assert reg.get_provider("cerebras").is_free_tier is True
    for lane in ("zai", "dashscope", "mistral"):
        assert reg.get_provider(lane).is_free_tier is False


def test_fail_closed_availability_without_env_keys(monkeypatch):
    import os

    for var in EXPECTED_ENV_VARS.values():
        monkeypatch.delenv(var, raising=False)
    reg = _fresh_registry()
    for lane in NEW_LANES:
        cfg = reg.get_provider(lane)
        cfg.status = ProviderStatus.ACTIVE  # pretend healthy: key is still the gate
        assert cfg.api_key is None
        assert cfg.is_available is False
    available_ids = {p.provider_id for p in reg.get_available_providers()}
    assert not (available_ids & set(NEW_LANES))


def test_no_key_material_in_registry_source():
    src = (REPO_ROOT / "core" / "services" / "dynamic_ai" / "provider_registry.py").read_text(
        encoding="utf-8"
    )
    for marker in ("sk-", "ghp_", "github_pat_", "AKIA"):
        assert marker not in src, f"key material marker {marker!r} must never appear"


def test_existing_providers_untouched():
    reg = _fresh_registry()
    for existing in (
        "gemini",
        "groq",
        "bynara",
        "bai",
        "huggingface",
        "openai",
        "deepseek",
        "moonshot",
        "together",
        "nvidia",
        "openrouter",
    ):
        assert reg.get_provider(existing) is not None, f"existing lane {existing} regressed"
