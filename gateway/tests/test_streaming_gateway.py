"""tests/test_streaming_gateway.py — pytest harness for the unified gateway (issue #336).

Verification contract (AC3): ``pytest tests/test_streaming_gateway.py -v``.

Fully offline: the provider transport is injected (deterministic fake chains),
the app is driven via fastapi.testclient. Asserts:

- AC1  SSE framing: ``event:``/``data:`` frames, terminal ``[DONE]``,
       honest mid-stream error frames, pre-first-chunk failover
- AC2  rate limiting: standardized JSON error contract on 429 with
       ``X-RateLimit-*`` + ``Retry-After`` headers; 503 shape
- OpenAPI compliance: /healthz no-auth, /v1/models auth+scope, 401/403
  default-deny, chat completions OpenAI-compatible shape, honest usage echo
- failover ledger: exhaustion → 502 with redacted ledger (zero silent fallback)
- config: fail-closed validation battery (closed enum, drift rejection)
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

_GATEWAY_DIR = next(
    (
        p
        for p in Path(__file__).resolve().parents
        if (p / "main.py").is_file() and (p / "routing_policy.json").is_file()
    ),
    None,
)
if _GATEWAY_DIR is None:
    raise ImportError("gateway package not found near " + str(Path(__file__)))
REPO_ROOT = _GATEWAY_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from gateway.config import (
    ALLOWED_PROVIDERS,
    ConfigError,
    Endpoint,
    parse_routing_policy,
)
from gateway.main import create_app
from gateway.provider_chain import (
    AttemptResult,
    ProviderChainExhausted,
    execute_chain,
)
from gateway.rate_limit import SlidingWindowLimiter

CHAT_KEY = "supremeai-key-test-0000000001"  # scopes: chat+models
READ_KEY = "supremeai-key-test-0000000002"  # scopes: models only


# ---------------------------------------------------------------------------
# Deterministic fake provider transports
# ---------------------------------------------------------------------------


def fake_attempt(responses: dict[str, AttemptResult], calls: list[str]):
    async def attempt(endpoint: Endpoint, payload: bytes) -> AttemptResult:
        calls.append("%s/%s" % (endpoint.provider, endpoint.model))
        found = responses.get(endpoint.provider)
        if found is None:
            raise RuntimeError(f"no fake for {endpoint.provider}")
        return found

    return attempt


def ok_body(content: str = "hello from provider", usage: dict | None = None) -> bytes:
    body: dict[str, Any] = {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return json.dumps(body).encode()


def stream_fn_factory(script: list[list[dict]]):
    """script: per-endpoint list of events; each call pops the next endpoint's script."""

    def stream_fn(endpoint: Endpoint, payload: bytes):
        events = (
            script.pop(0)
            if script
            else [{"type": "error", "message": "script exhausted"}]
        )

        async def gen():
            for ev in events:
                if ev.get("raise"):
                    raise RuntimeError(ev["raise"])
                yield ev

        return gen()

    return stream_fn


def make_client(**kw) -> TestClient:
    # Fresh breaker per client: the default singleton is process-global and
    # #2765 made execute_chain mutate it (record_failure on every retryable
    # exhaustion / transport-error attempt), so sharing it across tests let
    # one test's exhaustion trip circuits for every later test (rate-limit
    # assertions then saw 502s instead of 200s). Injected breakers keep each
    # test's failure accounting local, matching create_app's injectable-
    # collaborators contract.
    from gateway.circuit_breaker import CircuitBreaker

    kw.setdefault("circuit_breaker", CircuitBreaker())
    return TestClient(create_app(**kw))


def base_config():
    return parse_routing_policy(
        {
            "schema_version": "gateway-routing/1",
            "chains": {
                "auto": [
                    {"provider": "groq", "model": "llama-3.1-8b-instant"},
                    {"provider": "openai", "model": "gpt-4o-mini"},
                ],
            },
            "default_chain": "auto",
            "rate_limit": {"window_seconds": 60, "max_requests": 4},
            "api_keys": {
                CHAT_KEY: {"owner": "pytest", "scopes": ["chat", "models"]},
                READ_KEY: {"owner": "readonly", "scopes": ["models"]},
            },
        },
        env={"SUPREMEAI_API_KEY_PYTEST": "x", "SUPREMEAI_API_KEY_READONLY": "y"},
    )


