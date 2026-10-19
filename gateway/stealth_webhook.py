"""SupremeAI stealth web-relay forwarder (Priority-1 $0 engine).

Mirrors the contract in docs/SUPREMEAI_BROWSER_INTEGRATION.md §9.6:
  POST <STEALTH_WEBHOOK_URL>/api/chat   (or configured path)
  headers: X-Stealth-Secret (when configured)
  body:    the OpenAI chat-completion request body (messages, model, ...)
  returns: (status, parsed_json_or_none, latency_ms)

Transport is stdlib asyncio (no third-party client) so the gateway stays
dependency-light and offline-testable. The function is injectable into
create_app so tests can stub it deterministically.
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
from collections.abc import Awaitable, Callable
from typing import Any

ForwardFn = Callable[[str, str | None, bytes, float], Awaitable[tuple[int, Any, int]]]


async def forward_stealth_webhook(
    url: str,
    secret: str | None,
    body: bytes,
    timeout: float = 10.0,
) -> tuple[int, Any, int]:
    """Forward a chat-completion request to the stealth (browser) relay.

    Returns (http_status, parsed_json_or_None, latency_ms). On transport
    failure returns (0, None, latency_ms) so callers can fail over honestly
    without fabricating a response.
    """
    if not url:
        return 0, None, 0
    started = time.monotonic()
    # Normalise: ensure a path.
    full = url if "://" in url else "http://" + url
    # The bridge exposes an OpenAI-compatible endpoint at /v1/chat/completions.
    # Always target that (it understands the messages[] body we send). If the
    # operator pointed at /api/chat or /chat, rewrite to the compatible path.
    base = full.split("?", 1)[0].rstrip("/")
    if base.endswith(("/api/chat", "/chat")):
        base = base.rsplit("/", 1)[0].rstrip("/")
    if not base.endswith("/v1/chat/completions"):
        base = base + "/v1/chat/completions"
    full = base + (full[len(full.split("?", 1)[0]) :] if "?" in full else "")
    rest = full.split("://", 1)[1]
    host_port, _, path = rest.partition("/")
    host, _, port_s = host_port.partition(":")
    secure = full.startswith("https")
    port = int(port_s) if port_s else (443 if secure else 80)
    path = "/" + path if path else "/"

    try:
        if secure:
            opener = asyncio.open_connection(
                host, port, ssl=ssl.create_default_context()
            )
        else:
            opener = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(opener, timeout=timeout)
    except Exception:
        return 0, None, int((time.monotonic() - started) * 1000)

    try:
        headers = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {host_port}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Connection: close\r\n"
        )
        if secret:
            headers += f"X-Stealth-Secret: {secret}\r\n"
        headers += "\r\n"
        writer.write(headers.encode("latin-1") + body)
        await writer.drain()

        status_line = (
            await asyncio.wait_for(reader.readline(), timeout=timeout)
        ).decode("latin-1")
        parts = status_line.split(" ")
        status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        resp_headers: dict[str, str] = {}
        while True:
            line = (await asyncio.wait_for(reader.readline(), timeout=timeout)).decode(
                "latin-1"
            )
            if line in ("\r\n", "\n", ""):
                break
            k, _, v = line.partition(":")
            resp_headers[k.strip().lower()] = v.strip()
        resp_body = b""
        if "content-length" in resp_headers:
            resp_body = await asyncio.wait_for(
                reader.readexactly(int(resp_headers["content-length"])), timeout=timeout
            )
        else:
            try:
                resp_body = await asyncio.wait_for(reader.read(), timeout=timeout)
            except asyncio.TimeoutError:
                pass
        parsed = None
        if resp_body:
            try:
                parsed = json.loads(resp_body)
            except (json.JSONDecodeError, UnicodeDecodeError):
                parsed = None
        return status, parsed, int((time.monotonic() - started) * 1000)
    except Exception:
        return 0, None, int((time.monotonic() - started) * 1000)
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
