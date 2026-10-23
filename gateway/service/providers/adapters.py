"""
service/providers/adapters.py — Unified Provider Execution Layer.

All 6 providers are connected via their OpenAI-compatible HTTP surfaces:
- Gemini (Google Generative AI OpenAI-compat surface)
- Groq (High-speed Llama/Qwen models)
- OpenRouter (Aggregated catalog)
- OpenAI (Official OpenAI platform)
- Mistral (Mistral AI endpoints)
- Hugging Face (Inference Router)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple
import httpx

logger = logging.getLogger("supremeai.adapters")

PROVIDER_CONFIGS: Dict[str, Dict[str, Any]] = {
    "gemini": {
        "base_url": os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
        "default_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    },
    "groq": {
        "base_url": os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        "default_model": os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"),
    },
    "openrouter": {
        "base_url": os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        "default_model": os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free"),
    },
    "openai": {
        "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "default_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    },
    "mistral": {
        "base_url": os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1"),
        "default_model": os.getenv("MISTRAL_MODEL", "mistral-small-latest"),
    },
    "huggingface": {
        "base_url": os.getenv("HF_BASE_URL", "https://router.huggingface.co/hf-inference/v1"),
        "default_model": os.getenv("HF_MODEL", "meta-llama/Llama-3.2-3B-Instruct"),
    },
    "v0": {
        "base_url": os.getenv("V0_BASE_URL", "https://api.v0.dev/v1"),
        "default_model": os.getenv("V0_MODEL", "v0-web"),
    },
    "ghost_gemini": {
        "base_url": os.getenv("GHOST_TOWER_URL", "http://127.0.0.1:8788"),
        "default_model": "gemini-web",
    },
    "web_session": {
        "base_url": os.getenv("WEB_SESSION_URL", "http://127.0.0.1:8788"),
        "default_model": "web-session-auto",
    },
}

# Exhaustive zero-waste model cascades: if top model hits quota/limit (429) or is unavailable (404/400),
# the adapter seamlessly tries the next model in sequence without failing the client request.
PROVIDER_MODEL_CASCADES: Dict[str, list[str]] = {
    "groq": [
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "allam-2-7b",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-2.5-flash-lite",
        "gemini-2.5-pro",
        "gemini-1.5-flash-latest",
        "gemini-1.5-pro-latest",
        "gemini-2.0-flash",
    ],
    "openrouter": [
        "nvidia/nemotron-3.5-lightning:free",
        "cohere/north-mini-code:free",
        "dots-studio/dots-3-note-preview:free",
        "poolside/laguna-s-2.1:free",
        "liquid/lfm-2.5-2.6b:free",
        "meta-llama/llama-3.3-70b-instruct:free",
    ],
    "mistral": [
        "mistral-small-latest",
        "open-mistral-7b",
        "mistral-medium-latest",
    ],
    "openai": [
        "gpt-4o-mini",
        "gpt-4o",
    ],
    "v0": [
        "v0-web",
        "v0-preview",
    ],
}


def normalize_stealth_url(url: str) -> str:
    """
    Ensure the webhook URL targets the exact synchronous OpenAI-compatible endpoint
    (/v1/chat/completions) instead of base domains, /mcp, or /dispatch.
    """
    raw = url.strip()
    if not raw:
        return ""
    full = raw if "://" in raw else "http://" + raw
    base = full.split("?", 1)[0].rstrip("/")
    query = ("?" + full.split("?", 1)[1]) if "?" in full else ""

    # Strip incompatible non-chat suffixes
    if base.endswith(("/api/chat", "/chat", "/dispatch", "/mcp", "/webhook/telegram")):
        base = base.rsplit("/", 1)[0].rstrip("/")

    # Ensure path ends with /v1/chat/completions
    if not base.endswith("/v1/chat/completions"):
        if base.endswith("/v1"):
            base = base + "/chat/completions"
        else:
            base = base + "/v1/chat/completions"

    return base + query


async def forward_chat_completion(
    provider: str,
    api_key: str,
    payload: Dict[str, Any],
    timeout: float = 60.0
) -> Tuple[int, Dict[str, Any] | str]:
    """
    Forwards an OpenAI-format chat completion request to the chosen provider.
    Executes an in-flight model cascade: if the top model returns 429/404/400/503,
    it automatically attempts the remaining prioritized models before reporting error.
    Returns (status_code, parsed_json_or_text).
    """
    config = PROVIDER_CONFIGS.get(provider)
    if not config:
        return 400, {"error": f"Unknown provider: {provider}"}

    base_url = config["base_url"].rstrip("/")
    url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "SupremeAI-Gateway/2.0",
    }

    # OpenRouter requires optional referer/title headers
    if provider == "openrouter":
        headers["HTTP-Referer"] = "https://supremeai-api-ulw0.onrender.com"
        headers["X-Title"] = "SupremeAI Gateway"

    # Build prioritized candidate models list
    body = dict(payload)
    client_model = body.get("model", "auto")
    cascade = PROVIDER_MODEL_CASCADES.get(provider, [config["default_model"]])
    candidate_models: list[str] = []

    if client_model and client_model not in ("auto", "default", "") and not str(client_model).startswith("supremeai/"):
        candidate_models.append(str(client_model))

    for m in cascade:
        if m not in candidate_models:
            candidate_models.append(m)

    last_status = 500
    last_data: Any = {"error": f"No models available for provider {provider}"}

    async with httpx.AsyncClient(timeout=timeout) as client:
        for model_name in candidate_models:
            body["model"] = model_name
            try:
                response = await client.post(url, json=body, headers=headers)
                status_code = response.status_code
                try:
                    data = response.json()
                except Exception:  # noqa: BLE001
                    data = response.text

                # Success path (2xx)
                if 200 <= status_code < 300:
                    if isinstance(data, dict) and "model" not in data:
                        data["model"] = model_name
                    return status_code, data

                # Skip paid tiers if requested payment (402)
                if status_code == 402:
                    logger.warning(f"[{provider}] Model {model_name} requested payment (402); skipping paid tier.")
                    last_status, last_data = status_code, data
                    continue

                # Auto-downgrade on quota exhaustion, missing model slug, or temporary overload
                if status_code in (404, 400, 429, 503):
                    logger.warning(
                        f"[{provider}] Model {model_name} returned {status_code}; "
                        f"cascading to next available model..."
                    )
                    last_status, last_data = status_code, data
                    continue

                # For fatal authentication errors (401/403 on key), do not loop other models with same key
                last_status, last_data = status_code, data
                break

            except httpx.TimeoutException:
                logger.warning(f"[{provider}] Model {model_name} timed out after {timeout}s; trying next model...")
                last_status, last_data = 504, {"error": f"Provider {provider} model {model_name} timed out"}
                continue
            except httpx.RequestError as exc:
                return 502, {"error": f"Connection error to {provider}: {str(exc)}"}

    return last_status, last_data


async def forward_stealth_webhook(
    webhook_url: str,
    secret: Optional[str],
    payload: Dict[str, Any],
    timeout: float = 28.0,
) -> Tuple[int, Dict[str, Any] | str]:
    """
    Priority-1 Stealth Forwarder.
    Normalizes the webhook endpoint to /v1/chat/completions, sends OpenAI chat payload,
    and uses a 28.0s timeout for the stealth relay.
    """
    if not webhook_url:
        return 404, {"error": "Stealth webhook not configured"}

    target_url = normalize_stealth_url(webhook_url)

    # Self-loop protection: if STEALTH_WEBHOOK_URL points to gateway itself
    if "supremeai-api-ulw0.onrender.com" in target_url:
        logger.warning("Stealth webhook points to gateway itself; skipping loop.")
        return 400, {"error": "Stealth webhook target points to self (loop prevented)"}

    # If pointed to async worker without explicit permission
    if "supremeai-worker" in target_url and not os.getenv("ALLOW_WORKER_STEALTH"):
        logger.warning(f"Stealth webhook target ({target_url}) is async worker node (not chat completions).")
        return 405, {"error": "Configured stealth URL points to worker-node instead of chat completions relay"}

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SupremeAI-Stealth-Gateway/2.0",
    }
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
        headers["X-Stealth-Secret"] = secret
        headers["X-SupremeAI-Key"] = secret

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(target_url, json=payload, headers=headers)
            try:
                data = response.json()
            except Exception:  # noqa: BLE001
                data = response.text

            # If response is {"reply": "..."} or {"source": "webhook", "reply": "..."}, wrap in OpenAI format
            if isinstance(data, dict) and "reply" in data and "choices" not in data:
                data = {
                    "id": "chatcmpl-stealth-" + os.urandom(6).hex(),
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": payload.get("model", "stealth-priority1"),
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": str(data["reply"]),
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                }
            return response.status_code, data
        except httpx.TimeoutException:
            logger.warning(f"Stealth webhook timed out after {timeout}s")
            return 504, {"error": "Stealth webhook timed out"}
        except httpx.RequestError as exc:
            logger.warning(f"Stealth webhook connection error: {exc}")
            return 502, {"error": f"Stealth webhook connection error: {str(exc)}"}
