# backend/core/llm/llm_gateway/http_client.py
"""Shared httpx connection-pool singleton + zero-leak SSE relay.

Task 4-a package split: code moved VERBATIM from core/llm/llm_gateway.py.
`_client` is THE single shared httpx.AsyncClient holder (kept in exactly this
one module and managed only by get_http_client/shutdown_http_client here).
"""

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from core.logging_config import logger

from ...config import settings  # Fixed import path - using relative import

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """
    বাংলা মন্তব্য: HTTP Client Connection Pool Singleton.
    App startup-এ একবার তৈরি করে limits/timeout সেট করে reuse করা হয়।
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.LLM_CONNECT_TIMEOUT,
                read=settings.LLM_READ_TIMEOUT,
                write=settings.LLM_WRITE_TIMEOUT,
                pool=settings.LLM_POOL_TIMEOUT,
            ),
            limits=httpx.Limits(
                max_connections=settings.LLM_MAX_CONNECTIONS,
                max_keepalive_connections=settings.LLM_MAX_KEEPALIVE,
            ),
        )
    return _client


async def shutdown_http_client() -> None:
    """বাংলা মন্তব্য: Connection Pool Clean Shutdown."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def stream_llm_response(
    request: Any,
    provider_url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> AsyncGenerator[str, None]:
    """
    Upstream provider থেকে Zero-Memory-Leak SSE streaming response প্রদান করে।
    request.is_disconnected() চেক করে অকাল ডিসকানেক্টে সকেট রিলিজ নিশ্চিত করে।
    """
    client = get_http_client()
    try:
        async with client.stream("POST", provider_url, json=payload, headers=headers) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if hasattr(request, "is_disconnected") and await request.is_disconnected():
                    logger.info("Client disconnected mid-stream, closing upstream connection.")
                    break
                if not line or not line.startswith("data:"):
                    continue
                data_str = line[len("data:") :].strip()
                if data_str == "[DONE]":
                    yield "data: [DONE]\n\n"
                    break
                yield f"data: {data_str}\n\n"
    except httpx.HTTPStatusError as e:
        logger.error(f"Upstream error {e.response.status_code}: {provider_url}")
        error_payload = json.dumps({"error": "upstream_error", "status": e.response.status_code})
        yield f"data: {error_payload}\n\n"
    except httpx.TimeoutException:
        logger.error(f"Timeout while streaming from {provider_url}")
        yield f"data: {json.dumps({'error': 'timeout'})}\n\n"
    except Exception as exc:
        logger.exception(f"Unexpected streaming error: {exc}")
        yield f"data: {json.dumps({'error': 'internal_stream_error'})}\n\n"
