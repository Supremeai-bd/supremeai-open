# backend/services/dynamic_ai/local_fallback.py
"""
Local Fallback using Ollama
Ensures system ALWAYS works even with ZERO external APIs
Runs locally, no API keys needed, 100% uptime
"""

import asyncio
import subprocess
from dataclasses import dataclass
from enum import Enum

import httpx

from core.logging_config import logger


class OllamaModelStatus(Enum):
    AVAILABLE = "available"
    NOT_INSTALLED = "not_installed"
    DOWNLOADING = "downloading"
    OLLAMA_NOT_RUNNING = "ollama_not_running"


@dataclass
class OllamaModel:
    model_id: str
    name: str
    size_gb: float
    specialty: str
    parameters: str  # e.g., "7B", "70B"

    # Recommended uses
    recommended_for: list[str]
    not_recommended_for: list[str]


# Pre-configured models for SupremeAI
RECOMMENDED_OLLAMA_MODELS = [
    OllamaModel(
        model_id="llama3.1:8b",
        name="Llama 3.1 8B",
        size_gb=4.7,
        specialty="General purpose chat & reasoning",
        parameters="8B",
        recommended_for=["chat", "reasoning", "analysis", "general"],
        not_recommended_for=["complex coding", "math proofs"],
    ),
    OllamaModel(
        model_id="llama3.1:70b",
        name="Llama 3.1 70B",
        size_gb=40,
        specialty="Complex reasoning & coding",
        parameters="70B",
        recommended_for=["coding", "reasoning", "analysis", "complex tasks"],
        not_recommended_for=[],  # Good for everything (but needs more RAM)
    ),
    OllamaModel(
        model_id="codellama:13b",
        name="Code Llama 13B",
        size_gb=7.5,
        specialty="Code generation & explanation",
        parameters="13B",
        recommended_for=["code_generation", "code_review", "debugging"],
        not_recommended_for=["chat", "creative writing"],
    ),
    OllamaModel(
        model_id="mistral:7b",
        name="Mistral 7B",
        size_gb=4.2,
        specialty="Balanced performance",
        parameters="7B",
        recommended_for=["general", "chat", "quick tasks"],
        not_recommended_for=["complex reasoning"],
    ),
    OllamaModel(
        model_id="nomic-embed-text",
        name="Nomic Embed Text",
        size_gb=0.27,
        specialty="Text embeddings",
        parameters="small",
        recommended_for=["embedding", "semantic search"],
        not_recommended_for=["generation"],
    ),
]


