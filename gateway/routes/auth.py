from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordBearer
from jwt import PyJWTError as JWTError
from pydantic import BaseModel, EmailStr, Field, model_validator

# বাংলা: A5/A6 (admin users) রুটের জন্য admin guard — circular import এড়াতে
# এটি lazy নয়, dependencies মডিউল core-only তাই এখানে safe।
from api.dependencies import get_current_admin
from core.cache.redis_manager import redis_manager
from core.config import settings
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.security import is_token_revoked, revoke_token
from core.security.authentication.rbac import UserContext
from database.supabase_client import db

try:
    from supabase_auth.errors import AuthApiError
except ImportError:
    try:
        from gotrue.errors import AuthApiError  # type: ignore[no-redef]
    except ImportError:
        AuthApiError = None  # type: ignore[assignment]

router = APIRouter(prefix="/auth", tags=["auth"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

ALGORITHM = "HS256"
# বাংলা: ২৪ ঘণ্টার টোকেন অনেক বেশি — অ্যাক্সেস টোকেন ১ ঘণ্টা, রিফ্রেশ টোকেন দীর্ঘ মেয়াদী।
ACCESS_TOKEN_EXPIRE_MINUTES = 60
# বাংলা: রিফ্রেশ টোকেন ৭ দিন — প্রোডাকশন স্ট্যান্ডার্ড।
REFRESH_TOKEN_EXPIRE_DAYS = 7

# বাংলা মন্তব্য (JWT-COOKIE-MIGRATION, ধাপ ১/২): টোকেন এখন থেকে httpOnly cookie
# হিসেবেও সেট হবে, যাতে ফ্রন্টএন্ড JS (localStorage) থেকে টোকেন সরিয়ে আনা যায়।
# ট্রানজিশন পিরিয়ডে response body-তেও টোকেন থাকছে (ব্রেকিং চেঞ্জ নয়) —
# ফ্রন্টএন্ড পুরোপুরি cookie-নির্ভর হয়ে গেলে body থেকে টোকেন সরানো যাবে।
ACCESS_COOKIE_NAME = "supreme_access_token"
REFRESH_COOKIE_NAME = "supreme_refresh_token"
CSRF_COOKIE_NAME = "supreme_csrf_token"


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str | None) -> None:
    """বাংলা: access/refresh টোকেন httpOnly cookie হিসেবে সেট করা হয়, প্লাস একটা
    non-httpOnly CSRF cookie (double-submit pattern) যাতে state-changing
    request-এ CSRF protection করা যায় — JS এই CSRF cookie পড়ে হেডারে পাঠাবে।
    """
    import secrets

    # Issue #709 (item 4): Secure cookies for production AND staging — not just
    # production. Only local dev (and the pytest ENV=test harness) keeps
    # Secure=False so plain-HTTP development/testing keeps working.
    secure = (settings.env or "").lower() in ("production", "prod", "staging")
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    if refresh_token:
        response.set_cookie(
            key=REFRESH_COOKIE_NAME,
            value=refresh_token,
            max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
            httponly=True,
            secure=secure,
            samesite="lax",
            path="/auth",
        )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=secrets.token_urlsafe(32),
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=False,
        secure=secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    for name, path in (
        (ACCESS_COOKIE_NAME, "/"),
        (REFRESH_COOKIE_NAME, "/auth"),
        (CSRF_COOKIE_NAME, "/"),
    ):
        response.delete_cookie(key=name, path=path)


async def _token_from_header_or_cookie(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
) -> str | None:
    """বাংলা: আগে Authorization header চেক করা হয় (backward-compat), না পেলে
    httpOnly cookie থেকে fallback করা হয়। এতে পুরনো (localStorage-based)
    এবং নতুন (cookie-based) দুই ধরনের ক্লায়েন্টই চলবে ট্রানজিশনের সময়।
    """
    if token:
        return token
    return request.cookies.get(ACCESS_COOKIE_NAME)


def _get_secret_key() -> str:
    return settings.jwt_secret


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    if jwt is None:
        raise RuntimeError("PyJWT is required for token issuance")
    to_encode = data.copy()
    # বাংলা: iat (issued-at) ও jti (token id) — রিভোকেশন ও অডিট ট্রেইলিং এর জন্য আবশ্যক।
    import uuid as _uuid

    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "jti": to_encode.get("jti") or f"jti-{_uuid.uuid4().hex[:16]}",
            "type": "access",
        }
    )
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """বাংলা: রিফ্রেশ টোকেন — অ্যাক্সেস টোকেন পুনঃপ্রদানের জন্য দীর্ঘ মেয়াদী।"""
    if jwt is None:
        raise RuntimeError("PyJWT is required for token issuance")
    import uuid as _uuid

    to_encode = data.copy()
    now = datetime.now(UTC)
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update(
        {
            "exp": expire,
            "iat": now,
            "type": "refresh",
            # বাংলা মন্তব্য: Token family ID — সব refresh token একই family-এ থাকবে
            # stolen token শনাক্ত করতে reuse detection-এ ব্যবহৃত হয়
            "tfid": data.get("tfid") or f"tfid-{_uuid.uuid4().hex[:12]}",
            "jti": f"jti-{_uuid.uuid4().hex[:16]}",
        }
    )
    return jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)


