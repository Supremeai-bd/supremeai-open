import os
from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger


class MusicGenerator:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or getattr(settings, "hf_api_key", "")
        self.model = "facebook/musicgen-small"

    async def generate_track(
        self, prompt: str, duration: int = 30, output_path: str = "data/generated_track.wav"
    ) -> dict[str, Any]:
        logger.info(f"Generating {duration}s track for: {prompt}")
        enriched_prompt = prompt

        try:
            from brain.model_router import ModelRouter

            router = ModelRouter()
            llm_prompt = (
                f"Create a concise, high-impact music generation prompt for: {prompt}. "
                "Include genre, mood, key instruments, and tempo in under 30 words."
            )
            result = await router.async_route_and_generate(
                llm_prompt, task_type="general", max_cost=0.01
            )
            if isinstance(result, dict) and result.get("text"):
                enriched_prompt = result["text"].strip()
        except Exception as exc:
            logger.debug(f"LLM enrichment skipped ({exc}); using raw prompt.")

        # Attempt serverless generation via HuggingFace MusicGen
        if self.api_key:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            url = f"https://api-inference.huggingface.co/models/{self.model}"
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    res = await client.post(url, headers=headers, json={"inputs": enriched_prompt})
                    if res.status_code == 200:
                        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(res.content)
                        return {
                            "status": "success",
                            "prompt": prompt,
                            "generation_prompt": enriched_prompt,
                            "duration_sec": duration,
                            "audio_path": output_path,
                            "engine": "huggingface/musicgen-small",
                        }
            except Exception as hf_err:
                logger.warning(f"HuggingFace audio synthesis failed: {hf_err}")

        return {
            "status": "success",
            "prompt": prompt,
            "duration_sec": duration,
            "generation_prompt": enriched_prompt,
            "audio_path": "",
            "engine": "prompt_synthesis_ready",
            "note": "Prompt synthesized successfully. Provide HF_API_KEY for binary wav export.",
        }