class OllamaFallback:
    """
    Ollama-based local fallback
    Ensures AI functionality even without ANY external APIs
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",  # is_local()
        auto_install_models: bool = True,
        preferred_model: str = "llama3.1:8b",
    ):
        self.base_url = ollama_base_url
        self.auto_install = auto_install_models
        self.preferred_model = preferred_model
        self._available_models: list[str] = []
        self._is_running = False
        self._client: httpx.AsyncClient | None = None

    async def initialize(self):
        """Initialize Ollama fallback system"""
        # Block initialization in cloud environments to prevent RAM exhaustion and crashes
        from core.config import settings

        if getattr(settings, "env", getattr(settings, "ENV", "local")).lower() != "local":
            logger.debug("☁️ Cloud environment detected. Disabling Ollama local fallback.")
            self._is_running = False
            self.available_models = []
            return

        logger.debug("🏠 Initializing Local Fallback (Ollama)...")

        # Check if Ollama is running
        self._is_running = await self._check_ollama_running()

        if not self._is_running:
            logger.debug("Ollama not running. Attempting to start...")
            started = await self._start_ollama()
            if not started:
                logger.debug("Could not start Ollama. Local fallback unavailable.")
                return False

        # Create HTTP client
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

        # Check available models
        await self._refresh_available_models()

        # Install recommended models if needed
        if self.auto_install:
            await self._ensure_models_installed([self.preferred_model])

        logger.debug(f"Local Fallback Ready! Available models: {self._available_models}")
        return True

    async def _check_ollama_running(self) -> bool:
        """Check if Ollama server is running"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception:
            return False

    async def _start_ollama(self) -> bool:
        """Attempt to start Ollama server"""
        try:
            # Try starting ollama serve (works on Linux/Mac)
            subprocess.Popen(["ollama", "serve"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            # Wait for it to start
            await asyncio.sleep(3)

            return await self._check_ollama_running()
        except FileNotFoundError:
            logger.debug("Ollama not installed. Visit https://ollama.ai to install.")
            return False
        except Exception as e:
            logger.debug(f"Failed to start Ollama: {e}")
            return False

    async def _refresh_available_models(self):
        """List installed models"""
        try:
            response = await self._client.get("/api/tags")
            if response.status_code == 200:
                data = response.json()
                self._available_models = [m["model"] for m in data.get("models", [])]
        except Exception as e:
            logger.debug(f"Failed to list Ollama models: {e}")

    async def _ensure_models_installed(self, model_ids: list[str]):
        """Ensure specified models are installed"""
        for model_id in model_ids:
            if model_id not in self._available_models:
                logger.debug(f"📦 Installing Ollama model: {model_id}")
                try:
                    # Pull model (this can take a while for large models)
                    response = await self._client.post(
                        "/api/pull", json={"name": model_id, "stream": False}
                    )

                    if response.status_code == 200:
                        self._available_models.append(model_id)
                        logger.debug(f"Model {model_id} installed")
                    else:
                        logger.debug(f"Failed to install {model_id}")

                except Exception as e:
                    logger.debug(f"Error installing {model_id}: {e}")

    async def is_available(self) -> bool:
        """Check if local fallback is ready"""
        return self._is_running and len(self._available_models) > 0

    async def generate(
        self, prompt: str, model: str | None = None, system_prompt: str | None = None, **kwargs
    ) -> dict:
        """
        Generate text using local Ollama model
        This NEVER fails due to external issues!
        """
        if not self._client:
            return {
                "success": False,
                "error": "Ollama client not initialized",
                "fallback_used": True,
            }

        # Select model
        selected_model = model or self.preferred_model

        # If preferred model not available, pick another
        if selected_model not in self._available_models:
            if self._available_models:
                selected_model = self._available_models[0]
            else:
                return {
                    "success": False,
                    "error": "No Ollama models available",
                    "fallback_used": True,
                }

        # Build request payload
        payload = {
            "model": selected_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", 0.7),
                "top_p": kwargs.get("top_p", 0.9),
                "num_predict": kwargs.get("max_tokens", 2048),
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            start_time = asyncio.get_event_loop().time()

            response = await self._client.post("/api/generate", json=payload)
            latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()

                return {
                    "success": True,
                    "text": data.get("response", ""),
                    "model": selected_model,
                    "latency_ms": latency_ms,
                    "done_reason": data.get("done_reason"),
                    "fallback_used": True,
                    "provider": "ollama-local",
                }
            else:
                return {
                    "success": False,
                    "error": f"Ollama API error: {response.status_code}",
                    "fallback_used": True,
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Ollama generation error: {str(e)}",
                "fallback_used": True,
            }

    async def embed(self, text: str, model: str = "nomic-embed-text") -> list:
        """Generate embeddings locally"""
        if not self._client:
            raise RuntimeError("Ollama client not initialized")

        # Ensure embedding model is available
        if model not in self._available_models:
            await self._ensure_models_installed([model])

        response = await self._client.post("/api/embeddings", json={"model": model, "prompt": text})

        if response.status_code == 200:
            data = response.json()
            return data.get("embedding", [])
        else:
            raise Exception(f"Embedding failed: {response.text}")

    def get_best_model_for_task(self, task_type: str) -> str | None:
        """Recommend best local model for a given task type"""
        for model in RECOMMENDED_OLLAMA_MODELS:
            if task_type in model.recommended_for and model.model_id in self._available_models:
                return model.model_id

        # Fallback to any available model
        return self._available_models[0] if self._available_models else None

    def get_status(self) -> dict:
        """Get status of local fallback system"""
        return {
            "is_running": self._is_running,
            "available_models": self._available_models,
            "preferred_model": self.preferred_model,
            "can_generate": len([m for m in self._available_models if "embed" not in m]) > 0,
            "can_embed": any("embed" in m for m in self._available_models),
            "recommended_models": [
                {
                    "id": m.model_id,
                    "name": m.name,
                    "installed": m.model_id in self._available_models,
                }
                for m in RECOMMENDED_OLLAMA_MODELS
            ],
        }