@with_error_bus("optional_current_user")
async def optional_current_user(
    token: str | None = Depends(_token_from_header_or_cookie),
) -> UserContext | None:
    if not token or jwt is None:
        return None
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        # বাংলা: type=access অথবা role=admin (admin step-up token) ছাড়া অন্য টোকেন (যেমন refresh) ব্যবহার রোধ।
        token_type = payload.get("type")
        if token_type is not None and token_type != "access":
            return None
        if token_type is None and payload.get("role") != "admin":
            return None
        # বাংলা মন্তব্য (ROOT-CAUSE FIX, /logout ফিচারের অংশ): logout করা
        # (blacklist-এ থাকা) টোকেন যেন আর valid না ধরা হয়, নাহলে logout-এর
        # পরেও পুরনো access_token দিয়ে /me কাজ করতে থাকবে।
        jti = payload.get("jti")
        # বাংলা (production-readiness plan, item 2): revocation check এখন
        # role-aware fail-closed — অ্যাডমিন টোকেনে Redis ডাউন থাকলে রিজেক্ট,
        # সাধারণ ইউজার আগের মতোই fail-open।
        if jti and await is_token_revoked(
            jti, is_admin=payload.get("role") in ("admin", "master_admin")
        ):
            return None
        # বাংলা মন্তব্য: User-level revocation চেক — token family reuse detected হলে
        # পুরো user-এর সব session revoke করা হয়
        user_id_check = payload.get("sub", "")
        if user_id_check:
            try:
                from core.cache.redis_manager import redis_manager

                if redis_manager.client and await redis_manager.client.get(
                    f"user_revoked:{user_id_check}"
                ):
                    logger.warning(f"User {user_id_check} is revoked due to suspected token theft")
                    return None
            except Exception as e:
                logger.debug(f"Redis revocation check skipped (fail-open): {e}")

        # বাংলা মন্তব্য: JWT ডিকোড সফল হলে UserContext তৈরি করে return করা হচ্ছে।
        user_id = payload.get("sub", "unknown")
        role = payload.get("role", "viewer")
        return UserContext(
            user_id=user_id,
            role=role,
            email=payload.get("email") if isinstance(payload.get("email"), str) else None,
        )
    except (JWTError, ValueError):
        logger.debug("JWT decode failed in optional_current_user", exc_info=True)
        return None


class LoginRequest(BaseModel):
    username: EmailStr | None = None
    email: EmailStr | None = None
    password: str

    @model_validator(mode="before")
    @classmethod
    def reconcile_username_email(cls, values: Any) -> Any:
        if isinstance(values, dict):
            email_val = values.get("email")
            user_val = values.get("username")
            if not user_val and not email_val:
                raise ValueError("Either 'username' or 'email' must be provided")
            if not user_val and email_val:
                values["username"] = email_val
            elif not email_val and user_val:
                values["email"] = user_val
        return values


