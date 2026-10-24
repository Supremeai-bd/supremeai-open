"""Proxy-aware client-IP extraction (R2-08 fix, shared helper).

বাংলা মন্তব্য: X-Forwarded-For-এর প্রথম এন্ট্রি ক্লায়েন্ট নিজেই স্পুফ করতে পারে —
তাই কখনো `split(',')[0]` বিশ্বাস করা যাবে না। রিভার্স প্রক্সি (Render) আসল ক্লায়েন্ট
IP টি XFF-এর **শেষে** যোগ করে। এই হেল্পার:
  1. সরাসরি এক্সপোজারে (প্রক্সি নেই) → request.client.host (XFF সম্পূর্ণ উপেক্ষা)
  2. Render-এ (RENDER env) → ডিফল্ট ১টি trusted proxy hop ধরে XFF-এর শেষ-১ নম্বর এন্ট্রি
  3. কাস্টম সেটআপে → settings.trusted_proxy_count দিয়ে hop সংখ্যা নিয়ন্ত্রণ
ফলে রেট-লিমিট বাইপাস (এলোমেলো XFF দিয়ে নতুন বাকেট) আর সম্ভব নয়, আবার
ফ্রি-টিয়ারে "সব ইউজার এক প্রক্সি-IP বাকেটে" আটকে যাওয়াও নয়।
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _trusted_proxy_count() -> int:
    """How many proxy hops sit between the internet and this process."""
    import os

    # 1) Explicit operator configuration always wins
    explicit = os.getenv("TRUSTED_PROXY_COUNT")
    if explicit:
        try:
            return max(0, int(explicit))
        except ValueError as err:
            logger.debug(f"Invalid TRUSTED_PROXY_COUNT value {explicit!r}: {err}")

    # 2) Render always fronts web services with its proxy (appends client IP)
    try:
        from core.config import settings

        configured = getattr(settings, "trusted_proxy_count", None)
        if configured is not None:
            return max(0, int(configured))
    except Exception as exc:  # noqa: BLE001 — settings may be unavailable early in boot
        import logging

        logging.getLogger(__name__).debug(
            f"Unable to read trusted_proxy_count from settings: {exc}"
        )

    try:
        from core.config import settings

        if settings.is_cloud:
            return 1
    except Exception as exc:  # noqa: BLE001 — preserve safe local fallback during bootstrap
        logger.debug("Unable to determine platform from canonical settings: %s", exc)

    # 3) Direct local exposure — trust no header
    return 0


def get_client_ip(request) -> str:
    """Extract the trustworthy client IP from a Request.

    XFF semantics: every proxy APPENDS the address of the peer it received
    the request from. With N trusted proxy hops, the LAST N entries were
    appended by your own proxies; the outermost trusted proxy appended the
    true client IP at position `parts[-N]`. Anything before that may be
    attacker-controlled junk and must NEVER be trusted (the old
    `split(',')[0]` and `parts[-N-1]` patterns both let spoofed entries
    through).

    Example (Render, N=1): attacker sends "X-Forwarded-For: 1.2.3.4";
    Render appends the attacker's real IP 5.6.7.8 → "1.2.3.4, 5.6.7.8".
    parts[-1] = 5.6.7.8 ✓ (spoof ignored).
    """
    raw_host = request.client.host if request.client else "unknown"

    trusted = _trusted_proxy_count()
    if trusted <= 0:
        return raw_host

    xff = request.headers.get("x-forwarded-for", "") or request.headers.get("X-Forwarded-For", "")
    if not xff:
        return raw_host

    parts = [p.strip() for p in xff.split(",") if p.strip()]
    if len(parts) < trusted:
        # Fewer entries than proxy hops — malformed/spoofed chain, stay safe
        return raw_host
    return parts[-trusted]
