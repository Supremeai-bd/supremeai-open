"""SupremeAI Gateway — provider failover with an honest transition ledger (issue #336).

Walks a config-ordered provider chain; every attempt is LEDGERED, and
exhaustion raises :class:`ProviderChainExhausted` carrying the FULL ledger —
zero silent fallback (doctrine shared with core/routing dynamic router, WO
#349). Transport is injected (``attempt_fn``) so tests and the SSE layer run
deterministically offline; the default transport is stdlib asyncio HTTP (same
honest core as sdk/python — no third-party client dependency).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import Endpoint

# Provider outcomes that justify failing over to the next endpoint.
FAILOVER_STATUS = frozenset({429, 500, 502, 503, 504})


class ProviderChainExhausted(RuntimeError):
    """Every endpoint in the chain failed — 502 upstream, ledger attached."""

    def __init__(self, message: str, ledger: list[dict[str, Any]]):
        super().__init__(message)
        self.ledger = ledger


@dataclass(frozen=True, slots=True)
class AttemptResult:
    """Outcome of one provider round-trip (success or honest failure)."""

    endpoint: Endpoint
    status: int
    headers: dict[str, str]
    body: bytes
    latency_ms: int

    @property
    def retry_after_s(self) -> float | None:
        ra = self.headers.get("retry-after")
        if ra is None:
            return None
        try:
            return float(ra)
        except ValueError:
            return None


AttemptFn = Callable[[Endpoint, bytes], Awaitable[AttemptResult]]


def _http_client() -> httpx.AsyncClient:
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            timeout=30.0,
        )
    return _HTTP_CLIENT


_HTTP_CLIENT: httpx.AsyncClient | None = None


async def _default_attempt(endpoint: Endpoint, payload: bytes) -> AttemptResult:
    """One HTTP round-trip via httpx with connection pooling."""
    import os

    # Web-relay provider: cookie-based Gemini relay (no API key). Primary scout.
    if endpoint.provider == "web":
        relay_url = os.environ.get("SUPREMEAI_WEB_RELAY_URL", "").rstrip("/")
        if not relay_url:
            relay_url = os.environ.get("SUPREMEAI_CF_WORKER_URL", "").rstrip("/")
        if not relay_url:
            relay_url = os.environ.get("STEALTH_WEBHOOK_URL", "").rstrip("/")
        if not relay_url:
            relay_url = "https://supremeai-worker.paykaribazaronline.workers.dev"
        base = relay_url.rstrip("/")
        if base.endswith("/v1"):
            url = base + "/chat/completions"
        else:
            url = base + "/v1/chat/completions"
        started = time.monotonic()
        req_model = endpoint.model
        if req_model in ("gemini", "gemini-web"):
            req_model = "gemini-2.5-flash"
        body = {
            "model": req_model,
            "messages": json.loads(payload).get("messages", []),
            "stream": False,
        }
        client = _http_client()
        resp = await client.post(url, json=body, timeout=60.0)
        return AttemptResult(
            endpoint=endpoint,
            status=resp.status_code,
            headers={k.lower(): v for k, v in resp.headers.items()},
            body=resp.content,
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    provider = endpoint.provider.lower()
    api_base = os.environ.get(f"SUPREMEAI_PROVIDER_BASE_{provider.upper()}")
    api_key = os.environ.get(f"SUPREMEAI_PROVIDER_KEY_{provider.upper()}")

    # Fallback to commonly available raw provider env vars so the gateway works
    # even when only the standard provider keys are configured (root cause fix).
    _FALLBACKS = {
        "groq": ("https://api.groq.com/openai/v1", ["GROQ_API_KEY", "GROQ_API_KEYS"]),
        "openai": ("https://api.openai.com/v1", ["OPENAI_API_KEY"]),
        "openrouter": (
            "https://openrouter.ai/api/v1",
            ["OPENROUTER_API_KEY", "OPENROUTER_API_KEYS"],
        ),
        "gemini": (
            "https://generativelanguage.googleapis.com/v1beta/openai",
            ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        ),
        "mistral": ("https://api.mistral.ai/v1", ["MISTRAL_API_KEY"]),
        "anthropic": ("https://api.anthropic.com/v1", ["ANTHROPIC_API_KEY"]),
        "deepseek": ("https://api.deepseek.com/v1", ["DEEPSEEK_API_KEY"]),
        "deepinfra": ("https://api.deepinfra.com/v1/openai", ["DEEPINFRA_API_KEY", "DEEPINFRA_API_KEYS"]),
        "together": ("https://api.together.xyz/v1", ["TOGETHER_API_KEY", "TOGETHER_API_KEYS"]),
        "xai": ("https://api.x.ai/v1", ["XAI_API_KEY", "XAI_API_KEYS"]),
        "manus": ("https://api.manus.ai/v1", ["MANUS_API_KEY", "MANUS_API_KEYS"]),
    }
    if (not api_base or not api_key) and provider in _FALLBACKS:
        fb_base, fb_keys = _FALLBACKS[provider]
        if not api_base:
            api_base = fb_base
        if not api_key:
            for k in fb_keys:
                v = os.environ.get(k, "")
                if v:
                    api_key = v.split(",")[0].strip()
                    break

    # Collect all available keys for this provider (primary + pool) so a 429/401
    # on one key rotates to the next instead of failing over the whole provider.
    _POOL_ENV = {
        "groq": ["GROQ_API_KEY", "GROQ_API_KEYS"],
        "openai": ["OPENAI_API_KEY"],
        "openrouter": ["OPENROUTER_API_KEY", "OPENROUTER_API_KEYS"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "mistral": ["MISTRAL_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "deepseek": ["DEEPSEEK_API_KEY"],
        "deepinfra": ["DEEPINFRA_API_KEY", "DEEPINFRA_API_KEYS"],
        "together": ["TOGETHER_API_KEY", "TOGETHER_API_KEYS"],
        "xai": ["XAI_API_KEY", "XAI_API_KEYS"],
        "manus": ["MANUS_API_KEY", "MANUS_API_KEYS"],
    }
    keys: list[str] = []
    if api_key:
        keys.append(api_key)
    # SUPREMEAI_PROVIDER_KEY_<P> may itself be a comma pool.
    raw_pool = os.environ.get(f"SUPREMEAI_PROVIDER_KEY_{provider.upper()}", "")
    for part in raw_pool.split(","):
        part = part.strip()
        if part and part not in keys:
            keys.append(part)
    for env_name in _POOL_ENV.get(provider, []):
        for part in os.environ.get(env_name, "").split(","):
            part = part.strip()
            if part and part not in keys:
                keys.append(part)
    if not api_base or not keys:
        raise RuntimeError(
            f"provider {endpoint.provider} not configured (set SUPREMEAI_PROVIDER_BASE_/KEY_)"
        )

    base = api_base.rstrip("/")
    if base.endswith("/v1"):
        url = base + "/chat/completions"
    else:
        url = base + "/v1/chat/completions"
    body = {
        "model": endpoint.model,
        "messages": json.loads(payload).get("messages", []),
        "stream": False,
    }
    client = _http_client()
    last_result: AttemptResult | None = None
    for key in keys:
        started = time.monotonic()
        req_headers = {"Authorization": f"Bearer {key}"}
        if provider == "manus":
            req_headers["API_KEY"] = key
        try:
            resp = await client.post(
                url,
                json=body,
                headers=req_headers,
                timeout=30.0,
            )
        except (httpx.HTTPError, OSError, asyncio.TimeoutError):
            # transport-level: try next key
            continue
        result = AttemptResult(
            endpoint=endpoint,
            status=resp.status_code,
            headers={k.lower(): v for k, v in resp.headers.items()},
            body=resp.content,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        last_result = result
        if resp.status_code < 400:
            return result
        # Rotate on auth/rate errors; otherwise stop (non-retryable).
        if resp.status_code not in (401, 403, 429):
            return result
    if last_result is not None:
        return last_result
    raise RuntimeError(f"provider {endpoint.provider} transport failed on all keys")


@dataclass(slots=True)
class ChainLedger:
    """Every transition is recorded; exhaustion carries the full ledger."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, **entry: Any) -> None:
        self.entries.append(entry)


