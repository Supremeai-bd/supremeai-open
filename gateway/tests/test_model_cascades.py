"""
test_model_cascades.py — Tests for Zero-Waste Model Priority Cascade and Fallback.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from gateway.service.providers.adapters import (
    forward_chat_completion,
    PROVIDER_MODEL_CASCADES,
    PROVIDER_CONFIGS,
)
from gateway.service.pool import FederationSquad, ProviderKeyPool, KeySlot


def test_provider_cascades_defined():
    """Verify all major providers have non-empty prioritized model cascades."""
    assert "groq" in PROVIDER_MODEL_CASCADES
    assert "gemini" in PROVIDER_MODEL_CASCADES
    assert "openrouter" in PROVIDER_MODEL_CASCADES
    assert "perplexity" in PROVIDER_MODEL_CASCADES
    assert "sonar" in PROVIDER_MODEL_CASCADES["perplexity"]

    # Verify Groq contains live verified models
    assert "qwen/qwen3.8-27b" in PROVIDER_MODEL_CASCADES["groq"]
    assert "openai/gpt-oss-120b" in PROVIDER_MODEL_CASCADES["groq"]

    # Verify Gemini contains live verified models
    assert "gemini-2.5-flash" in PROVIDER_MODEL_CASCADES["gemini"]
    assert "gemini-flash-latest" in PROVIDER_MODEL_CASCADES["gemini"]

    # Verify Cerebras is strictly excluded (per user mandate)
    assert "cerebras" not in PROVIDER_MODEL_CASCADES


@pytest.mark.asyncio
async def test_in_flight_model_cascade_on_404():
    """If top model returns 404, adapter must automatically try the next model in cascade."""
    call_history = []

    async def mock_post(url, json=None, headers=None):
        model = json.get("model")
        call_history.append(model)
        mock_resp = MagicMock()
        if model == "qwen/qwen3.8-27b":
            mock_resp.status_code = 404
            mock_resp.json.return_value = {"error": "model_not_found"}
            mock_resp.text = '{"error": "model_not_found"}'
        else:
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": f"Success with {model}"}}]
            }
            mock_resp.text = "ok"
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        status, data = await forward_chat_completion(
            provider="groq",
            api_key="gsk-test",
            payload={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert status == 200
        assert isinstance(data, dict)
        assert data.get("model") == "openai/gpt-oss-120b"
        assert call_history == ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]


@pytest.mark.asyncio
async def test_skip_paid_tier_on_402():
    """If a model returns 402 Payment Required, adapter skips paid tier and cascades."""
    call_history = []

    async def mock_post(url, json=None, headers=None):
        model = json.get("model")
        call_history.append(model)
        mock_resp = MagicMock()
        if model == "gemini-2.5-flash":
            mock_resp.status_code = 402
            mock_resp.json.return_value = {"error": "Payment required"}
            mock_resp.text = '{"error": "Payment required"}'
        else:
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}}]
            }
            mock_resp.text = "ok"
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        status, data = await forward_chat_completion(
            provider="gemini",
            api_key="AIza-test",
            payload={"messages": [{"role": "user", "content": "hi"}]},
        )
        assert status == 200
        assert data.get("model") == "gemini-flash-latest"


def test_jules_key_included_in_gemini_pool(monkeypatch):
    """Verify JULES_API_KEY is discovered and included as an additional Gemini key."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTest1")
    monkeypatch.setenv("JULES_API_KEY", "AQ.SyTestJules")

    squad = FederationSquad()
    gemini_pool = squad.pools.get("gemini")
    assert gemini_pool is not None
    slot_names = [s.name for s in gemini_pool.slots]
    assert "GEMINI_API_KEY" in slot_names
    assert "JULES_API_KEY" in slot_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
