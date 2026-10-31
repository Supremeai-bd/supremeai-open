"""Tests for Native Admin Auth (Zero-Firebase).

Verifies:
- POST /api/admin/login (validation, credential checking, direct vs TOTP flow)
- POST /api/admin/totp-setup (secret generation & provisioning URI)
- POST /api/admin/totp-verify (valid vs invalid TOTP code, JWT issuance)
- POST /api/admin/logout (session cleanup)
- GET  /api/admin/me (Bearer token verification)
"""

from __future__ import annotations

import sys
import asyncio
import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
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
    # Repo root ONLY (tests/conftest.py also does this). Never insert the
    # gateway/ package dir itself: it forks gateway.service.* into duplicate
    # module objects (split-brain singletons — drift class F-K, order-dependent
    # suite failures). The laddered imports below fall back to gateway.* forms.
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
        check_totp,
        generate_totp_secret,
        issue_admin_jwt,
        verify_admin_jwt,
    )
except ImportError:
    from gateway.admin_auth import (
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



def _compute_totp(secret: str) -> str:
    """Compute a valid RFC 6238 code for a base32 secret (shared test helper)."""
    import base64
    import hashlib
    import hmac
    import struct
    import time

    clean_secret = secret.strip().upper()
    missing_padding = len(clean_secret) % 8
    if missing_padding:
        clean_secret += "=" * (8 - missing_padding)
    key = base64.b32decode(clean_secret)
    current_time = int(time.time() // 30)
    msg = struct.pack(">Q", current_time)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[19] & 15
    code_num = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{code_num % 1000000:06d}"


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

    # 4. Valid verify code with newly generated setup secret succeeds
    import base64
    import hashlib
    import hmac
    import struct
    import time
    clean_secret = setup_data["secret"].strip().upper()
    missing_padding = len(clean_secret) % 8
    if missing_padding:
        clean_secret += "=" * (8 - missing_padding)
    key = base64.b32decode(clean_secret)
    current_time = int(time.time() // 30)
    msg = struct.pack(">Q", current_time)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[19] & 15
    code_num = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    valid_otp = f"{code_num % 1000000:06d}"

    good_verify = client.post("/api/admin/totp-verify", json={"otp": valid_otp})
    assert good_verify.status_code == 200
    assert good_verify.json()["status"] == "success"
    assert "token" in good_verify.json()


def test_admin_logout(client):
    res = client.post("/api/admin/logout")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_trusted_browser_full_lifecycle(client, monkeypatch):
    import base64
    import hashlib
    import hmac
    import struct
    import time

    monkeypatch.setenv("ADMIN_ENFORCE_TOTP", "true")
    monkeypatch.delenv("SUPREMEAI_ADMIN_TOTP_SECRET", raising=False)

    # 1. Initiate setup
    setup_res = client.post("/api/admin/totp-setup")
    assert setup_res.status_code == 200
    secret = setup_res.json()["secret"]

    # Calculate valid OTP
    clean_secret = secret.strip().upper()
    missing_padding = len(clean_secret) % 8
    if missing_padding:
        clean_secret += "=" * (8 - missing_padding)
    key = base64.b32decode(clean_secret)
    current_time = int(time.time() // 30)
    msg = struct.pack(">Q", current_time)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[19] & 15
    code_num = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
    valid_otp = f"{code_num % 1000000:06d}"

    # 2. Verify with remember_browser=True
    verify_res = client.post(
        "/api/admin/totp-verify",
        json={"otp": valid_otp, "remember_browser": True},
    )
    assert verify_res.status_code == 200
    data = verify_res.json()
    assert data["status"] == "success"
    assert "trusted_browser_token" in data
    trusted_token = data["trusted_browser_token"]
    admin_token = data["token"]

    # Verify cookie was set
    assert "supreme_admin_trusted_browser" in verify_res.cookies

    # 3. Next login with trusted_browser_token in body bypasses TOTP!
    login_res = client.post(
        "/api/admin/login",
        json={
            "email": "admin@supremeai.com",
            "password": "secret123",
            "trusted_browser_token": trusted_token,
        },
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["status"] == "trusted_browser"
    assert "token" in login_data

    # 4. Login with X-Trusted-Browser header bypasses TOTP!
    header_res = client.post(
        "/api/admin/login",
        json={"email": "admin@supremeai.com", "password": "secret123"},
        headers={"X-Trusted-Browser": trusted_token},
    )
    assert header_res.status_code == 200
    assert header_res.json()["status"] == "trusted_browser"

    # 5. List trusted browsers
    list_res = client.get(
        "/api/admin/trusted-browsers",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert list_res.status_code == 200
    browsers = list_res.json().get("browsers", [])
    assert len(browsers) >= 1
    browser_id = browsers[0]["id"]

    # 6. Revoke trusted browser
    del_res = client.delete(
        f"/api/admin/trusted-browsers/{browser_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert del_res.status_code == 200
    assert del_res.json()["revoked"] is True

    # 7. Login after revocation prompts for TOTP again!
    revoked_login = client.post(
        "/api/admin/login",
        json={
            "email": "admin@supremeai.com",
            "password": "secret123",
            "trusted_browser_token": trusted_token,
        },
    )
    assert revoked_login.status_code == 200
    assert revoked_login.json()["status"] in ("otp_required", "totp_setup_required")




# ── Code-only gate + DB-backed trust (SQLite persistence) ────────────────────
# বাংলা: user dashboard থেকে admin-এ ঢুকতে শুধু authentication code; ৭-দিন
# trust ডাটাবেসে থাকে (restart-প্রতিরোধী); কোনো bypass নেই — fail-closed।


def _fresh_setup_otp(client) -> str:
    """Fresh TOTP enrollment → compute a valid OTP from the pending secret.

    বাংলা: টেস্ট-নিরোধক (isolation) — pending setup cache-ই একমাত্র সত্য,
    অন্য টেস্টের env/secret অবস্থার উপর নির্ভর করে না।
    """
    setup = client.post("/api/admin/totp-setup")
    assert setup.status_code == 200
    return _compute_totp(setup.json()["secret"])


def test_trusted_browser_code_free_reentry_without_credentials(client):
    # 1. First entry: code is mandatory (remember_browser=true → DB trust)
    first = client.post(
        "/api/admin/totp-verify",
        json={"otp": _fresh_setup_otp(client), "remember_browser": True},
    )
    assert first.status_code == 200
    raw_token = first.json()["trusted_browser_token"]

    # 2. Re-entry with ONLY the trusted token — no email, no password
    re_entry = client.post("/api/admin/login", json={"trusted_browser_token": raw_token})
    assert re_entry.status_code == 200
    re_data = re_entry.json()
    assert re_data["status"] == "trusted_browser"
    assert re_data["role"] == "admin"

    # 3. The issued JWT is a real admin JWT
    me = client.get("/api/admin/me", headers={"Authorization": f"Bearer {re_data['token']}"})
    assert me.status_code == 200
    assert me.json()["admin"]["role"] == "admin"


def test_trusted_browser_unknown_token_fail_closed(client):
    # Unknown token + no credentials → 401, never a JWT (no bypass)
    bad = client.post("/api/admin/login", json={"trusted_browser_token": "not-a-real-token"})
    assert bad.status_code == 401
    assert "expired" in bad.json().get("detail", "").lower() or "invalid" in bad.json().get("detail", "").lower()


def test_totp_verify_without_remember_issues_no_trust(client):
    res = client.post(
        "/api/admin/totp-verify",
        json={"otp": _fresh_setup_otp(client), "remember_browser": False},
    )
    assert res.status_code == 200
    assert "trusted_browser_token" not in res.json()


def test_trusted_browser_revoke_via_raw_token_header(client):
    first = client.post(
        "/api/admin/totp-verify",
        json={"otp": _fresh_setup_otp(client), "remember_browser": True},
    )
    raw_token = first.json()["trusted_browser_token"]

    # Possession of the raw token = right to revoke (LOCK button path)
    revoke = client.delete(
        "/api/admin/trusted-browsers",
        headers={"X-Trusted-Browser-Token": raw_token},
    )
    assert revoke.status_code == 200
    assert revoke.json()["revoked"] is True

    # Revoked token no longer re-enters — fail-closed
    re_entry = client.post("/api/admin/login", json={"trusted_browser_token": raw_token})
    assert re_entry.status_code == 401


def test_trusted_browser_revoke_requires_token_or_bearer(client):
    res = client.delete("/api/admin/trusted-browsers")
    assert res.status_code == 401


# Tenant administration is granted only from Supabase server-managed app_metadata.
def _admin_auth_module():
    from gateway.service import admin_auth

    return admin_auth


def test_tenant_jwt_carries_only_explicit_server_tenant_claim(monkeypatch):
    monkeypatch.setenv("SUPREMEAI_JWT_SECRET", "test-jwt-secret-for-native-admin-tests")
    tenant_token = issue_admin_jwt(
        uid="tenant-user-1",
        email="manager@example.com",
        role="tenant_admin",
        expiry_hours=1,
        tenant_id="tenant-1",
    )
    tenant_claims = verify_admin_jwt(tenant_token)
    assert tenant_claims["role"] == "tenant_admin"
    assert tenant_claims["tenant_id"] == "tenant-1"

    owner_token = issue_admin_jwt(uid="admin-root-001", email="admin@supremeai.com")
    owner_claims = verify_admin_jwt(owner_token)
    assert owner_claims["role"] == "admin"
    assert "tenant_id" not in owner_claims


def test_verify_admin_jwt_requires_expiration(monkeypatch):
    auth = _admin_auth_module()
    secret = "test-jwt-secret-for-native-admin-tests"
    monkeypatch.setenv("SUPREMEAI_JWT_SECRET", secret)
    header = auth._b64url_encode(b'{"alg":"HS256","typ":"JWT"}')
    payload = auth._b64url_encode(json.dumps({"sub": "user-1", "role": "admin"}).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = auth._b64url_encode(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())

    with pytest.raises(HTTPException) as exc_info:
        auth.verify_admin_jwt(f"{header}.{payload}.{signature}")
    assert exc_info.value.status_code == 401


def test_tenant_login_uses_app_metadata_and_ignores_user_metadata(client, monkeypatch):
    auth = _admin_auth_module()

    async def fake_login(email, password):
        assert email == "manager@example.com"
        assert password == "tenant-password"
        return {
            "id": "supabase-user-1",
            "email": email,
            "app_metadata": {"role": "tenant_admin", "tenant_id": "tenant-1"},
            "user_metadata": {"role": "admin", "tenant_id": "tenant-other"},
        }

    async def fake_tenant(tenant_id):
        assert tenant_id == "tenant-1"
        return {"tenant_id": tenant_id, "org_name": "Tenant One"}

    monkeypatch.setattr(auth, "_supabase_password_login", fake_login)
    monkeypatch.setattr(auth, "_tenant_record", fake_tenant)
    response = client.post(
        "/api/admin/tenant-login",
        json={"email": "manager@example.com", "password": "tenant-password"},
    )

    assert response.status_code == 200
    result = response.json()
    claims = verify_admin_jwt(result["token"])
    assert result["role"] == "tenant_admin"
    assert claims["sub"] == "supabase-user-1"
    assert claims["tenant_id"] == "tenant-1"
    assert claims["role"] == "tenant_admin"
    assert "refresh_token" not in result


def test_tenant_login_rejects_user_metadata_only_role_or_tenant(client, monkeypatch):
    auth = _admin_auth_module()

    async def fake_login(email, password):
        return {
            "id": "supabase-user-2",
            "email": email,
            "app_metadata": {},
            "user_metadata": {"role": "tenant_admin", "tenant_id": "tenant-1"},
        }

    monkeypatch.setattr(auth, "_supabase_password_login", fake_login)
    response = client.post(
        "/api/admin/tenant-login",
        json={"email": "user@example.com", "password": "password"},
    )
    assert response.status_code == 403
    assert "token" not in response.json()


def test_tenant_login_rejects_mismatched_tenant_row(client, monkeypatch):
    auth = _admin_auth_module()

    async def fake_login(email, password):
        return {
            "id": "supabase-user-3",
            "email": email,
            "app_metadata": {"role": "tenant_admin", "tenant_id": "tenant-3"},
        }

    async def mismatched_tenant(tenant_id):
        return {"tenant_id": "tenant-other"}

    monkeypatch.setattr(auth, "_supabase_password_login", fake_login)
    monkeypatch.setattr(auth, "_tenant_record", mismatched_tenant)
    response = client.post(
        "/api/admin/tenant-login",
        json={"email": "manager@example.com", "password": "password"},
    )
    assert response.status_code == 403
    assert "token" not in response.json()


def test_tenant_dashboard_scope_comes_from_token_not_query(client, monkeypatch):
    auth = _admin_auth_module()
    seen = []

    async def fake_tenant(tenant_id):
        seen.append(tenant_id)
        return {"tenant_id": tenant_id, "org_name": "Tenant One"}

    async def fake_usage(tenant_id):
        assert tenant_id == "tenant-1"
        return {"tenant_id": tenant_id, "requests_today": 4, "tokens_today": 80, "cost_today": 0.02}

    monkeypatch.setattr(auth, "_tenant_record", fake_tenant)
    monkeypatch.setattr(auth, "_tenant_usage", fake_usage)
    token = issue_admin_jwt(
        uid="tenant-user-1",
        email="manager@example.com",
        role="tenant_admin",
        expiry_hours=1,
        tenant_id="tenant-1",
    )
    response = client.get(
        "/api/admin/tenant-dashboard?tenant_id=tenant-other",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["tenant"]["tenant_id"] == "tenant-1"
    assert result["usage"]["tenant_id"] == "tenant-1"
    assert seen == ["tenant-1"]


def test_tenant_admin_cannot_read_platform_overview(client, monkeypatch):
    auth = _admin_auth_module()
    token = issue_admin_jwt(
        uid="tenant-user-1",
        email="manager@example.com",
        role="tenant_admin",
        expiry_hours=1,
        tenant_id="tenant-1",
    )

    async def unexpected_query(*args, **kwargs):
        raise AssertionError("unauthorized platform query must not run")

    monkeypatch.setattr(auth, "_supabase_rows", unexpected_query)
    response = client.get("/api/admin/tenant-overview", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_platform_tenant_overview_is_owner_only_and_sanitized(client, monkeypatch):
    auth = _admin_auth_module()
    queried = []

    async def fake_rows(table, params):
        queried.append(table)
        if table == "tenant_limits":
            return [{
                "tenant_id": "tenant-1",
                "org_name": "Tenant One",
                "billing_tier": "pro",
                "created_at": "2026-11-01T00:00:00Z",
                "service_secret": "must-not-leak",
            }]
        return [{"tenant_id": "tenant-1", "requests_count": 7, "tokens_used": 120, "cost_incurred": 0.04}]

    monkeypatch.setattr(auth, "_supabase_rows", fake_rows)
    owner_token = issue_admin_jwt(uid="admin-root-001", email="admin@supremeai.com", role="admin")
    response = client.get("/api/admin/tenant-overview", headers={"Authorization": f"Bearer {owner_token}"})

    assert response.status_code == 200
    result = response.json()
    assert result["scope"] == "platform"
    assert result["total"] == 1
    assert result["tenants"][0]["org_name"] == "Tenant One"
    assert "service_secret" not in result["tenants"][0]
    assert result["usages"][0]["requests_today"] == 7
    assert queried == ["tenant_limits", "tenant_usage"]

    other_admin = issue_admin_jwt(uid="other", email="not-owner@example.com", role="admin")
    denied = client.get("/api/admin/tenant-overview", headers={"Authorization": f"Bearer {other_admin}"})
    assert denied.status_code == 403


def test_tenant_admin_cannot_use_owner_totp_or_trusted_browser_routes(client, monkeypatch):
    monkeypatch.setenv("ENV", "production")
    token = issue_admin_jwt(
        uid="tenant-user-1",
        email="manager@example.com",
        role="tenant_admin",
        expiry_hours=1,
        tenant_id="tenant-1",
    )
    headers = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/admin/totp-setup", headers=headers).status_code == 403
    assert client.get("/api/admin/trusted-browsers", headers=headers).status_code == 403
    assert client.delete("/api/admin/trusted-browsers/browser-1", headers=headers).status_code == 403
    assert client.delete("/api/admin/trusted-browsers", headers=headers).status_code == 403


def test_supabase_mfa_challenge_is_not_bypassed(monkeypatch):
    import httpx

    auth = _admin_auth_module()
    monkeypatch.setattr(auth, "_supabase_base_url", lambda: "https://project.supabase.co")
    monkeypatch.setattr(auth, "get_vault_secret", lambda _name: "test-anon-key")

    class FakeResponse:
        status_code = 200
        is_success = True

        @staticmethod
        def json():
            return {
                "user": {"id": "tenant-user", "app_metadata": {"role": "tenant_admin", "tenant_id": "tenant-1"}},
                "mfa": {"type": "totp", "totp": {"challenge_id": "challenge-1"}},
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth._supabase_password_login("manager@example.com", "password"))
    assert exc_info.value.status_code == 403
