# backend/api/dependencies.py
"""API dependencies for SupremeAI.

Provides:
- verify_autonomous_agent_token: Fully async JWT verification with ErrorEventBus integration.
- get_fitness_engine: Fitness engine singleton.
- get_current_user_token: User token extraction.
- get_tenant_db: Tenant-aware database client.
"""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus
from core.self_evolution.fitness_engine import FitnessEngine
from database.tenant_db import TenantAwareFirestore

# শেয়ার্ড ইউটিলিটি — টেস্ট এনভায়রনমেন্ট চেক কেন্দ্রীভূত
from utils.environment import is_test_environment

security = HTTPBearer()

_fitness_engine = FitnessEngine()


def get_fitness_engine() -> FitnessEngine:
    return _fitness_engine


async def get_rate_limiter():
    """FastAPI dependency that returns the singleton rate limiter."""
    from core.provider_rate_limiter import get_provider_rate_limiter

    return get_provider_rate_limiter()


async def get_ai_integrator():
    """FastAPI dependency for the production-wired AI integrator."""
    from core.factory import get_factory

    factory = get_factory()
    if getattr(factory, "_integrator", None) is None:
        await factory.create_production_instance()
    return factory._integrator


@with_error_bus("verify_autonomous_agent_token")
async def verify_autonomous_agent_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Stateless JWT verification using PyJWT. Validates requests coming from the frontend
    or external integrations without blocking the main thread.
    """
    correlation_id = getattr(request.state, "correlation_id", "unknown")

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=["HS256"],
        )
        return payload

    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.PyJWTError as e:
        error_event_bus.emit(
            ErrorEvent(
                module="AuthGuard",
                error_type="INVALID_TOKEN",
                message=str(e)[:500],
                severity="WARNING",
                context={
                    "correlation_id": correlation_id,
                    "token_prefix": (
                        credentials.credentials[:10] if credentials.credentials else "none"
                    ),
                },
                structured_context=ErrorContext(
                    module="api.dependencies",
                    request_id=correlation_id,
                    env=settings.env,
                ),
            )
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def get_current_user_token(request: Request) -> dict:
    # 1. Check context injected by AuthMiddleware
    user = getattr(request.state, "user", None)
    if user:
        return user

    # 2. Test Environment fallback
    # SECURITY FIX (AUDIT-SEC-9, HIGH): আগে শুধু ENV != production এবং CI=true
    # (বা pytest/GITHUB_ACTIONS) থাকলেই এখানে role=admin ফেরত দেওয়া হত — কোনো
    # টোকেন ছাড়াই পুরো admin API খোলা পড়ত। একটা ভুল কনফিগ বা accidentally-set
    # CI env var-ই যথেষ্ট ছিল বাইপাসের জন্য। এখন explicit ALLOW_TEST_AUTH_BYPASS=true
    # (settings.is_bypass_allowed, production-এ hardcoded False) ছাড়া এই fallback
    # কাজ করবে না — টেস্টগুলোকে স্পষ্টভাবে opt-in করতে হবে।
    if is_test_environment() and settings.is_bypass_allowed:
        import os

        admin_email = os.getenv("ADMIN_EMAIL", "test_admin@supremeai.com")
        return {
            "sub": admin_email,
            "role": "admin",
            "tenant_id": os.getenv("ADMIN_TENANT_ID", "test-tenant"),
        }

    # 3. Fallback check
    raise HTTPException(status_code=401, detail="Unauthorized")


def _verified_subject(payload: dict) -> str:
    subject = str(
        payload.get("sub") or payload.get("user_id") or payload.get("email") or ""
    ).strip()
    if not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token subject required"
        )
    return subject


def get_current_admin(payload: dict = Depends(get_current_user_token)) -> dict:
    """Enforce the authenticated admin role for admin-facing routes."""
    if payload.get("role") != "admin":
        logger.warning("Unauthorized admin access attempt by %s", payload.get("sub"))
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return payload


def get_project_admin(payload: dict = Depends(get_current_user_token)) -> dict:
    """Require a tenant-bound project administrator; never accept tenant headers."""
    tenant_id = str(payload.get("tenant_id") or payload.get("org_id") or "").strip()
    role = str(payload.get("role") or "").lower()
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context required")
    if role not in {"admin", "owner", "project_admin", "tenant_admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Project administrator access required"
        )
    return {**payload, "tenant_id": tenant_id, "subject": _verified_subject(payload)}


def get_current_platform_admin(payload: dict = Depends(get_current_admin)) -> dict:
    """Require a platform administrator for cross-tenant control-plane operations.

    Project admins may manage their own workspace, but tenant provisioning and
    global usage controls must remain restricted to the explicitly configured
    platform administrator identities.
    """
    subject = str(payload.get("sub") or payload.get("email") or "").strip().lower()
    configured = {str(email).strip().lower() for email in settings.admin_emails if email}
    if not subject or subject not in configured:
        logger.warning("Platform-admin access denied for subject=%s", subject or "unknown")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform administrator access required",
        )
    return payload


def get_tenant_db(
    payload: dict = Depends(get_current_user_token),
) -> TenantAwareFirestore:
    """
    Dependency Injection: Extracts tenant_id (user email/uid) from JWT
    and returns a hard-isolated Firestore client.
    """
    tenant_id = payload.get("sub")
    if not tenant_id:
        logger.error("Token payload missing 'sub' (tenant_id) claim.")
        raise HTTPException(status_code=401, detail="Invalid token structure.")

    # রিটার্ন করছে আইসোলেটেড ডিবি ক্লায়েন্ট
    return TenantAwareFirestore(tenant_id=tenant_id)


def get_current_tenant(
    user: dict = Depends(get_current_user_token),
) -> str:
    """
    বাংলা মন্তব্য: TenantExtractionMiddleware-এর লজিক এখন Depends() হিসেবে।
    শুধুমাত্র যাচাইকৃত JWT claims থেকে tenant_id বের করে।

    শুধুমাত্র যে রাউটে tenant context দরকার সেখানে ব্যবহার করুন।
    উদাহরণ: tenant_id: str = Depends(get_current_tenant)
    """
    tenant_id = str(user.get("tenant_id") or user.get("org_id") or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context required")
    return tenant_id


async def verify_idempotency(request: Request) -> None:
    """
    বাংলা মন্তব্য: IdempotencyMiddleware-এর লজিক এখন Depends() হিসেবে।
    Redis-based distributed idempotency — শুধুমাত্র POST mutation routes-এ ব্যবহার করুন।

    উদাহরণ: _: None = Depends(verify_idempotency)
    """
    # শুধু POST রিকোয়েস্টে প্রযোজ্য
    if request.method != "POST":
        return

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail="Bad Request: 'Idempotency-Key' header is required for mutating operations.",
        )

    # বাংলা মন্তব্য: Redis manager import — fail-open কৌশল ব্যবহার করা হলো
    try:
        from core.cache.redis_manager import acquire_idempotency_lock, redis_manager
    except ImportError:
        logger.warning("[Idempotency Dep] Redis import failed — skipping (fail-open)")
        return

    if redis_manager.client is None:
        return

    # বাংলা মন্তব্য: ক্যাশে আগের রেসপন্স আছে কিনা চেক করা হচ্ছে
    import json

    try:
        cached_key = f"idempotency:response:{idempotency_key}"
        cached = await redis_manager.client.get(cached_key)
        if cached:
            json.loads(cached)
            # বাংলা মন্তব্য: HTTPException দিয়ে cached response ফেরত দেওয়া সম্ভব নয়
            # তাই এখানে শুধু duplicate lock চেক করা হয়
            logger.info(f"[Idempotency Dep] Cache hit for key: {idempotency_key}")
    except Exception as e:
        logger.warning(f"[Idempotency Dep] Cache read failed: {e}")

    # বাংলা মন্তব্য: ডুপ্লিকেট রিকোয়েস্ট প্রসেসিং ব্লক করা হচ্ছে
    acquired = await acquire_idempotency_lock(idempotency_key, 120)
    if not acquired:
        raise HTTPException(
            status_code=409,
            detail="Conflict: Request is already being processed. Duplicate execution blocked.",
        )

    # বাংলা মন্তব্য: Lock অ্যাকোয়ার হলে request state-এ key রাখা হচ্ছে
    request.state.idempotency_key = idempotency_key

    # বাংলা মন্তব্য: Exception হলেও lock release হবে এমন ব্যবস্থা করা
    # response send হলে বা exception হলে উভয় ক্ষেত্রেই lock release হবে
    import asyncio

    from starlette.middleware.base import BaseHTTPMiddleware

    # বাংলা মন্তব্য: Background task দিয়ে request complete হলে lock release করা
    # এটি response middleware হিসেবে কাজ করে

    # পদ্ধতি: Request state-এ cleanup function store করা, যা response পাঠানোর পর call হবে
    async def cleanup_idempotency_lock():
        """Idempotency lock release করার জন্য callback।
        বাংলা মন্তব্য: এটি response middleware ��্বারা call হবে।
        """
        try:
            from core.cache.redis_manager import release_idempotency_lock

            await release_idempotency_lock(idempotency_key)
            logger.debug(f"[Idempotency Dep] Lock released for key: {idempotency_key}")
        except Exception as e:
            logger.warning(f"[Idempotency Dep] Failed to release lock: {e}")

    # বাংলা মন্তব্য: Request state-এ cleanup function register করা
    if not hasattr(request.state, "_cleanup_callbacks"):
        request.state._cleanup_callbacks = []
    request.state._cleanup_callbacks.append(cleanup_idempotency_lock)

    original_send = request.scope.get("send")

    async def release_lock_on_response(message):
        if message["type"] == "http.response.body" and not message.get("more_body"):
            try:
                from core.cache.redis_manager import release_idempotency_lock

                await release_idempotency_lock(idempotency_key)
                logger.debug(f"[Idempotency Dep] Lock released for key: {idempotency_key}")
            except Exception as e:
                logger.warning(f"[Idempotency Dep] Failed to release lock: {e}")
        if original_send:
            await original_send(message)

    # বাংলা মন্তব্য: Middleware-এর send function override করা
    # এটি response পাঠানোর পরে lock release করবে
    if "send" in request.scope:
        request.scope["send"] = release_lock_on_response


def require_api_key_scope(required_scope: str):
    """Dependency that enforces a specific scope on the authenticated API key (Issue 7.8)."""

    async def _scope_checker(request: Request) -> dict:
        api_key_info = getattr(request.state, "api_key", None)
        if not api_key_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API Key required",
            )
        scopes = api_key_info.get("scopes") or []
        if "*" in scopes or required_scope in scopes:
            return api_key_info
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: API key lacks required scope '{required_scope}'",
        )

    return _scope_checker


__all__ = [
    "get_current_admin",
    "get_current_tenant",
    "get_current_user_token",
    "get_fitness_engine",
    "get_tenant_db",
    "require_api_key_scope",
    "verify_autonomous_agent_token",
    "verify_idempotency",
]
