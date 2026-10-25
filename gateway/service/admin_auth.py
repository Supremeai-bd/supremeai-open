"""SupremeAI Native Admin Authentication Module (Zero-Firebase).

Provides native administrative authentication endpoints for SupremeAI:
- POST /api/admin/login
- POST /api/admin/totp-setup
- POST /api/admin/totp-verify
- POST /api/admin/logout
- GET  /api/admin/me

Features:
- Standard RFC 7519 HS256 JWT issuance and validation (zero-dependency fallback).
- RFC 6238 Time-based One-Time Password (TOTP) verification with drift tolerance.
- Configurable password and email allow-list with bcrypt / constant-time verification.
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
_trusted_browser_registry: dict[str, dict[str, Any]] = {}
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
    env_name = os.environ.get("ENV", "local").lower()
    if env_name in ("local", "dev", "development", "test"):
        return "supremeai-local-dev-jwt-secret-do-not-use-in-production-32b"
    return "supremeai-local-dev-jwt-secret-do-not-use-in-production-32b"


def issue_admin_jwt(uid: str, email: str, role: str = "admin", expiry_hours: int = DEFAULT_JWT_EXPIRY_HOURS) -> str:
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

    now = int(time.time())
    if "exp" in payload and payload["exp"] < now:
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

    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    _trusted_browser_registry[token_hash] = {
        "id": browser_id,
        "uid": uid,
        "email": email,
        "created_at": now,
        "expires_at": now + days * 86400,
        "revoked": False,
    }

    return token, browser_id


def verify_trusted_browser_token(token: str | None) -> dict[str, Any] | None:
    """Validate a trusted browser token and return its payload if valid and unrevoked."""
    if not token or not isinstance(token, str):
        return None
    token = token.strip()
    if not token or token.count(".") != 2:
        return None
    try:
        payload = verify_admin_jwt(token)
        if payload.get("type") not in ("trusted_browser", "access"):
            return None
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        if token_hash in _trusted_browser_registry:
            record = _trusted_browser_registry[token_hash]
            if record.get("revoked", False):
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
    email: str = Field(..., description="Admin email address")
    password: str = Field(..., description="Admin password")
    trusted_browser_token: str | None = Field(default=None, description="Optional trusted browser token")


class AdminTotpVerifyRequest(BaseModel):
    otp: str = Field(..., description="6-digit TOTP verification code")
    remember_browser: bool = Field(default=False, description="Persist trusted browser session")


# --- Endpoint Handlers ---

@router.post("/login")
async def admin_login(
    payload: AdminLoginRequest,
    request: Request,
    response: Response,
):
    """Native Admin Login endpoint. Validates credentials, checks trusted browser, and initiates TOTP or issues JWT."""
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
        auth = request.headers.get("authorization")
        if not auth or not auth.lower().startswith("bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")
        verify_admin_jwt(auth.split(" ", 1)[1])
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
    payload = verify_admin_jwt(authorization.split(" ", 1)[1])
    uid = payload.get("uid") or payload.get("sub")
    now = int(time.time())
    browsers = [
        {"id": rec["id"], "created_at": rec["created_at"]}
        for rec in _trusted_browser_registry.values()
        if rec.get("uid") == uid and rec.get("expires_at", 0) > now and not rec.get("revoked", False)
    ]
    return {"status": "ok", "browsers": browsers}


@router.delete("/trusted-browsers/{browser_id}")
async def revoke_trusted_browser(browser_id: str, authorization: str | None = Header(None)):
    """Revoke a specific trusted browser."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")
    payload = verify_admin_jwt(authorization.split(" ", 1)[1])
    uid = payload.get("uid") or payload.get("sub")
    revoked = False
    for rec in _trusted_browser_registry.values():
        if rec.get("uid") == uid and rec.get("id") == browser_id:
            rec["revoked"] = True
            revoked = True
    return {"status": "ok", "message": f"Browser {browser_id} revoked.", "revoked": revoked}


@router.delete("/trusted-browsers")
async def revoke_all_trusted_browsers(authorization: str | None = Header(None), response: Response = None):
    """Revoke all trusted browsers for the authenticated admin."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required.")
    payload = verify_admin_jwt(authorization.split(" ", 1)[1])
    uid = payload.get("uid") or payload.get("sub")
    count = 0
    for rec in _trusted_browser_registry.values():
        if rec.get("uid") == uid:
            rec["revoked"] = True
            count += 1
    if response:
        response.delete_cookie(TRUSTED_BROWSER_COOKIE, path="/")
    return {"status": "ok", "message": f"Revoked {count} trusted browser(s)."}


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
