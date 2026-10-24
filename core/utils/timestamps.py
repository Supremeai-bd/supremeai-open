"""
টাইমস্ট্যাম্প ইউটিলিটি — datetime.now(UTC).isoformat() এর পুনরাবৃত্তি রোধ করতে
একটি কেন্দ্রীয় মডিউল।

সমস্ত মডিউল জুড়ে `datetime.now(UTC).isoformat()` বারবার লেখার বদলে
এখন `utc_now_iso()` কল করলেই চলবে। এতে ফরম্যাট পরিবর্তন করতে হলে
শুধু এখানে একবার করলেই সর্বত্র প্রযোজ্য হবে।
"""

from datetime import UTC, datetime


def utc_now_iso() -> str:
    """বর্তমান UTC সময় ISO 8601 ফরম্যাটে রিটার্ন করে।

    Returns:
        ISO 8601 ফরম্যাটেড টাইমস্ট্যাম্প স্ট্রিং (যেমন '2026-07-04T02:30:00+00:00')।
    """
    return datetime.now(UTC).isoformat()


def utc_now() -> datetime:
    """বর্তমান UTC সময় datetime অবজেক্ট হিসেবে রিটার্ন করে।

    Returns:
        timezone-aware datetime(UTC)।
    """
    return datetime.now(UTC)


def utc_timestamp() -> int:
    """বর্তমান UTC সময় Unix timestamp (int) হিসেবে রিটার্ন করে।

    Returns:
        ইন্টিজার Unix timestamp।
    """
    return int(datetime.now(UTC).timestamp())