class RegisterRequest(BaseModel):
    username: EmailStr
    password: str
    name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: str
    role: str


class MeResponse(BaseModel):
    user_id: str
    role: str
    scopes: tuple[str, ...] = ()
    email: str | None = None


class RefreshRequest(BaseModel):
    # FIX (AUDIT-CONTRACT-4): cookie-based refresh সমর্থনে ফিল্ডটি optional —
    # এন্ডপয়েন্ট এমনিতেই REFRESH_COOKIE_NAME থেকে fallback করে; কিন্তু বাধ্যতামূলক
    # ফিল্ড থাকায় cookie-only ক্লায়েন্ট (EventSource/SSE) 422-তে আটকে যেত।
    refresh_token: str | None = None


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, response: Response):
    # Issue #685 (Domain 15): the id assigned by the tracing middleware —
    # included in the audit log lines below so auth failures are joinable
    # with the request's structured-log stream.
    correlation_id = getattr(request.state, "correlation_id", "")
    if not db.client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase client is not initialized",
        )

    # বাংলা: supabase-py এর auth.sign_in_with_password সিঙ্ক্রোনাস — সরাসরি কল করলে
    # event loop ব্লক হয়ে যায়। asyncio.to_thread দিয়ে thread pool-এ পাঠাচ্ছি।
    try:
        res = await asyncio.to_thread(
            db.client.auth.sign_in_with_password,
            {"email": body.username, "password": body.password},
        )
        if not res.user:
            # বাংলা: auth ফেইলিওরে generic message — internal detail লিক করছি না।
            logger.warning(
                f"Login failed for email={body.username!r}: no user returned "
                f"(correlation_id={correlation_id})"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        user_id = res.user.id
        # বাংলা: ডাটাবেসের app_metadata এবং settings.admin_emails উভয় উৎস থেকে রোল যাচাই।
        # SECURITY FIX (AUDIT-SEC-1, CRITICAL): user_metadata এন্ড-ইউজার নিজেই লিখতে পারে
        # (supabase.auth.updateUser({data:{role:"admin"}})) — এটাতে বিশ্বাস করলে যেকোনো
        # ইউজার নিজেকে admin JWT বানিয়ে ফেলত (privilege escalation)। রোল এখন শুধু
        # সার্ভার-রাইটেবল app_metadata বা ADMIN_EMAILS অ্যালোলিস্ট থেকে আসবে।
        user_meta_role = (
            res.user.app_metadata.get("role")
            if hasattr(res.user, "app_metadata") and isinstance(res.user.app_metadata, dict)
            else None
        )
        is_admin = user_meta_role == "admin" or (
            body.username
            and any(
                body.username.lower() == admin_email.lower()
                for admin_email in settings.admin_emails
            )
        )
        primary_role = "admin" if is_admin else (user_meta_role or "user")
        # FIX (final-test 2026-09-13): `tenant_id` claim যোগ — এটা ছাড়া
        # get_current_tenant()/orchestrate-এর মতো tenant-scoped endpoint সবসময়
        # 401 "Authenticated tenant claim required" দিত। tenant_id == user_id,
        # TenantAwareFirestore (get_tenant_db) এর sub-based isolation-এর সাথে সামঞ্জস্যপূর্ণ।
        token_data = {
            "sub": user_id,
            "role": primary_role,
            "email": body.username,
            "method": "supabase_auth",
            "tenant_id": user_id,
        }
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        # বাংলা মন্তব্য: Phase 2 — Hybrid Fingerprint Login। হেডারটি ঐচ্ছিক, তাই না থাকলেও
        # লগইন স্বাভাবিকভাবে চলবে (ব্রেকিং চেঞ্জ নয়); থাকলে ডিভাইসটি known-devices সেটে যোগ হয়
        # যা AntiHackingContextMiddleware admin scope-এ তৃতীয় সিগন্যাল হিসেবে ব্যবহার করে।
        fingerprint = request.headers.get("x-device-fingerprint")
        if fingerprint and redis_manager and redis_manager.client:
            try:
                await redis_manager.client.sadd(f"device:known:{user_id}", fingerprint)
            except Exception as exc:
                logger.warning(f"Failed to register device fingerprint for {user_id}: {exc}")

        _set_auth_cookies(response, access_token, refresh_token)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
            role=primary_role,
        )
    except HTTPException:
        # বাংলা: নিজে রেইজ করা HTTPException পুনরায় রেইজ করি — বাকি সব exception 500।
        raise
    except Exception as e:
        if AuthApiError is not None and isinstance(e, AuthApiError):
            logger.warning(
                f"Authentication rejected for email={body.username!r}: {e.message} "
                f"(correlation_id={correlation_id})"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=e.message or "Invalid credentials",
            ) from e
        # বাংলা: অন্য কোনো exception (network, DB, Supabase internal) — ক্লায়েন্টকে
        # generic বার্তা দেখাচ্ছি, কিন্তু server-side এ পূর্ণ stack লগ করছি।
        logger.exception(
            f"Unexpected login error for email={body.username!r} (correlation_id={correlation_id})"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login service temporarily unavailable. Please try again.",
        ) from e


