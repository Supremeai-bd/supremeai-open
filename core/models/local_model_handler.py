"""Local Model Handler for SupremeAI 2.0
=====================================
Handles local model inference (Ollama / HuggingFace Transformers)
with health checking, async execution, caching, and fallback resilience.

বাংলা মন্তব্য: লোকাল ইনফারেন্স হ্যান্ডলার — Ollama এবং লোকাল ট্রান্সফর্মার্স সাপোর্টসহ।
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

from core.config import settings
from core.logging_config import logger


class LocalModelHandler:
    """Local model provider supporting Ollama API and custom local transformer endpoints."""

    DISTILLED_EDGE_MODELS = [
        "qwen2.5:3b",
        "llama3.2:3b",
        "deepseek-r1:1.5b",
        "phi3:mini",
    ]

    def __init__(self, ollama_base_url: str | None = None) -> None:
        self.base_url = (
            ollama_base_url
            or os.getenv("OLLAMA_URL")
            or getattr(settings, "ollama_url", "")
            or "http://localhost:11434"  # is_local()
        ).rstrip("/")
        self.timeout = float(os.getenv("LOCAL_MODEL_TIMEOUT", "30.0"))
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._cache_ttl = 60.0  # 1 minute TTL for local caching

    async def deploy_distilled_edge_model(self, model_tag: str = "qwen2.5:3b") -> dict[str, Any]:
        """Pull and initialize distilled 3B/4B edge model on local Ollama runtime.

        বাংলা মন্তব্য: ডিস্টিল্ড ৩বি/৪বি এজ মডেল ওলামাতে পুল এবং সেটআপ।
        """
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                res = await client.post(
                    f"{self.base_url}/api/pull", json={"name": model_tag, "stream": False}
                )
                if res.status_code == 200:
                    logger.info(f"Successfully deployed distilled edge model: {model_tag}")
                    return {"status": "deployed", "model": model_tag}
                return {"status": "error", "model": model_tag, "error": res.text}
        except Exception as exc:
            logger.error(f"Failed to deploy distilled edge model {model_tag}: {exc}")
            return {"status": "error", "model": model_tag, "error": str(exc)}

    async def health_check(self) -> bool:
        """Check if local inference engine (Ollama) is operational.

        বাংলা মন্তব্য: লোকাল ওলামা এন্ডপয়েন্টের স্বাস্থ্য পরীক্ষা।
        """
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                return res.status_code == 200
        except Exception as exc:
            logger.debug(f"Local model handler health check failed: {exc}")
            return False

    async def list_models(self) -> list[str]:
        """List models available locally in Ollama.

        বাংলা মন্তব্য: লোকাল ওলামায় ইনস্টল থাকা মডেলগুলোর তালিকা।
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self.base_url}/api/tags")
                if res.status_code == 200:
                    data = res.json()
                    models = data.get("models", [])
                    return [m.get("name") for m in models if "name" in m]
        except Exception as exc:
            logger.warning(f"Failed to list local models: {exc}")
        return []

    async def infer(
        self, model: str, prompt: str, system_prompt: str | None = None
    ) -> dict[str, Any]:
        """Run inference on a local model.

        বাংলা মন্তব্য: ইনফারেন্স এক্সিকিউশন — মেমোরি ক্যাশিং ও টাইমআউট হ্যান্ডলিং সহ।
        """
        cache_key = f"{model}:{hash(prompt)}"
        now = time.time()
        if cache_key in self._cache:
            created_at, result = self._cache[cache_key]
            if now - created_at < self._cache_ttl:
                return {**result, "cached": True}

        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    output_text = data.get("response", "")
                    res_dict = {
                        "text": output_text,
                        "model": model,
                        "status": "success",
                        "eval_count": data.get("eval_count", 0),
                        "cached": False,
                    }
                    self._cache[cache_key] = (now, res_dict)
                    return res_dict
                else:
                    logger.error(f"Local model error [{res.status_code}]: {res.text}")
                    return {"text": "", "model": model, "status": "error", "error": res.text}
        except httpx.TimeoutException:
            logger.error(f"Local model inference timed out after {self.timeout}s")
            return {"text": "", "model": model, "status": "timeout", "error": "Inference timed out"}
        except Exception as exc:
            logger.error(f"Local model inference failed: {exc}")
            return {"text": "", "model": model, "status": "error", "error": str(exc)}
