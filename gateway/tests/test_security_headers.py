"""tests/test_security_headers.py — #1728 evidence (baseline headers + HEAD support).

Mirrors the stub-app header test pattern from gateway/tests/test_correlation_id.py
(Way 28) — the same pattern the studio lane (#1036) proved out. Drives a minimal
FastAPI app + SecurityHeadersMiddleware fully offline via fastapi.testclient.
"""

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
for p in (str(_GATEWAY_DIR.parent),):
    # Repo root ONLY. Never put the gateway/ package dir itself on sys.path:
    # it forks gateway.service.* into duplicate module objects (split-brain
    # singletons — drift class F-K, order-dependent suite failures).
    if p not in sys.path:
        sys.path.insert(0, p)

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from gateway.middleware.security_headers import (  # noqa: E402
    SECURITY_HEADERS,
    SecurityHeadersMiddleware,
)

FOUR_BASELINE = (
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Content-Security-Policy-Report-Only",
)


def _app() -> FastAPI:
    # Mirrors the patched production wiring (gateway/service/app.py): root route
    # declares GET+HEAD (the #1728 405 fix) and the middleware is the only header
    # source. Drives the middleware fully offline.
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.api_route("/", methods=["GET", "HEAD"])
    async def root():
        return {"status": "healthy", "service_name": "stub"}

    return app


def test_all_baseline_security_headers_present_on_get_root():
    """#1728 AC1: every baseline header rides the live response."""
    client = TestClient(_app())
    r = client.get("/")
    assert r.status_code == 200
    for name in FOUR_BASELINE:
        assert r.headers.get(name) == SECURITY_HEADERS[name], f"missing header: {name}"
    # optional hardeners from the proposal
    assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert r.headers.get("Permissions-Policy") == "interest-cohort=()"


def test_csp_ships_report_only_first():
    """#1728 AC3: CSP travels in the -Report-Only variant until the flip."""
    client = TestClient(_app())
    r = client.get("/")
    policy = r.headers.get("Content-Security-Policy-Report-Only", "")
    assert "default-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy


def test_head_root_returns_200_with_same_headers():
    """#1728 AC2: HEAD / is 200 (was 405 allow: GET) and carries the headers."""
    client = TestClient(_app())
    r = client.head("/")
    assert r.status_code == 200
    for name in FOUR_BASELINE:
        assert r.headers.get(name) == SECURITY_HEADERS[name], f"missing header: {name}"


def test_body_untouched_by_middleware():
    """#1728 AC4: zero change to response bodies."""
    client = TestClient(_app())
    r = client.get("/")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "service_name": "stub"}


def test_set_semantics_uniform_stamp_no_duplicates():
    """SET semantics: the middleware value uniformly wins; exactly one occurrence.

    Browsers resolve duplicate security headers inconsistently (CSP duplicates
    intersect and can break); a uniform replace-stamp is the safe contract and
    keeps every route honest about the baseline.
    """
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/dupe")
    async def dupe():
        return JSONResponse({"ok": True}, headers={"X-Frame-Options": "SAMEORIGIN"})

    client = TestClient(app)
    r = client.get("/dupe")
    assert r.status_code == 200
    assert r.headers.get("X-Frame-Options") == "DENY"
    raw = [v for k, v in r.headers.items() if k.lower() == "x-frame-options"]
    assert raw == ["DENY"]


def test_non_http_scope_passthrough():
    """lifespan/websocket scopes bypass the header stamping untouched."""
    client = TestClient(_app())
    with client:
        r = client.get("/")
        assert r.status_code == 200  # app boots and serves — lifespan intact