@router.post("/register", response_model=TokenResponse)
async def register(body: RegisterRequest, response: Response):
    if not db.client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase client is not initialized",
        )

    try:
        user_id = None
        session_obj = None

        try:
            # বাংলা: sign_up ও সিঙ্ক্রোনাস — to_thread দিয়ে wrap করা হলো।
            res = await asyncio.to_thread(
                db.client.auth.sign_up,
                {"email": body.username, "password": body.password},
            )
            if res.user:
                user_id = res.user.id
                session_obj = res.session
        except Exception as signup_err:
            # বাংলা: Supabase Free-Tier built-in SMTP-তে per-hour rate limit থাকে (e.g. 2-3 emails/hour)।
            # সেক্ষেত্রে service_client (Admin API) দিয়ে নিরাপদে ইউজার তৈরি করে অটো-কনফার্ম করা হবে।
            err_msg = str(signup_err).lower()
            # SECURITY FIX (AUDIT-SEC-5, HIGH): "invalid" substring সরানো হলো —
            # password-policy বা invalid-email রিজেকশনও এই fallback-এ ঢুকে admin-API
            # দিয়ে auto-confirm অ্যাকাউন্ট তৈরি হয়ে যেত (email confirmation bypass)।
            # এখন শুধুমাত্র সত্যিকারের provider rate-limit-এ fallback চলবে।
            if db.service_client and ("rate limit" in err_msg or "429" in err_msg):
                logger.info(
                    f"Public sign_up hit provider limit for {body.username!r} ({signup_err}). Falling back to Admin creation."
                )
                admin_res = await asyncio.to_thread(
                    db.service_client.auth.admin.create_user,
                    {
                        "email": body.username,
                        "password": body.password,
                        "email_confirm": True,
                        "user_metadata": {"full_name": body.name or ""},
                    },
                )
                if admin_res.user:
                    user_id = admin_res.user.id
                    session_obj = "admin_provisioned"
            else:
                raise

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Registration failed"
            )

        # বাংলা মন্তব্য: যদি সাধারণ সাইনআপে ইমেইল ভেরিফিকেশন অন থাকে এবং সেশন না থাকে
        if session_obj is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Email confirmation required"
            )

        # বাংলা মন্তব্য: ইমেইলটি settings.admin_emails তালিকায় আছে কি না তা দেখে রোল অ্যাসাইন করা হচ্ছে।
        is_admin = body.username and any(
            body.username.lower() == admin_email.lower() for admin_email in settings.admin_emails
        )
        primary_role = "admin" if is_admin else "user"
        # FIX (final-test 2026-09-13): register-এও tenant_id claim — login-এর সাথে সামঞ্জস্য।
        token_data = {
            "sub": user_id,
            "role": primary_role,
            "email": body.username,
            "method": "supabase_auth",
            "tenant_id": user_id,
        }
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)
        _set_auth_cookies(response, access_token, refresh_token)
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
            role=primary_role,
        )
    except HTTPException:
        raise
    except Exception as e:
        if AuthApiError is not None and isinstance(e, AuthApiError):
            logger.warning(f"Registration rejected for email={body.username!r}: {e.message}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.message or "Registration failed",
            ) from e
        # বাংলা: registration-এর ক্ষেত্রেও internal error লিক করছি না।
        logger.exception(f"Unexpected registration error for email={body.username!r}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration service temporarily unavailable. Please try again.",
        ) from e


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token_endpoint(body: RefreshRequest, request: Request, response: Response):
    """বাংলা: রিফ্রেশ টোকেন দিয়ে নতুন অ্যাক্সেস টোকেন প্রদান।

    type=refresh চেক করে access token রিফ্রেশে ব্যবহার রোধ করা হয় — token confusion প্রতিরোধ।
    """
    if jwt is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="JWT service unavailable"
        )
    refresh_token_value = body.refresh_token or (
        request.cookies.get(REFRESH_COOKIE_NAME) if request else None
    )
    if not refresh_token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing"
        )
    try:
        payload = jwt.decode(refresh_token_value, _get_secret_key(), algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is not a refresh token"
        )

    # বাংলা মন্তব্য: Refresh token rotation - পুরানো refresh token ব্ল্যাকলিস্ট করা
    # একবার ব্যবহৃত refresh token আর ব্যবহার করা যাবে না (replay attack প্রতিরোধ)
    refresh_jti = payload.get("jti")
    if refresh_jti:
        try:
            # Token এর expiration time বের করা
            exp_timestamp = payload.get("exp")
            await revoke_token(refresh_jti, exp=exp_timestamp)
            logger.info(f"Old refresh token rotated and blacklisted: {refresh_jti[:20]}...")
        except Exception as e:
            # rotation ব্যর্থ হলেও login বন্ধ করা হচ্ছে না, শুধু লগ করা
            logger.warning(f"Failed to rotate refresh token: {e}")

    # বাংলা মন্তব্য: Token family বজায় রাখা - stolen token detection-এর জন্য
    token_family = payload.get("tfid")
    # FIX (final-test 2026-09-13): refresh-এ tenant_id ক্যারি-ওভার — না হলে
    # refresh-পরবর্তী access token দিয়ে tenant endpoints আবার 401 করত।
    token_data = {
        "sub": payload.get("sub", "unknown"),
        "role": payload.get("role", "viewer"),
        "email": payload.get("email"),
        "method": payload.get("method", "supabase_auth"),
        "tenant_id": payload.get("tenant_id") or payload.get("sub", "unknown"),
    }
    if token_family:
        token_data["tfid"] = token_family

    # বাংলা মন্তব্য: Token Family Tracking — stolen refresh token শনাক্তকরণ
    # যদি রোটেট করা token আবার আসে, তাহলে সেটি stolen হয়েছে বলে ধরা হবে
    if token_family:
        try:
            from core.cache.redis_manager import redis_manager

            if redis_manager.client:
                family_key = f"refresh_family:{token_family}"
                is_reuse = await redis_manager.client.get(family_key)
                if is_reuse:
                    # বাংলা মন্তব্য: Token reuse detected! পুরো family revoke করা
                    logger.critical(
                        f"Refresh token reuse detected for family {token_family}. "
                        f"Possible token theft. Revoking entire token family."
                    )
                    # পুরো user-এর সব session revoke করা
                    user_sub = payload.get("sub", "")
                    await redis_manager.client.setex(
                        f"user_revoked:{user_sub}",
                        int(timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()),
                        "1",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token reuse detected. All sessions revoked.",
                    )
                # এই token use হয়েছে হিসেবে চিহ্নিত করা
                await redis_manager.client.setex(
                    family_key,
                    int(timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS).total_seconds()),
                    "used",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Token family tracking failed: {e}")

    # বাংলা মন্তব্য: Refresh Token Rotation — পুরনো refresh token ব্ল্যাকলিস্টে যোগ করা
    # যাতে একবার ব্যবহৃত refresh token আর ব্যবহার করা না যায় (replay attack প্রতিরোধ)
    if refresh_jti:
        try:
            await revoke_token(refresh_jti, REFRESH_TOKEN_EXPIRE_DAYS * 86400)
            logger.info(f"Old refresh token {refresh_jti[:8]}... blacklisted (rotation)")
        except Exception as e:
            logger.warning(f"Failed to blacklist old refresh token: {e}")

    token_data = {
        "sub": payload.get("sub", "unknown"),
        "role": payload.get("role", "viewer"),
        "email": payload.get("email"),
        "method": payload.get("method", "supabase_auth"),
        # FIX (final-test 2026-09-13): rotation-এ tenant_id অবশ্যই অব্যাহত থাকবে।
        "tenant_id": payload.get("tenant_id") or payload.get("sub", "unknown"),
        # বাংলা মন্তব্য: Token family ID একই রাখা — rotation-এ family অব্যাহত থাকে
        "tfid": payload.get("tfid", ""),
    }
    new_access = create_access_token(token_data)
    new_refresh = create_refresh_token(token_data)
    if response is not None:
        _set_auth_cookies(response, new_access, new_refresh)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user_id=str(token_data["sub"]),
        role=str(token_data["role"]),
    )


