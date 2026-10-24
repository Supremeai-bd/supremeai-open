"""M19 P-C — preferred_language → system-directive লুপ-বন্ধ (issue #453 Wave 4)।

বাংলা: ব্যবহারকারীর সংরক্ষিত ভাষা-পছন্দ (user_preferences._extended.
preferred_language) আগে কেবল সংরক্ষিত হতো — chat/SSE-পথ কখনো মডেলকে
জানাত না (খোলা লুপ)। এই মডিউল সেটি পড়ে ক্যানোনিকাল system-directive
তৈরি করে — ContextEngine-এর SYSTEM block হিসেবে (M07 P-F caps-সম্মত)।

চুক্তি:
- পছন্দ-অনুপস্থিত/``en`` → ``None`` — আজকের আচরণ byte-সমতুল্য;
- read-ব্যর্থতা → লাউড warning + ``None`` (নীরব ভান নয়, directive-বিহীন);
- kill-switch ``SUPREMEAI_LANGUAGE_LOOP=off`` → লুপ বন্ধ; অজানা-মান
  fail-closed (M05 P-A শৃঙ্খলা)।
"""

from __future__ import annotations

import os

from core.logging_config import logger

_KILL_SWITCH = "SUPREMEAI_LANGUAGE_LOOP"

_EN_VARIANTS = frozenset({"", "en", "en-us", "english"})
_BN_VARIANTS = frozenset({"bn", "bn-bd", "bn-in", "bangla", "bengali"})


def language_loop_enabled() -> bool:
    """Kill-switch gate — ডিফল্ট চালু (পছন্দ-অনুপস্থিতে নিরীহ no-op)।"""
    raw = (os.getenv(_KILL_SWITCH, "") or "").strip().lower()
    if raw == "off":
        return False
    if raw in ("on", "true"):
        return True
    if raw == "":
        return True
    logger.warning(f"{_KILL_SWITCH} অজানা মান ({raw!r}) — fail-closed: লুপ বন্ধ।")
    return False


async def resolve_preferred_language(user_id: str | None) -> str | None:
    """user_preferences থেকে preferred_language — best-effort, অনুপস্থিতে ``None``।

    বাংলা: ERR-H01-এর হোস্টিং-চুক্তি অনুসরণ — মান ``custom_shortcuts._extended``-এ
    থাকে; পুরনো সারিতে top-level থাকলে সেটিও সম্মানিত।
    """
    if not user_id:
        return None
    try:
        from database.supabase_client import db

        if not db.client:
            return None
        res = (
            await db.client.table("user_preferences")
            .select("custom_shortcuts, preferred_language")
            .eq("user_id", str(user_id))
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return None
        row = rows[0]
        shortcuts = row.get("custom_shortcuts")
        extended = shortcuts.get("_extended") if isinstance(shortcuts, dict) else None
        lang = None
        if isinstance(extended, dict):
            lang = extended.get("preferred_language")
        if not lang:
            lang = row.get("preferred_language")
        if not lang:
            return None
        normalized = str(lang).strip().lower()
        return normalized or None
    except Exception as exc:
        logger.warning(
            f"[M19 P-C] preferred_language read failed for {user_id!r}: {exc!r} — "
            "language directive skipped (loud, non-fatal)"
        )
        return None


def build_language_directive(lang: str | None) -> str | None:
    """ভাষা-নির্দেশ টেক্সট — অনুপস্থিত/English-এ ``None`` (আজকের আচরণ)।"""
    if not lang:
        return None
    normalized = str(lang).strip().lower()
    if normalized in _EN_VARIANTS:
        return None
    if normalized in _BN_VARIANTS:
        return (
            "Language directive: the user's preferred language is Bengali (বাংলা). "
            "Respond in natural, standard Bengali prose. Code, identifiers and "
            "established technical terms may remain in English."
        )
    return (
        f"Language directive: respond in the user's preferred language ({normalized}) "
        "unless the user explicitly writes in another language."
    )
