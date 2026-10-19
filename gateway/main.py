"""SupremeAI Gateway — unified provider gateway (issue #336).

FastAPI/Starlette implementation of api-schemas/gateway.openapi.yaml:

- ``GET /health`` + ``GET /healthz`` — credential-free probes (OpenAPI security: [])
- ``GET /v1/models`` — enabled models from the routing policy (scope ``models``)
- ``POST /v1/chat/completions`` — OpenAI-compatible completions (scope ``chat``);
  ``stream: true`` relays Server-Sent Events with ``event:``/``data:`` framing
  (docs/MCP_CONNECT.md §3) and the ``data: [DONE]`` terminal sentinel
- Sliding-window rate limiting → standardized JSON error contract on
  429/503 with ``X-RateLimit-*`` + ``Retry-After`` headers (AC2)
- Provider failover via gateway/provider_chain.py — exhaustion → 502 with a
  REDACTED transition ledger (zero silent fallback, provider names visible,
  keys NEVER — OpenAPI §ChatCompletionResponse model description)

Wire honesty: usage is echoed only when the provider reported it; ``model``
names the endpoint that ACTUALLY served the request.

App factory (``create_app``) keeps every dependency injectable — the pytest
suite drives it fully offline via fastapi.testclient.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .config import GatewayConfig
from .provider_chain import (
    AttemptFn,
    AttemptResult,
    ProviderChainExhausted,
    _default_attempt,
    execute_chain,
)
from .rate_limit import SlidingWindowLimiter

GATEWAY_VERSION = "1.0.0"

# --- standardized JSON error contract (AC2) --------------------------------


def error_response(
    status: int,
    *,
    err_type: str,
    code: str,
    message: str,
    param: str | None = None,
    headers: dict[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "error": {"message": message, "type": err_type, "param": param, "code": code}
    }
    if extra:
        payload.update(extra)
    return JSONResponse(status_code=status, content=payload, headers=headers or {})


def _redact_ledger(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep provider/model/outcome/status; drop anything key-shaped."""
    safe = {"index", "provider", "model", "outcome", "status", "latency_ms", "detail"}
    return [{k: v for k, v in entry.items() if k in safe} for entry in ledger]


# --- auth -------------------------------------------------------------------


def authenticate(request: Request, config: GatewayConfig) -> JSONResponse | None:
    """X-SupremeAI-Key → 401 (missing/unknown) or 403 (scope) — default-deny."""
    key = request.headers.get("x-supremeai-key")
    if not key:
        return error_response(
            401,
            err_type="authentication_error",
            code="missing_api_key",
            message="Missing X-SupremeAI-Key header. One SUPREMEAI_API_KEY, provider-agnostic responses.",
        )
    record = config.api_keys.get(key)
    if record is None:
        return error_response(
            401,
            err_type="authentication_error",
            code="invalid_api_key",
            message="Unknown SUPREMEAI_API_KEY — credential invalid or revoked.",
        )
    request.state.key_record = record
    return None


def require_scope(request: Request, scope: str) -> JSONResponse | None:
    record = getattr(request.state, "key_record", None)
    if record is None or scope not in record.scopes:
        return error_response(
            403,
            err_type="permission_error",
            code="insufficient_scope",
            message=f"Key lacks required scope '{scope}'.",
        )
    return None


# --- rate limiting (AC2) ----------------------------------------------------


def rate_limit_headers(
    response: Response, limiter: SlidingWindowLimiter, decision
) -> None:
    response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
    response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    response.headers["X-RateLimit-Reset"] = str(decision.reset_epoch)


async def check_rate_limit(request: Request, limiter: SlidingWindowLimiter):
    """Per-key sliding window (IP fallback); returns the full decision."""
    key_id = request.headers.get("x-supremeai-key") or (
        request.client.host if request.client else "anonymous"
    )
    return await limiter.check(key_id)


def build_429(limiter: SlidingWindowLimiter, decision) -> JSONResponse:
    """Standardized JSON error contract for a rejected request (AC2)."""
    return error_response(
        429,
        err_type="rate_limit_error",
        code="rate_limit_exceeded",
        message=(
            f"Rate limit exceeded: {limiter.max_requests} requests per "
            f"{limiter.window_s}s window. Honor Retry-After; never hot-loop."
        ),
        headers={
            "Retry-After": str(decision.retry_after_s or 1),
            "X-RateLimit-Limit": str(limiter.max_requests),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(decision.reset_epoch),
        },
    )


