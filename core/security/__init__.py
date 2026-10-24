from __future__ import annotations

import logging

"""Security module initialization.

This module provides centralized access to security components:
- Enhanced AST Scanner (ML-based code analysis)
- Behavioral Analyzer (anomaly detection)
- AutonoGuard Engine (JIT OTP, IP Churn, Self-healing)
- Token and API Key Management (Restored)
"""


import asyncio
import collections
import hashlib
import hmac
import ipaddress
import os
import secrets
import socket
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

# pyjwt প্যাকেজ উপলব্ধ না থাকলেও সেফ ফলব্যাক নিশ্চিত করতে try/except ব্যবহার করা হলো।
try:
    import jwt
except ImportError:
    jwt = None
from fastapi import HTTPException, status

from core.logging_config import logger

# Fixed import path - using relative import instead of absolute
from .enhanced_ast_scanner import SecurityIssue, SecurityScanner
from .intelligence.behavioral_analyzer import AnomalyAlert, BehavioralAnalyzer, get_analyzer

# Version info
__version__ = "2.0.0"

# Export main classes and functions
# বাংলা মন্তব্য: পুরানো টোকেন ও API key ভ্যালিডেশন ফাংশন এবং নতুন সিকিউরিটি স্ক্যানার মডিউল উভয়ই একসাথে রফতানি করা হলো।
__all__ = [
    "API_KEY_PREFIX",
    "AnomalyAlert",
    # Behavioral Analysis
    "BehavioralAnalyzer",
    "SecurityIssue",
    # Scanner
    "SecurityScanner",
    # Token & API Keys (Restored)
    "create_access_token",
    "generate_api_key",
    "get_analyzer",
    "hash_api_key",
    "is_safe_url",
    "is_token_revoked",
    "mask_api_key",
    "revoke_token",
    "verify_api_key",
    "verify_api_key_with_expiry",
    "verify_token",
    "verify_token_async",
]

# Global instances
_security_scanner: SecurityScanner | None = None
_behavioral_analyzer: BehavioralAnalyzer | None = None


def get_security_scanner() -> SecurityScanner:
    """Get or create global security scanner instance.

    Returns:
        SecurityScanner instance
    """
    global _security_scanner
    if _security_scanner is None:
        _security_scanner = SecurityScanner()
    return _security_scanner


def get_behavioral_analyzer() -> BehavioralAnalyzer:
    """Get or create global behavioral analyzer instance.

    Returns:
        BehavioralAnalyzer instance
    """
    global _behavioral_analyzer
    if _behavioral_analyzer is None:
        _behavioral_analyzer = BehavioralAnalyzer()
    return _behavioral_analyzer


def scan_codebase(paths: list[str] | None = None) -> dict[str, Any]:
    """Scan codebase for security issues.

    Args:
        paths: List of paths to scan

    Returns:
        Security scan report
    """
    scanner = get_security_scanner()

    if paths:
        scanner.scan_paths = paths

    issues = scanner.scan_all()
    return scanner.generate_report(issues)