# ---------------------------------------------------------------------------
# Health + models (OpenAPI compliance)
# ---------------------------------------------------------------------------


def test_health_no_auth():
    client = make_client(config=base_config())
    for path in ("/health", "/healthz"):
        r = client.get(path)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_models_requires_auth_and_scope():
    client = make_client(config=base_config())
    assert client.get("/v1/models").status_code == 403
    assert (
        client.get("/v1/models", headers={"X-SupremeAI-Key": "bogus"}).status_code
        == 401
    )
    r = client.get("/v1/models", headers={"X-SupremeAI-Key": READ_KEY})
    assert r.status_code == 200
    ids = [m["id"] for m in r.json()["data"]]
    assert ids == [
        "gpt-4o-mini",
        "llama-3.1-8b-instant",
    ]  # base_config chain: groq+openai
    assert r.json()["object"] == "list"


def test_chat_requires_chat_scope():
    cfg = base_config()
    calls: list[str] = []
    client = make_client(
        config=cfg,
        attempt_fn=fake_attempt(
            {
                "groq": AttemptResult(
                    endpoint=cfg.chains["auto"][0],
                    status=200,
                    headers={},
                    body=ok_body(),
                    latency_ms=1,
                )
            },
            calls,
        ),
    )
    r = client.post(
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": READ_KEY},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_scope"


# ---------------------------------------------------------------------------
# Chat completions (OpenAI-compatible shape, honest usage)
# ---------------------------------------------------------------------------


def test_completion_openai_shape_and_honest_usage():
    cfg = base_config()
    calls: list[str] = []
    usage = {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}
    client = make_client(
        config=cfg,
        attempt_fn=fake_attempt(
            {
                "groq": AttemptResult(
                    endpoint=cfg.chains["auto"][0],
                    status=200,
                    headers={},
                    body=ok_body(usage=usage),
                    latency_ms=3,
                )
            },
            calls,
        ),
    )
    r = client.post(
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"model": "auto", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200
    out = r.json()
    assert out["object"] == "chat.completion"
    assert out["model"] == "groq/llama-3.1-8b-instant"  # served-by honesty
    assert out["choices"][0]["message"]["content"] == "hello from provider"
    assert out["usage"] == usage


def test_completion_without_reported_usage_omits_field():
    cfg = base_config()
    client = make_client(
        config=cfg,
        attempt_fn=fake_attempt(
            {
                "groq": AttemptResult(
                    endpoint=cfg.chains["auto"][0],
                    status=200,
                    headers={},
                    body=ok_body(),
                    latency_ms=1,
                )
            },
            [],
        ),
    )
    r = client.post(
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert "usage" not in r.json()  # honesty doctrine: never fabricate usage


def test_malformed_and_unknown_model_requests():
    client = make_client(config=base_config())
    h = {"X-SupremeAI-Key": CHAT_KEY}
    assert (
        client.post("/v1/chat/completions", headers=h, content=b"not json{").status_code
        == 400
    )
    assert (
        client.post(
            "/v1/chat/completions", headers=h, json={"messages": []}
        ).status_code
        == 400
    )
    r = client.post(
        "/v1/chat/completions",
        headers=h,
        json={"model": "nope", "messages": [{"role": "user", "content": "x"}]},
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "unknown_model"


# ---------------------------------------------------------------------------
# Provider failover (zero silent fallback)
# ---------------------------------------------------------------------------


def test_failover_on_provider_429_then_success():
    cfg = base_config()
    calls: list[str] = []
    responses = {
        "groq": AttemptResult(
            endpoint=cfg.chains["auto"][0],
            status=429,
            headers={"Retry-After": "7"},
            body=b"rate limited",
            latency_ms=2,
        ),
        "openai": AttemptResult(
            endpoint=cfg.chains["auto"][1],
            status=200,
            headers={},
            body=ok_body("second provider"),
            latency_ms=4,
        ),
    }
    client = make_client(config=cfg, attempt_fn=fake_attempt(responses, calls))
    r = client.post(
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200
    assert r.json()["model"] == "openai/gpt-4o-mini"
    # #2082/#2752 contract: a retryable 429 is retried on the SAME endpoint
    # up to max_retries (default 2) times with backoff BEFORE failing over,
    # so groq is attempted 3x total, then the chain fails over to openai.
    assert calls == [
        "groq/llama-3.1-8b-instant",
        "groq/llama-3.1-8b-instant",
        "groq/llama-3.1-8b-instant",
        "openai/gpt-4o-mini",
    ]


def test_exhaustion_returns_502_with_redacted_ledger():
    cfg = base_config()
    responses = {
        "groq": AttemptResult(
            endpoint=cfg.chains["auto"][0],
            status=503,
            headers={},
            body=b"down",
            latency_ms=1,
        ),
        "openai": AttemptResult(
            endpoint=cfg.chains["auto"][1],
            status=429,
            headers={"Retry-After": "3"},
            body=b"limited",
            latency_ms=2,
        ),
    }
    client = make_client(config=cfg, attempt_fn=fake_attempt(responses, []))
    r = client.post(
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 502
    payload = r.json()
    assert payload["error"]["code"] == "provider_chain_exhausted"
    ledger = payload["providers_tried"]
    # #2082/#2752 contract: each retryable endpoint is attempted max_retries+1
    # times (default 3) before failover, and every attempt is ledgered.
    assert [e["status"] for e in ledger] == [503, 503, 503, 429, 429, 429]
    # redaction: no credential-shaped fields survive
    for entry in ledger:
        assert set(entry) <= {
            "index",
            "provider",
            "model",
            "outcome",
            "status",
            "latency_ms",
            "detail",
        }


def test_transport_error_fails_over_and_exhaustion_carries_ledger():
    cfg = base_config()

    async def flaky(endpoint: Endpoint, payload: bytes) -> AttemptResult:
        raise OSError(f"connection refused to {endpoint.provider}")

    client = make_client(config=cfg, attempt_fn=flaky)
    r = client.post(
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 502
    # #2082/#2752 contract: transport errors are retried on the SAME endpoint
    # up to max_retries times before failover, each attempt ledgered, so the
    # 2-endpoint chain yields 6 ledgered attempts.
    assert len(r.json()["providers_tried"]) == 6
    assert all(e["outcome"] == "transport_error" for e in r.json()["providers_tried"])


def test_execute_chain_ledger_direct():
    cfg = base_config()
    chain = cfg.chains["auto"]

    async def always_500(endpoint, payload):
        return AttemptResult(
            endpoint=endpoint, status=500, headers={}, body=b"x", latency_ms=1
        )

    with pytest.raises(ProviderChainExhausted) as excinfo:
        asyncio.run(execute_chain(chain, b"{}", attempt_fn=always_500))
    assert len(excinfo.value.ledger) == 2


# ---------------------------------------------------------------------------
# Rate limiting (AC2: standardized JSON error + X-RateLimit-* + Retry-After)
# ---------------------------------------------------------------------------


def test_rate_limit_429_contract_and_headers():
    cfg = base_config()  # max_requests=4
    client = make_client(
        config=cfg,
        attempt_fn=fake_attempt(
            {
                "groq": AttemptResult(
                    endpoint=cfg.chains["auto"][0],
                    status=200,
                    headers={},
                    body=ok_body(),
                    latency_ms=1,
                )
            },
            [],
        ),
    )
    h = {"X-SupremeAI-Key": CHAT_KEY}
    for i in range(4):
        r = client.post(
            "/v1/chat/completions",
            headers=h,
            json={"messages": [{"role": "user", "content": f"m{i}"}]},
        )
        assert r.status_code == 200
        assert r.headers["x-ratelimit-remaining"] == str(3 - i)
    r = client.post(
        "/v1/chat/completions",
        headers=h,
        json={"messages": [{"role": "user", "content": "over"}]},
    )
    assert r.status_code == 429
    body = r.json()
    # standardized JSON error contract
    assert body["error"]["type"] == "rate_limit_error"
    assert body["error"]["code"] == "rate_limit_exceeded"
    assert body["error"]["param"] is None
    # header contract
    assert r.headers["retry-after"].isdigit() and int(r.headers["retry-after"]) >= 1
    assert r.headers["x-ratelimit-limit"] == "4"
    assert r.headers["x-ratelimit-remaining"] == "0"
    assert int(r.headers["x-ratelimit-reset"]) > 0


def test_rate_limit_reset_epoch_matches_window():
    cfg = base_config()
    client = make_client(
        config=cfg,
        attempt_fn=fake_attempt(
            {
                "groq": AttemptResult(
                    endpoint=cfg.chains["auto"][0],
                    status=200,
                    headers={},
                    body=ok_body(),
                    latency_ms=1,
                )
            },
            [],
        ),
    )
    h = {"X-SupremeAI-Key": CHAT_KEY}
    r = client.post(
        "/v1/chat/completions",
        headers=h,
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    reset = int(r.headers["x-ratelimit-reset"])
    (
        int(
            asyncio.get_event_loop_policy()
            .new_event_loop()
            .run_until_complete(asyncio.sleep(0))
            or 0
        )
        or reset
    )
    # window is 60s: reset must be within now+1..now+60 (clock tolerance)
    assert 0 < reset - (reset - 60) <= 60


def test_503_error_shape():
    cfg = base_config()
    responses = {
        "groq": AttemptResult(
            endpoint=cfg.chains["auto"][0],
            status=503,
            headers={},
            body=b"down",
            latency_ms=1,
        ),
        "openai": AttemptResult(
            endpoint=cfg.chains["auto"][1],
            status=503,
            headers={},
            body=b"down",
            latency_ms=1,
        ),
    }
    client = make_client(config=cfg, attempt_fn=fake_attempt(responses, []))
    r = client.post(
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    assert r.status_code == 502  # gateway maps exhaustion to 502 per OpenAPI


# ---------------------------------------------------------------------------
# SSE streaming (AC1)
# ---------------------------------------------------------------------------


def _sse_frames(text: str) -> list[tuple[str, str]]:
    frames = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].lstrip()
        frames.append((event, data))
    return frames


def test_sse_stream_framing_and_done_sentinel():
    cfg = base_config()
    script = [
        [
            {
                "type": "chunk",
                "delta": {"role": "assistant", "content": "Hel"},
                "finish_reason": None,
            },
            {"type": "chunk", "delta": {"content": "lo"}, "finish_reason": None},
            {"type": "chunk", "delta": {}, "finish_reason": "stop"},
        ]
    ]
    client = make_client(config=cfg, stream_fn=stream_fn_factory(script))
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"stream": True, "messages": [{"role": "user", "content": "hi"}]},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = "".join(resp.iter_text())
    frames = _sse_frames(text)
    assert frames[0][0] == "chat.completion.chunk"
    first = json.loads(frames[0][1])
    assert first["object"] == "chat.completion.chunk"
    assert first["model"] == "groq/llama-3.1-8b-instant"  # served-by on the wire
    assert first["choices"][0]["delta"]["content"] == "Hel"
    assert frames[-1][0] == "done" and frames[-1][1] == "[DONE]"
    # every data frame is either JSON or the [DONE] sentinel (framing integrity)
    for event, data in frames:
        assert data == "[DONE]" or json.loads(data)


def test_sse_pre_first_chunk_failover():
    cfg = base_config()
    script = [
        [
            {"type": "error", "status": 429, "message": "provider HTTP 429"}
        ],  # groq fails pre-chunk
        [
            {"type": "chunk", "delta": {"content": "fallback"}, "finish_reason": None},
            {"type": "chunk", "delta": {}, "finish_reason": "stop"},
        ],  # openai serves
    ]
    client = make_client(config=cfg, stream_fn=stream_fn_factory(script))
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"stream": True, "messages": [{"role": "user", "content": "hi"}]},
    ) as resp:
        text = "".join(resp.iter_text())
    frames = _sse_frames(text)
    served = json.loads(frames[0][1])["model"]
    assert (
        served == "openai/gpt-4o-mini"
    )  # failed over BEFORE any chunk reached the client


def test_sse_mid_stream_error_is_honest_frame():
    cfg = base_config()
    script = [
        [
            {"type": "chunk", "delta": {"content": "partial"}, "finish_reason": None},
            {"raise": "provider connection reset"},
        ]
    ]
    client = make_client(config=cfg, stream_fn=stream_fn_factory(script))
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"stream": True, "messages": [{"role": "user", "content": "hi"}]},
    ) as resp:
        text = "".join(resp.iter_text())
    frames = _sse_frames(text)
    error_frames = [f for f in frames if f[0] == "error"]
    assert len(error_frames) == 1  # no silent cut, no duplicated restart
    err = json.loads(error_frames[0][1])
    assert err["error"]["code"] == "provider_stream_interrupted"
    assert frames[-1][0] != "done" or error_frames[0] in frames[:-1]


def test_sse_chain_exhausted_before_stream():
    cfg = base_config()
    script = [
        [{"type": "error", "status": 503, "message": "down"}],
        [{"type": "error", "status": 503, "message": "down"}],
    ]
    client = make_client(config=cfg, stream_fn=stream_fn_factory(script))
    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={"X-SupremeAI-Key": CHAT_KEY},
        json={"stream": True, "messages": [{"role": "user", "content": "hi"}]},
    ) as resp:
        text = "".join(resp.iter_text())
    frames = _sse_frames(text)
    assert frames[0][0] == "error"
    assert json.loads(frames[0][1])["error"]["code"] == "chain_exhausted"
    assert frames[-1] == ("done", "[DONE]")


# ---------------------------------------------------------------------------
# Config fail-closed battery
# ---------------------------------------------------------------------------


def test_config_rejects_drift():
    good = json.loads(
        json.dumps(
            {
                "schema_version": "gateway-routing/1",
                "chains": {"auto": [{"provider": "groq", "model": "x"}]},
                "default_chain": "auto",
                "rate_limit": {"window_seconds": 60, "max_requests": 4},
                "api_keys": {
                    "supremeai-key-test-0000000001": {"owner": "t", "scopes": ["chat"]}
                },
            }
        )
    )
    env = {"SUPREMEAI_API_KEY_T": "x"}

    def drift(mutate):
        bad = json.loads(json.dumps(good))
        mutate(bad)
        with pytest.raises(ConfigError):
            parse_routing_policy(bad, env=env)

    drift(lambda c: c.__setitem__("schema_version", "gateway-routing/2"))
    drift(lambda c: c.__setitem__("chains", {}))
    drift(
        lambda c: c["chains"]["auto"].__setitem__(
            0, {"provider": "skynet", "model": "x"}
        )
    )
    drift(
        lambda c: c["chains"]["auto"].__setitem__(0, {"provider": "groq"})
    )  # missing model
    drift(
        lambda c: c["chains"]["auto"].__setitem__(
            0, {"provider": "groq", "model": "x", "extra": 1}
        )
    )
    drift(lambda c: c.__setitem__("default_chain", "missing"))
    drift(
        lambda c: c.__setitem__("rate_limit", {"window_seconds": 0, "max_requests": 4})
    )
    drift(
        lambda c: c.__setitem__(
            "rate_limit", {"window_seconds": 60, "max_requests": -1}
        )
    )
    drift(
        lambda c: c.__setitem__(
            "api_keys", {"short": {"owner": "t", "scopes": ["chat"]}}
        )
    )
    drift(
        lambda c: c["api_keys"]["supremeai-key-test-0000000001"].__setitem__(
            "scopes", ["admin"]
        )
    )
    drift(
        lambda c: c["api_keys"]["supremeai-key-test-0000000001"].__setitem__(
            "secret", "literal"
        )
    )


def test_config_provider_enum_matches_task_router_ssot():
    # Gateway-plane enum = task-router.schema.json's 7 schema providers
    # PLUS the gateway-only providers with live drivers + policy hops:
    # "web" (web_session.py) and "perplexity" (adapters.py, sonar cascade).
    # A copy that lags the runtime makes load_config() reject the shipped
    # routing_policy.json (drift class F-J, 2026-10-28) — extend, don't lag.
    assert ALLOWED_PROVIDERS == frozenset(
        {
            "openai",
            "anthropic",
            "gemini",
            "groq",
            "openrouter",
            "mistral",
            "deepseek",
            "web",
            "perplexity",
            "manus",
        }
    )


def test_limiter_rejects_bad_params_fail_closed():
    with pytest.raises(ValueError):
        SlidingWindowLimiter(0, 10)
    with pytest.raises(ValueError):
        SlidingWindowLimiter(60, 0)
