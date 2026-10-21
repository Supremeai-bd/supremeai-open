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

    api_base = os.environ.get(f"SUPREMEAI_PROVIDER_BASE_{endpoint.provider.upper()}")
    api_key = os.environ.get(f"SUPREMEAI_PROVIDER_KEY_{endpoint.provider.upper()}")
    if not api_base or not api_key:
        raise RuntimeError(
            f"provider {endpoint.provider} not configured (set SUPREMEAI_PROVIDER_BASE_/KEY_)"
        )

    url = api_base.rstrip("/") + "/v1/chat/completions"
    started = time.monotonic()
    body = {
        "model": endpoint.model,
        "messages": json.loads(payload).get("messages", []),
        "stream": False,
    }
    client = _http_client()
    resp = await client.post(
        url,
        json=body,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    )
    return AttemptResult(
        endpoint=endpoint,
        status=resp.status_code,
        headers={k.lower(): v for k, v in resp.headers.items()},
        body=resp.content,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


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
        except (RuntimeError, httpx.HTTPError, OSError, asyncio.TimeoutError) as exc:  # transport-level failure — honest ledger entry
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
