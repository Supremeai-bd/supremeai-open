from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


class LLMProvider(Protocol):
    name: str

    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        ...


@dataclass
class OpenAICompatibleProvider:
    """Works with OpenAI-compatible endpoints, including DeepSeek-style APIs."""
    name: str
    api_key_env: str
    base_url: str
    model: str

    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError("Install 'openai' to use OpenAICompatibleProvider") from exc

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing environment variable: {self.api_key_env}")

        client = AsyncOpenAI(api_key=api_key, base_url=self.base_url)
        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""


@dataclass
class AnthropicProvider:
    name: str
    api_key_env: str
    model: str
    max_tokens: int = 4096

    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise RuntimeError("Install 'anthropic' to use AnthropicProvider") from exc

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing environment variable: {self.api_key_env}")

        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=temperature,
        )
        return "".join(
            getattr(block, "text", "") for block in response.content
            if getattr(block, "type", None) == "text"
        )


@dataclass
class GeminiProvider:
    name: str
    api_key_env: str
    model: str

    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> str:
        try:
            from google import genai
        except ImportError as exc:
            raise RuntimeError("Install 'google-genai' to use GeminiProvider") from exc

        api_key = os.getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing environment variable: {self.api_key_env}")

        client = genai.Client(api_key=api_key)
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=f"{system}\n\nUSER:\n{user}",
        )
        return getattr(response, "text", "") or ""


def default_providers() -> list[LLMProvider]:
    providers: list[LLMProvider] = []

    if os.getenv("DEEPSEEK_API_KEY"):
        providers.append(
            OpenAICompatibleProvider(
                name="deepseek",
                api_key_env="DEEPSEEK_API_KEY",
                base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            )
        )

    if os.getenv("ANTHROPIC_API_KEY"):
        providers.append(
            AnthropicProvider(
                name="anthropic",
                api_key_env="ANTHROPIC_API_KEY",
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet"),
            )
        )

    if os.getenv("GEMINI_API_KEY"):
        providers.append(
            GeminiProvider(
                name="gemini",
                api_key_env="GEMINI_API_KEY",
                model=os.getenv("GEMINI_MODEL", "gemini-3.7-flash"),
            )
        )

    return providers
