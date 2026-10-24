from __future__ import annotations

from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger


class VideoGenerator:
    def __init__(
        self,
        runway_api_key: str | None = None,
        kling_api_key: str | None = None,
    ) -> None:
        self.runway_api_key = runway_api_key or getattr(settings, "runway_api_key", "")
        self.kling_api_key = kling_api_key or getattr(settings, "kling_api_key", "")

    @staticmethod
    def _runway_payload(prompt: str, duration: int) -> dict[str, Any]:
        return {
            "prompt": prompt,
            "duration": duration,
            "model": "gen-3-alpha",
        }

    @staticmethod
    def _kling_payload(prompt: str, duration: int) -> dict[str, Any]:
        return {
            "prompt": prompt,
            "duration": duration,
            "mode": "standard",
            "aspect_ratio": "16:9",
        }

    def _call_runway(self, prompt: str, duration: int) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.runway_api_key}",
            "Content-Type": "application/json",
        }
        url = "https://api.runwayml.com/v1/generate"
        payload = self._runway_payload(prompt, duration)
        with httpx.Client(timeout=120.0) as client:
            res = client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
        return {
            "success": True,
            "provider": "runway",
            "prompt": prompt,
            "duration": duration,
            "job_id": data.get("id"),
            "video_url": data.get("output", {}).get("url"),
            "mock": False,
        }

    def _call_kling(self, prompt: str, duration: int) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.kling_api_key}",
            "Content-Type": "application/json",
        }
        url = "https://api.klingai.ai/v1/videos/generate"
        payload = self._kling_payload(prompt, duration)
        with httpx.Client(timeout=120.0) as client:
            res = client.post(url, headers=headers, json=payload)
            res.raise_for_status()
            data = res.json()
        return {
            "success": True,
            "provider": "kling",
            "prompt": prompt,
            "duration": duration,
            "job_id": data.get("data", {}).get("task_id"),
            "video_url": data.get("data", {}).get("result", {}).get("url"),
            "mock": False,
        }

    def generate(
        self,
        prompt: str,
        duration: int = 5,
        provider: str = "auto",
        output_path: str | None = None,
        tried: set | None = None,
    ) -> dict[str, Any]:
        tried = tried or set()
        if provider == "auto":
            if self.runway_api_key and "runway" not in tried:
                provider = "runway"
            elif self.kling_api_key and "kling" not in tried:
                provider = "kling"

        if provider == "runway":
            if not self.runway_api_key:
                # বাংলা মন্তব্য: API key না থাকলে stub রিটার্ন করা হতো — এখন স্পষ্ট ValueError raise করা হয়
                raise ValueError(
                    "Runway API key required. Set RUNWAY_API_KEY environment variable. "
                    "Get your key from https://app.runwayml.com"
                )
            try:
                return self._call_runway(prompt, duration)
            except Exception as exc:
                logger.error(f"Runway failed: {exc}")
                if self.kling_api_key and "kling" not in tried:
                    logger.info("Falling back to Kling provider.")
                    return self.generate(
                        prompt=prompt,
                        duration=duration,
                        provider="kling",
                        output_path=output_path,
                        tried={*tried, "runway"},
                    )
                raise RuntimeError(
                    f"Runway generation failed and no fallback succeeded: {exc}"
                ) from exc

        if provider == "kling":
            if not self.kling_api_key:
                # বাংলা মন্তব্য: Kling API key না থাকলে stub রিটার্ন করা হতো — এখন স্পষ্ট ValueError raise করা হয়
                raise ValueError(
                    "Kling API key required. Set KLING_API_KEY environment variable. "
                    "Get your key from https://klingai.ai"
                )
            try:
                return self._call_kling(prompt, duration)
            except Exception as exc:
                logger.error(f"Kling failed: {exc}")
                if self.runway_api_key and "runway" not in tried:
                    logger.info("Falling back to Runway provider.")
                    return self.generate(
                        prompt=prompt,
                        duration=duration,
                        provider="runway",
                        output_path=output_path,
                        tried={*tried, "kling"},
                    )
                raise RuntimeError(
                    f"Kling generation failed and no fallback succeeded: {exc}"
                ) from exc

        raise ValueError(f"Unknown provider: {provider!r}. Use 'runway', 'kling', or 'auto'.")
