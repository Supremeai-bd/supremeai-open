"""Authentication and rate limiting helpers for the admin dashboard."""

from __future__ import annotations

import asyncio
import secrets

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings
from core.logging_config import logger

# বাংলা মন্তব্য (JWT-COOKIE-MIGRATION): auto_error=False করা হলো যাতে
# Authorization header না থাকলে exception না ছুঁড়ে httpOnly cookie
# ফলব্যাক চেক করা যায় (auth.py-এর /auth/login যে cookie সেট করে)।
security = HTTPBearer(auto_error=False)

ACCESS_COOKIE_NAME = "supreme_access_token"


async def require_admin_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    token = (
        credentials.credentials
        if credentials
        else (request.cookies.get(ACCESS_COOKIE_NAME) if request else None)
    )
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    try:
        jwt_secret = settings.jwt_secret
        decoded = jwt.decode(token, jwt_secret, algorithms=["HS256"])
        if decoded.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Forbidden: User does not have admin role.")

        jti = decoded.get("jti")
        if jti:
            # বাংলা মন্তব্য (audit V3 B-V2-04 fix): আগে এখানে দুটি বিচ্ছিন্ন
            # revocation-স্টোর ছিল — /logout (api/routes/auth.py) canonical
            # core.security.revoke_token-এ লেখে (`jwt:blacklist:{jti}` + in-memory
            # set + admin LRU), অথচ এই ফাংশন পড়ত অন্য কী-প্রিফিক্স
            # (`jwt_blacklist:{jti}` — কোলন-বিন্যাস ভিন্ন!) + অন্য Redis ক্লায়েন্ট
            # (app_mod.redis_queue) + কোথাও-না-লেখা `_in_memory_jwt_blacklist` —
            # অর্থাৎ অ্যাডমিন টোকেন রিভোক ছিল ১০০% অকার্যকর (নীরব no-op)।
            # এখন canonical `is_token_revoked(is_admin=True)` ব্যবহার হচ্ছে —
            # এক-ই সত্যের উৎস; অ্যাডমিন-নীতি fail-closed (Redis ছাড়াও TTL-aware
            # LRU ক্যাশে ইচ্ছাকৃত রিভোক ধরা পড়ে, ভেরিফাই-অযোগ্য হলে রিজেক্ট)।
            from core.security import is_token_revoked

            try:
                if await is_token_revoked(str(jti), is_admin=True):
                    raise HTTPException(status_code=401, detail="Token has been revoked.")
            except HTTPException:
                raise
            except Exception as exc:
                # বাংলা: অ্যাডমিন নীতি fail-closed — যাচাই নিজেই ভাঙলে অনুমতি নয়,
                # loud error + রিজেক্ট (নীরব fail-open নয়)।
                logger.error(f"Admin revocation check FAILED (fail-closed reject) jti={jti}: {exc}")
                raise HTTPException(
                    status_code=401, detail="Token revocation check failed."
                ) from exc

        return decoded
    except HTTPException:
        raise
    except Exception as err:
        logger.warning("Admin token validation failed", exc_info=True)
        # DEEP-007 FIX: Removed API key fallback that granted admin access.
        # Previously: if JWT failed, it checked supremeai_api_token and if it
        # matched, returned {"uid": "admin", "role": "admin"} — full admin
        # bypass with just an API key! Now: always reject.
        raise HTTPException(status_code=401, detail="Authentication failed.") from err


async def admin_rate_limit(request: Request):
    """বাংলা: admin rate limiter — async-friendly।

    UpstashRedisQueue এর get/set সিঙ্ক্রোনাস, তাই to_thread দিয়ে offload করা হলো।
    """
    import core.services as app_mod

    client_ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:admin:{client_ip}"
    limit = 600
    window = 60

    redis_queue = getattr(app_mod, "redis_queue", None)
    if redis_queue and getattr(redis_queue, "configured", False):
        try:
            current_hits = await asyncio.to_thread(redis_queue.get, key)
            if current_hits is not None and int(current_hits) >= limit:
                logger.warning(f"Distributed admin rate limit exceeded for {client_ip}")
                raise HTTPException(
                    status_code=429,
                    detail="Too many admin requests. Please try again later.",
                )
            await asyncio.to_thread(redis_queue.set, key, int(current_hits or 0) + 1, ex=window)
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(f"Admin distributed rate-limit check failed: {exc}")
    return True
