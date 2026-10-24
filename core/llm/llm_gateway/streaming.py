# backend/core/llm/llm_gateway/streaming.py
"""Streaming completion with fallback chain.

Task 4-a package split: code moved VERBATIM from core/llm/llm_gateway.py into
the StreamingMixin used by LLMGateway (core/llm/llm_gateway/gateway.py).

M16 P-A: stream শেষে বাস্তব usage থেকে খরচ meter হয় (non-streaming-এর সাথে
accounting parity)। provider usage না দিলে কিছুই record করা হয় না — gap-টি
দৃশ্যমান warning হিসেবে লগ হয় (বানানো সংখ্যা নিষিদ্ধ)।
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from core.logging_config import logger

from .registry import _resolve_litellm_target
from .spend_meter import settle_gateway_spend


class StreamingMixin:
    """Streaming fallback method for LLMGateway (verbatim move)."""

    async def _stream_completion(
        self,
        messages: list[dict[str, Any]],
        call_chain: list[str],
        timeout: float,
        *,
        tenant_id: str | None = None,
        tier: str | None = None,
        task_type: str = "general",
    ) -> AsyncGenerator[str, None]:
        """বাংলা মন্তব্ব: Streaming completion — fallback chain সহ।"""
        self._ensure_litellm_ready()
        import asyncio

        import litellm  # lazy import

        last_exception: Exception | None = None
        for current_model in call_chain:
            # FINAL-TEST FIX (2026-09-13): skip retired models + route
            # OpenAI-compatible routers (BYNARA/BAI) via their base URL.
            try:
                _litellm_model, _api_base = _resolve_litellm_target(current_model)
            except ValueError as retired_err:
                logger.warning(f"[LLMGateway] Streaming skip {current_model}: {retired_err}")
                continue
            # Circuit Breaker check
            cb = self._get_or_create_circuit_breaker(current_model)
            if not cb.allow_request():
                logger.warning(
                    f"[LLMGateway] Circuit breaker OPEN for {current_model}. Skipping..."
                )
                continue

            try:
                logger.info(f"[LLMGateway] Streaming attempt: {current_model}")
                # api_key per-call — os.environ injection নিষিদ্ধ
                api_key = await self._get_api_key_for_model(current_model)
                response_stream = await litellm.acompletion(
                    model=_litellm_model,
                    messages=messages,
                    timeout=timeout,
                    stream=True,
                    api_key=api_key,
                    api_base=_api_base,
                )
                usage_out: dict[str, Any] = {}
                async for content in self._drain_stream_collect_usage(response_stream, usage_out):
                    yield content
                cb.mark_success()
                # M16 P-A: stream শেষে বাস্তব usage দিয়ে খরচ meter — provider usage
                # না থাকলে settle নিজেই দৃশ্যমান gap-warning দেবে, কিছু বানাবে না।
                await settle_gateway_spend(
                    tenant_id=tenant_id,
                    tier=tier,
                    model=current_model,
                    task_type=task_type,
                    path="streaming",
                    usage=usage_out or None,
                )
                return
            except asyncio.CancelledError:
                # বাংলা মন্তব্ব: CancelledError re-raise — কখনো suppress করা যাবে না।
                # তবে বাতিল হওয়া স্ট্রিমের আংশিক খরচ unmetered থাকে — সেটা নীরবে
                # লুকানো যাবে না, তাই gap-টি স্পষ্ট লগ হচ্ছে।
                logger.warning(
                    f"[LLMGateway] Stream cancelled at model {current_model} — "
                    f"partial spend unmetered (tenant={tenant_id or 'unknown'})"
                )
                raise
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    # Handle rate limit in streaming case too
                    handled = await self._handle_rate_limit_error(current_model, exc)
                    if handled:
                        logger.info(
                            f"[LLMGateway] Retrying streaming {current_model} after rate limit backoff..."
                        )
                        try:
                            api_key = await self._get_api_key_for_model(current_model)
                            response_stream = await litellm.acompletion(
                                model=_litellm_model,
                                messages=messages,
                                timeout=timeout,
                                stream=True,
                                api_key=api_key,
                                api_base=_api_base,
                            )
                            usage_out: dict[str, Any] = {}
                            async for content in self._drain_stream_collect_usage(
                                response_stream, usage_out
                            ):
                                yield content
                            cb.mark_success()
                            # M16 P-A: 429-retry stream-ও বাস্তব খরচ — একই parity।
                            await settle_gateway_spend(
                                tenant_id=tenant_id,
                                tier=tier,
                                model=current_model,
                                task_type=task_type,
                                path="streaming-429-retry",
                                usage=usage_out or None,
                            )
                            return
                        except Exception as retry_exc:
                            logger.warning(
                                f"[LLMGateway] Retry failed for streaming {current_model}: {retry_exc}"
                            )
                last_exception = exc
                cb.mark_failure()
                logger.opt(exception=True).warning(
                    f"[LLMGateway] Stream model {current_model} failed."
                )
                continue
            except Exception as exc:
                last_exception = exc
                cb.mark_failure()
                logger.opt(exception=True).warning(
                    f"[LLMGateway] Stream model {current_model} failed."
                )
                continue

        raise last_exception or RuntimeError("All streaming fallback options failed.")

    async def _drain_stream_collect_usage(
        self, response_stream: Any, usage_out: dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """Yield content deltas and capture the final usage block when the provider sends one.

        বাংলা মন্তব্ব: কিছু provider (stream_options include_usage) শেষ chunk-এ
        usage পাঠায় যার ``choices`` খালি থাকে — পুরনো কোড `chunk.choices[0]` করায়
        ওই chunk-এই IndexError হতো। এখন খালি-choices chunk নিরাপদে skip হয় এবং
        usage থাকলে ``usage_out`` dict-এ লেখা হয় (in-place — async generator
        return দিয়ে মান ফেরত দিতে পারে না); usage না এলে dict খালি থাকে এবং
        caller সৎভাবে gap-log করবে — কোনো বানানো সংখ্যা নয়।
        """
        async for chunk in response_stream:
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None and (
                getattr(chunk_usage, "prompt_tokens", None)
                or getattr(chunk_usage, "completion_tokens", None)
            ):
                usage_out["prompt_tokens"] = getattr(chunk_usage, "prompt_tokens", 0) or 0
                usage_out["completion_tokens"] = getattr(chunk_usage, "completion_tokens", 0) or 0
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                # বাংলা মন্তব্ব: usage-only chunk (choices খালি) — content নেই।
                continue
            content = choices[0].delta.content
            if content:
                yield content