@router.get("/me", response_model=MeResponse)
async def me(current_user: UserContext | None = Depends(optional_current_user)):
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    # বাংলা মন্তব্য: scopes যদি None হয় তবে MeResponse ভ্যালিডেশন পাস করানোর জন্য খালি টুপল পাস করা হচ্ছে।
    scopes_val = current_user.scopes if current_user.scopes is not None else ()
    return MeResponse(
        user_id=current_user.user_id,
        role=current_user.role,
        scopes=scopes_val,
        email=current_user.email,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    token: str | None = Depends(_token_from_header_or_cookie),
):
    """বাংলা মন্তব্য (নতুন এন্ডপয়েন্ট): আগে /logout রুটটাই ছিল না (তাই 404
    আসত)। JWT stateless বলে সত্যিকারের "invalidate" সম্ভব না, কিন্তু ইতিমধ্যেই
    কোডবেসে থাকা Redis-ব্যাকড blacklist (core/security/revoke_token,
    is_token_revoked -- admin_auth.py-তে যেভাবে ব্যবহৃত হয়) পুনঃব্যবহার করে
    টোকেনের jti ব্ল্যাকলিস্ট করে দেওয়া হচ্ছে। এরপর optional_current_user
    (উপরে) revoke-চেক করে, তাই এই টোকেন দিয়ে /me আর কাজ করবে না।

    বাংলা (JWT-COOKIE-MIGRATION): auth cookie থাকলে সেগুলোও ক্লিয়ার করা হচ্ছে।
    """
    _clear_auth_cookies(response)
    if not token or jwt is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from None

    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti:
        # বাংলা: অ্যাডমিন টোকেন হলে TTL-aware LRU ক্যাশেও লেখা হয় (fail-closed সাপোর্ট)।
        await revoke_token(
            jti,
            exp=int(exp) if isinstance(exp, (int, float)) else None,
            is_admin=payload.get("role") in ("admin", "master_admin"),
        )

    # SECURITY FIX (AUDIT-SEC-3, CRITICAL): শুধু access token ব্ল্যাকলিস্ট করলে হয় না —
    # refresh token-এর jti-ও ব্ল্যাকলিস্ট করতে হবে, নাহলে logout-এর পরেও stolen
    # refresh token ৭ দিন (REFRESH_TOKEN_EXPIRE_DAYS) নতুন access token মাখতে পারে।
    refresh_token_value = request.cookies.get(REFRESH_COOKIE_NAME) if request else None
    if refresh_token_value:
        try:
            r_payload = jwt.decode(refresh_token_value, _get_secret_key(), algorithms=[ALGORITHM])
            r_jti = r_payload.get("jti")
            r_exp = r_payload.get("exp")
            if r_jti:
                await revoke_token(
                    r_jti,
                    exp=int(r_exp) if isinstance(r_exp, (int, float)) else None,
                    is_admin=r_payload.get("role") in ("admin", "master_admin"),
                )
        except Exception:
            # বাংলা: refresh cookie invalid/expired হলে access revocation-ই যথেষ্ট।
            logger.debug("Logout: refresh cookie absent or undecodable; access revoked only")
    return {"status": "logged_out"}


