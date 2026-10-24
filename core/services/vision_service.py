# SupremeAI 2.0 - Multimodal Vision Service Engine
# বাংলা মন্তব্য: এটি ইমেজ এবং ভিজ্যুয়াল ডায়াগ্রাম/আর্কিটেকচার এনালাইসিস এবং ইউআই স্ক্রিনশট থেকে কোড প্রস্তুত করে।

from __future__ import annotations

import base64
import os
import time
from typing import Any

from core.logging_config import logger

# Issue #444 doctrine (real work or loud failure, never fabricated success):
# the old implementation returned one HARDCODED description ("Identified 3-tier
# microservice backend architecture with Redis cache and PostgreSQL database.",
# confidence 0.94) for EVERY uploaded image without decoding a single byte.
# This service now performs a REAL vision-model call (Gemini) when a key is
# configured, and otherwise returns an explicit, honest "unavailable" status.
_vision_unavailable_announced = False

_MIME_SNIFFS: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),  # WebP containers start with RIFF
)


def _sniff_mime(image_bytes: bytes) -> str:
    for magic, mime in _MIME_SNIFFS:
        if image_bytes.startswith(magic):
            return mime
    return "image/png"


def _get_settings():
    from core.config import settings

    return settings


def _vision_model() -> str:
    """Resolve the vision model id (strip provider prefix if present)."""
    raw = getattr(_get_settings(), "model_vision", "") or ""
    model = str(raw).strip()
    if "/" in model:
        model = model.split("/", 1)[1]
    return model or "gemini-2.5-flash"


class VisionService:
    """
    Multimodal Vision Analysis Engine.
    Processes image inputs, diagrams, screenshots, and visual architectural mockups.
    """

    async def analyze_image(
        self, image_bytes: bytes, query: str = "Analyze this diagram", user_query: str | None = None
    ) -> dict[str, Any]:
        """
        Analyze image bytes and extract architectural components or UI code layout.

        বাংলা: আসল ভিশন মডেল কল (Gemini) — কোনো ফাঁকি সাকসেস নেই। কী না থাকলে
        সৎ "unavailable" স্ট্যাটাস, কখনো বানানো বিশ্লেষণ নয় (issue #444)।
        """
        global _vision_unavailable_announced
        try:
            if not image_bytes:
                return {
                    "status": "error",
                    "query": user_query,
                    "error": "EMPTY_IMAGE",
                    "message": "No image bytes were provided for analysis.",
                }

            gemini_key = os.getenv("GEMINI_API_KEY") or getattr(
                _get_settings(), "gemini_api_key", ""
            )
            if not gemini_key:
                if not _vision_unavailable_announced:
                    _vision_unavailable_announced = True
                    logger.warning(
                        "Vision analysis UNAVAILABLE: no vision provider configured "
                        "(set GEMINI_API_KEY). Returning honest 'unavailable' status "
                        "instead of fabricated analysis (issue #444)."
                    )
                return {
                    "status": "unavailable",
                    "reason": "VISION_NOT_CONFIGURED",
                    "query": user_query,
                    "analysis": "",
                    "detected_objects": [],
                    "message": (
                        "No vision provider is configured on this deployment "
                        "(GEMINI_API_KEY missing), so the image was NOT analyzed. "
                        "Configure a vision model to enable image understanding."
                    ),
                }

            return await self._analyze_with_gemini(image_bytes, query, user_query, gemini_key)
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return {"status": "error", "query": user_query, "analysis": "", "error": str(e)}

    async def _analyze_with_gemini(
        self, image_bytes: bytes, query: str, user_query: str | None, api_key: str
    ) -> dict[str, Any]:
        """Real Gemini vision call with the image inlined as base64 data."""
        import httpx

        model = _vision_model()
        base_url = "https://generativelanguage.googleapis.com/v1beta"
        url = f"{base_url}/models/{model}:generateContent"
        mime = _sniff_mime(image_bytes)
        prompt = user_query or query or "Analyze this image"

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime,
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 1024,
            },
        }

        started = time.monotonic()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                url,
                params={"key": api_key},
                json=payload,
                headers={"Content-Type": "application/json"},
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        if response.status_code != 200:
            logger.error(
                "Gemini vision call failed: HTTP %s: %s",
                response.status_code,
                response.text[:200],
            )
            return {
                "status": "error",
                "query": user_query,
                "analysis": "",
                "error": "VISION_PROVIDER_ERROR",
                "provider_status": response.status_code,
                "message": response.text[:300],
            }

        data = response.json()
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError):
            text = ""
        if not text:
            return {
                "status": "error",
                "query": user_query,
                "analysis": "",
                "error": "EMPTY_VISION_RESPONSE",
                "message": "Vision provider returned no textual analysis.",
            }

        logger.info(
            "Vision analysis completed via %s (%d bytes image, %dms)",
            model,
            len(image_bytes),
            latency_ms,
        )
        # Honest result shape: no fabricated confidence score, no fabricated
        # detected_objects — only what the model actually returned.
        return {
            "status": "success",
            "query": user_query,
            "analysis": text,
            "model": model,
            "latency_ms": latency_ms,
        }
