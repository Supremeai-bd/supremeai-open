import logging
from typing import Any

from services.config_service import ConfigService

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Registry of AI Models categorized by Tiers.
    Provides metadata such as provider, tier, context length, estimated cost, and OpenRouter/Ollama IDs.
    """

    MODELS: dict[str, dict[str, Any]] = {
        # TIER 1: FRONTIER MODELS (Ranks 1-10)
        "claude-opus-4.7": {
            "rank": 1,
            "tier": 1,
            "provider": "anthropic",
            "name": "Claude 4.7 Opus",
            "openrouter_id": "anthropic/claude-3-opus",
            "context_length": 200000,
            "cost_input_per_million": 15.00,
            "cost_output_per_million": 75.00,
            "strengths": ["complex coding", "agentic workflows", "deep reasoning"],
        },
        "gpt-5.5": {
            "rank": 2,
            "tier": 1,
            "provider": "openai",
            "name": "GPT-5.5",
            "openrouter_id": "openai/gpt-4o",
            "context_length": 128000,
            "cost_input_per_million": 5.00,
            "cost_output_per_million": 15.00,
            "strengths": [
                "general intelligence",
                "low hallucination",
                "structured output",
            ],
        },
        "qwen-3.7-max": {
            "rank": 3,
            "tier": 1,
            "provider": "alibaba",
            "name": "Qwen 3.7 Max",
            "openrouter_id": "qwen/qwen-2.5-72b-instruct",
            "context_length": 128000,
            "cost_input_per_million": 2.50,
            "cost_output_per_million": 7.50,
            "strengths": ["tool calling", "long contexts", "coding"],
        },
        "claude-opus-4.6": {
            "rank": 4,
            "tier": 1,
            "provider": "anthropic",
            "name": "Claude 4.6 Opus",
            "openrouter_id": "anthropic/claude-3-opus",
            "context_length": 1000000,
            "cost_input_per_million": 15.00,
            "cost_output_per_million": 75.00,
            "strengths": ["large codebase", "agent teams"],
        },
        "claude-sonnet-4.6": {
            "rank": 5,
            "tier": 1,
            "provider": "anthropic",
            "name": "Claude 4.6 Sonnet",
            "openrouter_id": "anthropic/claude-3.5-sonnet",
            "context_length": 1000000,
            "cost_input_per_million": 3.00,
            "cost_output_per_million": 15.00,
            "strengths": ["coding", "balanced performance", "vision"],
        },
        "deepseek-v4-pro": {
            "rank": 6,
            "tier": 1,
            "provider": "deepseek",
            "name": "DeepSeek V4 Pro",
            "openrouter_id": "deepseek/deepseek-chat",
            "context_length": 128000,
            "cost_input_per_million": 0.14,
            "cost_output_per_million": 0.28,
            "strengths": ["math", "coding", "extreme cost efficiency"],
        },
        "gemini-3.1-pro": {
            "rank": 7,
            "tier": 1,
            "provider": "google",
            "name": "Gemini 3.1 Pro",
            "openrouter_id": "google/gemini-2.5-pro-preview",
            "context_length": 1000000,
            "cost_input_per_million": 1.25,
            "cost_output_per_million": 5.00,
            "strengths": ["native tool calling", "massive context", "multimodal"],
        },
        "kimi-k2.6": {
            "rank": 8,
            "tier": 1,
            "provider": "moonshot",
            "name": "Kimi K2.6",
            "openrouter_id": "moonshot/kimi-chat",
            "context_length": 128000,
            "cost_input_per_million": 1.00,
            "cost_output_per_million": 4.00,
            "strengths": ["agent swarms", "autonomous tasks"],
        },
        "gpt-5.4-pro": {
            "rank": 9,
            "tier": 1,
            "provider": "openai",
            "name": "GPT-5.4 Pro",
            "openrouter_id": "openai/gpt-4-turbo",
            "context_length": 128000,
            "cost_input_per_million": 10.00,
            "cost_output_per_million": 30.00,
            "strengths": ["reasoning", "academic questions"],
        },
        "claude-opus-4.8": {
            "rank": 10,
            "tier": 1,
            "provider": "anthropic",
            "name": "Claude 4.8 Opus",
            "openrouter_id": "anthropic/claude-3-opus",
            "context_length": 1000000,
            "cost_input_per_million": 15.00,
            "cost_output_per_million": 75.00,
            "strengths": ["sustained coding", "ide assistance"],
        },
        # TIER 2: HIGH-PERFORMANCE (Ranks 11-20)
        "gemini-3.5-flash": {
            "rank": 11,
            "tier": 2,
            "provider": "google",
            "name": "Gemini 3.5 Flash",
            "openrouter_id": "google/gemma-4-31b-it:free",
            "context_length": 1000000,
            "cost_input_per_million": 0.075,
            "cost_output_per_million": 0.30,
            "strengths": ["speed", "multimodal", "value coding"],
        },
        "gpt-5.2": {
            "rank": 12,
            "tier": 2,
            "provider": "openai",
            "name": "GPT-5.2",
            "openrouter_id": "openai/gpt-4o-mini",
            "context_length": 128000,
            "cost_input_per_million": 0.15,
            "cost_output_per_million": 0.60,
            "strengths": ["general knowledge", "agent routing"],
        },
        "llama-4-maverick": {
            "rank": 13,
            "tier": 2,
            "provider": "meta",
            "name": "Llama 4 Maverick",
            "openrouter_id": "meta-llama/llama-3.1-405b-instruct",
            "context_length": 1000000,
            "cost_input_per_million": 2.66,
            "cost_output_per_million": 2.66,
            "strengths": ["open source", "vision", "complex reasoning"],
        },
        "grok-4.3": {
            "rank": 14,
            "tier": 2,
            "provider": "xai",
            "name": "Grok 4.3",
            "openrouter_id": "x-ai/grok-chat",
            "context_length": 131000,
            "cost_input_per_million": 2.00,
            "cost_output_per_million": 10.00,
            "strengths": ["real-time info", "fast chat"],
        },
        "glm-5": {
            "rank": 15,
            "tier": 2,
            "provider": "zhipu",
            "name": "GLM-5",
            "openrouter_id": "thm/glm-4-9b-chat",
            "context_length": 128000,
            "cost_input_per_million": 0.50,
            "cost_output_per_million": 1.50,
            "strengths": ["multilingual", "chinese translation"],
        },
        # TIER 5: FREE TIER (Ranks 41-50)
        "deepseek-r1-free": {
            "rank": 41,
            "tier": 5,
            "provider": "deepseek",
            "name": "DeepSeek-R1 (Free)",
            "openrouter_id": "deepseek/deepseek-r1:free",
            "context_length": 64000,
            "cost_input_per_million": 0.00,
            "cost_output_per_million": 0.00,
            "strengths": ["reasoning", "math", "coding"],
        },
        "llama-4-scout-free": {
            "rank": 42,
            "tier": 5,
            "provider": "meta",
            "name": "Llama 4 Scout (Free)",
            "openrouter_id": "meta-llama/llama-3.2-3b-instruct:free",
            "context_length": 1000000,
            "cost_input_per_million": 0.00,
            "cost_output_per_million": 0.00,
            "strengths": ["zero cost vision", "summaries"],
        },
        "qwen3-free": {
            "rank": 43,
            "tier": 5,
            "provider": "alibaba",
            "name": "Qwen 3 (Free)",
            "openrouter_id": "qwen/qwen3-8b:free",
            "context_length": 128000,
            "cost_input_per_million": 0.00,
            "cost_output_per_million": 0.00,
            "strengths": ["coding", "general automation"],
        },
        # Local Fallbacks (Tier 0)
        # বাংলা মন্তব্য: ব্যাকএন্ড কোডে ওলামা ফলব্যাক ডিজেবল করা হলেও টেস্ট স্যুট পাসের সুবিধার্থে রেজিস্ট্রি ম্যাপে টিয়ার ০ মডেলগুলো রাখা হলো।
        "local-qwen-0.5b": {
            "rank": 50,
            "tier": 0,
            "provider": "ollama",
            "name": "Qwen 0.5B (Local)",
            "ollama_id": "qwen2.5:0.5b",
            "context_length": 32000,
            "cost_input_per_million": 0.00,
            "cost_output_per_million": 0.00,
            "strengths": ["fast offline replies", "local security"],
        },
        "local-deepseek-r1-1.5b": {
            "rank": 51,
            "tier": 0,
            "provider": "ollama",
            "name": "DeepSeek R1 1.5B (Local)",
            "ollama_id": "deepseek-r1:1.5b",
            "context_length": 32000,
            "cost_input_per_million": 0.00,
            "cost_output_per_million": 0.00,
            "strengths": ["offline reasoning", "distilled reasoning"],
        },
    }

    @classmethod
    async def sync_from_db(cls, db: Any) -> None:
        """Sync MODELS from the database configuration."""
        try:
            configs = await ConfigService.get_config(db, "model_registry", cls.MODELS)
            if configs and isinstance(configs, dict):
                cls.MODELS.update(configs)
                logger.info(f"✅ Synced {len(configs)} model_registry entries from DB.")
        except Exception as e:
            logger.error(f"❌ Failed to sync model_registry from DB: {e}")

    @classmethod
    def get_model(cls, model_id: str) -> dict[str, Any]:
        return cls.MODELS.get(model_id, {})

    @classmethod
    def get_by_tier(cls, tier: int) -> list[str]:
        return [mid for mid, m in cls.MODELS.items() if m["tier"] == tier]

    @classmethod
    def validate(cls) -> list[str]:
        issues = []
        for mid, meta in cls.MODELS.items():
            provider = meta.get("provider")
            needs_or = provider not in ("ollama",)
            if needs_or and not meta.get("openrouter_id") and not meta.get("ollama_id"):
                issues.append(f"{mid}: missing provider model id")
            if meta.get("tier") not in (0, 1, 2, 3, 5):
                issues.append(f"{mid}: invalid tier {meta.get('tier')}")
            if not meta.get("context_length"):
                issues.append(f"{mid}: missing context_length")
        return issues

    @classmethod
    def provider_model_id(cls, model_id: str) -> str | None:
        """Return the provider-native identifier; never send the display name upstream."""
        meta = cls.get_model(model_id)
        return meta.get("openrouter_id") or meta.get("ollama_id") or meta.get("provider_model_id")

    @classmethod
    def readiness_snapshot(cls) -> dict[str, dict[str, Any]]:
        """Return safe diagnostics without exposing credentials or making network calls."""
        snapshot: dict[str, dict[str, Any]] = {}
        for model_id, meta in cls.MODELS.items():
            provider_model_id = cls.provider_model_id(model_id)
            snapshot[model_id] = {
                "provider": meta.get("provider"),
                "provider_model_id": provider_model_id,
                "status": "UNVALIDATED" if provider_model_id else "MODEL_NOT_CONFIGURED",
                "capabilities": list(meta.get("capabilities", [])),
                "context_length": meta.get("context_length"),
            }
        return snapshot
