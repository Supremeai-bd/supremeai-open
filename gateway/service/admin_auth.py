"""SupremeAI Native Admin Authentication Module (Zero-Firebase).

Provides native administrative authentication endpoints for SupremeAI:
- POST   /api/admin/login
- POST   /api/admin/totp-setup
- POST   /api/admin/totp-verify
- POST   /api/admin/logout
- GET    /api/admin/me
- GET    /api/admin/trusted-browsers
- DELETE /api/admin/trusted-browsers/{browser_id}
- DELETE /api/admin/trusted-browsers

Features:
- Standard RFC 7519 HS256 JWT issuance and validation (zero-dependency fallback).
- RFC 6238 Time-based One-Time Password (TOTP) verification with drift tolerance.
- Configurable password and email allow-list with bcrypt / constant-time verification.
- বাংলা: trusted-browser ৭-দিন মনে-রাখো এখন SQLite ডাটাবেসে (trusted_browsers
  টেবিল, SHA-256 হ্যাশ) — আগের in-memory registry restart-এ হারিয়ে যেত।
- বাংলা (code-only gate): login-এ বৈধ trusted token (body/header/cookie)
  থাকলে email/password ছাড়াই admin JWT — user dashboard থেকে admin-এ ঢুকতে
  শুধু authentication code যথেষ্ট। টোকেন অবৈধ আর credential না থাকলে
  fail-closed 401 — কোনো bypass নেই, প্রথমবার code দেওয়া বাধ্যতামূলক।
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import secrets
import struct
import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

import urllib.parse
import urllib.request

logger = logging.getLogger("supremeai.admin_auth")

# Router for native admin endpoints
router = APIRouter(prefix="/api/admin", tags=["admin-auth"])

DEFAULT_JWT_EXPIRY_HOURS = 24
DEFAULT_TRUSTED_BROWSER_DAYS = 7
TRUSTED_BROWSER_COOKIE = "supreme_admin_trusted_browser"
DEFAULT_ADMIN_EMAIL = "admin@supremeai.com"
PRIMARY_OWNER_EMAIL = "niloyjoy7@gmail.com"
DEFAULT_ADMIN_UID = "admin-root-001"

# In-memory registry for trusted browser sessions (multi-tier persistence)
# বাংলা: in-memory registry SQLite-এ উন্নীত — restart-এও ৭-দিন trust টেকে
# ("database e browser save hoa thakbe" — ইউজারের চাহিদা অনুযায়ী)।
try:  # pragma: no cover - import fallback mirrors service/app.py
    from service.storage import (
        get_valid_trusted_browser,
        list_trusted_browsers_for_user,
        purge_expired_trusted_browsers,
        revoke_all_trusted_browsers_for_user,
        revoke_trusted_browser_by_hash,
        revoke_trusted_browser_by_id,
        save_trusted_browser,
    )
except ImportError:  # pragma: no cover
    try:
        from gateway.service.storage import (
            get_valid_trusted_browser,
            list_trusted_browsers_for_user,
            purge_expired_trusted_browsers,
            revoke_all_trusted_browsers_for_user,
            revoke_trusted_browser_by_hash,
            revoke_trusted_browser_by_id,
            save_trusted_browser,
        )
    except ImportError:  # pragma: no cover - fail-closed without persistence
        get_valid_trusted_browser = None  # type: ignore[assignment]
        list_trusted_browsers_for_user = None  # type: ignore[assignment]
        purge_expired_trusted_browsers = None  # type: ignore[assignment]
        revoke_all_trusted_browsers_for_user = None  # type: ignore[assignment]
        revoke_trusted_browser_by_hash = None  # type: ignore[assignment]
        revoke_trusted_browser_by_id = None  # type: ignore[assignment]
        save_trusted_browser = None  # type: ignore[assignment]


def _hash_trusted_token(token: str) -> str:
    """SHA-256 hex digest — raw trusted-browser tokens are NEVER stored."""
    return hashlib.sha256(token.encode("ascii")).hexdigest()


_pending_totp_setups: dict[str, dict[str, Any]] = {}
_vault_cache: dict[str, str] = {}


def get_vault_secret(key_name: str) -> str | None:
    """Read a secret from os.environ, falling back to Infisical Vault if configured."""
    val = os.environ.get(key_name)
    if val:
        return val.strip()
    if key_name in _vault_cache:
        return _vault_cache[key_name]

    client_id = os.environ.get("INFISICAL_CLIENT_ID")
    client_secret = os.environ.get("INFISICAL_CLIENT_SECRET")
    project_id = os.environ.get("INFISICAL_PROJECT_ID")
    env = os.environ.get("INFISICAL_ENV", "prod")

    if client_id and client_secret and project_id:
        try:
            req_data = json.dumps({"clientId": client_id, "clientSecret": client_secret}).encode("utf-8")
            login_req = urllib.request.Request(
                "https://app.infisical.com/api/v1/auth/universal-auth/login",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(login_req, timeout=10) as resp:
                token = json.load(resp).get("accessToken")

            if token:
                query = urllib.parse.urlencode({"workspaceId": project_id, "environment": env, "secretPath": "/"})
                secret_req = urllib.request.Request(
                    f"https://app.infisical.com/api/v3/secrets/raw?{query}",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    method="GET",
                )
                with urllib.request.urlopen(secret_req, timeout=10) as s_resp:
                    data = json.load(s_resp)
                    for item in data.get("secrets", []):
                        k = item.get("secretKey")
                        v = item.get("secretValue")
                        if k and v:
                            _vault_cache[k] = str(v).strip()
                            if k not in os.environ:
                                os.environ[k] = str(v).strip()
            return _vault_cache.get(key_name)
        except Exception as exc:
            logger.warning("[admin_auth] Infisical secret fetch for %s failed: %s", key_name, exc)
    return None


def _resolve_totp_secret(email: str) -> str | None:
    """Retrieve TOTP secret from pending setups, environment, or Infisical Vault."""
    pending = _pending_totp_setups.get(email)
    if pending and (time.time() - pending.get("created_at", 0) < 600):
        return pending.get("secret")
    return get_vault_secret("SUPREMEAI_ADMIN_TOTP_SECRET")


def _get_cookie_secure_settings() -> tuple[bool, str]:
    """Return (secure, samesite) configuration based on environment."""
    env_name = os.environ.get("ENV", "local").lower()
    is_prod_staging = env_name in ("production", "prod", "staging")
    return is_prod_staging, "none" if is_prod_staging else "lax"


# --- Native HS256 JWT Implementation (Zero-Dependency Safe) ---

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = (4 - len(data) % 4) % 4
    return base64.urlsafe_b64decode(data + "=" * padding)


def get_jwt_secret() -> str:
    secret = (
        get_vault_secret("SUPREMEAI_JWT_SECRET")
        or get_vault_secret("JWT_SECRET")
        or get_vault_secret("SUPREMEAI_MASTER_KEY")
        or get_vault_secret("API_KEY_SIGNING_SECRET")
    )
    if secret:
        return secret
    env_name = os.environ.get("ENV", "").strip().lower()
    if env_name in ("local", "dev", "development", "test"):
        return "supremeai-local-dev-jwt-secret-do-not-use-in-production-32b"
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Admin token signing is not configured.",
    )


def issue_admin_jwt(
    uid: str,
    email: str,
    role: str = "admin",
    expiry_hours: int = DEFAULT_JWT_EXPIRY_HOURS,
    tenant_id: str | None = None,
) -> str:
    """Issue a standard RFC 7519 HS256 JSON Web Token."""
    now = int(time.time())
    payload = {
        "sub": uid,
        "uid": uid,
        "email": email,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + 3600 * expiry_hours,
        "jti": uuid.uuid4().hex,
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    secret = get_jwt_secret().encode("utf-8")
    sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def verify_admin_jwt(token: str) -> dict[str, Any]:
    """Verify an HS256 JWT and return its payload if valid."""
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed JWT token")

    header_b64, payload_b64, sig_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    secret = get_jwt_secret().encode("utf-8")
    expected_sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    provided_sig = _b64url_decode(sig_b64)

    if not hmac.compare_digest(expected_sig, provided_sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token signature")

    try:
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload JSON") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    now = int(time.time())
    expiry = payload.get("exp")
    if isinstance(expiry, bool) or not isinstance(expiry, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expiry is required")
    if expiry <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")

    return payload


def issue_trusted_browser_token(
    uid: str,
    email: str,
    days: int = DEFAULT_TRUSTED_BROWSER_DAYS,
) -> tuple[str, str]:
    """Issue a signed trusted browser token and unique browser ID."""
    now = int(time.time())
    browser_id = uuid.uuid4().hex
    payload = {
        "sub": uid,
        "uid": uid,
        "email": email,
        "type": "trusted_browser",
        "browser_id": browser_id,
        "iat": now,
        "exp": now + days * 86400,
        "jti": uuid.uuid4().hex,
    }
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")

    secret = get_jwt_secret().encode("utf-8")
    sig = hmac.new(secret, signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url_encode(sig)
    token = f"{header_b64}.{payload_b64}.{sig_b64}"

    token_hash = _hash_trusted_token(token)
    if save_trusted_browser is not None:
        save_trusted_browser(
            token_hash=token_hash,
            email=email,
            expires_at=float(now + days * 86400),
            browser_id=browser_id,
            uid=uid,
        )
        if purge_expired_trusted_browsers is not None:
            try:
                purge_expired_trusted_browsers()
            except Exception as exc:  # pragma: no cover - purge is best-effort
                logger.debug("Trusted-browser purge failed: %s", exc)

    return token, browser_id


def verify_trusted_browser_token(token: str | None) -> dict[str, Any] | None:
    """Validate a trusted browser token and return its payload if valid and unrevoked.

    বাংলা: এখন সিদ্ধান্ত হয় SQLite ডাটাবেস থেকে — হ্যাশ টেবিলে থাকতে হবে,
    revoked নয়, মেয়াদোত্তীর্ণ নয়। স্বাক্ষর বৈধ হলেও DB-রেকর্ড না থাকলে
    অগ্রাহ্য (যেমন restart-এর পরে পুরনো সাইন-করা টোকেন ভেতরে ঢুকতে পারবে না)।
    """
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    if not token or token.count(".") != 2:
        return None
    try:
        payload = verify_admin_jwt(token)
        if payload.get("type") not in ("trusted_browser", "access"):
            return None
        token_hash = _hash_trusted_token(token)
        if get_valid_trusted_browser is not None:
            record = get_valid_trusted_browser(token_hash)
            if not record:
                return None
        return payload
    except Exception as exc:
        logger.debug("Trusted browser verification failed: %s", exc)
        return None


# --- RFC 6238 TOTP Engine ---

def generate_totp_secret() -> str:
    """Generate a 16-character base32 secret."""
    return base64.b32encode(secrets.token_bytes(10)).decode("utf-8")


def build_provisioning_uri(email: str, secret: str) -> str:
    """Build an otpauth URI for QR code generation."""
    return f"otpauth://totp/SupremeAI:{email}?secret={secret}&issuer=SupremeAI&digits=6&period=30"


def check_totp(user_otp: str, base32_secret: str) -> bool:
    """Check a 6-digit TOTP code with clock-drift window (-1, 0, +1)."""
    if not user_otp or not base32_secret:
        return False
    try:
        clean_secret = base32_secret.strip().upper()
        missing_padding = len(clean_secret) % 8
        if missing_padding:
            clean_secret += "=" * (8 - missing_padding)
        key = base64.b32decode(clean_secret)
        current_time = int(time.time() // 30)

        for drift in (-1, 0, 1):
            msg = struct.pack(">Q", current_time + drift)
            h = hmac.new(key, msg, hashlib.sha1).digest()
            offset = h[19] & 15
            code_num = struct.unpack(">I", h[offset : offset + 4])[0] & 0x7FFFFFFF
            expected_code = f"{code_num % 1000000:06d}"
            if hmac.compare_digest(expected_code, user_otp.strip()):
                return True
        return False
    except (ValueError, TypeError, struct.error, binascii.Error) as exc:
        logger.debug("TOTP check failed: %s", exc)
        return False


# --- Admin Credential Checks ---

def _get_admin_emails() -> set[str]:
    raw = (
        os.environ.get("ADMIN_EMAILS")
        or os.environ.get("ADMIN_EMAIL")
        or os.environ.get("SUPREMEAI_ADMIN_LOGIN_EMAIL")
        or DEFAULT_ADMIN_EMAIL
    )
    emails = {e.strip().lower() for e in raw.split(",") if e.strip()}
    emails.add(PRIMARY_OWNER_EMAIL.lower())
    emails.add(DEFAULT_ADMIN_EMAIL.lower())
    return emails


def _verify_password(provided_password: str) -> bool:
    """Verify admin password against environment variables."""
    # 1. Plaintext password check from env
    env_pass = os.environ.get("SUPREMEAI_ADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD")
    if env_pass:
        return hmac.compare_digest(provided_password, env_pass)

    # 2. Bcrypt hash check from env if bcrypt is installed
    pass_hash = os.environ.get("SUPREMEAI_ADMIN_PASSWORD_HASH") or os.environ.get("ADMIN_PASSWORD_HASH")
    if pass_hash:
        try:
            import bcrypt
            return bcrypt.checkpw(provided_password.encode("utf-8"), pass_hash.encode("utf-8"))
        except (ImportError, ValueError, TypeError) as exc:
            logger.debug("Bcrypt check failed or not available: %s", exc)

    # FIX(auth 2026-10-24): removed the hardcoded fallback ("admin123",
    # "supremeadmin", "password") — it allowed full admin login on any deployment
    # that had not set SUPREMEAI_ADMIN_PASSWORD. Fail-closed instead.
    return False


# In-memory session store for TOTP setup state across requests (keyed by email)
_pending_totp_setups: dict[str, dict[str, Any]] = {}


# --- Request/Response Models ---

class AdminLoginRequest(BaseModel):
    # বাংলা: code-only যুগে email/password ঐচ্ছিক — বৈধ trusted-browser
    # টোকেনে পুনঃপ্রবেশে এগুলোর দরকার নেই; credential পথে দুটোই বাধ্যতামূলক
    # (নিচে 400 ভেরিফিকেশন অক্ষুণ্ণ)।
    email: str = Field(default="", description="Admin email address")
    password: str = Field(default="", description="Admin password")
    trusted_browser_token: str | None = Field(default=None, description="Optional trusted browser token")


class AdminTotpVerifyRequest(BaseModel):
    otp: str = Field(..., description="6-digit TOTP verification code")
    remember_browser: bool = Field(default=False, description="Persist trusted browser session")


class TenantAdminLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=1024)


def _clean_tenant_id(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if (
        not candidate
        or len(candidate) > 128
        or not candidate[0].isascii()
        or not candidate[0].isalnum()
        or any(not char.isascii() or not (char.isalnum() or char in "_-") for char in candidate)
    ):
        return None
    return candidate


def _validated_bearer_claims(authorization: str | None) -> dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")
    claims = verify_admin_jwt(authorization.split(" ", 1)[1])
    if claims.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token.")
    return claims


def _require_tenant_admin(authorization: str | None) -> tuple[dict[str, Any], str]:
    claims = _validated_bearer_claims(authorization)
    tenant_id = _clean_tenant_id(claims.get("tenant_id"))
    if claims.get("role") != "tenant_admin" or not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant administrator access required.")
    return claims, tenant_id


def _require_platform_owner(authorization: str | None) -> dict[str, Any]:
    claims = _validated_bearer_claims(authorization)
    email = str(claims.get("email") or "").strip().lower()
    allowed = {item.lower() for item in _get_admin_emails()}
    if claims.get("role") != "admin" or not email or email not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform owner access required.")
    return claims


def _supabase_base_url() -> str:
    value = get_vault_secret("SUPABASE_URL") or ""
    if not value.startswith("https://"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tenant administration is unavailable.")
    return value.rstrip("/")


async def _supabase_password_login(email: str, password: str) -> dict[str, Any]:
    import httpx

    base_url = _supabase_base_url()
    api_key = get_vault_secret("SUPABASE_ANON_KEY") or get_vault_secret("SUPABASE_KEY")
    if not api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tenant authentication is unavailable.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
            response = await client.post(
                f"{base_url}/auth/v1/token",
                params={"grant_type": "password"},
                headers={"apikey": api_key, "Content-Type": "application/json"},
                json={"email": email, "password": password},
            )
    except httpx.HTTPError as exc:
        logger.warning("Supabase tenant authentication request failed: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tenant authentication is unavailable.") from None
    if response.status_code in (400, 401):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    if not response.is_success:
        logger.warning("Supabase tenant authentication returned HTTP %s", response.status_code)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tenant authentication is unavailable.")
    try:
        auth_result = response.json()
    except ValueError:
        auth_result = None
    if not isinstance(auth_result, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    if auth_result.get("mfa_required") or auth_result.get("mfa") or auth_result.get("mfa_factors"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Additional Supabase verification is required and cannot be completed in this sign-in flow.",
        )
    user = auth_result.get("user")
    if not isinstance(user, dict):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    return user


async def _supabase_rows(table: str, params: dict[str, str]) -> list[dict[str, Any]]:
    import httpx

    if table not in {"tenant_limits", "tenant_usage"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported tenant data request.")
    base_url = _supabase_base_url()
    service_key = get_vault_secret("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tenant administration is unavailable.")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0)) as client:
            response = await client.get(
                f"{base_url}/rest/v1/{table}",
                params=params,
                headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("Supabase tenant data request failed for %s: %s", table, type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tenant data is temporarily unavailable.") from None
    if not response.is_success:
        logger.warning("Supabase tenant data query for %s returned HTTP %s", table, response.status_code)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tenant data is temporarily unavailable.")
    try:
        rows = response.json()
    except ValueError:
        rows = None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Tenant data is temporarily unavailable.")
    return rows


async def _tenant_record(tenant_id: str) -> dict[str, Any] | None:
    rows = await _supabase_rows(
        "tenant_limits",
        {
            "select": "tenant_id,org_name,billing_tier,created_at,requests_per_minute,max_tokens_per_day,max_concurrent_sessions",
            "tenant_id": f"eq.{tenant_id}",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


async def _tenant_usage(tenant_id: str) -> dict[str, Any]:
    today = time.strftime("%Y-%m-%d", time.gmtime())
    rows = await _supabase_rows(
        "tenant_usage",
        {
            "select": "tenant_id,requests_count,tokens_used,cost_incurred",
            "tenant_id": f"eq.{tenant_id}",
            "date": f"eq.{today}",
            "limit": "1",
        },
    )
    row = rows[0] if rows else {}
    return {
        "tenant_id": tenant_id,
        "requests_today": int(row.get("requests_count") or 0),
        "tokens_today": int(row.get("tokens_used") or 0),
        "cost_today": float(row.get("cost_incurred") or 0.0),
    }


@router.post("/tenant-login")
async def tenant_admin_login(payload: TenantAdminLoginRequest):
    email = payload.email.strip().lower()
    if not email or any(ord(char) < 32 for char in email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valid email is required.")
    user = await _supabase_password_login(email, payload.password)
    app_metadata = user.get("app_metadata")
    if not isinstance(app_metadata, dict) or app_metadata.get("role") != "tenant_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant administrator access required.")
    tenant_id = _clean_tenant_id(app_metadata.get("tenant_id"))
    uid = user.get("id")
    if not tenant_id or not isinstance(uid, str) or not uid.strip():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant administrator assignment is not configured.")
    tenant = await _tenant_record(tenant_id)
    if tenant is None or _clean_tenant_id(tenant.get("tenant_id")) != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant administrator assignment is not configured.")
    session_email = str(user.get("email") or email).strip().lower()
    token = issue_admin_jwt(
        uid=uid.strip(),
        email=session_email,
        role="tenant_admin",
        expiry_hours=1,
        tenant_id=tenant_id,
    )
    return {"status": "authenticated", "token": token, "role": "tenant_admin", "email": session_email}


@router.get("/tenant-dashboard")
async def tenant_admin_dashboard(authorization: str | None = Header(None)):
    _claims, tenant_id = _require_tenant_admin(authorization)
    tenant = await _tenant_record(tenant_id)
    if tenant is None or _clean_tenant_id(tenant.get("tenant_id")) != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant dashboard is unavailable.")
    return {"scope": "tenant", "role": "tenant_admin", "tenant": tenant, "usage": await _tenant_usage(tenant_id)}


@router.get("/tenant-overview")
async def platform_tenant_overview(authorization: str | None = Header(None)):
    _require_platform_owner(authorization)
    tenants = await _supabase_rows(
        "tenant_limits",
        {
            "select": "tenant_id,org_name,billing_tier,created_at,requests_per_minute,max_tokens_per_day,max_concurrent_sessions",
            "order": "created_at.desc",
            "limit": "1000",
        },
    )
    today = time.strftime("%Y-%m-%d", time.gmtime())
    usage_rows = await _supabase_rows(
        "tenant_usage",
        {"select": "tenant_id,requests_count,tokens_used,cost_incurred", "date": f"eq.{today}", "limit": "1000"},
    )
    usage_by_tenant = {
        str(row.get("tenant_id")): {
            "tenant_id": str(row.get("tenant_id")),
            "requests_today": int(row.get("requests_count") or 0),
            "tokens_today": int(row.get("tokens_used") or 0),
            "cost_today": float(row.get("cost_incurred") or 0.0),
        }
        for row in usage_rows
        if row.get("tenant_id")
    }
    safe_tenants = [
        {key: row.get(key) for key in (
            "tenant_id", "org_name", "billing_tier", "created_at",
            "requests_per_minute", "max_tokens_per_day", "max_concurrent_sessions",
        )}
        for row in tenants
        if _clean_tenant_id(row.get("tenant_id"))
    ]
    usages = [
        usage_by_tenant.get(
            str(row["tenant_id"]),
            {"tenant_id": str(row["tenant_id"]), "requests_today": 0, "tokens_today": 0, "cost_today": 0.0},
        )
        for row in safe_tenants
    ]
    return {"scope": "platform", "total": len(safe_tenants), "tenants": safe_tenants, "usages": usages, "truncated": len(tenants) == 1000}


# --- Endpoint Handlers ---

@router.post("/login")
async def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
):
    """Native Admin Login endpoint. Validates credentials, checks trusted browser, and initiates TOTP or issues JWT.

    বাংলা (code-only gate): বৈধ trusted-browser টোকেন (body / X-Trusted-Browser
    header / HttpOnly cookie) থাকলে email/password ছাড়াই admin JWT — ৭ দিনের
    মেয়াদের মধ্যে বার বার authentication code দিতে হয় না। টোকেন অবৈধ আর
    credential অনুপস্থিত হলে fail-closed 401 — কোনো bypass নেই।
    """
    # --- Path 1: DB-backed trusted browser (7-day remember) — BEFORE credentials ---
    trusted_token = (
        payload.trusted_browser_token
        or request.headers.get("X-Trusted-Browser")
        or request.cookies.get(TRUSTED_BROWSER_COOKIE)
    )
    if trusted_token:
        claims = verify_trusted_browser_token(trusted_token)
        if claims:
            trusted_email = (claims.get("email") or "").strip() or DEFAULT_ADMIN_EMAIL
            token = issue_admin_jwt(
                uid=DEFAULT_ADMIN_UID, email=trusted_email, role="admin",
                expiry_hours=DEFAULT_TRUSTED_BROWSER_DAYS * 24,
            )
            secure, samesite = _get_cookie_secure_settings()
            response.set_cookie(
                TRUSTED_BROWSER_COOKIE,
                trusted_token,
                max_age=DEFAULT_TRUSTED_BROWSER_DAYS * 86400,
                httponly=True,
                secure=secure,
                samesite=samesite,
                path="/",
            )
            logger.info("Trusted browser re-entry (code-free) for admin: %s", trusted_email)
            return {
                "status": "trusted_browser",
                "uid": DEFAULT_ADMIN_UID,
                "token": token,
                "role": "admin",
                "email": trusted_email,
            }
        # মেয়াদোত্তীর্ণ/অজানা/revoked টোকেন — credential-ও না থাকলে কিছুই দেওয়া হবে না।
        if not payload.email.strip() or not payload.password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Trusted browser session expired or invalid. Please enter your authentication code again.",
            )

    clean_email = payload.email.strip().lower()
    if not clean_email or not payload.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password are required.",
        )

    allowed_emails = _get_admin_emails()
    # If explicit admin emails configured, enforce email allowlist
    if allowed_emails and clean_email not in allowed_emails and clean_email != DEFAULT_ADMIN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized as admin.",
        )

    if not _verify_password(payload.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials.",
        )

    uid = DEFAULT_ADMIN_UID

    # Check for trusted browser bypass (from payload, header, or cookie)
    trusted_token = (
        payload.trusted_browser_token
        or request.headers.get("X-Trusted-Browser")
        or request.cookies.get(TRUSTED_BROWSER_COOKIE)
    )
    is_trusted = False
    if trusted_token:
        claims = verify_trusted_browser_token(trusted_token)
        if claims:
            token_email = (claims.get("email") or "").lower().strip()
            if not token_email or token_email == clean_email or clean_email in allowed_emails or clean_email == DEFAULT_ADMIN_EMAIL:
                is_trusted = True
                logger.info("Trusted browser verified for admin: %s", clean_email)

    if is_trusted:
        # Issue 7-day token for trusted browser login
        token = issue_admin_jwt(uid=uid, email=clean_email, role="admin", expiry_hours=DEFAULT_TRUSTED_BROWSER_DAYS * 24)
        secure, samesite = _get_cookie_secure_settings()
        response.set_cookie(
            TRUSTED_BROWSER_COOKIE,
            trusted_token,
            max_age=DEFAULT_TRUSTED_BROWSER_DAYS * 86400,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/",
        )
        return {
            "status": "trusted_browser",
            "uid": uid,
            "token": token,
            "role": "admin",
            "email": clean_email,
        }

    # Check if TOTP is required or configured
    totp_secret = _resolve_totp_secret(clean_email)
    enforce_totp = (
        os.environ.get("ADMIN_ENFORCE_TOTP", "false").lower() in ("true", "1", "yes")
        or bool(totp_secret)
    )

    if enforce_totp:
        if not totp_secret:
            # Need to setup TOTP first
            return {"status": "totp_setup_required", "uid": uid, "email": clean_email}
        return {"status": "otp_required", "uid": uid, "email": clean_email}

    # Direct login allowed when TOTP not strictly enforced
    token = issue_admin_jwt(uid=uid, email=clean_email, role="admin")
    return {
        "status": "authenticated",
        "uid": uid,
        "token": token,
        "role": "admin",
        "email": clean_email,
    }


@router.post("/totp-setup")
async def admin_totp_setup(request: Request):
    """Initiate TOTP setup, generating a fresh secret and provisioning URI."""
    env_name = os.environ.get("ENV", "local").lower()
    if env_name not in ("local", "dev", "development", "test"):
        _require_platform_owner(request.headers.get("authorization"))
    secret = generate_totp_secret()
    recovery_codes = [secrets.token_hex(4).upper() for _ in range(4)]
    email = os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    uri = build_provisioning_uri(email=email, secret=secret)

    # Store in pending cache for verification
    _pending_totp_setups[email] = {
        "secret": secret,
        "created_at": time.time(),
        "recovery_codes": recovery_codes,
    }

    return {
        "status": "ok",
        "secret": secret,
        "provisioning_uri": uri,
        "recovery_codes": recovery_codes,
    }


@router.post("/totp-verify")
async def admin_totp_verify(
    payload: AdminTotpVerifyRequest,
    response: Response,
):
    """Verify a 6-digit TOTP code and issue an admin JWT token (with trusted browser persistence)."""
    otp = payload.otp.strip()
    if len(otp) != 6 or not otp.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP must be exactly 6 digits.",
        )

    email = os.environ.get("ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    secret = _resolve_totp_secret(email)
    if not secret:
        # Check fallback global vault secret
        secret = get_vault_secret("SUPREMEAI_ADMIN_TOTP_SECRET")

    # Vault pattern: TOTP secret MUST come from env/vault. No hardcoded
    # fallback (fail-closed) — see secret-scan policy.
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOTP secret not configured.",
        )

    if not check_totp(otp, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid verification code.",
        )

    # Persist the confirmed secret into vault cache so server restarts don't lose enrollment
    if secret:
        _vault_cache["SUPREMEAI_ADMIN_TOTP_SECRET"] = secret

    trusted_token = None
    if payload.remember_browser:
        expiry_hours = DEFAULT_TRUSTED_BROWSER_DAYS * 24
        trusted_token, _ = issue_trusted_browser_token(
            uid=DEFAULT_ADMIN_UID, email=email, days=DEFAULT_TRUSTED_BROWSER_DAYS
        )
        secure, samesite = _get_cookie_secure_settings()
        response.set_cookie(
            TRUSTED_BROWSER_COOKIE,
            trusted_token,
            max_age=DEFAULT_TRUSTED_BROWSER_DAYS * 86400,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/",
        )
    else:
        expiry_hours = DEFAULT_JWT_EXPIRY_HOURS

    token = issue_admin_jwt(uid=DEFAULT_ADMIN_UID, email=email, role="admin", expiry_hours=expiry_hours)
    res_data: dict[str, Any] = {
        "status": "success",
        "token": token,
        "role": "admin",
    }
    if trusted_token:
        res_data["trusted_browser_token"] = trusted_token
    return res_data


@router.get("/trusted-browsers")
async def list_trusted_browsers(authorization: str | None = Header(None)):
    """List active trusted browsers for the authenticated admin."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")
    payload = _require_platform_owner(authorization)
    uid = payload.get("uid") or payload.get("sub")
    browsers = list_trusted_browsers_for_user(uid) if list_trusted_browsers_for_user else []
    return {"status": "ok", "browsers": browsers}


