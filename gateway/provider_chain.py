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
import ssl
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

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


async def _default_attempt(endpoint: Endpoint, payload: bytes) -> AttemptResult:
    """One honest HTTP/1.1 round-trip over stdlib asyncio streams.

    Provider credentials are injected by the operator via
    ``SUPREMEAI_PROVIDER_KEY_<PROVIDER>`` env vars — never logged, never in
    URLs (MCP_CONNECT §5 etiquette applies provider-side too).
    """
    import os

    api_base = os.environ.get(f"SUPREMEAI_PROVIDER_BASE_{endpoint.provider.upper()}")
    api_key = os.environ.get(f"SUPREMEAI_PROVIDER_KEY_{endpoint.provider.upper()}")
    if not api_base or not api_key:
        raise RuntimeError(
            f"provider {endpoint.provider} not configured (set SUPREMEAI_PROVIDER_BASE_/KEY_)"
        )

    url = api_base.rstrip("/") + "/v1/chat/completions"
    rest = url.split("://", 1)[1]
    host_port, _, path = rest.partition("/")
    host, _, port_s = host_port.partition(":")
    secure = url.startswith("https")
    port = int(port_s) if port_s else (443 if secure else 80)
    started = time.monotonic()
    if secure:
        opener = asyncio.open_connection(host, port, ssl=ssl.create_default_context())
    else:
        opener = asyncio.open_connection(host, port)
    reader, writer = await asyncio.wait_for(opener, timeout=30.0)
    try:
        body = json.dumps({
            "model": endpoint.model,
            "messages": json.loads(payload).get("messages", []),
            "stream": False,
        }).encode()
        head = (
            f"POST /{path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            "Content-Type: application/json\r\n"
            f"Authorization: Bearer {api_key}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(head.encode("latin-1") + body)
        await writer.drain()
        status_line = (await reader.readline()).decode("latin-1")
        status = int(status_line.split(" ")[1]) if len(status_line.split(" ")) > 1 else 0
        headers: dict[str, str] = {}
        while True:
            line = (await reader.readline()).decode("latin-1")
            if line in ("\r\n", "\n", ""):
                break
            k, _, v = line.partition(":")
            headers[k.strip().lower()] = v.strip()
        resp_body = b""
        if "content-length" in headers:
            resp_body = await reader.readexactly(int(headers["content-length"]))
        return AttemptResult(
            endpoint=endpoint,
            status=status,
            headers=headers,
            body=resp_body,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


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
    last: AttemptResult | None = None
    for idx, endpoint in enumerate(chain):
        try:
            result = await attempt(endpoint, payload)
        except Exception as exc:  # transport-level failure — honest ledger entry
            ledger.record(
                index=idx, provider=endpoint.provider, model=endpoint.model,
                outcome="transport_error", detail=str(exc)[:200],
            )
            last = None
            continue
        ledger.record(
            index=idx, provider=endpoint.provider, model=endpoint.model,
            outcome="success" if result.status < 400 else "provider_error",
            status=result.status, latency_ms=result.latency_ms,
        )
        if result.status < 400:
            return result
        last = result
        if result.status not in FAILOVER_STATUS and result.status not in (401, 403):
            # Non-retryable, non-auth provider error (e.g. 400 bad request
            # shaped by the gateway itself): honest 4xx passthrough.
            return result
    raise ProviderChainExhausted(
        "all providers in the chain failed — 502 upstream (zero silent fallback)",
        ledger=ledger.entries,
    )
