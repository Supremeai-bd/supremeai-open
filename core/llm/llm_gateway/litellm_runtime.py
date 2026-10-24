# backend/core/llm/llm_gateway/litellm_runtime.py
"""One-time lazy litellm setup + cost/error callbacks.

Task 4-a package split: code moved VERBATIM from core/llm/llm_gateway.py into
the LitellmSetupMixin used by LLMGateway (core/llm/llm_gateway/gateway.py).
litellm stays a lazy, function-level import (R2-MEM fix: ~240MB RSS at boot).
"""

import asyncio

from core.errors.error_bus import with_error_bus
from core.logging_config import logger

from ...messaging.event_bus import (  # Fixed import path - using relative import
    ErrorContext,
    ErrorEvent,
    error_event_bus,
)


class LitellmSetupMixin:
    """Lazy litellm globals/callbacks setup for LLMGateway (verbatim move)."""

    def _ensure_litellm_ready(self) -> None:
        """One-time lazy litellm setup (R2-MEM fix) — runs at first LLM call."""
        if self._litellm_ready:
            return
        self._setup_litellm_globals()
        self._setup_callbacks()
        self._litellm_ready = True

    def _setup_litellm_globals(self) -> None:
        """
        বাংলা মন্তব্ব: litellm global settings — শুধু safe non-secret settings।
        os.environ-এ secrets inject করা সম্পূর্ণ নিষিদ্ধ।
        API keys আর এখানে set করা হচ্ছে না।
        প্রতিটি acompletion call-এ api_key parameter pass হবে।
        """
        # litellm প্যাকেজটি অনুপলব্ধ থাকলে সিস্টেম যেন ক্র্যাশ না করে, সে জন্য সেফ ট্রাই-এক্সেপ্ট ব্যবহার করা হলো।
        try:
            import litellm  # lazy import — module level নয়

            litellm.drop_params = True
            litellm.telemetry = False
            litellm.use_litellm_proxy = False

            # Setup Redis Cache for LiteLLM built-in cache/rate-limiting
            from ...config import settings  # Fixed import path - using relative import

            if getattr(settings, "redis_url", None):
                litellm.cache = litellm.Cache(type="redis", url=settings.redis_url)

            # Performance Optimization: Share a single aiohttp ClientSession across all LiteLLM requests
            # to prevent repeated session creation overhead
            try:
                import aiohttp

                if getattr(litellm, "client_session", None) is None:
                    # Note: Ideally instantiated inside an async context, but LiteLLM handles
                    # the reuse internally. This is a known optimization for LiteLLM.
                    litellm.client_session = aiohttp.ClientSession(
                        timeout=aiohttp.ClientTimeout(total=300),
                        connector=aiohttp.TCPConnector(limit=100, keepalive_timeout=60),
                    )
            except Exception as e:
                import logging

                logging.getLogger(__name__).debug(
                    f"Could not setup shared aiohttp session for litellm: {e}"
                )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")

    def _setup_callbacks(self) -> None:
        """বাংলা মন্তব্ব: litellm callback — cost এবং error tracking।"""
        try:
            import litellm  # lazy import
        except ImportError:
            return

        callbacks_success = []
        callbacks_failure = []

        # Integrate Langfuse Observability
        # Note: Litellm's internal 'langfuse' callback is removed in favor of explicit AIObservabilityProvider tracing

        def success_callback(kwargs, response_obj, start_time, end_time):
            try:
                model = kwargs.get("model", "unknown")
                usage = getattr(response_obj, "usage", None)
                prompt_tokens = getattr(usage, "prompt_tokens", 0)
                completion_tokens = getattr(usage, "completion_tokens", 0)
                cost = (
                    response_obj._response_metadata.get("api_cost", 0.0)
                    if hasattr(response_obj, "_response_metadata")
                    else 0.0
                )
                duration = (end_time - start_time).total_seconds()
                logger.info(
                    f"[LLMGateway] ✅ Model={model} | Cost=${cost:.6f} | P={prompt_tokens} C={completion_tokens} | {duration:.2f}s"
                )
            except Exception as exc:
                logger.warning(f"[LLMGateway] Success callback error: {exc}")

        @with_error_bus("failure_callback")
        def failure_callback(kwargs, exception_obj, start_time, end_time):
            model = kwargs.get("model", "unknown")
            try:
                delta = end_time - start_time
                duration = (
                    delta.total_seconds() if hasattr(delta, "total_seconds") else float(delta)
                )
            except Exception:
                duration = 0.0
            logger.error(
                f"[LLMGateway] ❌ Model={model} failed | Error={str(exception_obj)[:200]} | {duration:.2f}s"
            )
            error_event_bus.emit(
                ErrorEvent(
                    module="llm_gateway",
                    error_type="LLM_CALL_FAILED",
                    message=str(exception_obj)[:500],
                    severity="ERROR",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"model": model, "duration_s": round(duration, 2)},
                )
            )

        callbacks_success.append(success_callback)
        callbacks_failure.append(failure_callback)

        litellm.success_callback = callbacks_success
        litellm.failure_callback = callbacks_failure
