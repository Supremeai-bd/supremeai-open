import json
from collections.abc import AsyncGenerator, Sequence
from typing import Any

import httpx

from core.logging_config import logger

from ...config import settings
from ..interfaces import ModelProvider


class OllamaLocalAdapter(ModelProvider):
    """
    Adapter for local Ollama execution.
    Ensures complete privacy by running models locally via Ollama's API.
    """

    def __init__(self, default_api_base: str = "http://localhost:11434"):  # is_local()
        if "localhost" in default_api_base:
            if settings.env == "local" or settings.env == "test":
                pass
            else:
                raise ValueError(
                    f"Ollama initialized with localhost fallback ({default_api_base}) in non-local "
                    f"environment '{settings.env}'. Please provide a valid external API base."
                )
        self.default_api_base = default_api_base
        # Privacy enforcement: Never send telemetry or logging for local execution to cloud
        self._enforce_privacy_boundary = True

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
        """Generate a complete text completion using Ollama's chat API."""
        base_url = api_base or self.default_api_base
        url = f"{base_url.rstrip('/')}/api/chat"

        payload = {
            "model": model,
            "messages": messages,
            "options": {
                "temperature": temperature,
            },
            "stream": False,
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()

                return {
                    "choices": [
                        {
                            "message": {
                                "role": data.get("message", {}).get("role", "assistant"),
                                "content": data.get("message", {}).get("content", ""),
                            }
                        }
                    ],
                    "usage": {
                        "prompt_tokens": data.get("prompt_eval_count", 0),
                        "completion_tokens": data.get("eval_count", 0),
                        "total_tokens": data.get("prompt_eval_count", 0)
                        + data.get("eval_count", 0),
                    },
                    "model": model,
                    "provider": "ollama",
                }
        except Exception as e:
            logger.error(f"[OllamaLocalAdapter] Failed to generate completion: {e}")
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
        """Stream a text completion using Ollama's chat API."""
        base_url = api_base or self.default_api_base
        url = f"{base_url.rstrip('/')}/api/chat"

        payload = {
            "model": model,
            "messages": messages,
            "options": {
                "temperature": temperature,
            },
            "stream": True,
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            yield {
                                "choices": [
                                    {
                                        "delta": {
                                            "role": data.get("message", {}).get("role", ""),
                                            "content": data.get("message", {}).get("content", ""),
                                        }
                                    }
                                ],
                                "model": model,
                                "provider": "ollama",
                            }
                        except json.JSONDecodeError:
                            logger.warning(
                                f"[OllamaLocalAdapter] Failed to parse stream chunk: {line}"
                            )
        except Exception as e:
            logger.error(f"[OllamaLocalAdapter] Failed to stream completion: {e}")
            raise

    async def health_check(self) -> bool:
        """Check if the Ollama daemon is reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(self.default_api_base.rstrip("/"))
                # Ollama typically returns "Ollama is running" on the root path
                return response.status_code == 200 and "Ollama is running" in response.text
        except Exception:
            return False
