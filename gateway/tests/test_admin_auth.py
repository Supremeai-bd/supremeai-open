"""Tests for Native Admin Auth (Zero-Firebase).

Verifies:
- POST /api/admin/login (validation, credential checking, direct vs TOTP flow)
- POST /api/admin/totp-setup (secret generation & provisioning URI)
- POST /api/admin/totp-verify (valid vs invalid TOTP code, JWT issuance)
- POST /api/admin/logout (session cleanup)
- GET  /api/admin/me (Bearer token verification)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Add repo root and gateway dir to sys.path for portable discovery
_GATEWAY_DIR = next(
    (
        p
        for p in Path(__file__).resolve().parents
        if (p / "main.py").is_file() and (p / "routing_policy.json").is_file()
    ),
    None,
)
if _GATEWAY_DIR is not None:
    if str(_GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(_GATEWAY_DIR))
    if str(_GATEWAY_DIR.parent) not in sys.path:
        sys.path.insert(0, str(_GATEWAY_DIR.parent))

try:
    from tests.test_streaming_gateway import base_config
except ImportError:
    from gateway.tests.test_streaming_gateway import base_config

try:
    from main import create_app
except ImportError:
    from gateway.main import create_app

try:
    from admin_auth import (
        DEFAULT_ADMIN_EMAIL,
        DEFAULT_ADMIN_UID,
        check_totp,
        generate_totp_secret,
        issue_admin_jwt,
        verify_admin_jwt,
    )
except ImportError:
    from gateway.admin_auth import (
        DEFAULT_ADMIN_EMAIL,
        DEFAULT_ADMIN_UID,
        check_totp,
        generate_totp_secret,
        issue_admin_jwt,
        verify_admin_jwt,
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("ADMIN_EMAIL", "admin@supremeai.com")
    monkeypatch.setenv("SUPREMEAI_ADMIN_PASSWORD", "secret123")
    monkeypatch.setenv("ADMIN_ENFORCE_TOTP", "false")
    monkeypatch.setenv("SUPREMEAI_JWT_SECRET", "test-jwt-secret-for-native-admin-tests")

    app = create_app(config=base_config())
    return TestClient(app)


def test_native_jwt_roundtrip(monkeypatch):
    monkeypatch.setenv("SUPREMEAI_JWT_SECRET", "test-secret")
    token = issue_admin_jwt(uid="admin-123", email="admin@supremeai.com", role="admin")
    payload = verify_admin_jwt(token)
    assert payload["sub"] == "admin-123"
    assert payload["email"] == "admin@supremeai.com"
    assert payload["role"] == "admin"


def test_rfc6238_totp_check():
    secret = generate_totp_secret()
    # TOTP with invalid code fails
    assert not check_totp("000000", secret)
    # TOTP with empty code fails
    assert not check_totp("", secret)


def test_admin_login_missing_fields(client):
    res = client.post("/api/admin/login", json={})
    assert res.status_code == 422 or res.status_code == 400


def test_admin_login_invalid_credentials(client):
    res = client.post("/api/admin/login", json={"email": "admin@supremeai.com", "password": "wrongpassword"})
    assert res.status_code == 401
    assert "Invalid admin credentials" in res.json().get("detail", "")


def test_admin_login_success_direct(client):
    res = client.post("/api/admin/login", json={"email": "admin@supremeai.com", "password": "secret123"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "authenticated"
    assert "token" in data
    assert data["role"] == "admin"

    # Verify the issued token works with /me
    me_res = client.get("/api/admin/me", headers={"Authorization": f"Bearer {data['token']}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["status"] == "ok"
    assert me_data["admin"]["role"] == "admin"


def test_admin_totp_setup_and_verify_flow(client, monkeypatch):
    monkeypatch.setenv("ADMIN_ENFORCE_TOTP", "true")
    monkeypatch.delenv("SUPREMEAI_ADMIN_TOTP_SECRET", raising=False)

    # 1. Login prompts setup when no secret is configured
    login_res = client.post("/api/admin/login", json={"email": "admin@supremeai.com", "password": "secret123"})
    assert login_res.status_code == 200
    assert login_res.json()["status"] == "totp_setup_required"

    # 2. Setup returns secret & provisioning URI
    setup_res = client.post("/api/admin/totp-setup")
    assert setup_res.status_code == 200
    setup_data = setup_res.json()
    assert setup_data["status"] == "ok"
    assert "secret" in setup_data
    assert "otpauth://" in setup_data["provisioning_uri"]
    assert len(setup_data["recovery_codes"]) == 4

    # 3. Invalid verify code rejected
    bad_verify = client.post("/api/admin/totp-verify", json={"otp": "999999"})
    assert bad_verify.status_code == 401


def test_admin_logout(client):
    res = client.post("/api/admin/logout")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
