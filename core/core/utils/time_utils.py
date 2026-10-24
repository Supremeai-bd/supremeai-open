from __future__ import annotations

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    """সবসময় timezone-aware (UTC) বর্তমান সময় রিটার্ন করে।
    সব নতুন কোডে `datetime.now()` বা `datetime.utcnow()` (যেটা deprecated
    এবং naive) এর বদলে এটা ব্যবহার করুন।
    """
    return datetime.now(UTC)


def utc_expiry(minutes: int = 0, seconds: int = 0, hours: int = 0) -> datetime:
    """TTL/expiry হিসাবের জন্য shortcut — `utc_now() + timedelta(...)`।"""
    return utc_now() + timedelta(minutes=minutes, seconds=seconds, hours=hours)


def ensure_aware(dt: datetime) -> datetime:
    """একটা naive datetime পেলে সেটাকে UTC-aware বানিয়ে দেয় (safe migration
    helper — পুরনো stored/serialized naive timestamp-এর সাথে নতুন aware
    কোড তুলনা করার সময় TypeError এড়াতে ব্যবহার করুন)।
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
