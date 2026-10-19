"""SupremeAI Unified Gateway clients (sync + async, stdlib only).

Both clients sign requests with a bearer key (argument or
``SUPREMEAI_API_KEY``), target the gateway base URL (argument or
``SUPREMEAI_GATEWAY_URL``), and retry transient 502/503/504 failures
with exponential backoff and full jitter.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
import urllib.error
import urllib.request
from collections.abc import AsyncIterator, Iterator
from typing import Any

from .errors import RETRYABLE_STATUSES, GatewayError
from .sse_listener import SSEListener, StreamEvent

USER_AGENT = "supremeai-sdk-python/0.1.0"


def _backoff_delay(attempt: int, floor: float) -> float:
    """Exponential backoff with full jitter."""
    return floor + random.random() * floor * (2**attempt)


class SupremeAIClient:
    """Synchronous gateway client built on urllib."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        max_retries: int = 3,
        timeout: float = 30.0,
        backoff_floor: float = 0.15,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        env = os.environ
        self.base_url = (base_url or env.get("SUPREMEAI_GATEWAY_URL") or "").rstrip("/")
        self.api_key = api_key or env.get("SUPREMEAI_API_KEY") or ""
        self.max_retries = max(1, max_retries)
        self.timeout = timeout
        self.backoff_floor = backoff_floor
        self.default_headers = dict(default_headers or {})

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        headers.update(self.default_headers)
        if extra:
            headers.update(extra)
        if self.api_key:
            headers["X-SupremeAI-Key"] = self.api_key
            headers["Authorization"] = "Bearer " + self.api_key
        return headers

    def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """Signed JSON request with retry on 502/503/504."""
        url = self.base_url + path
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        last_error: GatewayError | None = None
        for attempt in range(self.max_retries):
            if attempt:
                time.sleep(_backoff_delay(attempt - 1, self.backoff_floor))
            request = urllib.request.Request(url, data=body, method=method)
            for key, value in self._headers(headers).items():
                request.add_header(key, value)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                raw = exc.read() if hasattr(exc, "read") else b""
                parsed: Any = None
                if raw:
                    try:
                        parsed = json.loads(raw.decode("utf-8"))
                    except ValueError:
                        parsed = None
                parsed_obj = parsed if isinstance(parsed, dict) else {}
                # The gateway nests error details under "error"
                # ({"error": {"code", "message", ...}}); unwrap it, falling
                # back to the top-level shape for legacy/plain bodies.
                inner = parsed_obj.get("error")
                shape = inner if isinstance(inner, dict) else parsed_obj
                error = GatewayError(
                    status=exc.code,
                    code=str(shape.get("code", "GATEWAY_ERROR")),
                    message=str(shape.get("message", exc.reason)),
                    provider=shape.get("provider"),
                    retryable=shape.get("retryable"),
                    body=parsed,
                )
                last_error = error
                if exc.code in RETRYABLE_STATUSES and attempt < self.max_retries - 1:
                    continue
                raise error
        raise last_error or GatewayError(
            0, code="UNREACHABLE", message="gateway unreachable"
        )

    def run_task(
        self,
        task: str,
        payload: Any = None,
        model: str | None = None,
        idempotency_key: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> Any:
        """Submit a task run for gateway execution."""
        body: dict[str, Any] = {"task": task, "input": payload or {}}
        if model:
            body["model"] = model
        if idempotency_key:
            body["idempotencyKey"] = idempotency_key
        if metadata:
            body["metadata"] = metadata
        return self.request("POST", "/v1/runs", body)

    def get_run(self, run_id: str) -> Any:
        """Fetch a run's state and execution trace."""
        return self.request("GET", "/v1/runs/" + urllib.request.quote(run_id, safe=""))

    def list_models(self) -> Any:
        return self.request("GET", "/v1/models")

    def health(self) -> Any:
        return self.request("GET", "/health")

    def chat(
        self, messages: Any, model: str = "auto", stream: bool = False, **kwargs: Any
    ) -> Any:
        """OpenAI-compatible chat completion via /v1/chat/completions."""
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        body.update(kwargs)
        return self.request("POST", "/v1/chat/completions", body)

    def consensus(self, messages: Any, **kwargs: Any) -> Any:
        """Parallel multi-model consensus via /v1/consensus."""
        body: dict[str, Any] = {"messages": messages}
        body.update(kwargs)
        return self.request("POST", "/v1/consensus", body)

    def stream_run(self, run_id: str) -> Iterator[StreamEvent]:
        """Yield parsed SSE events for a run until the [DONE] sentinel."""
        url = (
            self.base_url
            + "/v1/runs/"
            + urllib.request.quote(run_id, safe="")
            + "/stream"
        )
        request = urllib.request.Request(url, method="GET")
        for key, value in self._headers({"Accept": "text/event-stream"}).items():
            request.add_header(key, value)
        listener = SSEListener()
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            for raw in response:
                for event in listener.feed(raw.decode("utf-8", errors="replace")):
                    if event.is_done:
                        return
                    yield event
            for event in listener.finish():
                if event.is_done:
                    return
                yield event


class AsyncSupremeAIClient:
    """Async facade over the sync client: executor-backed HTTP, queue-backed SSE."""

    def __init__(self, **options: Any) -> None:
        self._sync = SupremeAIClient(**options)

    async def request(
        self,
        method: str,
        path: str,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self._sync.request(method, path, payload, headers)
        )

    async def run_task(self, task: str, payload: Any = None, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self._sync.run_task(task, payload, **kwargs)
        )

    async def health(self) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._sync.health())

    async def list_models(self) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._sync.list_models())

    async def chat(
        self, messages: Any, model: str = "auto", stream: bool = False, **kwargs: Any
    ) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._sync.chat(messages, model=model, stream=stream, **kwargs),
        )

    async def consensus(self, messages: Any, **kwargs: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self._sync.consensus(messages, **kwargs)
        )

    async def stream_run(self, run_id: str) -> AsyncIterator[StreamEvent]:
        """Async SSE iterator: a background thread pumps bytes into a queue."""
        queue: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def pump() -> None:
            try:
                for event in self._sync.stream_run(run_id):
                    loop.call_soon_threadsafe(queue.put_nowait, event)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        import threading

        thread = threading.Thread(target=pump, daemon=True)
        thread.start()
        while True:
            event = await queue.get()
            if event is None:
                break
            yield event
