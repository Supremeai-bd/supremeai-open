# backend/services/dynamic_ai/orchestrator.py
"""
SupremeAI Dynamic AI Orchestrator
Main entry point - ties together all components for resilient AI access
NEVER crashes due to external API issues!
"""

import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.logging_config import logger

try:
    from .circuit_breaker import CircuitBreakerManager
except ImportError:
    # Fallback to the canonical resilience circuit breaker (issue #2250)
    from core.resilience.circuit_breaker import RedisCircuitBreaker as CircuitBreakerManager


class TaskType(StrEnum):
    """Task classification used to pick the best provider/model.

    Defined at module scope (not just as an ImportError fallback) because
    it is referenced throughout this module (e.g. DynamicAIOrchestrator's
    method signatures and routing tables) regardless of whether
    `.learning_engine` imports successfully. Previously this was only
    defined inside the `except ImportError` branch, so the normal/success
    import path raised `NameError: name 'TaskType' is not defined` as soon
    as the class body referencing it was evaluated.
    """

    CHAT = "chat"
    GENERAL = "general"
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    REASONING = "reasoning"
    CREATIVE_WRITING = "creative_writing"
    SUMMARIZATION = "summarization"


try:
    from .learning_engine import LearningEngine
except ImportError:
    # Define a stub if the module is missing

    class LearningEngine:
        def __init__(self, *args, **kwargs):
            pass

        async def process(self, *args, **kwargs):
            raise NotImplementedError("Dynamic AI learning engine not available")


try:
    from .local_fallback import OllamaFallback
except ImportError:
    OllamaFallback = None  # Will be checked before use

try:
    from .provider_registry import ProviderConfig, ProviderRegistry
except ImportError:

    class ProviderConfig:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class ProviderRegistry:
        def __init__(self):
            self._providers = {}

        def register(self, name, config):
            self._providers[name] = config

        def get(self, name):
            return self._providers.get(name)


@dataclass
class GenerationResult:
    """Result from AI generation attempt"""

    success: bool
    text: str | None = None
    provider_used: str | None = None
    model_used: str | None = None
    latency_ms: float = 0.0
    cost_usd: float = 0.0
    was_fallback: bool = False
    error: str | None = None
    metadata: dict[str, Any] = None