@router.get("/verify")
async def verify_token(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    return {
        "valid": True,
        "user_id": user.get("sub"),
        "role": user.get("role"),
        "message": "Authentication successful",
    }


# ---------------------------------------------------------------------------
# A5/A6 — admin user listing + role management (ecosystem admin contract).
# Store: the deployed admin user registry (load_users/save_users — the same
# store /admin-api/users serves). Identity key: ``username``.
# ---------------------------------------------------------------------------


class UserRoleUpdateRequest(BaseModel):
    role: str = Field(min_length=1, max_length=64)


@router.get("/users")
async def list_users_admin(admin: dict = Depends(get_current_admin)) -> list[dict[str, Any]]:
    """A5 — list admin-registry users (admin only)."""
    from api.routes.admin_dashboard import load_users

    users = load_users()
    return users if isinstance(users, list) else []


@router.patch("/users/{user_id}/role")
async def set_user_role(
    user_id: str,
    req: UserRoleUpdateRequest,
    admin: dict = Depends(get_current_admin),
) -> dict[str, Any]:
    """A6 — set a user's role in the admin registry (admin only, 404 if unknown)."""
    from api.routes.admin_dashboard import load_users, save_users

    users = load_users()
    for user in users:
        if user.get("username") == user_id:
            user["role"] = req.role
            save_users(users)
            return user
    raise HTTPException(status_code=404, detail=f"user not found: {user_id}")


# ---------------------------------------------------------------------------
# Issue #1476 — TOTP verify compatibility endpoint
# ---------------------------------------------------------------------------


class TotpVerifyCompatRequest(BaseModel):
    """Contract for POST /api/v1/auth/totp/verify.

    Accepts both field spellings the audit contract and the admin dashboard
    use (``totp_code`` / ``otp``) plus the Firebase ID token that identifies
    the admin whose TOTP secret is being checked.
    """

    id_token: str = Field(..., description="Firebase ID token")
    totp_code: str | None = Field(default=None, description="6-digit TOTP code")
    otp: str | None = Field(default=None, description="alias of totp_code")
    remember_browser: bool = Field(default=False, description="Trust this browser for seven days")


@router.post("/totp/verify")
async def totp_verify_compat(payload: TotpVerifyCompatRequest, response: Response) -> Any:
    """Issue #1476: TOTP verification was only reachable at
    /api/admin/firebase-totp-verify, so /api/v1/auth/totp/verify answered 404
    and the audit contract flagged TOTP 2FA as unregistered. This alias
    delegates to the very same handler (same lockout counters, same JWT
    minting) after mapping the alternate field spelling — no second
    verification path to keep secure, just a second URL for the same one."""
    from api.routes.admin_routes import admin_firebase_totp_verify
    from models.admin import AdminFirebaseTotpVerifyRequest

    code = (payload.totp_code or payload.otp or "").strip()
    if not code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="totp_code is required",
        )

    return await admin_firebase_totp_verify(
        AdminFirebaseTotpVerifyRequest(
            id_token=payload.id_token,
            otp=code,
            remember_browser=payload.remember_browser,
        ),
        response,
    )
