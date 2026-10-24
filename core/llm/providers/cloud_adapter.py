from collections.abc import AsyncGenerator, Sequence
from typing import Any

from core.logging_config import logger

from ..interfaces import ModelProvider

# ============================================================================
# PLAN-001: Anthropic prompt caching (2026-09-17)
# ---------------------------------------------------------------------------
# The system prompt (+ MCP tool catalog) is re-sent on every chat turn. When
# the routed provider is Anthropic-family, marking that prefix with Anthropic's
# `cache_control: {"type": "ephemeral"}` lets the vendor cache it: ~90% cheaper
# and 50-80% faster on cached portions (vendor pricing/benchmarks). LiteLLM
# passes the content-block format through natively — zero new dependency.
# Constitution anchors: #14 Sustainable Cost (primary), #8 Graceful Degradation
# (worst case = today's behavior), #3 Reuse Before Creation.
# ============================================================================


def _is_anthropic_family_model(model: str | None) -> bool:
    """Anthropic-family detection: claude-* models, or any router id that
    contains the `anthropic` segment (e.g. `openrouter/anthropic/claude-...`).
    Non-Anthropic providers (Gemini/Groq/OpenAI) reject unknown content-block
    params, so caching markers must never leak to them."""
    if not model or not isinstance(model, str):
        return False
    lowered = model.lower()
    return "claude" in lowered or "anthropic" in lowered


def _mark_anthropic_cache_blocks(
    messages: Sequence[dict[str, Any]],
    model: str | None,
) -> list[dict[str, Any]]:
    """Return a new messages list where every system-prefix block (system prompt,
    tool catalog) carries Anthropic's ephemeral cache_control marker.

    Pure function: never mutates the caller's list; only string contents are
    wrapped into the content-block format Anthropic's API expects (LiteLLM
    passes it through verbatim). Non-Anthropic models are returned untouched.
    """
    if not _is_anthropic_family_model(model):
        return list(messages)
    marked: list[dict[str, Any]] = []
    for msg in messages:
        if (
            isinstance(msg, dict)
            and msg.get("role") == "system"
            and isinstance(msg.get("content"), str)
            and msg["content"]
        ):
            marked.append(
                {
                    **msg,
                    "content": [
                        {
                            "type": "text",
                            "text": msg["content"],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            )
        else:
            # Non-system roles or already-block-encoded contents pass through.
            marked.append(msg)
    return marked


class CloudProviderAdapter(ModelProvider):
    """
    Adapter for cloud execution, wrapping LiteLLM.
    Handles multiple providers (OpenAI, Anthropic, Gemini, Groq, etc.)
    and enforces SupremeAI's telemetry and key rotation policies.
    """

    def __init__(self):
        # We lazy import litellm to avoid cold starts if only running locally
        pass

    def _get_litellm(self):
        try:
            import litellm

            # Enforce SupremeAI telemetry policies - disable LiteLLM's internal telemetry
            litellm.telemetry = False
            litellm.drop_params = True
            return litellm
        except ImportError:
            logger.error("litellm is not installed. CloudProviderAdapter requires litellm.")
            raise

    async def generate(
        self,
        model: str,
        messages: Sequence[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 60.0,
        api_key: str | None = None,
        api_base: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a complete text completion using LiteLLM."""
        litellm = self._get_litellm()

        try:
            # PLAN-001: mark the cacheable system prefix when the provider is
            # Anthropic-family (no-op for every other provider).
            messages = _mark_anthropic_cache_blocks(messages, model=model)
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                api_key=api_key,
                api_base=api_base,
                **kwargs,
            )

            # Format to consistent output
            return {
                "choices": [
                    {
                        "message": {
                            "role": response.choices[0].message.role,
                            "content": response.choices[0].message.content,
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                    # PLAN-001: surface Anthropic cache telemetry (0 when absent).
                    # This usage dict is forwarded to Langfuse via trace_generation,
                    # so cache-hit metrics become observable with zero new infra.
                    "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0)
                    or 0,
                    "cache_creation_input_tokens": getattr(
                        response.usage, "cache_creation_input_tokens", 0
                    )
                    or 0,
                },
                "model": response.model,
                "provider": "cloud",  # We could extract the exact provider from litellm if needed
            }
        except Exception as e:
            logger.error(f"[CloudProviderAdapter] Failed to generate completion: {e}")
            raise

    async def stream(
        self,
        model: str,
        messages: Sequence[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: float = 60.0,
        api_key: str | None = None,
        api_base: str | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a text completion using LiteLLM."""
        litellm = self._get_litellm()

        try:
            # PLAN-001: same cacheable-prefix marking on the streaming path.
            messages = _mark_anthropic_cache_blocks(messages, model=model)
            response = await litellm.acompletion(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                api_key=api_key,
                api_base=api_base,
                stream=True,
                **kwargs,
            )

            async for chunk in response:
                yield {
                    "choices": [
                        {
                            "delta": {
                                "role": chunk.choices[0].delta.role
                                if hasattr(chunk.choices[0].delta, "role")
                                else "",
                                "content": chunk.choices[0].delta.content or "",
                            }
                        }
                    ],
                    "model": chunk.model,
                    "provider": "cloud",
                }
        except Exception as e:
            logger.error(f"[CloudProviderAdapter] Failed to stream completion: {e}")
            raise

    async def health_check(self) -> bool:
        """
        Cloud providers are assumed to be handled per-request by LiteLLM exceptions.
        A true health check would ping a specific provider API.
        """
        return True
