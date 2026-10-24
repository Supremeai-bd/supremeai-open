"""tests/test_correlation_id.py — Way 28 evidence (per-request correlation id)."""

from __future__ import annotations

import sys
from pathlib import Path

_GATEWAY_DIR = next(
    (
        p
        for p in Path(__file__).resolve().parents
        if (p / "main.py").is_file() and (p / "routing_policy.json").is_file()
    ),
    Path(__file__).resolve().parent.parent,
)
for p in (str(_GATEWAY_DIR), str(_GATEWAY_DIR.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from gateway.middleware.correlation_id import (  # noqa: E402
    CorrelationIdMiddleware,
    current_correlation_id,
    mint_correlation_id,
)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/echo")
    async def echo():
        return {"cid": current_correlation_id()}

    @app.get("/boom")
    async def boom():
        raise RuntimeError("x")

    return app


def test_mints_and_echoes_correlation_id():
    client = TestClient(_app())
    r = client.get("/echo")
    assert r.status_code == 200
    cid = r.headers.get("X-Correlation-ID")
    assert cid and len(cid) == 32  # uuid4 hex
    assert r.json()["cid"] == cid


def test_honours_inbound_correlation_id():
    client = TestClient(_app())
    r = client.get("/echo", headers={"X-Correlation-ID": "trace-abc-123456"})
    assert r.headers.get("X-Correlation-ID") == "trace-abc-123456"
    assert r.json()["cid"] == "trace-abc-123456"


def test_honours_inbound_request_id_fallback():
    client = TestClient(_app())
    r = client.get("/echo", headers={"X-Request-ID": "req-xyz-987654321"})
    assert r.headers.get("X-Correlation-ID") == "req-xyz-987654321"


def test_rejects_unsafe_ids_by_minting_new():
    client = TestClient(_app())
    r = client.get("/echo", headers={"X-Correlation-ID": "bad id with spaces!!"})
    cid = r.headers.get("X-Correlation-ID", "")
    assert cid and " " not in cid and "!" not in cid


def test_mint_is_unique():
    assert mint_correlation_id() != mint_correlation_id()


def test_outside_request_context_is_empty():
    assert current_correlation_id() == ""