# --- SSE framing (AC1) ------------------------------------------------------

SSE_CHUNK_EVENT = "chat.completion.chunk"
SSE_ERROR_EVENT = "error"
SSE_DONE_EVENT = "done"


def sse_frame(event: str, data: str) -> str:
    """One SSE frame per docs/MCP_CONNECT.md §3 (event:/data: lines, blank-line terminator)."""
    return f"event: {event}\ndata: {data}\n\n"


def openai_chunk(
    completion_id: str,
    created: int,
    model: str,
    delta: dict[str, Any] | None,
    finish_reason: str | None,
) -> str:
    return json.dumps(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {"index": 0, "delta": delta or {}, "finish_reason": finish_reason}
            ],
        }
    )


async def relay_stream(
    chain,
    payload: bytes,
    completion_id: str,
    stream_fn,
) -> AsyncIterator[str]:
    """Relay provider deltas as SSE; fail over ONLY before the first chunk.

    Once chunks flow, a provider failure becomes an honest ``event: error``
    frame (restarting mid-stream would duplicate output — silent-fabrication
    is banned). Terminal frames are ``event: done`` + ``data: [DONE]``.
    """
    created = int(time.time())
    served_by: str | None = None
    for endpoint in chain:
        opened = False
        try:
            async for event in stream_fn(endpoint, payload):
                if event["type"] == "chunk":
                    if not opened:
                        opened = True
                        served_by = f"{endpoint.provider}/{endpoint.model}"
                    yield sse_frame(
                        SSE_CHUNK_EVENT,
                        openai_chunk(
                            completion_id,
                            created,
                            served_by,
                            event.get("delta"),
                            event.get("finish_reason"),
                        ),
                    )
                elif event["type"] == "error":
                    if not opened:
                        # pre-first-chunk provider failure → failover, no wire noise
                        break
                    yield sse_frame(
                        SSE_ERROR_EVENT,
                        json.dumps(
                            {
                                "error": {
                                    "message": str(
                                        event.get("message", "provider stream failed")
                                    ),
                                    "type": "api_error",
                                    "param": None,
                                    "code": "provider_stream_error",
                                    "served_by": served_by,
                                }
                            }
                        ),
                    )
                    return
            if opened:
                # clean provider EOF → terminal
                yield sse_frame(SSE_DONE_EVENT, "[DONE]")
                return
            continue  # provider failed before any chunk → next endpoint
        except Exception as exc:
            if not opened:
                continue  # pre-first-chunk failure → failover to next endpoint
            yield sse_frame(
                SSE_ERROR_EVENT,
                json.dumps(
                    {
                        "error": {
                            "message": f"provider stream interrupted: {exc}"[:300],
                            "type": "api_error",
                            "param": None,
                            "code": "provider_stream_interrupted",
                            "served_by": served_by,
                        }
                    }
                ),
            )
            return
    # exhausted before any chunk
    yield sse_frame(
        SSE_ERROR_EVENT,
        json.dumps(
            {
                "error": {
                    "message": "all providers in the chain failed before streaming began",
                    "type": "api_error",
                    "param": None,
                    "code": "chain_exhausted",
                }
            }
        ),
    )
    yield sse_frame(SSE_DONE_EVENT, "[DONE]")