class DynamicAIOrchestrator:
    """
    Main orchestrator for dynamic AI provider management
    Provides a single interface that NEVER fails
    """

    def __init__(
        self,
        learning_data_path: str = "/data/ai_learning_data.json",
        ollama_enabled: bool = True,
        auto_validate_keys: bool = True,
    ):
        # Core components
        self.registry = ProviderRegistry()
        self.circuit_breaker = CircuitBreakerManager()
        self.learning_engine = LearningEngine(storage_path=learning_data_path)
        self.local_fallback = OllamaFallback() if ollama_enabled else None

        # Configuration
        self.auto_validate_keys = auto_validate_keys
        self._initialized = False
        self._health_check_interval = 300.0  # 5 minutes

        # Statistics
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "fallback_used_count": 0,
            "external_success_count": 0,
            "external_failure_count": 0,
        }

    async def initialize(self):
        """Initialize all components"""
        logger.debug("Initializing SupremeAI Dynamic AI System...")

        # 1. Initialize provider registry
        await self.registry.initialize()

        # 2. Load historical learning data
        await self.learning_engine.load_learning_data()

        # 3. Initialize local fallback (Ollama)
        if self.local_fallback:
            await self.local_fallback.initialize()

        # 4. Validate all API keys (optional, can skip for faster startup)
        if self.auto_validate_keys:
            logger.debug("🔑 Validating API keys...")
            await self.registry.refresh_status()

        # 5. Start background health checks
        asyncio.create_task(self._background_health_check_loop())

        self._initialized = True
        logger.debug("SupremeAI Dynamic AI System Ready!")
        logger.debug(
            f"   External providers: {len(self.registry.get_available_providers())} available"
        )
        local_fallback_status = (
            "Ready"
            if self.local_fallback and await self.local_fallback.is_available()
            else "Unavailable"
        )
        logger.debug(f"   Local fallback: {local_fallback_status}")

    async def generate(
        self,
        prompt: str,
        task_type: str | None = None,
        system_prompt: str | None = None,
        prefer_free_tier: bool = True,
        max_retries: int = 3,
        **kwargs,
    ) -> GenerationResult:
        """
        Generate text using the best available provider
        THIS METHOD NEVER CRASHES - always returns a valid result
        """
        self.stats["total_requests"] += 1
        start_time = time.time()

        if not self._initialized:
            await self.initialize()

        # Detect task type if not provided
        detected_task = (
            TaskType(task_type) if task_type else self.learning_engine.detect_task_type(prompt)
        )

        # Get ranked list of best providers for this task
        available_providers = self.registry.get_available_providers(
            require_free_tier=prefer_free_tier
        )

        ranked_providers = await self.learning_engine.get_best_providers_for_task(
            prompt=prompt,
            available_providers=available_providers,
            context={"purpose": "generation"},
        )

        # Try each provider in order
        last_error = None

        for provider_id, confidence_score in ranked_providers[:max_retries]:
            # Check circuit breaker
            if not await self.circuit_breaker.is_available(provider_id):
                logger.debug(f"Circuit open for {provider_id}, skipping")
                continue

            # Get provider config
            provider_config = self.registry.get_provider(provider_id)
            if not provider_config:
                continue

            # Attempt generation
            try:
                result = await self._call_provider(
                    provider_config=provider_config,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    detected_task=detected_task,
                    **kwargs,
                )

                if result.success:
                    # Record success
                    latency_ms = (time.time() - start_time) * 1000

                    self.registry.record_success(provider_id, latency_ms)
                    await self.circuit_breaker.record_success(provider_id)
                    self.learning_engine.record_interaction(
                        provider_id=provider_id,
                        task_type=detected_task,
                        success=True,
                        latency_ms=latency_ms,
                        estimated_cost=result.cost_usd,
                    )

                    self.stats["successful_requests"] += 1
                    self.stats["external_success_count"] += 1

                    result.latency_ms = latency_ms
                    result.was_fallback = False

                    logger.info(f"Generated via {provider_id} ({latency_ms:.0f}ms)")
                    return result

                else:
                    # Provider returned error
                    last_error = result.error
                    self.registry.record_failure(provider_id, result.error or "Unknown error")
                    await self.circuit_breaker.record_failure(provider_id)
                    self.learning_engine.record_interaction(
                        provider_id=provider_id,
                        task_type=detected_task,
                        success=False,
                        latency_ms=(time.time() - start_time) * 1000,
                    )
                    self.stats["external_failure_count"] += 1

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Provider {provider_id} threw exception: {e}")

                self.registry.record_failure(provider_id, str(e))
                await self.circuit_breaker.record_failure(provider_id)
                self.learning_engine.record_interaction(
                    provider_id=provider_id,
                    task_type=detected_task,
                    success=False,
                    latency_ms=(time.time() - start_time) * 1000,
                )
                self.stats["external_failure_count"] += 1

        # ALL EXTERNAL PROVIDERS FAILED → Use Local Fallback
        logger.warning("All external providers failed, using local fallback")

        if self.local_fallback and await self.local_fallback.is_available():
            try:
                # Select best local model for task
                local_model = self.local_fallback.get_best_model_for_task(detected_task.value)

                local_result = await self.local_fallback.generate(
                    prompt=prompt,
                    model=local_model,
                    system_prompt=system_prompt
                    or "You are SupremeAI assistant. Respond helpfully.",
                    **kwargs,
                )

                if local_result.get("success"):
                    self.stats["fallback_used_count"] += 1
                    self.stats["successful_requests"] += 1

                    return GenerationResult(
                        success=True,
                        text=local_result["text"],
                        provider_used="ollama-local",
                        model_used=local_result.get("model"),
                        latency_ms=local_result.get("latency_ms", 0),
                        was_fallback=True,
                        metadata={"source": "local_fallback"},
                    )
                else:
                    last_error = local_result.get("error", "Local fallback also failed")

            except Exception as e:
                last_error = f"Local fallback error: {e}"

        # EVERYTHING FAILED - Return graceful error (still doesn't crash!)
        logger.error(f"All AI providers failed. Last error: {last_error}")

        return GenerationResult(
            success=False,
            error=f"All providers failed. Last error: {last_error}",
            was_fallback=False,
            metadata={
                "attempted_providers": [p[0] for p in ranked_providers[:max_retries]],
                "local_fallback_available": self.local_fallback
                and await self.local_fallback.is_available(),
            },
        )

    async def _call_provider(
        self,
        provider_config: ProviderConfig,
        prompt: str,
        system_prompt: str | None,
        detected_task: TaskType,
        **kwargs,
    ) -> GenerationResult:
        """
        Call a specific provider
        Implement provider-specific calling logic here
        """

        # Select best model for this provider based on task
        model = self._select_best_model_for_task(provider_config, detected_task)

        # Provider-specific implementation
        if provider_config.provider_id == "gemini":
            return await self._call_gemini(provider_config, model, prompt, system_prompt, **kwargs)

        elif provider_config.provider_id in [
            "openai",
            "deepseek",
            "moonshot",
            "together",
            "nvidia",
            "groq",
        ]:
            return await self._call_openai_compatible(
                provider_config, model, prompt, system_prompt, **kwargs
            )

        elif provider_config.provider_id == "huggingface":
            return await self._call_huggingface(provider_config, model, prompt, **kwargs)

        elif provider_config.provider_id == "openrouter":
            return await self._call_openrouter(
                provider_config, model, prompt, system_prompt, **kwargs
            )

        else:
            # Default to OpenAI-compatible
            return await self._call_openai_compatible(
                provider_config, model, prompt, system_prompt, **kwargs
            )

    def _select_best_model_for_task(self, provider: ProviderConfig, task: TaskType) -> str:
        """Select best model from provider for given task type"""
        if not provider.models:
            return "default"

        # Find model that matches task requirements
        task_specialty_map = {
            TaskType.CODE_GENERATION: ["coding", "code"],
            TaskType.CODE_REVIEW: ["coding", "code", "review"],
            TaskType.REASONING: ["reasoning", "reason"],
            TaskType.CREATIVE_WRITING: ["creative", "write"],
            TaskType.CHAT: [],
            TaskType.GENERAL: [],
        }

        specialties = task_specialty_map.get(task, [])

        # First try to find specialized model
        for model in provider.models:
            if any(spec in model.get("specialty", "").lower() for spec in specialties):
                return model["id"]

        # Then try economy tier for simple tasks
        if task in [TaskType.CHAT, TaskType.GENERAL, TaskType.SUMMARIZATION]:
            for model in provider.models:
                if model.get("tier") == "economy":
                    return model["id"]

        # Default to first model
        return provider.models[0]["id"]

    async def _call_gemini(
        self, provider: ProviderConfig, model: str, prompt: str, system_prompt: str | None, **kwargs
    ) -> GenerationResult:
        """Call Google Gemini API"""
        import httpx

        url = f"{provider.base_url}/{model}:generateContent"

        contents = []
        if system_prompt:
            contents.append(
                {"role": "user", "parts": [{"text": f"System: {system_prompt}\n\nUser: {prompt}"}]}
            )
        else:
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": kwargs.get("temperature", 0.7),
                "topP": kwargs.get("top_p", 0.95),
                "maxOutputTokens": kwargs.get("max_tokens", 2048),
            },
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                params={"key": provider.api_key},
                json=payload,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code == 200:
                data = response.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return GenerationResult(success=True, text=text, model_used=model)
            else:
                error_msg = f"Gemini API error {response.status_code}: {response.text[:200]}"
                return GenerationResult(success=False, error=error_msg)

    async def _call_openai_compatible(
        self, provider: ProviderConfig, model: str, prompt: str, system_prompt: str | None, **kwargs
    ) -> GenerationResult:
        """Call OpenAI-compatible API (works for OpenAI, DeepSeek, Moonshot, Together, Groq, NVIDIA)"""
        import httpx

        url = f"{provider.base_url}/chat/completions"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "max_tokens": kwargs.get("max_tokens", 2048),
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 200:
                data = response.json()
                text = data["choices"][0]["message"]["content"]

                # Estimate cost (rough)
                usage = data.get("usage", {})
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                estimated_cost = (
                    prompt_tokens * 0.000001 + completion_tokens * 0.000002
                )  # Rough estimate

                return GenerationResult(
                    success=True, text=text, model_used=model, cost_usd=estimated_cost
                )
            else:
                error_msg = f"{provider.provider_id} API error {response.status_code}: {response.text[:200]}"
                return GenerationResult(success=False, error=error_msg)

    async def _call_huggingface(
        self, provider: ProviderConfig, model: str, prompt: str, **kwargs
    ) -> GenerationResult:
        """Call HuggingFace Serverless Inference API"""
        import httpx

        url = f"{provider.base_url}/{model}"

        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": kwargs.get("temperature", 0.7),
                "max_new_tokens": kwargs.get("max_tokens", 1024),
                "return_full_text": False,
            },
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {provider.api_key}",
                    "Content-Type": "application/json",
                },
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    text = data[0].get("generated_text", "")
                elif isinstance(data, dict):
                    text = data.get("generated_text", data.get("text", ""))
                else:
                    text = str(data)

                return GenerationResult(success=True, text=text, model_used=model)

            elif response.status_code == 503:
                # FIX (P1, review 2026-09-12): the "retry once" was actually UNBOUNDED
                # recursion — every 503 from a cold HF Space spawned another recursion
                # level with a new httpx client (request hung forever; max_retries was
                # never applied). Bound it to a single retry, then fail honestly.
                if kwargs.get("_hf_retry_done"):
                    return GenerationResult(
                        success=False,
                        error=f"HF model {model} still loading after retry (503)",
                    )
                await asyncio.sleep(10)
                kwargs = dict(kwargs)
                kwargs["_hf_retry_done"] = True
                return await self._call_huggingface(provider, model, prompt, **kwargs)
            else:
                error_msg = f"HF API error {response.status_code}: {response.text[:200]}"
                return GenerationResult(success=False, error=error_msg)

    async def _call_openrouter(
        self, provider: ProviderConfig, model: str, prompt: str, system_prompt: str | None, **kwargs
    ) -> GenerationResult:
        """Call OpenRouter API (similar to OpenAI-compatible but with special handling)"""
        # OpenRouter is mostly OpenAI-compatible
        return await self._call_openai_compatible(provider, model, prompt, system_prompt, **kwargs)

    async def _background_health_check_loop(self):
        """Background loop for continuous health monitoring"""
        while True:
            try:
                await asyncio.sleep(self._health_check_interval)
                await self.registry.refresh_status()

                # Log summary
                summary = self.registry.get_status_summary()
                active = summary.get("active", 0)
                total = summary.get("total_providers", 0)

                logger.info(f"🏥 Health check: {active}/{total} providers active")

            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def get_system_status(self) -> dict:
        """Get complete system status"""
        return {
            "initialized": self._initialized,
            "registry": self.registry.get_status_summary(),
            "circuit_breakers": self.circuit_breaker.get_all_circuit_states(),
            "local_fallback": self.local_fallback.get_status() if self.local_fallback else None,
            "statistics": self.stats.copy(),
        }


# ============================================================================
# SINGLETON INSTANCE (use throughout application)
# ============================================================================

_orchestrator: DynamicAIOrchestrator | None = None


async def get_ai_orchestrator() -> DynamicAIOrchestrator:
    """Get or create the singleton orchestrator instance"""
    global _orchestrator

    if _orchestrator is None:
        _orchestrator = DynamicAIOrchestrator()
        await _orchestrator.initialize()

    return _orchestrator


async def generate_text(prompt: str, **kwargs) -> GenerationResult:
    """
    Convenience function for generating text
    Usage: result = await generate_text("Hello, world!")
    """
    orchestrator = await get_ai_orchestrator()
    return await orchestrator.generate(prompt, **kwargs)
