"""Tests for the SupremeAI Browser lightweight Gemini cookie relay entrypoint."""

import os
import sys
import unittest.mock as mock
from fastapi.testclient import TestClient

# Ensure parent directory is in path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main


def test_main_app_structure() -> None:
    """Verify main.py loads the FastAPI app with expected routes."""
    routes = [r.path for r in main.app.routes]
    assert "/health" in routes
    assert "/api/chat" in routes
    assert "/v1/chat/completions" in routes


def test_health_check() -> None:
    """Verify GET /health returns 200 OK and healthy status."""
    client = TestClient(main.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "supremeai-browser" in data.get("browser_service", data.get("service", ""))


def test_stealth_secret_auth_guard() -> None:
    """Verify STEALTH_WEBHOOK_SECRET guard behaviour."""
    client = TestClient(main.app)

    # 1. Without secret configured, missing header should not trigger 401
    with mock.patch.dict(os.environ, {"STEALTH_WEBHOOK_SECRET": ""}, clear=False):
        # Mock relay_engine.ask to avoid live network call
        with mock.patch.object(main.relay_engine, "ask", return_value="mock reply"):
            resp = client.post("/api/chat", json={"message": "hello"})
            assert resp.status_code == 200
            assert resp.json()["reply"] == "mock reply"

    # 2. With secret configured, missing/invalid header triggers 401
    with mock.patch.dict(os.environ, {"STEALTH_WEBHOOK_SECRET": "guard-token-xyz"}, clear=False):
        resp_unauth = client.post("/api/chat", json={"message": "hello"})
        assert resp_unauth.status_code == 401
        assert "Unauthorized" in resp_unauth.json()["detail"]

        resp_wrong = client.post(
            "/api/chat", json={"message": "hello"}, headers={"X-Stealth-Secret": "wrong-token"}
        )
        assert resp_wrong.status_code == 401

        with mock.patch.object(main.relay_engine, "ask", return_value="authenticated reply"):
            # Valid X-Stealth-Secret
            resp_x_secret = client.post(
                "/api/chat",
                json={"message": "hello"},
                headers={"X-Stealth-Secret": "guard-token-xyz"},
            )
            assert resp_x_secret.status_code == 200
            assert resp_x_secret.json()["reply"] == "authenticated reply"

            # Valid Bearer Authorization
            resp_bearer = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hello"}]},
                headers={"Authorization": "Bearer guard-token-xyz"},
            )
            assert resp_bearer.status_code == 200
            data = resp_bearer.json()
            assert data["choices"][0]["message"]["content"] == "authenticated reply"


def test_duck_ai_routing_and_fallback() -> None:
    """Verify Duck.ai explicit model routing and Gemini failure fallback."""
    client = TestClient(main.app)

    # 1. Explicit duck model routes to duck_engine
    with mock.patch.object(main.duck_engine, "ask", return_value="duck reply") as mock_duck:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "duck-gpt-4o-mini",
                "messages": [{"role": "user", "content": "test prompt"}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["choices"][0]["message"]["content"] == "duck reply"
        assert data["model"] == "duck-gpt-4o-mini"
        assert data["supremeai_engine"] == "dk"
        mock_duck.assert_called_once_with("test prompt", model="duck-gpt-4o-mini")

    # 2. When Gemini fails, it seamlessly falls back to Duck.ai
    with mock.patch.object(main.relay_engine, "ask", side_effect=Exception("Gemini cookie expired")):
        with mock.patch.object(main.duck_engine, "ask", return_value="fallback reply") as mock_fallback:
            resp = client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "prompt needing fallback"}]},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["choices"][0]["message"]["content"] == "fallback reply"
            assert data["model"] == "duck-gpt-4o-mini"
            assert data["supremeai_engine"] == "dk"
            mock_fallback.assert_called_once_with("prompt needing fallback", model="gpt-4o-mini")
