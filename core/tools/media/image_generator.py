import os
from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger


class HFImageGenerator:
    """
    Generates images using HuggingFace Inference API.
    """

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or getattr(settings, "hf_api_key", "")
        self.default_model = "stabilityai/stable-diffusion-xl-base-1.0"

    async def generate_image(
        self,
        prompt: str,
        model: str | None = None,
        output_path: str = "data/generated_image.png",
    ) -> dict[str, Any]:
        """
        Calls HuggingFace Inference API text-to-image pipeline asynchronously.
        """
        import asyncio

        model = model or self.default_model
        if not self.api_key:
            # বাংলা মন্তব্য: এপিআই কী অনুপস্থিত থাকলে এআই মক করার বদলে সরাসরি ValueError ছুঁড়ে দেবে, জিরো-স্টাব পলিসি অনুযায়ী।
            raise ValueError(
                "HF_API_KEY is not configured. HuggingFace image generation requires a valid API key."
            )

        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = f"https://api-inference.huggingface.co/models/{model}"

        try:
            logger.info(f"Generating image via HF Model '{model}' with prompt: {prompt}")
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(url, headers=headers, json={"inputs": prompt})

                # Check for model loading
                if res.status_code == 503:
                    estimated_time = float(res.json().get("estimated_time", 20.0))
                    logger.warning(
                        f"HF Model is loading. Estimated time: {estimated_time}s. Retrying once..."
                    )
                    # Use non-blocking delays for async HTTP retry
                    await asyncio.sleep(min(estimated_time, 60.0))
                    res = await client.post(url, headers=headers, json={"inputs": prompt})

                res.raise_for_status()
                image_data = res.content

                # Ensure directories exist
                os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(image_data)

                return {
                    "success": True,
                    "model": model,
                    "prompt": prompt,
                    "output_path": output_path,
                    "mock": False,
                }
        except Exception as e:
            # বাংলা মন্তব্য: কানেকশন বা সার্ভার এরর হলে এটি আর সাইলেন্টলি ফেইল না করে সরাসরি এরর ডিকশনারি রিটার্ন করবে।
            logger.error(f"HuggingFace image generation failed: {e}")
            return {"success": False, "error": f"HuggingFace API call failed: {e!s}"}