@router.delete("/trusted-browsers/{browser_id}")
async def revoke_trusted_browser(browser_id: str, authorization: str | None = Header(None)):
    """Revoke a specific trusted browser."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")
    payload = _require_platform_owner(authorization)
    uid = payload.get("uid") or payload.get("sub")
    revoked = revoke_trusted_browser_by_id(uid, browser_id) if revoke_trusted_browser_by_id else False
    return {"status": "ok", "message": f"Browser {browser_id} revoked.", "revoked": revoked}


@router.delete("/trusted-browsers")
async def revoke_all_trusted_browsers(
    request: Request,
    authorization: str | None = Header(None),
    response: Response = None,
    payload: dict | None = None,
):
    """Revoke trusted browsers.

    বাংলা: দুই পথ —
    1. Admin Bearer JWT → ঐ uid-এর সব trusted browser revoke (আগের চুক্তি)।
    2. কাঁচা টোকেন উপস্থাপন (X-Trusted-Browser-Token header / body
       {"trusted_browser_token"} / নিজের cookie) → শুধু সেটিই revoke —
       টোকেনের ধারকই বৈধ মালিক; admin session ছাড়াও LOCK/রিভোক করা যায়।
    কোনোটাই না থাকলে 401 (আগের মতোই fail-closed)।
    """
    if authorization and authorization.startswith("Bearer "):
        jwt_payload = _require_platform_owner(authorization)
        uid = jwt_payload.get("uid") or jwt_payload.get("sub")
        count = revoke_all_trusted_browsers_for_user(uid) if revoke_all_trusted_browsers_for_user else 0
        if response:
            response.delete_cookie(TRUSTED_BROWSER_COOKIE, path="/")
        return {"status": "ok", "message": f"Revoked {count} trusted browser(s).", "revoked": count > 0}

    raw = None
    if isinstance(payload, dict):
        raw = payload.get("trusted_browser_token")
    raw = (
        raw
        or request.headers.get("x-trusted-browser-token")
        or request.headers.get("X-Trusted-Browser")
        or request.cookies.get(TRUSTED_BROWSER_COOKIE)
    )
    if raw and raw.strip() and revoke_trusted_browser_by_hash is not None:
        removed = revoke_trusted_browser_by_hash(_hash_trusted_token(raw.strip()))
        if response:
            response.delete_cookie(TRUSTED_BROWSER_COOKIE, path="/")
        return {"status": "ok", "message": "Trusted browser revoked.", "revoked": removed}

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")


@router.post("/logout")
async def admin_logout(response: Response):
    """Stateless Admin Logout endpoint."""
    response.delete_cookie(TRUSTED_BROWSER_COOKIE, path="/")
    return {"status": "ok", "message": "Logged out successfully."}


@router.get("/me")
async def admin_me(authorization: str | None = Header(None)):
    """Retrieve verified session payload for currently authenticated admin."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required.",
        )
    token = authorization.split(" ", 1)[1]
    payload = verify_admin_jwt(token)
    return {"status": "ok", "admin": payload}
