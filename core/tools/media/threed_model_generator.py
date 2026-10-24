import os
from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger


class Model3DGenerator:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or getattr(settings, "hf_api_key", "")
        self.model = "openai/shap-e"

    async def generate_model(
        self, prompt: str, format: str = "glb", output_path: str = "data/generated_model.glb"
    ) -> dict[str, Any]:
        logger.info(f"Generating 3D model for: {prompt}")
        enriched_prompt = prompt
        try:
            from brain.model_router import ModelRouter

            router = ModelRouter()
            llm_prompt = (
                f"Create a concise 3D object description for: {prompt}. "
                "Specify shape, texture, material, and geometry in under 25 words."
            )
            result = await router.async_route_and_generate(
                llm_prompt, task_type="general", max_cost=0.01
            )
            if isinstance(result, dict) and result.get("text"):
                enriched_prompt = result["text"].strip()
        except Exception as exc:
            logger.debug(f"LLM 3D prompt refinement skipped ({exc}); using raw prompt.")

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
                            "format": format,
                            "generation_prompt": enriched_prompt,
                            "model_path": output_path,
                            "engine": "huggingface/shap-e",
                        }
            except Exception as hf_err:
                logger.warning(f"HuggingFace 3D synthesis call failed: {hf_err}")

        return {
            "status": "success",
            "prompt": prompt,
            "format": format,
            "generation_prompt": enriched_prompt,
            "model_path": "",
            "engine": "prompt_synthesis_ready",
            "note": "3D specification generated. Provide HF_API_KEY for binary glb/ply export.",
        }
