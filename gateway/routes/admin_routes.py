"""This module defines FastAPI routes for the SupremeAI project's administrative interface, providing secure authentication mechanisms, system monitoring, and configuration management. It supports both traditional password-based and Firebase-authenticated admin logins with Time-based One-Time Password (TOTP) verification, alongside endpoints for observing cloud resource distribution, free-tier usage, token budgets, GCP service health, rules engine management, and available AI skills. This centralizes control and visibility for the AI ecosystem's backend operations.

Key Components:
- `router`: The FastAPI APIRouter instance for admin-specific endpoints.
- `_hash_password()`: Hashes a given password using bcrypt.
- `_verify_password()`: Verifies a plain-text password against a bcrypt hash.
- `_get_admin_credentials()`: Retrieves the admin password hash from environment variables.
- `admin_login()`: Handles the initial step of traditional admin login, requiring a TOTP code.
- `admin_verify()`: Completes traditional admin login by verifying password and TOTP, issuing a JWT.
- `admin_firebase_login()`: Authenticates administrators via Firebase ID tokens, checks roles, and initiates TOTP flow if needed.
- `admin_firebase_totp_setup()`: Generates a TOTP secret and provisioning URI for Firebase-authenticated admins.
- `admin_firebase_totp_verify()`: Verifies a TOTP code for Firebase-authenticated admins, finalizing setup or issuing a JWT.
- `cloud_distribution()`: Provides statistics on the distribution of requests across LLM providers.
- `free_tier_status()`: Returns the overall status of free-tier usage.
- `free_tier_provider_status()`: Returns the free-tier status for a specific LLM provider.
- `free_tier_pause_provider()`: Pauses a free-tier provider for a specified duration.
- `free_tier_override_limits()`: Overrides the usage limits for a free-tier provider.
- `token_budget_stats()`: Provides statistics on token budget consumption.
- `gcp_health()`: Performs health checks for various Google Cloud Platform services.
- `gcp_verification_queue_stats()`: Returns statistics for the GCP verification queue.
- `gcp_pubsub_stats()`: Returns statistics for GCP Pub/Sub.
- `get_admin_rules()`: Retrieves the current rules from the rules engine.
- `post_admin_rules()`: Updates the rules within the rules engine.
- `get_skills()`: Lists available AI skills and their descriptions.
- `verify_totp_code()`: Verifies a Time-based One-Time Password (TOTP) code.
- `check_totp()`: An alias for `verify_totp_code()`, used for TOTP verification.

Dependencies:
- `base64`: For Base32 encoding/decoding in TOTP.
- `hashlib`: For SHA1 hashing in TOTP.
- `hmac`: For HMAC-SHA1 in TOTP.
- `os`: For environment variable access and secure random generation.
- `struct`: For packing/unpacking binary data in TOTP.
- `time`: For time-related operations in TOTP and JWT expiration.
- `fastapi`: For defining API routes and handling HTTP requests/responses.
- `loguru`: For structured logging.
- `bcrypt`: (Optional) For secure password hashing and verification.
- `core.services`: For accessing various core services like parallel router, GCP router, queues, and rules engine.
- `core.config`: For accessing application settings (e.g., `settings.jwt_secret`, `settings.admin_emails`).
- `core.messaging.events`: For `get_firebase_auth` to interact with Firebase Admin SDK.
- `services.storage.gcp_firestore`: For `get_firestore_client` to interact with Firestore for admin user management.
- `models.admin`: For Pydantic models defining admin request payloads.
- `jwt`: For encoding JSON Web Tokens (JWTs).
- `google.cloud.firestore`: For Firestore field deletion.
- `core.llm.free_tier_tracker`: For managing and monitoring LLM free-tier usage.
- `core.llm.token_budget`: For managing and monitoring LLM token budgets."""

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from core.logging_config import logger

# বাংলা মন্তব্য: TOTP ব্রুট-ফোর্স প্রতিরোধে Redis lockout constants
_TOTP_MAX_ATTEMPTS = 5
_TOTP_LOCKOUT_SECONDS = 600  # 10 minutes
# STATE-LOCK LIFECYCLE (2026-09-20): Display-Once + Instant Lock policy —
# বাংলা মন্তব্য: freshly issued temp TOTP secret সর্বোচ্চ ১০ মিনিট বৈধ থাকবে;
# এর পরে pending enrollment বাতিল গণ্য হবে এবং ACTIVE secret-এ fallback হবে।
_TOTP_PENDING_TTL_SECONDS = 600  # 10 minutes to verify a freshly issued QR
_TRUSTED_BROWSER_COOKIE = "supreme_admin_trusted_browser"
_TRUSTED_BROWSER_TTL = 7 * 24 * 60 * 60


def _trusted_browser_key(token: str) -> str:
    return "admin:trusted-browser:" + hashlib.sha256(token.encode()).hexdigest()


async def _get_redis_client():
    from core.cache.redis_manager import redis_manager

    return redis_manager.client


async def _trusted_browser_uid(request: Request) -> str | None:
    token = request.cookies.get(_TRUSTED_BROWSER_COOKIE)
    if not token:
        return None
    redis = await _get_redis_client()
    if not redis:
        return None
    try:
        value = await redis.get(_trusted_browser_key(token))
        raw = value.decode() if isinstance(value, bytes) else value
        return json.loads(raw).get("uid") if raw else None
    except Exception as exc:
        logger.warning("Trusted browser lookup failed: %s", exc)
        return None


