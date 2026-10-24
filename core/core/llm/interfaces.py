from collections.abc import AsyncGenerator, Sequence
from enum import StrEnum
from typing import Any, Protocol


class ExecutionMode(StrEnum):
    CLOUD = "cloud"
    LOCAL = "local"
    AUTO = "auto"


class ModelProvider(Protocol):
    """
    Contract for AI model execution providers (e.g., Cloud, Ollama, Anthropic).
    Ensures SupremeAI maintains authority over execution and telemetry boundaries.
    """

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
        """Generate a complete text completion."""
        ...

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
        """Stream a text completion."""
        ...

    async def health_check(self) -> bool:
        """Check if the provider is reachable and healthy."""
        ...
