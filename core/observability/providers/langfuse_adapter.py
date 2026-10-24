import json
import uuid
from typing import Any

from core.logging_config import logger

from ..interfaces import AIObservabilityProvider, PrivacyMode


class LangfuseAdapter(AIObservabilityProvider):
    """
    Adapter for Langfuse Observability.
    Enforces PrivacyMode to ensure sensitive local LLM content does not leave the boundary.
    """

    def __init__(self):
        self.enabled = False
        self._langfuse = None
        self._setup_langfuse()

    def _setup_langfuse(self) -> None:
        try:
            from core.config import settings

            public_key = getattr(settings, "LANGFUSE_PUBLIC_KEY", None)
            secret_key = getattr(settings, "LANGFUSE_SECRET_KEY", None)
            host = getattr(settings, "LANGFUSE_HOST", "https://cloud.langfuse.com")

            if public_key and secret_key:
                try:
                    from langfuse import Langfuse

                    self._langfuse = Langfuse(
                        public_key=public_key,
                        secret_key=secret_key,
                        host=host,
                    )
                    self.enabled = True
                    logger.info("[LangfuseAdapter] Successfully initialized Langfuse client.")
                except ImportError:
                    logger.warning(
                        "[LangfuseAdapter] Keys provided but 'langfuse' package is not installed."
                    )
            else:
                logger.info("[LangfuseAdapter] Missing keys; running in NO-OP mode.")
        except Exception as e:
            logger.warning(f"[LangfuseAdapter] Initialization error: {e}")

    async def trace_generation(
        self,
        model: str,
        prompt: str | list[dict[str, Any]],
        response_text: str | None = None,
        usage: dict[str, Any] | None = None,
        duration_s: float | None = None,
        cost: float | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        privacy_mode: PrivacyMode = PrivacyMode.FULL,
    ) -> str | None:
        if not self.enabled or self._langfuse is None or privacy_mode == PrivacyMode.DISABLED:
            return None

        try:
            # Privacy enforcement: scrub content if METADATA_ONLY
            safe_prompt = prompt
            safe_response = response_text

            if privacy_mode == PrivacyMode.METADATA_ONLY:
                safe_prompt = "<REDACTED DUE TO LOCAL PRIVACY POLICY>"
                safe_response = "<REDACTED DUE TO LOCAL PRIVACY POLICY>"
            elif isinstance(prompt, list):
                # Ensure JSON serializeable
                try:
                    safe_prompt = json.dumps(prompt)
                except Exception:
                    safe_prompt = str(prompt)

            trace_id = str(uuid.uuid4())
            trace_name = (
                metadata.get("task_type", "llm_generation") if metadata else "llm_generation"
            )

            trace = self._langfuse.trace(
                id=trace_id,
                name=trace_name,
                session_id=session_id,
                user_id=user_id,
                metadata=metadata,
            )

            # Map usage
            langfuse_usage = {}
            if usage:
                if "prompt_tokens" in usage:
                    langfuse_usage["input"] = usage["prompt_tokens"]
                if "completion_tokens" in usage:
                    langfuse_usage["output"] = usage["completion_tokens"]
                if "total_tokens" in usage:
                    langfuse_usage["total"] = usage["total_tokens"]

            trace.generation(
                name="model_inference",
                model=model,
                input=safe_prompt,
                output=safe_response,
                usage=langfuse_usage,
                usage_details=usage,
                cost=cost,
                startTime=None,  # In a real highly-accurate setup we'd pass exact start/end times
                endTime=None,
            )

            # Removed self._langfuse.flush() to allow background batching
            return trace_id
        except Exception as e:
            logger.warning(f"[LangfuseAdapter] Failed to trace generation: {e}")
            return None

    async def log_evaluation(
        self,
        trace_id: str,
        score: float,
        name: str,
        comment: str | None = None,
    ) -> None:
        if not self.enabled or self._langfuse is None:
            return

        try:
            self._langfuse.score(
                trace_id=trace_id,
                name=name,
                value=score,
                comment=comment,
            )
            # Removed self._langfuse.flush() to allow background batching
        except Exception as e:
            logger.warning(f"[LangfuseAdapter] Failed to log evaluation: {e}")

    async def health_check(self) -> bool:
        if not self.enabled or self._langfuse is None:
            return False

        try:
            return self._langfuse.auth_check()
        except Exception:
            return False
