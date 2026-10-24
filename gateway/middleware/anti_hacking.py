"""Anti-Hacking Agent — context-aware checks + JIT OTP routing (Admin API only).

Alert-only by default (ENFORCE_ANTI_HACKING=false): logs + notifies on context
mismatch but never blocks. Flip the env var to enforce once false-positive
rate from VPNs/CGNAT/mobile-switching has been observed and is acceptable.

বাংলা মন্তব্য: অ্যাডমিন সিকিউরিটি ওটিপি মিডলওয়্যার। এটি ইউজারের আইপি, কান্ট্রি ও ডিভাইস ফিঙ্গারপ্রিন্ট ভেরিফিকেশন চেক করে।
"""

from __future__ import annotations

import json
import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.cache.redis_manager import redis_manager
from core.config import settings
from core.otp_router import send_otp

_CONTEXT_KEY_PREFIX = "security:last_context:"
_CONTEXT_TTL = int(os.getenv("SECURITY_CONTEXT_TTL") or "86400")
_OTP_COOLDOWN_PREFIX = "security:otp_cooldown:"
_CAUTION_LOG_PREFIX = "security:caution_log:"
_CAUTION_LOG_TTL = int(os.getenv("SECURITY_CAUTION_LOG_TTL") or "86400")


def _octet3(ip: str) -> str:
    """First 3 octets of an IPv4 address (e.g. '1.2.3.4' -> '1.2.3'). Falls back to
    the full value for IPv6/unknown so those never spuriously match each other.

    বাংলা: IPv4-এর প্রথম ৩টি অক্টেট বের করে — CGNAT/mobile handoff-এ সাধারণত শেষ অক্টেটই বদলায়।
    """
    parts = ip.split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else ip


class AntiHackingContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        from utils.client_ip import get_client_ip

        signal = {
            "ip": get_client_ip(request),
            "country": request.headers.get("cf-ipcountry", "unknown"),
            "ua": request.headers.get("user-agent", "unknown"),
            "fingerprint": request.headers.get("x-device-fingerprint", "unknown"),
        }
        request.state.security_signal = signal

        admin_id = getattr(getattr(request.state, "user", None), "get", lambda *_: None)("sub")
        if admin_id:
            if redis_manager and redis_manager.client:
                key = f"{_CONTEXT_KEY_PREFIX}{admin_id}"
                raw_last = await redis_manager.get_cache(key)
                last = json.loads(raw_last) if raw_last else None

                mismatch = False
                caution = False
                if last:
                    mismatch = (
                        last.get("ip") != signal["ip"] or last.get("country") != signal["country"]
                    )

                    fingerprint_match = (
                        last.get("fingerprint") not in (None, "unknown")
                        and signal["fingerprint"] not in (None, "unknown")
                        and last.get("fingerprint") == signal["fingerprint"]
                    )

                    if mismatch:
                        same_ua = (
                            last.get("ua") not in (None, "unknown")
                            and last.get("ua") == signal["ua"]
                        )
                        same_subnet = bool(signal["ip"]) and _octet3(last.get("ip", "")) == _octet3(
                            signal["ip"]
                        )
                        # বাংলা মন্তব্য: একই ইউজার-এজেন্ট অথবা সাবনেট পাওয়া গেলে সেটিকে আংশিক ম্যাচ (Caution) হিসেবে ধরা হবে এবং OTP ট্রিগার হবে না।
                        if same_ua or same_subnet or fingerprint_match:
                            caution = True
                            mismatch = False

                if caution:
                    from core.logging_config import logger as _logger

                    _logger.info(
                        f"CAUTION: partial context match for admin {admin_id} (same_ua/subnet, no OTP fired): {signal} vs last {last}"
                    )
                    if redis_manager and redis_manager.client:
                        await redis_manager.client.lpush(
                            f"{_CAUTION_LOG_PREFIX}{admin_id}", json.dumps(signal)
                        )
                        await redis_manager.client.ltrim(f"{_CAUTION_LOG_PREFIX}{admin_id}", 0, 49)
                        await redis_manager.client.expire(
                            f"{_CAUTION_LOG_PREFIX}{admin_id}", _CAUTION_LOG_TTL
                        )

                if mismatch:
                    cooldown_key = f"{_OTP_COOLDOWN_PREFIX}{admin_id}"
                    cooldown_active = False
                    if redis_manager and redis_manager.client:
                        acquired = await redis_manager.client.set(
                            cooldown_key, "1", nx=True, ex=settings.otp_cooldown_seconds
                        )
                        cooldown_active = not bool(acquired)

                    if cooldown_active:
                        from core.logging_config import logger as _logger2

                        _logger2.info(
                            f"OTP cooldown active for admin {admin_id} - suppressing duplicate send/notification."
                        )
                        request.state.security_otp_pending = True
                        if settings.enforce_anti_hacking:
                            return JSONResponse(
                                status_code=403,
                                content={
                                    "error": "context_mismatch",
                                    "detail": "OTP verification required — check your configured channel.",
                                },
                            )
                        await redis_manager.set_cache(
                            key, json.dumps(signal), ex_seconds=_CONTEXT_TTL
                        )
                        return await call_next(request)

                    code = f"{secrets.randbelow(900000) + 100000}"
                    await send_otp(admin_id, code, signal)
                    request.state.security_otp_pending = True

                    # বাংলা মন্তব্য: ওটিপি কোড যাচাইয়ের জন্য Redis-এ রাখা হচ্ছে
                    # (M13 P-B: TTL এখন config-চালিত — SECURITY_OTP_PENDING_TTL,
                    # ডিফল্ট 300s অপরিবর্তিত)।
                    await redis_manager.set_cache(
                        f"security:otp_pending:{admin_id}",
                        json.dumps({"code": code, "signal": signal}),
                        ex_seconds=settings.security_otp_pending_ttl,
                    )

                    if settings.enforce_anti_hacking:
                        return JSONResponse(
                            status_code=403,
                            content={
                                "error": "context_mismatch",
                                "detail": "OTP verification required — check your configured channel.",
                            },
                        )
                    # alert-only: log and continue
                    from core.logging_config import logger

                    logger.warning(
                        f"🔓 [ALERT-ONLY] Context mismatch for admin {admin_id}: {signal} vs last {last}"
                    )

                await redis_manager.set_cache(key, json.dumps(signal), ex_seconds=_CONTEXT_TTL)

        return await call_next(request)