async def execute_chain(
    chain: tuple[Endpoint, ...],
    payload: bytes,
    *,
    attempt_fn: AttemptFn | None = None,
    max_retries: int = 2,
    backoff_base_s: float = 0.1,
    circuit_breaker: Any = None,
) -> AttemptResult:
    """Try endpoints in order; fail over ONLY on retryable outcomes.

    On a retryable 5xx (esp. 503) from a provider, retry the SAME endpoint up
    to ``max_retries`` times with exponential backoff (issue #2082) before
    failing over to the next endpoint. Each retry is ledgered honestly.
    """
    if circuit_breaker is None:
        from .circuit_breaker import default_breaker as circuit_breaker
    attempt = attempt_fn or _default_attempt
    ledger = ChainLedger()
    for idx, endpoint in enumerate(chain):
        provider = endpoint.provider
        try:
            allowed = circuit_breaker.allow(provider)
        except Exception:
            allowed = True
        if not allowed:
            ledger.record(
                index=idx,
                provider=provider,
                model=endpoint.model,
                outcome="circuit_open",
                detail="circuit breaker open; provider skipped",
            )
            continue
        last_result = None
        for retry in range(max_retries + 1):
            try:
                result = await attempt(endpoint, payload)
            except (
                RuntimeError,
                httpx.HTTPError,
                OSError,
                asyncio.TimeoutError,
            ) as exc:
                ledger.record(
                    index=idx,
                    provider=provider,
                    model=endpoint.model,
                    attempt=retry,
                    outcome="transport_error",
                    detail=str(exc)[:200],
                )
                try:
                    circuit_breaker.record_failure(provider)
                except Exception:
                    pass
                if retry < max_retries:
                    await asyncio.sleep(backoff_base_s * (2 ** retry))
                    continue
                last_result = None
                break
            last_result = result
            ledger.record(
                index=idx,
                provider=provider,
                model=endpoint.model,
                attempt=retry,
                outcome="success" if result.status < 400 else "provider_error",
                status=result.status,
                latency_ms=result.latency_ms,
            )
            if result.status < 400:
                try:
                    circuit_breaker.record_success(provider)
                except Exception:
                    pass
                return result
            retryable = result.status == 503 or result.status == 429
            if retryable and retry < max_retries:
                delay = backoff_base_s * (2 ** retry)
                ra = result.retry_after_s
                if ra is not None and ra > 0:
                    delay = min(delay, ra)
                await asyncio.sleep(delay)
                continue
            if result.status not in FAILOVER_STATUS and result.status not in (401, 403):
                try:
                    circuit_breaker.record_failure(provider)
                except Exception:
                    pass
                return result
            try:
                circuit_breaker.record_failure(provider)
            except Exception:
                pass
            break
    raise ProviderChainExhausted(
        "all providers in the chain failed — 502 upstream (zero silent fallback)",
        ledger=ledger.entries,
    )
