"""JIT OTP channel router — Human-in-the-loop delivery for Anti-Hacking Agent.

Zero-cost: Discord webhooks (free, unlimited), Resend free tier (3k emails/mo).
Telegram/WhatsApp are manual-trigger only (Option 3) — no default traffic,
since WhatsApp's free tier requires Meta Business verification we haven't
set up, and Telegram needs a bot registered per-admin. Wiring those is a
follow-up once you've created the credentials; the interface below already
supports both if triggered explicitly by an admin.

বাংলা মন্তব্য: অ্যাডমিন অথেনটিকেশনের জন্য ওটিপি সুইচিং রাউটার। ডিসকর্ড ওয়েবহুক এবং রিসেন্ড ইমেল সার্ভিস ব্যবহার করে।
"""

from __future__ import annotations

import os
import re

import httpx

from core.cache.redis_manager import redis_manager
from core.config import settings
from core.logging_config import logger

CHANNEL_DISCORD = "discord"
CHANNEL_EMAIL = "email"
CHANNEL_TELEGRAM = "telegram"  # manual only
CHANNEL_WHATSAPP = "whatsapp"  # manual only

_REDIS_KEY_PREFIX = "otp:channel:"  # per-admin channel override, TTL'd


def _mask(value: str | None, visible: int = 4) -> str:
    if not value:
        return "***"
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}...{value[-visible:]}"


def _sanitize_error(exc: Exception) -> str:
    msg = str(exc)
    msg = re.sub(r"https?://[^\s]+", "[REDACTED_URL]", msg)
    msg = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", r"\1[REDACTED_TOKEN]", msg)
    return msg[:200]


async def get_active_channel(admin_id: str) -> str:
    """Redis-backed channel preference; defaults to Discord."""
    if redis_manager and redis_manager.client:
        override = await redis_manager.get_cache(f"{_REDIS_KEY_PREFIX}{admin_id}")
        if override:
            return override
    return CHANNEL_DISCORD


async def set_active_channel(admin_id: str, channel: str, ttl_seconds: int = 3600) -> None:
    """Admin-triggered channel switch (human-in-the-loop). TTL'd so a forgotten
    override doesn't silently redirect OTPs forever."""
    if channel not in {
        CHANNEL_DISCORD,
        CHANNEL_EMAIL,
        CHANNEL_TELEGRAM,
        CHANNEL_WHATSAPP,
    }:
        raise ValueError(f"Unknown OTP channel: {channel}")
    if redis_manager and redis_manager.client:
        await redis_manager.set_cache(
            f"{_REDIS_KEY_PREFIX}{admin_id}", channel, ex_seconds=ttl_seconds
        )
    logger.info(
        f"🔐 OTP channel for admin {_mask(admin_id)} switched to {channel} (ttl={ttl_seconds}s)"
    )


async def send_otp(admin_id: str, code: str, context: dict) -> bool:
    """Send OTP via the admin's active channel, falling back to email on failure."""
    channel = await get_active_channel(admin_id)
    sent = False

    if channel == CHANNEL_DISCORD:
        sent = await _send_discord(admin_id, code, context)
        if not sent:
            logger.warning(
                f"Discord OTP delivery failed for {_mask(admin_id)}, falling back to email."
            )
            sent = await _send_email(admin_id, code, context)
    elif channel == CHANNEL_EMAIL:
        sent = await _send_email(admin_id, code, context)
    elif channel in (CHANNEL_TELEGRAM, CHANNEL_WHATSAPP):
        logger.warning(
            f"{channel} OTP requested for {_mask(admin_id)} but not yet wired up — falling back to Discord."
        )
        sent = await _send_discord(admin_id, code, context)

    return sent


async def _send_discord(admin_id: str, code: str, context: dict) -> bool:
    webhook_url = settings.discord_otp_webhook_url
    if not webhook_url or not webhook_url.get_secret_value():
        logger.error("DISCORD_OTP_WEBHOOK_URL not configured.")
        return False
    masked_admin = _mask(admin_id, visible=3)
    payload = {
        "content": (
            f"🚨 **Admin Login Verification** — `{masked_admin}`\n"
            f"Code: `{code}`\n"
            f"IP: `{context.get('ip', 'unknown')}` · Country: `{context.get('country', 'unknown')}`\n"
            f"Reply is not monitored here — verify in the admin dashboard."
        )
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(webhook_url.get_secret_value(), json=payload)
            return resp.status_code in (200, 204)
    except httpx.HTTPError as exc:
        logger.error(f"Discord OTP send failed: {_sanitize_error(exc)}")
        return False


async def _send_email(admin_id: str, code: str, context: dict) -> bool:
    api_key = settings.resend_api_key
    to_addr = settings.admin_notification_email
    if not api_key or not api_key.get_secret_value() or not to_addr:
        logger.error("RESEND_API_KEY or ADMIN_NOTIFICATION_EMAIL not configured.")
        return False
    masked_admin = _mask(admin_id, visible=3)
    # SECURE FIX: email sender is now env-driven (EMAIL_FROM_ADDRESS).
    # Previously hardcoded "SupremeAI Security <security@supremeai.app>" —
    # violates "zero hardcoded value" principle.
    email_from = os.getenv(
        "EMAIL_FROM_ADDRESS",
        "SupremeAI Security <noreply@supremeai.app>",  # dev fallback only
    )
    payload = {
        "from": email_from,
        "to": [to_addr],
        "subject": f"Admin Login Verification — {masked_admin}",
        "html": (
            f"<p>Code: <b>{code}</b></p>"
            f"<p>IP: {context.get('ip', 'unknown')} · Country: {context.get('country', 'unknown')}</p>"
        ),
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={"Authorization": f"Bearer {api_key.get_secret_value()}"},
            )
            return resp.status_code in (200, 201)
    except httpx.HTTPError as exc:
        logger.error(f"Resend OTP email failed: {_sanitize_error(exc)}")
        return False