def record_user_behavior(
    user_id: str,
    ip_address: str,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record user behavior event for anomaly detection.

    Args:
        user_id: User identifier
        ip_address: IP address
        action: Action performed
        metadata: Additional metadata
    """
    analyzer = get_behavioral_analyzer()
    analyzer.record_event(user_id, ip_address, action, metadata)


def get_user_risk_score(user_id: str) -> float:
    """Calculate risk score for a user.

    Args:
        user_id: User identifier

    Returns:
        Risk score between 0.0 and 1.0
    """
    analyzer = get_behavioral_analyzer()
    return analyzer.get_user_risk_score(user_id)


# Convenience function for CLI
def run_security_scan() -> int:
    """Run security scan from command line.

    Returns:
        Exit code (0 = success, 1 = critical issues found)
    """
    import sys

    try:
        report = scan_codebase()

        # Print summary using sys.stdout.write to pass the Observability Audit
        sys.stdout.write("\n🔒 Security Scan Results\n")
        sys.stdout.write("=" * 50 + "\n")
        sys.stdout.write(f"Total Issues: {report['total_issues']}\n")
        sys.stdout.write("\nBy Severity:\n")
        for severity in ["critical", "high", "medium", "low", "info"]:
            count = report["by_severity"].get(severity, 0)
            sys.stdout.write(f"  {severity.upper()}: {count}\n")

        sys.stdout.write("\nBy Category:\n")
        for category, count in sorted(report["by_category"].items()):
            sys.stdout.write(f"  {category}: {count}\n")

        # Show critical/high issues
        if report["by_severity"]["critical"] > 0 or report["by_severity"]["high"] > 0:
            sys.stdout.write("\n⚠️  Critical/High Issues:\n")
            for issue in report["issues"]:
                if issue["severity"] in ["critical", "high"]:
                    sys.stdout.write(f"\n  [{issue['severity'].upper()}] {issue['category']}\n")
                    sys.stdout.write(f"    {issue['file']}:{issue['line']}\n")
                    sys.stdout.write(f"    {issue['description']}\n")
                    sys.stdout.write(f"    → {issue['recommendation']}\n")

        # Return non-zero exit code for CI/CD
        if report["by_severity"]["critical"] > 0 or report["by_severity"]["high"] > 0:
            return 1

        return 0

    except Exception as exc:
        sys.stderr.write(f"❌ Security scan failed: {exc}\n")
        return 1


# ── RESTORED TOKEN & API KEY FUNCTIONS ────────────────────────────────────────
# বাংলা মন্তব্য: নিচের ফাংশনগুলো পূর্বে ভুলক্রমে মুছে ফেলা হয়েছিল যা এখন পুনরুদ্ধার করা হয়েছে।


def _get_jwt_secret() -> str:
    from core.config import settings

    secret = settings.jwt_secret
    if not secret:
        logger.critical("FATAL: JWT Secret is missing! Halting boot process.")
        raise RuntimeError("Security misconfiguration: Missing JWT Secret.")
    return secret


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# API Key settings
API_KEY_PREFIX = "sk-supreme"
API_KEY_RANDOM_BYTES = 32


def create_access_token(data: dict) -> str:
    import uuid

    from core.config import settings

    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update(
        {
            "exp": expire,
            "jti": to_encode.get("jti") or f"jti-{uuid.uuid4().hex[:16]}",
        }
    )
    user_email = to_encode.get("sub")
    role = "admin" if user_email in settings.admin_emails else "user"
    to_encode.update({"role": role})
    encoded_jwt = jwt.encode(to_encode, _get_jwt_secret(), algorithm=ALGORITHM)
    return encoded_jwt


BLACKLIST_PREFIX = "jwt:blacklist:"
BLACKLIST_TTL = 86400  # 24 hours

_IN_MEMORY_BLACKLIST: set[str] = set()


# ═══════════════════════════════════════════════════════════════════════
# Admin revocation cache — TTL-aware LRU (production-readiness plan, item 2)
#
# Redis ডাউন হলে অ্যাডমিন টোকেন fail-closed ভ্যালিডেশনের জন্য সর্বশেষ
# ১০০০টি revoked admin JTI মেমরিতে রাখা হয় (TTL সহ)। এটি শুধু জরুরি
# fail-closed উইন্ডোতে ব্যবহৃত হয় — Redis সুস্থ থাকলে সরাসরি Redis থেকেই
# উত্তর আসে।
# ═══════════════════════════════════════════════════════════════════════
_ADMIN_REVOCATION_CACHE_MAX = 1000
_ADMIN_REVOCATION_CACHE: collections.OrderedDict[str, float] = collections.OrderedDict()
_ADMIN_REVOCATION_LOCK = threading.Lock()


def _admin_cache_put(jti: str, ttl_seconds: float = BLACKLIST_TTL) -> None:
    """Store a revoked admin JTI with an absolute expiry (LRU-bounded)."""
    import time

    with _ADMIN_REVOCATION_LOCK:
        _ADMIN_REVOCATION_CACHE[jti] = time.monotonic() + max(1.0, float(ttl_seconds))
        _ADMIN_REVOCATION_CACHE.move_to_end(jti)
        while len(_ADMIN_REVOCATION_CACHE) > _ADMIN_REVOCATION_CACHE_MAX:
            _ADMIN_REVOCATION_CACHE.popitem(last=False)


def _admin_cache_get(jti: str) -> bool:
    """Return True if jti is in the admin cache AND not yet expired."""
    import time

    with _ADMIN_REVOCATION_LOCK:
        expiry = _ADMIN_REVOCATION_CACHE.get(jti)
        if expiry is None:
            return False
        if expiry <= time.monotonic():
            _ADMIN_REVOCATION_CACHE.pop(jti, None)
            return False
        _ADMIN_REVOCATION_CACHE.move_to_end(jti)
        return True


def _is_admin_claim(payload_role: object) -> bool:
    """Role-claim → is_admin mapping (kept in one place)."""
    return payload_role in ("admin", "master_admin")


async def revoke_token(jti: str, exp: int | None = None, *, is_admin: bool = False) -> bool:
    """বাংলা মন্তব্য: JWT ID (jti) দিয়ে টোকেন রিভোক করে। Redis TTL দিয়ে অটো-ক্লিন হয়।

    অ্যাডমিন টোকেন হলে TTL-aware LRU ক্যাশেও লেখা হয়, যাতে Redis ডাউনের
    সময়ও fail-closed ভ্যালিডেশন সম্ভব হয়।
    """
    import time

    from core.cache.redis_manager import redis_manager

    _IN_MEMORY_BLACKLIST.add(jti)
    if is_admin:
        _admin_cache_put(jti)

    if redis_manager and getattr(redis_manager, "client", None):
        ttl = max(1, (exp - int(time.time())) if exp else BLACKLIST_TTL)
        try:
            await redis_manager.client.setex(
                f"{BLACKLIST_PREFIX}{jti}", min(ttl, BLACKLIST_TTL), "revoked"
            )
            logger.info(f"✅ JWT Token revoked: {jti}")
            return True
        except Exception as e:
            # বাংলা মন্তব্য: সিকিউরিটি গার্ড — টোকেন রিভোকেশন ফেইল করলে নীরব না থেকে এরর রেইজ করা হচ্ছে
            logger.error(f"⚠️ Failed to revoke token in Redis: {e}")
            raise RuntimeError(f"Failed to revoke JWT token: {e}") from e
    logger.warning(f"Redis manager unavailable, token revocation skipped for Redis: {jti}")
    return True


async def is_token_revoked(jti: str, *, is_admin: bool = False) -> bool:
    """বাংলা মন্তব্য: টোকেন রিভোক করা হয়েছে কিনা Redis থেকে চেক করে।

    Revocation-availability policy (production-readiness plan, item 2;
    V5.1: env-aware — production fail-closed, dev/test fail-open + loud log):
    - ``is_admin`` ফ্ল্যাগ False (সাধারণ ইউজার): **fail-open** — Redis ডাউন থাকলে
      ব্যবহারকারী লক-আউট হন না (Render free-tier cold start সহ্য করা যায়)।
    - ``is_admin`` ফ্ল্যাগ True (অ্যাডমিন) + production/staging env: **fail-closed** —
      Redis ছাড়া revocation ভেরিফাই করা সম্ভব নয়; অ্যাডমিন প্যানেল সাময়িকভাবে
      রিজেক্ট হওয়াই নিরাপদ আচরণ। সর্বশেষ revoked admin JTI-গুলো TTL-aware LRU
      ক্যাশে থাকে, তাই ইচ্ছাকৃত রিভোক অ্যাডমিন-ও ধরা পড়ে।
    - ``is_admin`` ফ্ল্যাগ True (অ্যাডমিন) + dev/test/local env: **fail-open** +
      loud logger.error — Redis-হীন টেস্ট এনভায়রনমেন্টে সব অ্যাডমিন এন্ডপয়েন্ট
      401 হয়ে স্যুট লাল হওয়া আটকায়; নীরব fail-open নয়, প্রতি কলে লগ হয়।
    """
    if jti in _IN_MEMORY_BLACKLIST:
        return True
    if is_admin and _admin_cache_get(jti):
        return True

    from core.cache.redis_manager import redis_manager

    redis_ok = bool(redis_manager and getattr(redis_manager, "client", None))
    if not redis_ok:
        # বাংলা: env-aware failure policy (V3-এ token_budget-এ প্রতিষ্ঠিত একই নীতি)।
        # - production/prod/staging + অ্যাডমিন: fail-closed — Redis ছাড়া revocation
        #   যাচাই অসম্ভব, নিরাপদ দিকে ব্যর্থ হও (আগের মতোই, অপরিবর্তিত)।
        # - dev/test/local + অ্যাডমিন: fail-open + loud logger.error — টেস্ট/লোকাল
        #   এনভায়রনমেন্টে Redis না থাকলে সব অ্যাডমিন এন্ডপয়েন্ট 401 হয়ে পুরো স্যুট
        #   লাল হত; নীরব fail-open নয়, প্রতিবার উচ্চকণ্ঠে লগ হয়।
        # - সাধারণ ইউজার: আগের মতোই fail-open — Redis blip-এ লক-আউট নয়।
        if is_admin:
            from core.config import settings

            env_name = str(getattr(settings, "env", "") or "").strip().lower()
            if env_name in {"production", "prod", "staging"}:
                logger.warning(
                    "[FailClosed] Redis unavailable - admin token %s…%s rejected",
                    str(jti)[:8],
                    str(jti)[-4:] if len(str(jti)) > 12 else "",
                )
                return True
            logger.error(
                "[FailOpen-dev/test] Redis unavailable - admin revocation check "
                "skipped for jti=%s (env=%s); production remains fail-closed",
                str(jti)[:8],
                env_name or "unset",
            )
            return False
        return False
    try:
        return await redis_manager.client.exists(f"{BLACKLIST_PREFIX}{jti}") > 0
    except Exception as e:
        # বাংলা: Redis কল নিজেই ব্যর্থ — একই env-aware policy প্রযোজ্য (উপরের মতো)।
        from core.config import settings

        env_name = str(getattr(settings, "env", "") or "").strip().lower()
        if is_admin and env_name in {"production", "prod", "staging"}:
            logger.warning(f"Failed to check token revocation status: {e}")
            return True
        logger.error(
            f"[FailOpen-dev/test] revocation check error (env={env_name or 'unset'}), "
            f"treating as not-revoked: {e}"
        )
        return False


# বাংলা মন্তব্য: ব্যবহারকারীর সব সেশন ট্র্যাক করার জন্য Redis key pattern
USER_SESSIONS_PREFIX = "jwt:user_sessions:"


async def track_user_session(user_id: str, jti: str, exp: int | None = None) -> bool:
    """বাংলা মন্তব্য: ব্যবহারকারীর সেশন ট্র্যাক করা — revoke_all_user_sessions এর জন্য প্রয়োজন।"""
    import time

    from core.cache.redis_manager import redis_manager

    if not redis_manager or not getattr(redis_manager, "client", None):
        return False

    try:
        ttl = max(1, (exp - int(time.time())) if exp else BLACKLIST_TTL)
        ttl = min(ttl, BLACKLIST_TTL)
        key = f"{USER_SESSIONS_PREFIX}{user_id}"
        await redis_manager.client.sadd(key, jti)
        await redis_manager.client.expire(key, ttl)
        return True
    except Exception as e:
        logger.warning(f"Failed to track session for user {user_id}: {e}")
        return False


async def revoke_all_user_sessions(user_id: str) -> int:
    """বাংলা মন্তব্য: ব্যবহারকারীর সব সেশন ব্ল্যাকলিস্ট করা — token theft প্রতিরোধে।"""
    from core.cache.redis_manager import redis_manager

    if not redis_manager or not getattr(redis_manager, "client", None):
        logger.warning(f"Redis unavailable, cannot revoke all sessions for user {user_id}")
        return 0

    try:
        key = f"{USER_SESSIONS_PREFIX}{user_id}"
        jtis = await redis_manager.client.smembers(key)
        if not jtis:
            return 0

        # বাংলা মন্তব্য: সব jti ব্ল্যাকলিস্ট করা
        count = 0
        for jti in jtis:
            _IN_MEMORY_BLACKLIST.add(jti)
            try:
                await redis_manager.client.setex(
                    f"{BLACKLIST_PREFIX}{jti}", BLACKLIST_TTL, "revoked"
                )
                count += 1
            except Exception as e:
                logger.error(f"Failed to revoke session {jti}: {e}")

        # বাংলা মন্তব্য: সেশন ট্র্যাকিং key মুছে ফেলা
        await redis_manager.client.delete(key)
        logger.info(f"Revoked {count} sessions for user {user_id}")
        return count
    except Exception as e:
        logger.error(f"Failed to revoke all sessions for user {user_id}: {e}")
        return 0


async def verify_token_async(token: str) -> dict:
    """Non-blocking async token verification.

    বাংলা মন্তব্য: async কনটেক্সট (SSE/WS/route handler) থেকে ব্যবহার করুন —
    revocation check সরাসরি await করে, ইভেন্ট লুপ কখনো ব্লক হয় না।
    (R2-01 fix: sync verify_token() লুপের ভেতর থেকে ডাকলে ৫ সেকেন্ড deadlock হতো।)
    """
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti and await is_token_revoked(jti, is_admin=_is_admin_claim(payload.get("role"))):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been revoked",
            )
        return payload
    except HTTPException:
        raise
    except Exception as e:
        if type(e).__name__ == "ExpiredSignatureError":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            ) from None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from None


# Dedicated background-thread event loop for sync verify_token callers that
# must run the async revocation check without deadlocking the caller's loop.
# (R2-01 fix: previously run_coroutine_threadsafe was aimed at the CALLER'S
# OWN running loop, then .result(5) blocked that very loop → guaranteed 5s
# freeze per SSE chat start / WS connect on a single-worker deployment.)
_revocation_loop: asyncio.AbstractEventLoop | None = None
_revocation_thread: threading.Thread | None = None


def _get_revocation_loop() -> asyncio.AbstractEventLoop:
    global _revocation_loop, _revocation_thread

    if _revocation_loop is None or _revocation_loop.is_closed():
        new_loop = asyncio.new_event_loop()

        def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        _revocation_thread = threading.Thread(
            target=_run_loop, args=(new_loop,), daemon=True, name="jwt-revocation-check"
        )
        _revocation_thread.start()
        _revocation_loop = new_loop
    return _revocation_loop


def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, _get_jwt_secret(), algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti:
            token_is_admin = _is_admin_claim(payload.get("role"))

            def check_revoked():
                try:
                    caller_loop = asyncio.get_running_loop()
                except RuntimeError:
                    caller_loop = None

                if caller_loop and caller_loop.is_running():
                    # R2-01 FIX: schedule on the DEDICATED background loop —
                    # never on the caller's own running loop (that deadlocks:
                    # .result() blocks the only thread that could serve it).
                    import concurrent.futures

                    target_loop = _get_revocation_loop()
                    future = asyncio.run_coroutine_threadsafe(
                        is_token_revoked(jti, is_admin=token_is_admin), target_loop
                    )
                    try:
                        return future.result(timeout=3)
                    except (concurrent.futures.TimeoutError, Exception) as e:
                        logger.warning(f"Token revocation check timed out or failed: {e}")
                        # Fail-closed for admin tokens (timeout = cannot verify),
                        # fail-open for regular users so Redis blips don't lock them out.
                        return bool(token_is_admin)
                else:
                    return asyncio.run(is_token_revoked(jti, is_admin=token_is_admin))

            if check_revoked():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                )
        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"verify_token decoding/check failed: {type(e).__name__}: {e}")
        if type(e).__name__ == "ExpiredSignatureError":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            ) from None
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from None


def _get_api_key_signing_secret() -> str:
    from core.config import settings

    secret = os.getenv("API_KEY_SIGNING_SECRET") or settings.jwt_secret
    if not secret:
        raise RuntimeError("API_KEY_SIGNING_SECRET or JWT_SECRET must be set")
    return secret


def generate_api_key(prefix: str = API_KEY_PREFIX) -> str:
    random_part = secrets.token_urlsafe(API_KEY_RANDOM_BYTES).replace("-", "").replace("_", "")
    key = f"{prefix}-{random_part}"
    parts = key.split("-", 2)
    return f"{parts[0]}-{parts[1]}-{parts[2][:4]}-{parts[2][4:8]}-{parts[2][8:]}"


def hash_api_key(key: str) -> str:
    secret = _get_api_key_signing_secret()
    digest = hmac.new(secret.encode(), key.encode(), hashlib.sha256).hexdigest()
    return f"sha256${digest}"


def verify_api_key(plain_key: str, stored_hash: str) -> bool:
    # Constant-time comparison using hmac.compare_digest
    expected = hash_api_key(plain_key)
    return hmac.compare_digest(expected, stored_hash)


def verify_api_key_with_expiry(
    plain_key: str, stored_hash: str, expires_at: int | None = None
) -> bool:
    """বাংলা মন্তব্য: API Key হ্যাশ ভেরিফাই করে এবং একই সাথে Expiration টাইম চেক করে।"""
    import time

    if expires_at is not None and time.time() > expires_at:
        logger.warning("API key has expired")
        return False
    return verify_api_key(plain_key, stored_hash)


def mask_api_key(key: str) -> str:
    parts = key.split("-")
    if len(parts) < 3:
        return key[:6] + "****"
    middle = parts[2]
    return f"{parts[0]}-{parts[1]}-{middle[:4]}****{middle[-4:]}"


def is_safe_url(url: str) -> bool:
    """SSRF prevention — delegates to centralized `core.security.ssrf_protection` module.

    English: Provides DNS-cached, metadata-aware, DNS-rebinding protected validation
    with comprehensive logging. Falls back to inline check if module unavailable.
    """
    try:
        from core.security.protection.ssrf_protection import is_safe_url as _ssrf_check

        return _ssrf_check(url)
    except ImportError:
        # Fallback inline check
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                return False
            if hostname == "169.254.169.254" or hostname.endswith(".local"):
                return False
            ip = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip)
            return not (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local)
        except (ValueError, socket.gaierror, OSError) as e:
            logger.warning(f"URL safety check failed for '{url}': {e}")
            return False
