# backend/middleware/tenant_rate_limiter.py
"""Upstash / Redis atomics-based tenant rate limiter middleware.

বাংলা মন্তব্য: ডিস্ট্রিবিউটেড টেন্যান্ট রেট লিমিটিং। race condition রোধ করতে Redis pipeline/incr পরমাণু (atomic) অপারেশন ব্যবহার করা হয়েছে।

M13 (P-B + P-C): সীমা/জানালা config-চালিত (TENANT_RATE_LIMIT_MAX_HITS /
TENANT_RATE_LIMIT_WINDOW_SECONDS — ডিফল্ট অপরিবর্তিত 100/60); Redis-বিভ্রাটে
fail-মোড config-চালিত (TENANT_RATE_LIMIT_FAIL_MODE): "open" (ডিফল্ট = আজকের
আচরণ, loud লগসহ) | "fallback" (বাউন্ডেড ইন-মেমরি sliding window — per-instance,
aggregate-safe নয়, লাউড লগ) | "closed" (429 — কঠোর পরিবেশে fail-closed)।
নীতি-প্যাটার্ন: V5.1 is_token_revoked env-aware fail-policy।
"""

from fastapi import HTTPException, Request

from core.config import settings
from core.logging_config import logger

# M13 P-C: Redis-বিভ্রাটে fallback ব্যবহারের জন্য বাউন্ডেড ইন-মেমরি limiter
# (InMemoryFallbackLimiter-প্যাটার্ন পুনঃব্যবহার) — "fallback" মোডে কেবল।
from middleware.rate_limiter import InMemoryFallbackLimiter

_tenant_fallback_limiter = InMemoryFallbackLimiter(burst=100, window=60.0)


def _rate_limit_identity(request: Request) -> str:
    """Return an identity that is never controlled by a tenant header.

    Authentication middleware may run after this dependency, so unauthenticated
    requests are isolated by source IP until a verified tenant is available.
    """
    tenant_id = getattr(request.state, "tenant_id", None)
    if tenant_id:
        return f"tenant:{tenant_id}"

    user = getattr(request.state, "user", None) or {}
    subject = user.get("sub") or user.get("subject")
    if subject:
        return f"subject:{subject}"

    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


def _resolve_fail_mode() -> str:
    """Config fail-মোড সৎ-সংকল্প — অজানা মান fail-closed নয়, 'open'-এ পড়ে না;
    অজানা মান = loud 'open' + সতর্কবার্তা (নীরব পছন্দ নিষিদ্ধ)।"""
    mode = (settings.tenant_rate_limit_fail_mode or "").strip().lower()
    if mode in {"open", "fallback", "closed"}:
        return mode
    logger.warning(
        f"⚠️ Unknown TENANT_RATE_LIMIT_FAIL_MODE={settings.tenant_rate_limit_fail_mode!r} "
        f"— treating as 'open' (loud, not silent)."
    )
    return "open"


def _degraded_response(identity: str, mode: str) -> None:
    """Redis-অনুপস্থিতিতে fail-মোড অনুযায়ী সিদ্ধান্ত — কোনো নীরব শাখা নেই।"""
    if mode == "closed":
        # M13 P-C: fail-closed — কঠোর পরিবেশে Redis ছাড়া টেন্যান্ট-সীমা
        # অনুপস্থিত থাকা = পুরো গেট অর্থহীন; তাই স্পষ্ট 429।
        logger.critical(
            f"🚨 Tenant rate limiter Redis unavailable and fail-mode='closed' — "
            f"rejecting {identity} (fail-closed policy)."
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limiter unavailable — request rejected (fail-closed policy).",
        )
    if mode == "fallback":
        allowed = _tenant_fallback_limiter.is_allowed(identity, settings.tenant_rate_limit_max_hits)
        logger.warning(
            f"⚠️ Tenant rate limiter Redis unavailable — bounded in-memory fallback "
            f"active for {identity} (per-instance, NOT aggregate-safe). allowed={allowed}"
        )
        if not allowed:
            raise HTTPException(status_code=429, detail="Too Many Requests. Rate limit exceeded.")
        return
    # mode == "open" (ডিফল্ট): আজকের আচরণ — loud লগ + bypass।
    logger.warning(
        f"⚠️ Tenant rate limiter Redis unavailable — failing OPEN for {identity} "
        f"(TENANT_RATE_LIMIT_FAIL_MODE=open). Set 'fallback'/'closed' to enforce."
    )
    return


async def enforce_tenant_rate_limit(request: Request):
    """Upstash / Redis atomic sliding window rate limiting guard."""
    identity = _rate_limit_identity(request)
    fail_mode = _resolve_fail_mode()

    from core.cache.redis_manager import redis_manager

    if not redis_manager or not getattr(redis_manager, "client", None):
        _degraded_response(identity, fail_mode)
        return

    # Issue #460: dedicated namespace. The old "rate_limit:{identity}" name
    # collides with AsyncRateLimiter's ZSET keys ("rate_limit:ip:{ip}") —
    # a counter INCR against a ZSET is WRONGTYPE, so the two limiters used
    # to fight over the same keys.
    cache_key = f"tenant_rl:{identity}"

    try:
        # Issue #460: single atomic EVAL (1 billable op) instead of the
        # INCR+EXPIRE 2-command pipeline.
        # M13 P-B (union-merge): window config-চালিত — hardcode 60 নয়।
        from core.cache.rate_limit_atomic import atomic_window_incr

        # Issue #936: raise_on_failure=True পাস করা হলো যাতে Redis pipeline/EVAL
        # exception propagate করে নিচের `except Exception` branch-এ যায় — সেখানে
        # `_degraded_response(identity, fail_mode)` tenant fail_mode policy apply
        # করে (closed=429 / fallback=in-memory bounded / open=loud log bypass)।
        # ডিফল্ট False হলে atomic_window_incr নিজেই fail-open return 0 করত (Issue
        # #895 contract), কিন্তু তাতে fail_mode apply হত না — test_pipeline_error_
        # applies_fail_mode contract ভেঙে যেত।
        current_hits = await atomic_window_incr(
            redis_manager.client,
            cache_key,
            settings.tenant_rate_limit_window_seconds,
            raise_on_failure=True,
        )

        if current_hits > settings.tenant_rate_limit_max_hits:
            logger.critical(f"🚨 Rate Limit Exceeded for {identity} ({current_hits} hits)!")
            raise HTTPException(status_code=429, detail="Too Many Requests. Rate limit exceeded.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"⚠️ Rate limiter error: {exc}. Applying fail-mode '{fail_mode}'.")
        _degraded_response(identity, fail_mode)
        return
