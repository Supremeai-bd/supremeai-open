"""ASGI entrypoint for the SupremeAI gateway (issue #336).

Run with: uvicorn gateway.serve:app (default port 8080).

Deliberately separate from the package init so the boot smoke
(import gateway.main) stays offline safe. This module builds the validated
app at import time, fail closed: a missing routing policy or missing key
material aborts startup.

MOCK PROVIDER: set SUPREMEAI_GATEWAY_MOCK_PROVIDER=1 to wire a deterministic
local transport so the AC3 curl smoke (examples/curl-tests/health.sh with the
gateway subcommand) runs end to end with zero external credentials. The mock
is a TEST fixture only, never production, and every mock completion carries a
[mock] label on the wire.
"""
from __future__ import annotations

import asyncio
import json
import os

from .config import load_config
from .main import create_app
from .provider_chain import AttemptResult


async def _mock_attempt(endpoint, payload: bytes) -> AttemptResult:
    """Deterministic mock provider completion (labeled [mock])."""
    try:
        messages = json.loads(payload).get("messages", [])
        last_user = next(
            (m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), ""
        )
    except json.JSONDecodeError:
        last_user = ""
    body = json.dumps({
        "choices": [{
            "index": 0,
            "message": {"role": "assistant",
                        "content": f"[mock:{endpoint.provider}] echo: {last_user}"},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }).encode()
    return AttemptResult(endpoint=endpoint, status=200, headers={}, body=body, latency_ms=1)


def _mock_stream(endpoint, payload: bytes):
    """Deterministic mock provider stream: 3 chunks + stop (labeled [mock])."""
    async def gen():
        yield {"type": "chunk",
               "delta": {"role": "assistant", "content": f"[mock:{endpoint.provider}] "},
               "finish_reason": None}
        yield {"type": "chunk", "delta": {"content": "streaming "}, "finish_reason": None}
        yield {"type": "chunk", "delta": {"content": "echo"}, "finish_reason": None}
        yield {"type": "chunk", "delta": {}, "finish_reason": "stop"}
    return gen()


config = load_config(os.environ.get("SUPREMEAI_ROUTING_POLICY"))

if os.environ.get("SUPREMEAI_GATEWAY_MOCK_PROVIDER") == "1":
    import sys

    print("gateway.serve: MOCK PROVIDER ENABLED (SUPREMEAI_GATEWAY_MOCK_PROVIDER=1) "
          "— test fixture only, never production", file=sys.stderr)
    app = create_app(config, attempt_fn=_mock_attempt, stream_fn=_mock_stream)
else:
    app = create_app(config)
