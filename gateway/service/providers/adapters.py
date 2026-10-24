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

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlsplit
import httpx

logger = logging.getLogger("supremeai.adapters")

# One-shot config-defect warnings: keyed by defect signature so a hot request
# path never spams the log, but every distinct misconfiguration surfaces loudly
# exactly once per process (DNS ENOTFOUND storms are otherwise undiagnosable).
_stealth_warned: set = set()


def _mask_host(url: str) -> str:
    """Host-only view of a webhook URL, safe for logs and API error bodies.

    Strips scheme, userinfo, path and query (a relay URL may embed a token in
    its path/query — never echo those back to anonymous callers). The hostname
    itself is additionally truncated so even infra names stay partially masked:
    supremeai-worker.paykaribazaronline.workers.dev -> supr….workers.dev
    """
    try:
        host = urlsplit(url if "://" in url else "http://" + url).hostname or ""
    except ValueError:
        host = ""
    if not host:
        return "(unparseable-host)"
    labels = host.split(".")
    tail = ".".join(labels[-2:]) if len(labels) >= 2 else host
    return f"{host[:4]}…{tail}" if len(host) > 12 else host


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
    "perplexity": {
        "base_url": os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai"),
        "default_model": os.getenv("PERPLEXITY_MODEL", "sonar"),
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
    "perplexity": [
        "sonar",
        "sonar-pro",
        "sonar-reasoning",
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

    Config-defect hardening (root cause of the Oct-23 "relay offline" outage:
    STEALTH_WEBHOOK_URL held a value whose host failed DNS with [Errno -2]):
    - strip env-quoting accidents (value wrapped in "..." or '...')
    - collapse internal whitespace (never valid in a URL)
    - repair doubled scheme (https://https://… -> host parsed as "https" -> ENOTFOUND)
    - one-shot CRITICAL warnings for hosts that cannot possibly work:
      underscore in host (getaddrinfo fails) and workers.dev APEX
      (a worker URL is always <name>.<account-subdomain>.workers.dev — the apex
      does not resolve; verified by DNS probe during the outage diagnosis).
    """
    raw = url.strip()
    if not raw:
        return ""
    while len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("\"", "'"):
        raw = raw[1:-1].strip()
    if not raw:
        return ""
    if any(ch.isspace() for ch in raw):
        raw = "".join(raw.split())
    _low = raw.lower()
    for _dbl in ("https://https://", "https://http://", "http://https://", "http://http://"):
        if _low.startswith(_dbl):
            raw = raw.split("://", 1)[1]
            break
    full = raw if "://" in raw else "http://" + raw
    base = full.split("?", 1)[0].rstrip("/")
    query = ("?" + full.split("?", 1)[1]) if "?" in full else ""

    # One-shot diagnostics for values that will fail DNS regardless of network
    try:
        _host = urlsplit(base).hostname or ""
    except ValueError:
        _host = ""
    if _host:
        if "_" in _host and ("bad-host" + _host) not in _stealth_warned:
            _stealth_warned.add("bad-host" + _host)
            logger.critical(
                "STEALTH_WEBHOOK_URL host '%s' contains '_' — getaddrinfo() will fail "
                "with [Errno -2]. Fix the Infisical value (underscore hosts are not DNS-resolvable).",
                _mask_host(base),
            )
        _labels = _host.split(".")
        if _host.endswith(".workers.dev") and len(_labels) <= 3 and ("apex" + _host) not in _stealth_warned:
            _stealth_warned.add("apex" + _host)
            logger.critical(
                "STEALTH_WEBHOOK_URL host '%s' is the workers.dev APEX (does not resolve). "
                "A worker URL is always <worker-name>.<account-subdomain>.workers.dev.",
                _mask_host(base),
            )

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



@asynccontextmanager
async def _pooled_http_client(timeout: float = 28.0):
    """Yield the shared pooled httpx client (connection reuse)."""
    yield _get_stealth_client()

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
        headers["HTTP-Referer"] = (
            os.getenv("OPENROUTER_REFERER")
            or os.getenv("RENDER_EXTERNAL_URL")
            or "https://supremeai-api.onrender.com"
        )
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

    async with _pooled_http_client(timeout) as client:
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
    Priority-1 Stealth Forwarder (improved).

    Improvements vs previous version:
    - Reuses a pooled httpx.AsyncClient (keep-alive, HTTP/2) instead of opening
      a new connection per request -> much lower latency on repeated calls.
    - Fast-fail connect timeout (5s) so dead hosts surface quickly.
    - One automatic retry on transient connect/timeout errors.
    - Structured diagnostics: host, reason class, latency_ms in both logs and
      error bodies, plus latency_ms on success.
    """
    if not webhook_url:
        return 404, {"error": "Stealth webhook not configured"}

    target_url = normalize_stealth_url(webhook_url)

    # Self-loop protection
    self_url = os.getenv("RENDER_EXTERNAL_URL", "")
    if (self_url and self_url in target_url) or "supremeai-api" in target_url:
        logger.warning("Stealth webhook points to gateway itself; skipping loop.")
        return 400, {"error": "Stealth webhook target points to self (loop prevented)"}

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

    client = _get_stealth_client()
    started = time.monotonic()
    last_exc: Optional[Exception] = None
    for attempt in range(2):
        try:
            response = await client.post(target_url, json=payload, headers=headers, timeout=timeout)
            try:
                data = response.json()
            except Exception:  # noqa: BLE001
                data = response.text

            if isinstance(data, dict) and "reply" in data and "choices" not in data:
                data = {
                    "id": "chatcmpl-stealth-" + os.urandom(6).hex(),
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": payload.get("model", "stealth-priority1"),
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": str(data["reply"])},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                }
            latency = int((time.monotonic() - started) * 1000)
            logger.info("Stealth webhook OK status=%s latency=%sms attempt=%s", response.status_code, latency, attempt + 1)
            if isinstance(data, dict):
                data.setdefault("latency_ms", latency)
            return response.status_code, data
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            last_exc = exc
            if attempt == 0:
                await asyncio.sleep(0.2)
                continue
            break
        except httpx.RequestError as exc:
            last_exc = exc
            break

    latency = int((time.monotonic() - started) * 1000)
    exc = last_exc
    _exc_text = str(exc) if exc is not None else "unknown error"
    _host = _mask_host(target_url)
    if isinstance(exc, httpx.TimeoutException) or "timed out" in _exc_text.lower() or "timeout" in _exc_text.lower():
        _errno = "timeout"
    elif any(sig in _exc_text for sig in ("Name or service not known", "Temporary failure in name resolution", "No address associated", "nodename nor servname")):
        _errno = "dns"
    elif "Connection refused" in _exc_text:
        _errno = "refused"
    else:
        _errno = "connect"
    logger.warning(
        "Stealth webhook connection error for host=%s class=%s: %s (latency=%sms)",
        _host,
        _errno,
        _exc_text,
        latency,
    )
    body = {"error": f"Stealth webhook connection error for host {_host} ({_errno}): {_exc_text}", "host": _host, "reason": _errno, "latency_ms": latency}
    if _errno == "timeout":
        body["error"] = "Stealth webhook timed out"
        return 504, body
    return 502, body


# Shared pooled client helpers
_STEALTH_CLIENT: Optional[httpx.AsyncClient] = None


def _get_stealth_client() -> httpx.AsyncClient:
    global _STEALTH_CLIENT
    if _STEALTH_CLIENT is not None:
        try:
            if not _STEALTH_CLIENT.is_closed:
                return _STEALTH_CLIENT
        except AttributeError:
            _STEALTH_CLIENT = None
    try:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(28.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            http2=True,
        )
    except Exception:
        client = httpx.AsyncClient(
            timeout=httpx.Timeout(28.0, connect=5.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    # Only cache real clients (fakes used in tests lack is_closed).
    if hasattr(client, "is_closed"):
        _STEALTH_CLIENT = client
    return client


async def close_stealth_client() -> None:
    global _STEALTH_CLIENT
    if _STEALTH_CLIENT is not None and not _STEALTH_CLIENT.is_closed:
        await _STEALTH_CLIENT.aclose()
    _STEALTH_CLIENT = None
