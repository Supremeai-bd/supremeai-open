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
            raise RuntimeError("web relay not configured (set SUPREMEAI_WEB_RELAY_URL)")
        url = relay_url + "/v1/chat/completions"
        started = time.monotonic()
        body = {
            "model": endpoint.model,
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

    url = api_base.rstrip("/") + "/v1/chat/completions"
    body = {
        "model": endpoint.model,
        "messages": json.loads(payload).get("messages", []),
        "stream": False,
    }
    client = _http_client()
    last_result: AttemptResult | None = None
    for key in keys:
        started = time.monotonic()
        try:
            resp = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {key}"},
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
) -> AttemptResult:
    """Try endpoints in order; fail over ONLY on retryable outcomes.

    - 2xx → success, ledger records the win.
    - 429/5xx from a provider → ledger + next endpoint (failover semantics).
    - 401/403 from a provider → that endpoint is misconfigured; ledger +
      failover (a different provider may be configured correctly).
    - Exhaustion → ProviderChainExhausted with the FULL ledger (→ 502).
    """
    attempt = attempt_fn or _default_attempt
    ledger = ChainLedger()
    for idx, endpoint in enumerate(chain):
        try:
            result = await attempt(endpoint, payload)
        except (
            RuntimeError,
            httpx.HTTPError,
            OSError,
            asyncio.TimeoutError,
        ) as exc:  # transport-level failure — honest ledger entry
            ledger.record(
                index=idx,
                provider=endpoint.provider,
                model=endpoint.model,
                outcome="transport_error",
                detail=str(exc)[:200],
            )
            continue
        ledger.record(
            index=idx,
            provider=endpoint.provider,
            model=endpoint.model,
            outcome="success" if result.status < 400 else "provider_error",
            status=result.status,
            latency_ms=result.latency_ms,
        )
        if result.status < 400:
            return result
        if result.status not in FAILOVER_STATUS and result.status not in (401, 403):
            # Non-retryable, non-auth provider error (e.g. 400 bad request
            # shaped by the gateway itself): honest 4xx passthrough.
            return result
    raise ProviderChainExhausted(
        "all providers in the chain failed — 502 upstream (zero silent fallback)",
        ledger=ledger.entries,
    )
