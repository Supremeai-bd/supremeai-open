"""
IDE Trio Stage 1: Gemini Flash Writer
Uses FREE Gemini Flash for code generation
"""

import asyncio
import time

import httpx

from core.config import settings


class GeminiWriter:
    """
    Gemini Flash integration for IDE Trio Pipeline

    Free Tier Limits:
    - 15 requests per minute
    - 1,500 requests per day
    - FREE for development use
    """

    GEMINI_FLASH_MODEL = getattr(settings, "model_vision", "models/gemini-2.5-flash")
    GEMINI_1_5_FLASH = "models/gemini-1.5-flash"  # Backup

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            base_url="https://generativelanguage.googleapis.com/v1beta",
            headers={"x-goog-api-key": api_key},
            timeout=60.0,
        )

        # Rate limiting tracker
        self._requests_today: int = 0
        self._last_request_time: float = 0
        self._min_interval: float = 4.0  # 60s / 15 RPM = 4s between requests

    async def generate_code(
        self, prompt: str, context: str = "", language: str = "python"
    ) -> str | None:
        """Generate code using Gemini Flash (FREE)"""

        # Respect rate limits
        await self._rate_limit_wait()

        # Construct prompt with best practices
        full_prompt = f"""You are Stage 1 of the IDE Trio Pipeline (WRITER).
Your job is to WRITE clean, production-ready code based on requirements.

Language: {language}
Context: {context}

Requirements:
{prompt}

Output ONLY the code implementation. No explanations, no markdown fences."""

        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "topK": 40,
                "topP": 0.95,
                "maxOutputTokens": 8192,
            },
        }

        try:
            response = await self.client.post(
                f"/{self.GEMINI_FLASH_MODEL}:generateContent", json=payload
            )

            response.raise_for_status()
            data = response.json()

            # Track usage
            self._requests_today += 1

            # Extract generated text
            text = data["candidates"][0]["content"]["parts"][0]["text"]

            return text.strip()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                # Rate limited - wait and retry once
                await asyncio.sleep(10)
                return await self.generate_code(prompt, context, language)
            raise
        finally:
            self._last_request_time = time.time()

    async def _rate_limit_wait(self):
        """Ensure we don't exceed 15 RPM"""
        elapsed = time.time() - self._last_request_time

        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