async def _issue_trusted_browser(uid: str, email: str, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    redis = await _get_redis_client()
    if not redis:
        raise HTTPException(status_code=503, detail="Trusted browser service unavailable")
    browser_id = uuid.uuid4().hex
    metadata = {"id": browser_id, "uid": uid, "email": email, "created_at": int(time.time())}
    await redis.setex(_trusted_browser_key(token), _TRUSTED_BROWSER_TTL, json.dumps(metadata))
    await redis.sadd(f"admin:trusted-browsers:{uid}", browser_id)
    await redis.setex(
        f"admin:trusted-browser-record:{uid}:{browser_id}",
        _TRUSTED_BROWSER_TTL,
        json.dumps({"token_key": _trusted_browser_key(token), **metadata}),
    )
    env_name = str(getattr(settings, "env", "local") or "").lower()
    # Issue #709 (item 4): Secure cookie for production AND staging — not just
    # production. SameSite=None requires the Secure attribute, so it follows the
    # same env set; local HTTP development keeps the cookie lax/insecure.
    secure_env = env_name in ("production", "prod", "staging")
    response.set_cookie(
        _TRUSTED_BROWSER_COOKIE,
        token,
        max_age=_TRUSTED_BROWSER_TTL,
        httponly=True,
        secure=secure_env,
        samesite="none" if secure_env else "lax",
        path="/",
    )


async def _issue_admin_jwt(uid: str) -> str:
    import jwt

    now = int(time.time())
    payload = {
        "sub": uid,
        "uid": uid,
        "role": "admin",
        "exp": now + 3600 * int(os.environ.get("ADMIN_JWT_EXPIRY_HOURS", 24)),
        "iat": now,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


from api.dependencies import get_current_user_token
from core import services
from core.config import settings
from core.firebase_auth import get_firebase_auth
from models.admin import (
    AdminFirebaseLoginRequest,
    AdminFirebaseTotpSetupRequest,
    AdminFirebaseTotpVerifyRequest,
)
from services.storage.gcp_firestore import get_firestore_client

router = APIRouter()


def get_current_admin(payload: dict = Depends(get_current_user_token)) -> dict:
    """Enforce admin role for sensitive admin routes (e.g. rules engine)."""
    if payload.get("role") != "admin":
        logger.warning(f"Unauthorized admin access attempt by {payload.get('sub')}")
        # বাংলা মন্তব্য: রেন্ডার ডকার লেআউটের জন্য সঠিক status.HTTP_403_FORBIDDEN অবজেক্ট ব্যবহার করা হলো
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return payload


auth = get_firebase_auth()


# ERR-S01 FIX (2026-09-15): single shared, ALLOW-LIST gate for every `mock-`
# token bypass site in this file. Previously several sites used deny-list
# comparisons (`env == "production"` / `env != "production"`) while login and
# TOTP-setup used allow-lists — the same token prefix had two different
# policies. Deny-lists fail open for "prod", "staging", misspelled or unset
# ENV values (config.py itself treats "prod" as production in is_bypass_allowed).
_MOCK_TOKEN_ALLOWED_ENVS = frozenset({"local", "dev", "development", "test", "testing", "ci"})


def _mock_token_allowed() -> bool:
    """Return True only in explicitly permitted local/test environments.

    Fail-closed by design: production, prod, staging, and any unknown/unset
    env value are all rejected. This is the only gate that should guard
    ``mock-`` token bypasses in this module.
    """
    env = str(getattr(settings, "env", "local") or "local").lower()
    return env in _MOCK_TOKEN_ALLOWED_ENVS


def _reject_mock_token() -> None:
    """Raise the standard 403 for mock-token bypass attempts outside dev/test."""
    logger.warning(
        "Mock-token bypass attempt rejected (env=%r is not in the local/test allow-list).",
        getattr(settings, "env", "local"),
    )
    raise HTTPException(
        status_code=403,
        detail="Mock tokens are strictly forbidden outside of local testing environments.",
    )


# বাংলা মন্��ব্য: শুধুমাত্র স্ট্যান্ডার্ড ২-স্টেপ পাসওয়ার্ড + TOTP ফ্লো এবং ৭-ডিজিট ফায়ারবেস অথেনটিকেশন ফ্লোটি সক্রিয় রাখা হয়েছে।


@router.post("/api/admin/firebase-login")
async def admin_firebase_login(payload: AdminFirebaseLoginRequest, request: Request):
    id_token = payload.id_token

    try:
        if id_token.startswith("mock-"):
            # ERR-S01 FIX: shared allow-list gate (single source of truth for all
            # mock-token sites in this module — fail-closed outside dev/test).
            if not _mock_token_allowed():
                _reject_mock_token()
            uid = "mock-admin-uid"
            email = settings.admin_emails[0] if settings.admin_emails else "admin@example.com"
            logger.warning(
                f"Bypassing verification using mock token mode. Token: {id_token[:20]}..."
            )
        elif auth:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token.get("uid", decoded_token.get("sub", "mock-admin-uid"))
            email = decoded_token.get("email", "")
            logger.info(f"Verified Firebase token for email: {email}")
        else:
            raise HTTPException(
                status_code=401,
                detail="Firebase Admin SDK is unavailable. Cannot authenticate.",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Token verification/decoding failed")
        raise HTTPException(status_code=401, detail="Authentication failed") from e

    db = get_firestore_client()
    role = "user"
    totp_secret = None
    totp_enabled = False

    if db:
        try:
            doc_ref = db.collection("admin_users").document(uid)
            doc = doc_ref.get()
            if doc.exists:
                data = doc.to_dict()
                role = data.get("role", "user")
                totp_secret = data.get("totp_secret")
                totp_enabled = data.get("totp_enabled", False)
            elif email.lower() in [e.lower() for e in settings.admin_emails]:
                role = "admin"
                doc_ref.set(
                    {
                        "email": email,
                        "role": "admin",
                        "created_at": str(time.time()),
                        "totp_enabled": False,
                    }
                )
        except Exception as e:
            logger.critical(
                f"Firestore admin lookup failed (Possible DB connection issue/attack): {e}"
            )
            role = "user"
    elif email.lower() in [e.lower() for e in settings.admin_emails]:
        role = "admin"
    else:
        role = "user"

    if role != "admin":
        logger.warning(f"Unauthorized admin access attempt by UID: {uid}, Email: {email}")
        raise HTTPException(
            status_code=403, detail="Forbidden: Not authorized as an admin role user"
        )

    if await _trusted_browser_uid(request) == uid:
        trusted_token = await _issue_admin_jwt(uid)
        if not trusted_token:
            raise HTTPException(status_code=401, detail="Authentication token missing")
        return {"status": "trusted_browser", "uid": uid, "token": trusted_token}

    # বাংলা মন্তব্য: Default password login gives direct dashboard access.
    # TOTP is optional: only enforced if globally enabled via ADMIN_ENFORCE_TOTP or user opted in (totp_enabled: True).
    enforce_totp = getattr(settings, "admin_enforce_totp", False) or totp_enabled
    if not enforce_totp:
        admin_jwt = await _issue_admin_jwt(uid)
        if not admin_jwt:
            raise HTTPException(status_code=500, detail="Failed to issue admin authorization token")
        return {"status": "authenticated", "uid": uid, "token": admin_jwt, "role": "admin"}

    if not totp_secret:
        return {"status": "totp_setup_required", "uid": uid, "email": email}

    # বাংলা মন্তব্য: Frontend (frontend/src/store/adminStore.ts) `otp_required` অনুযায়ী
    # status check করে OTP স্ক্রিনে যায়।
    return {"status": "otp_required", "uid": uid}


def _ensure_admin_authorized(uid: str, email: str = "") -> None:
    """SECURITY FIX (P0, review 2026-09-12): enforce admin role on TOTP flows.

    বাংলা মন্তব্য: totp-setup / totp-verify / totp-recover এন্ডপয়েন্টগুলো public path-এ
    ছিল এবং Firebase ID token যাচাই করলেও role চেক করত না — ফলে যেকোনো self-registered
    ইউজার নিজের uid-তে TOTP secret সেটআপ করে সরাসরি role:"admin" JWT মিন্ট করতে পারত
    (full admin escalation)। এখন শুধুমাত্র admin_users/{uid} (role=admin) অথবা
    ADMIN_EMAILS allowlist-এ থাকা ইমেইল এগোতে পারবে। Firestore lookup ব্যর্থ হলে
    fail-closed (অনুমোদন দেওয়া হবে না) — login flow-এর সাথে সামঞ্জস্যপূর্ণ।
    """
    # ERR-S01 FIX (2026-09-15): was a deny-list (`env != "production"`), which
    # authorized mock-admin-uid for ANY non-"production" env value — including
    # "prod" (which config.py treats as production) and unset/unknown values.
    # Now it uses the shared allow-list helper so all five mock-token sites in
    # this file enforce one identical, fail-closed policy.
    if uid == "mock-admin-uid" and _mock_token_allowed():
        return  # বাংলা মন্তব্য: dev/test-only mock পথ; বাকি সব env-এ fail-closed

    admin_emails = {e.lower() for e in (getattr(settings, "admin_emails", None) or [])}
    if email and email.lower() in admin_emails:
        return

    db = get_firestore_client()
    if db:
        try:
            doc = db.collection("admin_users").document(uid).get()
            if doc.exists and (doc.to_dict() or {}).get("role") == "admin":
                return
        except Exception as lookup_err:
            logger.error(f"Admin role lookup failed for uid={uid}: {lookup_err}")

    logger.warning(f"Unauthorized TOTP admin-flow attempt blocked: uid={uid}, email={email!r}")
    raise HTTPException(status_code=403, detail="Forbidden: Not authorized as an admin role user")


@router.post("/api/admin/firebase-totp-setup")
def admin_firebase_totp_setup(payload: AdminFirebaseTotpSetupRequest):
    id_token = payload.id_token

    try:
        if id_token.startswith("mock-"):
            # বাংলা মন্তব্য: mock টোকেন দিয়ে TOTP সেটআপ বাইপাস শুধুমাত্র local/test env-এ অনুমোদিত
            # ERR-S01 FIX: shared fail-closed allow-list gate (was: deny-list `== production`).
            if not _mock_token_allowed():
                _reject_mock_token()
            uid = "mock-admin-uid"
            email = settings.admin_emails[0] if settings.admin_emails else "admin@example.com"
        elif auth:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token.get("uid", decoded_token.get("sub", "mock-admin-uid"))
            email = decoded_token.get("email", "")
        else:
            raise HTTPException(
                status_code=401,
                detail="Firebase Admin SDK is unavailable. Cannot authenticate.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token decoding failed: {e!s}") from e

    # SECURITY FIX (P0): admin role verification before issuing TOTP material
    _ensure_admin_authorized(uid, email)

    # STATE-LOCK LIFECYCLE (P0, 2026-09-20): guard before issuing ANY TOTP material.
    # বাংলা মন্তব্য: 2FA ইতিমধ্যে ACTIVE থাকলে নতুন QR/secret/recovery-codes ইস্যু করা
    # যাবে না — নইলে যেকোনো চুরি হওয়া Firebase ID token দিয়ে TOTP + recovery codes
    # ঘুরিয়ে ফেলে পুরো 2FA বাইপাস করা যেত। Re-enroll করতে হলে recovery code
    # (/api/admin/firebase-totp-recover) বাধ্যতামূলক — এটাই Instant Lock নীতি।
    db = get_firestore_client()
    if db:
        try:
            existing_doc = db.collection("admin_users").document(uid).get()
            existing = existing_doc.to_dict() if existing_doc.exists else {}
        except Exception as e:
            logger.error(f"TOTP state lookup failed for uid={uid}: {e}")
            raise HTTPException(status_code=503, detail="Security database unavailable") from e
        if existing.get("totp_secret"):
            raise HTTPException(
                status_code=400,
                detail="2FA is already ACTIVE. Use a recovery code via /api/admin/firebase-totp-recover to re-enroll.",
            )
        pending_secret = existing.get("temp_totp_secret")
        pending_created = existing.get("temp_totp_created_at")
        # বাংলা মন্তব্য: টাটকা pending enrollment থাকলে re-issue ব্লক — QR একবারই (Display-Once)
        # দেখানো হবে এবং pending অবস্থায় recovery codes বারবার rotate করা যাবে না।
        if (
            pending_secret
            and isinstance(pending_created, (int, float))
            and (time.time() - float(pending_created)) < _TOTP_PENDING_TTL_SECONDS
        ):
            raise HTTPException(
                status_code=409,
                detail="A TOTP enrollment is already pending. Verify the code you scanned, or wait 10 minutes for it to expire.",
            )

    secret = base64.b32encode(os.urandom(10)).decode("utf-8")
    recovery_codes = [secrets.token_urlsafe(10) for _ in range(8)]
    recovery_hashes = [hashlib.sha256(code.encode()).hexdigest() for code in recovery_codes]

    # বাংলা মন্তব্য: db guard-এর আগেই STATE-LOCK lookup হয়ে গেছে; এখানে শুধু লেখা হচ্ছে।
    if db:
        try:
            db.collection("admin_users").document(uid).set(
                {
                    "temp_totp_secret": secret,
                    "temp_totp_created_at": int(time.time()),
                    "recovery_code_hashes": recovery_hashes,
                },
                merge=True,
            )
        except Exception as e:
            logger.error(f"Failed to store temp TOTP secret in Firestore: {e}")

    # বাংলা মন্তব্য: ৬ ডিজিটের ওটিপি রিকোয়েস্ট করা হলো
    provisioning_uri = f"otpauth://totp/SupremeAI:{email}?secret={secret}&issuer=SupremeAI&digits=6"
    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri,
        "recovery_codes": recovery_codes,
    }


class AdminRecoveryRequest(BaseModel):
    id_token: str
    recovery_code: str


@router.post("/api/admin/firebase-totp-recover")
async def admin_firebase_totp_recover(payload: AdminRecoveryRequest):
    """Consume one single-use recovery code and issue a fresh TOTP enrollment."""
    try:
        if payload.id_token.startswith("mock-"):
            # ERR-S01 FIX: shared fail-closed allow-list gate (was: deny-list `== production`).
            if not _mock_token_allowed():
                _reject_mock_token()
            uid = "mock-admin-uid"
            email = settings.admin_emails[0] if settings.admin_emails else "admin@example.com"
        elif auth:
            decoded = auth.verify_id_token(payload.id_token)
            uid = decoded.get("uid", decoded.get("sub"))
            email = decoded.get("email", "")
        else:
            raise HTTPException(status_code=401, detail="Authentication service unavailable")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Authentication failed") from exc

    # SECURITY FIX (P0): admin role verification before recovery re-enrollment
    _ensure_admin_authorized(uid, email)

    db = get_firestore_client()
    if not db:
        raise HTTPException(status_code=503, detail="Security database unavailable")

    # STATE-LOCK LIFECYCLE (P0, 2026-09-20): recovery-code অনলাইন brute-force প্রতিরোধে
    # verify route-এর মতো Redis lockout (৫ বার ভুল → ১০ মিনিট লক, fail-closed)।
    # বাংলা মন্তব্য: verify route-এর সাথে consistent — Redis ইমপোর্ট ব্যর্থ হলে (dev, redis ছাড়া)
    # এগোনো যাবে, কিন্তু Redis আছে অথচ ত্রুটি হলে fail-closed (৫০৩)।
    recover_lockout_key = f"admin:totp:recover:lockout:{uid}"
    recover_attempt_key = f"admin:totp:recover:attempts:{uid}"
    _redis = None
    try:
        from core.cache.redis_manager import redis_manager

        _redis = redis_manager.client
    except Exception as e:
        logger.debug(f"Redis client not available: {e}")

    if _redis:
        try:
            if await _redis.get(recover_lockout_key):
                raise HTTPException(
                    status_code=429,
                    detail="Recovery locked. Please wait 10 minutes.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.critical(f"Redis recovery-lockout check failed — blocking (fail-closed): {e}")
            raise HTTPException(
                status_code=503,
                detail="Authentication service temporarily unavailable. Please try again later.",
            )

    ref = db.collection("admin_users").document(uid)
    doc = ref.get()
    data = doc.to_dict() if doc.exists else {}
    digest = hashlib.sha256(payload.recovery_code.strip().encode()).hexdigest()
    hashes = data.get("recovery_code_hashes", [])
    if digest not in hashes:
        if _redis:
            try:
                attempts = await _redis.incr(recover_attempt_key)
                await _redis.expire(recover_attempt_key, _TOTP_LOCKOUT_SECONDS)
                if int(attempts) >= _TOTP_MAX_ATTEMPTS:
                    await _redis.setex(recover_lockout_key, _TOTP_LOCKOUT_SECONDS, "locked")
                    logger.critical(
                        f"TOTP recovery lockout triggered for uid={uid} after {attempts} failed attempts"
                    )
            except Exception as e:
                logger.warning(f"Redis recovery attempt tracking failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid or already used recovery code")

    # বাংলা মন্তব্য: সফল recovery-তে attempt counter রিসেট
    if _redis:
        try:
            await _redis.delete(recover_attempt_key)
        except Exception as e:
            logger.debug(f"Failed to clear Redis recovery attempts: {e}")

    secret = base64.b32encode(os.urandom(10)).decode("utf-8")
    remaining = [item for item in hashes if item != digest]
    ref.set(
        {
            "temp_totp_secret": secret,
            "temp_totp_created_at": int(time.time()),
            "recovery_code_hashes": remaining,
        },
        merge=True,
    )
    provisioning_uri = f"otpauth://totp/SupremeAI:{email}?secret={secret}&issuer=SupremeAI&digits=6"
    logger.warning("Admin %s used a single-use TOTP recovery code", uid)
    return {"secret": secret, "provisioning_uri": provisioning_uri}


@router.post("/api/admin/firebase-totp-verify")
async def admin_firebase_totp_verify(payload: AdminFirebaseTotpVerifyRequest, response: Response):
    id_token = payload.id_token
    otp = payload.otp

    try:
        if id_token.startswith("mock-"):
            # বাংলা মন্তব্য: mock টোকেন দিয়ে TOTP ভেরিফিকেশন বাইপাস শুধুমাত্র local/test env-এ অনুমোদিত
            # ERR-S01 FIX: shared fail-closed allow-list gate (was: deny-list `== production`).
            if not _mock_token_allowed():
                _reject_mock_token()
            uid = "mock-admin-uid"
            email = ""
        elif auth:
            decoded_token = auth.verify_id_token(id_token)
            uid = decoded_token.get("uid", decoded_token.get("sub", "mock-admin-uid"))
            email = decoded_token.get("email", "")
        else:
            raise HTTPException(
                status_code=401,
                detail="Firebase Admin SDK is unavailable. Cannot authenticate.",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Token decoding failed: {e!s}") from e

    # SECURITY FIX (P0): admin role verification before minting an admin JWT
    _ensure_admin_authorized(uid, email)

    db = get_firestore_client()
    totp_secret = None
    temp_totp_secret = None
    temp_created_at = None

    if db:
        try:
            doc = db.collection("admin_users").document(uid).get()
            if doc.exists:
                data = doc.to_dict()
                totp_secret = data.get("totp_secret")
                temp_totp_secret = data.get("temp_totp_secret")
                temp_created_at = data.get("temp_totp_created_at")
        except Exception as e:
            logger.error(f"Failed to retrieve TOTP secret: {e}")

    # বাংলা মন্তব্য: temp_totp_secret (সবচেয়ে নতুন setup request) আগে ব্যবহার করা হয়।
    # বাংলা মন্তব্য: reset/regenerate-এর পরে নতুন pending secret দিয়েই OTP যাচাই হবে — নিচের PENDING-TTL logic দেখুন।
    # PENDING-TTL (STATE-LOCK LIFECYCLE, 2026-09-20):
    # বাংলা মন্তব্য: temp_totp_secret শুধুমাত্র ইস্যুর ১০ মিনিটের মধ্যে বৈধ। TTL পার হলে
    # pending enrollment বাতিল গণ্য হবে এবং ACTIVE totp_secret-এ fallback হবে।
    # Timestamp নেই এমন legacy pending secret-ও বাতিল গণ্য হবে (fail-closed)।
    temp_is_fresh = (
        bool(temp_totp_secret)
        and isinstance(temp_created_at, (int, float))
        and (time.time() - float(temp_created_at)) <= _TOTP_PENDING_TTL_SECONDS
    )

    if temp_is_fresh:
        secret_to_use = temp_totp_secret
    else:
        secret_to_use = totp_secret
    if not secret_to_use:
        # STATE-LOCK LIFECYCLE: shared env fallback শুধুমাত্র local/test mock flow-এ অনুমোদিত।
        # বাংলা মন্তব্য: প্রোডাকশনে per-user Firestore secret ছাড়া OTP যাচাই অসম্ভব (fail-closed) —
        # ফলে publicly-known example key (SUPREMEAI_ADMIN_TOTP_SECRET) আর কোনো কাজে আসবে না।
        if _mock_token_allowed():
            secret_to_use = os.getenv("SUPREMEAI_ADMIN_TOTP_SECRET")
        if not secret_to_use:
            raise HTTPException(
                status_code=500,
                detail="TOTP is not enrolled for this account. Please complete TOTP setup first.",
            )

    # বাংলা মন্তব্য: Redis TOTP lockout — ব্রুট-ফোর্স অ্যাটাক প্রতিরোধ (Patch 3 fix)
    lockout_key = f"admin:totp:lockout:{uid}"
    attempt_key = f"admin:totp:attempts:{uid}"
    _redis = None
    try:
        from core.cache.redis_manager import redis_manager

        _redis = redis_manager.client
    except Exception as e:
        logger.debug(f"Redis client not available: {e}")

    if _redis:
        try:
            if await _redis.get(lockout_key):
                raise HTTPException(
                    status_code=429,
                    detail="TOTP verification locked. Please wait 10 minutes.",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.critical(f"Redis lockout check failed — blocking login (fail-closed): {e}")
            raise HTTPException(
                status_code=503,
                detail="Authentication service temporarily unavailable. Please try again later.",
            )

    if not check_totp(otp.strip(), secret_to_use):
        # বাংলা মন্তব্য: ব্যর্থ OTP attempt counter বাড়ানো হচ্ছে, সীমা ছাড়ালে lockout
        if _redis:
            try:
                attempts = await _redis.incr(attempt_key)
                await _redis.expire(attempt_key, _TOTP_LOCKOUT_SECONDS)
                if int(attempts) >= _TOTP_MAX_ATTEMPTS:
                    await _redis.setex(lockout_key, _TOTP_LOCKOUT_SECONDS, "locked")
                    logger.critical(
                        f"TOTP lockout triggered for uid={uid} after {attempts} failed attempts"
                    )
            except Exception as e:
                logger.warning(f"Redis attempt tracking failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid verification code")

    # বাংলা মন্তব্য: সফল OTP-এ attempt counter রিসেট
    if _redis:
        try:
            await _redis.delete(attempt_key)
        except Exception as e:
            logger.debug(f"Failed to clear Redis attempts: {e}")

    if db and temp_totp_secret:
        from google.cloud import firestore

        try:
            if temp_is_fresh and secret_to_use == temp_totp_secret:
                # বাংলা মন্তব্য: OTP যাচাই হয়েছে টাটকা pending secret দিয়ে — এখন সেটিই ACTIVE
                # হবে (promotion) এবং pending মুছে যাবে। এটাই Instant Lock: পুরনো secret
                # সাথে সাথে অচল হয়ে যায়।
                db.collection("admin_users").document(uid).update(
                    {
                        "totp_secret": temp_totp_secret,
                        "temp_totp_secret": firestore.DELETE_FIELD,
                        "temp_totp_created_at": firestore.DELETE_FIELD,
                    }
                )
            else:
                # STATE-LOCK LIFECYCLE: সফল লগইন যদি ACTIVE secret দিয়েই হয়, তবে
                # stale/expired pending enrollment পরিষ্কার হবে — stale temp কখনও
                # ACTIVE secret-কে replace করতে পারবে না।
                db.collection("admin_users").document(uid).update(
                    {
                        "temp_totp_secret": firestore.DELETE_FIELD,
                        "temp_totp_created_at": firestore.DELETE_FIELD,
                    }
                )
        except Exception as e:
            logger.error(f"Failed to finalize TOTP state: {e}")

    import jwt

    now = int(time.time())
    # বাংলা মন্তব্য: jti (JWT ID) + sub + iat যোগ করা হলো — JWT replay attack প্রতিরোধ (Patch 6 fix)
    expiry_hours = int(os.environ.get("ADMIN_JWT_EXPIRY_HOURS", 24))
    jwt_payload = {
        "sub": uid,
        "uid": uid,
        "role": "admin",
        "type": "access",
        "exp": now + 3600 * expiry_hours,
        "iat": now,
        "jti": uuid.uuid4().hex,
    }
    jwt_secret = settings.jwt_secret
    token = jwt.encode(jwt_payload, jwt_secret, algorithm="HS256")

    if payload.remember_browser:
        await _issue_trusted_browser(uid, "", response)

    return {"status": "success", "token": token}


@router.get("/admin/trusted-browsers")
async def list_trusted_browsers(admin: dict = Depends(get_current_admin)):
    redis = await _get_redis_client()
    if not redis:
        raise HTTPException(status_code=503, detail="Trusted browser service unavailable")
    uid = str(admin.get("sub"))
    browser_ids = await redis.smembers(f"admin:trusted-browsers:{uid}")
    browsers = []
    for raw_id in browser_ids:
        browser_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
        record = await redis.get(f"admin:trusted-browser-record:{uid}:{browser_id}")
        if record:
            parsed = json.loads(record.decode() if isinstance(record, bytes) else record)
            parsed.pop("token_key", None)
            browsers.append(parsed)
    return {"browsers": browsers}


@router.delete("/admin/trusted-browsers/{browser_id}")
async def revoke_trusted_browser(browser_id: str, admin: dict = Depends(get_current_admin)):
    redis = await _get_redis_client()
    if not redis:
        raise HTTPException(status_code=503, detail="Trusted browser service unavailable")
    uid = str(admin.get("sub"))
    record_key = f"admin:trusted-browser-record:{uid}:{browser_id}"
    record = await redis.get(record_key)
    if not record:
        raise HTTPException(status_code=404, detail="Trusted browser not found")
    parsed = json.loads(record.decode() if isinstance(record, bytes) else record)
    await redis.delete(parsed["token_key"], record_key)
    await redis.srem(f"admin:trusted-browsers:{uid}", browser_id)
    return {"ok": True}


@router.delete("/admin/trusted-browsers")
async def revoke_all_trusted_browsers(admin: dict = Depends(get_current_admin)):
    redis = await _get_redis_client()
    if not redis:
        raise HTTPException(status_code=503, detail="Trusted browser service unavailable")
    uid = str(admin.get("sub"))
    browser_ids = await redis.smembers(f"admin:trusted-browsers:{uid}")
    for raw_id in browser_ids:
        browser_id = raw_id.decode() if isinstance(raw_id, bytes) else raw_id
        record_key = f"admin:trusted-browser-record:{uid}:{browser_id}"
        record = await redis.get(record_key)
        if record:
            parsed = json.loads(record.decode() if isinstance(record, bytes) else record)
            await redis.delete(parsed["token_key"], record_key)
        await redis.srem(f"admin:trusted-browsers:{uid}", browser_id)
    return {"ok": True}


@router.get("/admin/cloud-distribution")
def cloud_distribution(_admin: dict = Depends(get_current_admin)):
    return {
        "distribution": services.parallel_router.get_distribution_stats(),
        "total_requests": sum(
            p["current_requests"] for p in services.parallel_router.PROVIDERS.values()
        ),
        "active_providers": sum(
            1 for p in services.parallel_router.PROVIDERS.values() if p["status"] == "active"
        ),
        "strategy": "parallel_active_active",
        "rebalance_interval": "1 hour",
    }


@router.get("/admin/free-tier-status")
def free_tier_status(_admin: dict = Depends(get_current_admin)):
    from core.llm.free_tier_tracker import get_tracker

    tracker = get_tracker()
    return tracker.get_status()


@router.get("/admin/free-tier-status/{provider}")
def free_tier_provider_status(provider: str, _admin: dict = Depends(get_current_admin)):
    from fastapi import HTTPException

    from core.llm.free_tier_tracker import get_tracker

    tracker = get_tracker()
    status = tracker.get_provider_status(provider)
    if status is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider}' not tracked")
    return status


@router.post("/admin/free-tier-pause/{provider}")
def free_tier_pause_provider(
    provider: str,
    payload: dict = Body(default={"seconds": 60}),
    _admin: dict = Depends(get_current_admin),
):
    from core.llm.free_tier_tracker import get_tracker

    seconds = float(payload.get("seconds", 60))
    tracker = get_tracker()
    tracker.mark_rate_limited(provider, pause_seconds=seconds)
    logger.warning(f"Admin {_admin.get('sub')} paused provider '{provider}' for {seconds}s")
    return {"status": "paused", "provider": provider, "seconds": seconds}


@router.post("/admin/free-tier-override/{provider}")
def free_tier_override_limits(
    provider: str,
    payload: dict = Body(...),
    _admin: dict = Depends(get_current_admin),
):
    from core.llm.free_tier_tracker import get_tracker

    tracker = get_tracker()
    tracker.override_limits(provider, payload)
    logger.warning(f"Admin {_admin.get('sub')} overrode limits for '{provider}': {payload}")
    return {"status": "updated", "provider": provider, "new_limits": payload}


@router.get("/admin/token-budget-stats")
def token_budget_stats(_admin: dict = Depends(get_current_admin)):
    from core.llm.token_budget import get_budget_manager

    manager = get_budget_manager()
    return manager.get_stats()


@router.get("/gcp/health")
def gcp_health(_admin: dict = Depends(get_current_admin)):
    return {
        "status": "ok",
        "cloud_run": services.gcp_router.health_check(timeout=3),
        "firestore_mode": services.verification_queue.provider,
        "pubsub_mode": services.gcp_pubsub_queue.provider,
        "cloud_functions": services.cloud_function_client.get_config(),
    }


@router.get("/gcp/verification-queue/stats")
def gcp_verification_queue_stats(_admin: dict = Depends(get_current_admin)):
    return services.verification_queue.stats()


@router.get("/gcp/pubsub/stats")
def gcp_pubsub_stats(_admin: dict = Depends(get_current_admin)):
    return services.gcp_pubsub_queue.stats()


@router.get("/admin/rules", deprecated=True)
def get_admin_rules(_admin: dict = Depends(get_current_admin)):
    """Deprecated alias of GET /admin-api/rules (issue #1497).

    Both paths are backed by the SAME services.rules_engine instance, so
    behavior cannot drift — but /admin-api/rules (CommandCenter/RulesEnginePanel
    contract, core/effective_policy-aware) is the canonical surface. New callers
    must use the canonical path; this legacy shape is retained for contract
    compatibility only.
    """
    return services.rules_engine.rules


@router.post("/admin/rules", deprecated=True)
def post_admin_rules(payload: dict = Body(...), _admin: dict = Depends(get_current_admin)):
    """Deprecated alias of POST /admin-api/rules (issue #1497).

    Single source of truth: services.rules_engine.save_rules — identical to the
    canonical endpoint. Retained for legacy-contract compatibility only.
    """
    new_rules = payload.get("rules")
    if new_rules:
        success = services.rules_engine.save_rules(new_rules)
        if success:
            return {"status": "success"}
    return {"status": "error", "message": "Failed to save rules"}


@router.get("/skills")
def get_skills(_admin: dict = Depends(get_current_admin)):
    return {
        "web_scraper": {
            "name": "web_scraper",
            "version": "1.0.0",
            "description": "Scrapes website contents using BeautifulSoup.",
        },
        "csv_exporter": {
            "name": "csv_exporter",
            "version": "1.0.0",
            "description": "Exports tabular data to CSV using pandas.",
        },
    }


def check_totp(user_otp: str, base32_secret: str) -> bool:
    try:
        # বাংলা মন্তব্য: বেস-৩২ সিক্রেট কি প্যাডিং ঠিক করা হলো
        missing_padding = len(base32_secret) % 8
        if missing_padding:
            base32_secret += "=" * (8 - missing_padding)
        key = base64.b32decode(base32_secret.upper())
        current_time = int(time.time() // 30)
        for drift in [-1, 0, 1]:
            msg = struct.pack(">Q", current_time + drift)
            h = hmac.new(key, msg, hashlib.sha1).digest()
            o = h[19] & 15
            h_num = struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF
            # বাংলা মন্তব্য: ৬ ডিজিটের ওটিপি জেনারেট করা হলো
            code = f"{h_num % 1000000:06d}"
            # বাংলা মন্তব্য: টাইমিং অ্যাটাক প্রতিরোধে constant-time তুলনা ব্যবহার করা হলো
            if hmac.compare_digest(code, user_otp):
                return True
        return False
    except Exception:
        return False


# বাংলা মন্তব্য: verify_totp_code এখন check_totp-এর backward-compatible alias (Patch 5 fix)
# duplicate function সরানো হয়েছে, কিন্তু tests ও external callers-এর জন্য alias রাখা হয়েছে
verify_totp_code = check_totp


@router.get("/api/health-aggregation")
async def health_aggregation_contract(admin: dict = Depends(get_current_admin)):
    """Issue #1475 contract alias: GET /api/health-aggregation.

    The real implementation lives in api.routes.health_aggregation (mounted at
    /admin-api/health-aggregation). This prefix-less router can serve the
    absolute contract path directly; it reuses the very same handler, so both
    URLs always report identical, real service-health data under admin auth.
    """
    from api.routes.health_aggregation import get_health_aggregation

    return await get_health_aggregation()


# FIX (CI red 36219425476, follow-up of #1510): the three #1493 contract
# aliases below (traffic/kill-switch, tenant-limits GET/PUT) were RE-ADDED by
# #1510 with quoted annotations ("CloudNodeTarget"/"TenantLimitUpdate") that
# are not importable in this module's namespace — ruff F821 ×2, OpenAPI
# ForwardRef blow-up (test_app_contract) AND a full ×2 double registration
# (test_router_mount_hygiene). The canonical, self-contained versions live
# further down this file (classes _ContractCloudNodeTarget + local imports).
# Keep exactly one definition of each — this block is the duplicate, so it is
# removed, not the original.


class _ContractCloudNodeTarget(BaseModel):
    """Body of POST /api/admin/traffic/kill-switch (same shape as cloud_mesh)."""

    target_node: str


class _ContractSmellCheckRequest(BaseModel):
    """Body of POST /api/admin/cloud-mesh/smell-check (same shape as tools_ops)."""

    path: str
    thresholds: dict[str, int] | None = None


@router.post("/api/admin/cloud-mesh/smell-check")
async def cloud_mesh_smell_check_contract_alias(
    payload: _ContractSmellCheckRequest, admin: dict = Depends(get_current_admin)
):
    """Issue #1493 contract alias: POST /api/admin/cloud-mesh/smell-check.

    The codebase's real smell-check implementation is POST /tools/smell-check
    (api.routes.tools_ops, admin-gated). Route the contract path to it instead
    of leaving a misleading 404."""
    from api.routes.tools_ops import SmellCheckRequest as _RealRequest
    from api.routes.tools_ops import smell_check as _real_smell_check

    return await _real_smell_check(_RealRequest(path=payload.path, thresholds=payload.thresholds))


@router.post("/api/admin/traffic/kill-switch")
async def traffic_kill_switch_contract_alias(
    payload: _ContractCloudNodeTarget, admin: dict = Depends(get_current_admin)
):
    """Issue #1493 contract alias: POST /api/admin/traffic/kill-switch.

    The real implementation lives at /api/admin/cloud-mesh/kill-switch
    (api.routes.cloud_mesh) — same body shape, same admin gate, same handler."""
    from api.routes.cloud_mesh import CloudNodeTarget as _RealTarget
    from api.routes.cloud_mesh import kill_switch as _real_kill_switch

    return await _real_kill_switch(_RealTarget(target_node=payload.target_node))


@router.get("/api/admin/tenant-limits")
async def list_tenant_limits_contract_alias(
    include_usage: bool = True, admin: dict = Depends(get_current_admin)
):
    """Issue #1493 contract alias: GET /api/admin/tenant-limits.

    Real implementation: /admin-api/tenant-limits (api.routes.tenant_admin)."""
    from api.routes.tenant_admin import TenantLimitUpdate
    from api.routes.tenant_admin import list_tenants as _real_list_tenants

    return await _real_list_tenants(include_usage=include_usage)


@router.put("/api/admin/tenant-limits/{tenant_id}")
async def update_tenant_limits_contract_alias(
    tenant_id: str,
    org_name: str | None = None,
    billing_tier: str | None = None,
    requests_per_minute: int | None = None,
    max_tokens_per_day: int | None = None,
    max_concurrent_sessions: int | None = None,
    stripe_customer_id: str | None = None,
    notes: str | None = None,
    admin: dict = Depends(get_current_admin),
):
    """Issue #1493 contract alias: PUT /api/admin/tenant-limits/{tenant_id}.

    Delegates to api.routes.tenant_admin.update_tenant with the identical
    field set (TenantLimitUpdate)."""
    from api.routes.tenant_admin import TenantLimitUpdate as _RealUpdate
    from api.routes.tenant_admin import update_tenant as _real_update_tenant

    payload = _RealUpdate(
        org_name=org_name,
        billing_tier=billing_tier,
        requests_per_minute=requests_per_minute,
        max_tokens_per_day=max_tokens_per_day,
        max_concurrent_sessions=max_concurrent_sessions,
        stripe_customer_id=stripe_customer_id,
        notes=notes,
    )
    return await _real_update_tenant(tenant_id=tenant_id, payload=payload)
