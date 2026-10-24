from enum import StrEnum
from typing import Any, Protocol


class PrivacyMode(StrEnum):
    FULL = "full"
    METADATA_ONLY = "metadata_only"
    DISABLED = "disabled"


class AIObservabilityProvider(Protocol):
    """
    Contract for AI observability (e.g. Langfuse, custom telemetry).
    Decouples tracing logic from the specific LLM Gateway or underlying LLM library.
    """

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
        """
        Record a generation trace.
        If privacy_mode is METADATA_ONLY, the prompt and response_text MUST NOT be transmitted to cloud endpoints.
        Returns the ID of the recorded trace (if applicable).
        """
        ...

    async def log_evaluation(
        self,
        trace_id: str,
        score: float,
        name: str,
        comment: str | None = None,
    ) -> None:
        """
        Log an evaluation score for a specific trace.
        """
        ...

    async def health_check(self) -> bool:
        """Check if the observability provider is reachable."""
        ...
