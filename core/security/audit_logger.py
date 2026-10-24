"""Centralized security audit logging with structured context.

বাংলা মন্তব্য: সমস্ত সিকিউরিটি ইভেন্ট (লগইন, টোকেন জেনারেট/রিভোক, আইপি অ্যানোমালি) সেন্ট্রালি ট্র্যাক এবং রিয়েল-টাইমে লগ করে।
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from core.cache.redis_manager import redis_manager
from core.logging_config import logger

AUDIT_PREFIX = "audit:event:"
AUDIT_LIST_PREFIX = "audit:recent:"
MAX_RECENT_EVENTS = 1000


async def log_security_event(
    event_type: str,
    user_id: str | None,
    details: dict[str, Any],
    severity: str = "INFO",
) -> str:
    """Log a security event with unique trace ID and persist to Redis log."""

    event_id = f"sec-{uuid.uuid4().hex[:12]}"
    event = {
        "event_id": event_id,
        "event_type": event_type,
        "user_id": user_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "severity": severity,
        "details": details,
    }

    # Structured log output
    logger.bind(event_type=event_type, severity=severity).info(
        f"🛡️ Security Event: {event_type} | User: {user_id}"
    )

    # Redis persistence
    if redis_manager and getattr(redis_manager, "client", None):
        try:
            payload = json.dumps(event, default=str)
            pipe = redis_manager.client.pipeline()
            pipe.setex(f"{AUDIT_PREFIX}{event_id}", 86400 * 30, payload)  # 30 days retention
            pipe.lpush(AUDIT_LIST_PREFIX, payload)
            pipe.ltrim(AUDIT_LIST_PREFIX, 0, MAX_RECENT_EVENTS - 1)
            import inspect

            res = pipe.execute()
            # বাংলা মন্তব্য: টেস্টে যদি MagicMock ব্যবহার করা হয় যা awaitable নয়, তা হ্যান্ডেল করার জন্য চেক যোগ করা হলো
            if inspect.isawaitable(res):
                await res
        except Exception as exc:
            # বাংলা মন্তব্য: সিকিউরিটি গার্ড — সিকিউরিটি অডিট ইভেন্ট পারসিস্ট না হলে সাইলেন্ট ফেলিয়ার প্রতিরোধে এরর রেইজ করা হচ্ছে
            logger.error(f"⚠️ Failed to persist security audit event {event_id}: {exc}")
            raise RuntimeError(
                f"Audit logger persistence failed for event {event_id}: {exc}"
            ) from exc

    return event_id