def parse_completion_response(result: AttemptResult) -> dict[str, Any]:
    """Parse a provider completion body honestly (no fabricated usage)."""
    try:
        body = json.loads(result.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("provider returned a non-JSON completion body") from None
    choices = body.get("choices") or []
    if not choices:
        raise ValueError("provider completion body has no choices")
    return body


# --- app factory ------------------------------------------------------------


def create_app(
    config: GatewayConfig,
    *,
    limiter: SlidingWindowLimiter | None = None,
    attempt_fn: AttemptFn | None = None,
    stream_fn=None,
    stealth_webhook_fn=None,
    memory_store=None,
) -> FastAPI:
    """Build the gateway. Every collaborator is injectable for offline tests."""
    limiter = limiter or SlidingWindowLimiter(
        config.rate_limit_window_s, config.rate_limit_max_requests
    )
    if memory_store is None:
        from .memory import MemoryStore

        memory_store = MemoryStore()
    if stealth_webhook_fn is None:
        from .stealth_webhook import forward_stealth_webhook as _fwd

        async def stealth_webhook_fn(url, secret, body, timeout=10.0):
            return await _fwd(url, secret, body, timeout)

    app = FastAPI(
        title="SupremeAI API", version=GATEWAY_VERSION, docs_url=None, redoc_url=None
    )

    # ---- health (no auth, OpenAPI security: []) ----
    @app.get("/health")
    @app.get("/healthz")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "supremeai-gateway",
            "version": GATEWAY_VERSION,
            "chains": sorted(config.chains),
        }

    # ---- /v1/models ----
    @app.get("/v1/models")
    async def list_models(request: Request) -> Response:
        if (err := authenticate(request, config)) is not None:
            return err
        if (err := await gate(request, "models")) is not None:
            return err
        seen: dict[str, dict[str, str]] = {}
        for chain in config.chains.values():
            for endpoint in chain:
                seen.setdefault(
                    endpoint.model,
                    {
                        "id": endpoint.model,
                        "object": "model",
                        "owned_by": "supremeai",
                    },
                )
        return attach_rate_headers(
            request,
            JSONResponse(
                {"object": "list", "data": sorted(seen.values(), key=lambda m: m["id"])}
            ),
        )

    def attach_rate_headers(request: Request, response: Response) -> Response:
        """Success responses carry the standardized X-RateLimit-* contract."""
        decision = getattr(request.state, "rate_decision", None)
        if decision is not None:
            response.headers["X-RateLimit-Limit"] = str(limiter.max_requests)
            response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
            response.headers["X-RateLimit-Reset"] = str(decision.reset_epoch)
        return response

    async def gate(request: Request, scope: str) -> JSONResponse | None:
        """Shared per-request gate: rate limit first-class, scope pinned."""
        decision = await check_rate_limit(request, limiter)
        if not decision.allowed:
            return build_429(limiter, decision)
        request.state.rate_decision = decision  # per-request, no shared-state race
        return require_scope(request, scope)

    # ---- /v1/chat/completions ----
    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        if (err := authenticate(request, config)) is not None:
            return err
        if (err := await gate(request, "chat")) is not None:
            return err

        try:
            body = await request.json()
        except Exception:
            return error_response(
                400,
                err_type="invalid_request_error",
                code="malformed_json",
                message="Request body is not valid JSON.",
            )
        messages = body.get("messages") if isinstance(body, dict) else None
        if not isinstance(messages, list) or not messages:
            return error_response(
                400,
                err_type="invalid_request_error",
                code="missing_messages",
                message="'messages' must be a non-empty array (OpenAPI ChatCompletionRequest).",
            )
        model = body.get("model", "auto")
        wants_stream = bool(body.get("stream", False))

        try:
            chain = config.chain_for(model if isinstance(model, str) else "auto")
        except Exception:
            return error_response(
                400,
                err_type="invalid_request_error",
                code="unknown_model",
                message=f"No routing chain configured for model '{model}'.",
            )

        payload = json.dumps({"messages": messages, "stream": wants_stream}).encode()
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"

        if wants_stream:
            if stream_fn is None:
                # Default stdlib transport relays the non-stream completion as
                # a single chunk — honest, no fabricated deltas.
                async def default_stream(endpoint, pl):
                    res = await (attempt_fn or _default_attempt)(endpoint, pl)
                    if res.status >= 400:
                        yield {
                            "type": "error",
                            "status": res.status,
                            "message": f"provider HTTP {res.status}",
                        }
                        return
                    try:
                        parsed = parse_completion_response(res)
                    except ValueError as exc:
                        yield {
                            "type": "error",
                            "status": res.status,
                            "message": str(exc),
                        }
                        return
                    content = (parsed["choices"][0].get("message") or {}).get(
                        "content", ""
                    )
                    yield {
                        "type": "chunk",
                        "delta": {"role": "assistant", "content": content},
                        "finish_reason": None,
                    }
                    yield {"type": "chunk", "delta": {}, "finish_reason": "stop"}

                relay = default_stream
            else:
                relay = stream_fn
            return StreamingResponse(
                relay_stream(chain, payload, completion_id, relay),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                },
            )

        result = await execute_chain(chain, payload, attempt_fn=attempt_fn)
        served_model = f"{result.endpoint.provider}/{result.endpoint.model}"
        try:
            parsed = parse_completion_response(result)
        except ValueError as exc:
            return error_response(
                502,
                err_type="api_error",
                code="provider_malformed_response",
                message=str(exc),
            )
        usage = parsed.get("usage")  # honesty: echo ONLY if provider reported it
        out: dict[str, Any] = {
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": served_model,
            "choices": parsed["choices"],
        }
        if usage is not None:
            out["usage"] = usage
        return attach_rate_headers(request, JSONResponse(out))

    # ---- provider exhaustion → 502 with redacted ledger ----
    # ---- /v1/consensus : parallel Priority-1 (stealth web) + Priority-2 (API squad) ----
    @app.post("/v1/consensus")
    async def multi_model_consensus(request: Request) -> Response:
        if (err := authenticate(request, config)) is not None:
            return err
        if (err := await gate(request, "chat")) is not None:
            return err
        try:
            body = await request.json()
        except Exception:
            return error_response(
                400,
                err_type="invalid_request_error",
                code="malformed_json",
                message="Request body is not valid JSON.",
            )
        if not isinstance(body, dict):
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_body",
                message="Request body must be a JSON object.",
            )

        import os as _os

        stealth_url = _os.environ.get("STEALTH_WEBHOOK_URL", "")
        stealth_secret = _os.environ.get("STEALTH_WEBHOOK_SECRET")
        stealth_timeout = float(_os.environ.get("STEALTH_WEBHOOK_TIMEOUT", "10"))
        payload = json.dumps(body).encode()

        async def run_provider_slot(provider_name: str):
            try:
                chain = config.chain_for("auto")
            except Exception as exc:
                return {"provider": provider_name, "status": 503, "error": str(exc)}
            endpoint = None
            for ep in chain:
                if ep.provider == provider_name:
                    endpoint = ep
                    break
            if endpoint is None:
                return {
                    "provider": provider_name,
                    "status": 503,
                    "error": "no endpoint configured for provider",
                }
            try:
                res = await (attempt_fn or _default_attempt)(endpoint, payload)
            except Exception as exc:
                return {"provider": provider_name, "status": 0, "error": str(exc)[:200]}
            parsed = None
            try:
                parsed = json.loads(res.body) if res.body else None
            except Exception:
                parsed = None
            return {
                "provider": provider_name,
                "slot": f"{endpoint.provider}/{endpoint.model}",
                "status": res.status,
                "response": parsed,
            }

        tasks = []
        if stealth_url:

            async def _stealth():
                status, parsed, latency = await stealth_webhook_fn(
                    stealth_url, stealth_secret, payload, stealth_timeout
                )
                return {
                    "provider": "stealth-web",
                    "status": status,
                    "latency_ms": latency,
                    "response": parsed,
                }

            tasks.append(_stealth())
        tasks.append(run_provider_slot("groq"))
        tasks.append(run_provider_slot("gemini"))

        import asyncio as _asyncio

        results = await _asyncio.gather(*tasks, return_exceptions=True)
        safe = []
        for r in results:
            if isinstance(r, Exception):
                safe.append({"provider": "unknown", "status": 0, "error": str(r)[:200]})
            else:
                safe.append(r)
        return attach_rate_headers(
            request,
            JSONResponse(
                {
                    "status": "success",
                    "timestamp": int(time.time()),
                    "consensus_count": len(
                        [
                            r
                            for r in safe
                            if not (isinstance(r, dict) and r.get("status", 0) >= 400)
                        ]
                    ),
                    "responses": safe,
                }
            ),
        )

    # ---- /v1/memory/store + /v1/memory/search (P4 sidecar) ----
    @app.post("/v1/memory/store")
    async def memory_store_endpoint(request: Request) -> Response:
        if (err := authenticate(request, config)) is not None:
            return err
        decision = await check_rate_limit(request, limiter)
        if not decision.allowed:
            return build_429(limiter, decision)
        request.state.rate_decision = decision
        try:
            body = await request.json()
        except Exception:
            return error_response(
                400,
                err_type="invalid_request_error",
                code="malformed_json",
                message="Request body is not valid JSON.",
            )
        if not isinstance(body, dict):
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_body",
                message="Request body must be a JSON object.",
            )
        text = body.get("text")
        if not isinstance(text, str) or not text.strip():
            return error_response(
                400,
                err_type="invalid_request_error",
                code="missing_text",
                message="'text' must be a non-empty string.",
            )
        namespace = body.get("namespace", "default")
        if not isinstance(namespace, str):
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_namespace",
                message="'namespace' must be a string.",
            )
        item_id = body.get("id")
        if item_id is not None and not isinstance(item_id, str):
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_id",
                message="'id' must be a string.",
            )
        metadata = body.get("metadata", {})
        if not isinstance(metadata, dict):
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_metadata",
                message="'metadata' must be an object.",
            )
        item = memory_store.store(
            text=text, namespace=namespace, item_id=item_id, metadata=metadata
        )
        return attach_rate_headers(
            request,
            JSONResponse(
                {
                    "status": "stored",
                    "id": item.id,
                    "namespace": item.namespace,
                    "created": item.created,
                }
            ),
        )

    @app.post("/v1/memory/search")
    async def memory_search_endpoint(request: Request) -> Response:
        if (err := authenticate(request, config)) is not None:
            return err
        decision = await check_rate_limit(request, limiter)
        if not decision.allowed:
            return build_429(limiter, decision)
        request.state.rate_decision = decision
        try:
            body = await request.json()
        except Exception:
            return error_response(
                400,
                err_type="invalid_request_error",
                code="malformed_json",
                message="Request body is not valid JSON.",
            )
        if not isinstance(body, dict):
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_body",
                message="Request body must be a JSON object.",
            )
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            return error_response(
                400,
                err_type="invalid_request_error",
                code="missing_query",
                message="'query' must be a non-empty string.",
            )
        top_k = body.get("top_k", 5)
        if (
            not isinstance(top_k, int)
            or isinstance(top_k, bool)
            or top_k < 1
            or top_k > 256
        ):
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_top_k",
                message="'top_k' must be an integer in [1,256].",
            )
        namespace = body.get("namespace")
        if namespace is not None and not isinstance(namespace, str):
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_namespace",
                message="'namespace' must be a string.",
            )
        threshold = body.get("score_threshold", 0.0)
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_threshold",
                message="'score_threshold' must be a number.",
            )
        hits = memory_store.search(
            query=query, top_k=top_k, namespace=namespace, threshold=float(threshold)
        )
        return attach_rate_headers(
            request,
            JSONResponse(
                {
                    "status": "ok",
                    "count": len(hits),
                    "hits": hits,
                }
            ),
        )

    @app.get("/v1/memory/search")
    async def memory_search_get(request: Request) -> Response:
        if (err := authenticate(request, config)) is not None:
            return err
        decision = await check_rate_limit(request, limiter)
        if not decision.allowed:
            return build_429(limiter, decision)
        request.state.rate_decision = decision
        query = request.query_params.get("q") or request.query_params.get("query")
        if not query:
            return error_response(
                400,
                err_type="invalid_request_error",
                code="missing_query",
                message="query param 'q' or 'query' required.",
            )
        try:
            top_k = int(request.query_params.get("top_k", "5"))
        except ValueError:
            return error_response(
                400,
                err_type="invalid_request_error",
                code="invalid_top_k",
                message="'top_k' must be an integer.",
            )
        namespace = request.query_params.get("namespace")
        hits = memory_store.search(query=query, top_k=top_k, namespace=namespace)
        return attach_rate_headers(
            request, JSONResponse({"status": "ok", "count": len(hits), "hits": hits})
        )

    @app.exception_handler(ProviderChainExhausted)
    async def chain_exhausted_handler(request: Request, exc: ProviderChainExhausted):
        return error_response(
            502,
            err_type="api_error",
            code="provider_chain_exhausted",
            message=str(exc),
            extra={"providers_tried": _redact_ledger(exc.ledger)},
        )

    return app


async def _noop_attempt(endpoint, payload) -> AttemptResult:  # pragma: no cover
    raise RuntimeError("no provider transport configured")
