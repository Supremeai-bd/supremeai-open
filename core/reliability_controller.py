from __future__ import annotations

import time
from typing import Any

from fastapi import Request

from core.errors.error_bus import with_error_bus
from core.failure_fingerprint import make_fingerprint
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus
from core.request_context import get_correlation_id


class ReliabilityController:
    """
    বাংলা মন্তব্য: অ্যাপ্লিকেশনের সেলফ-হিলিং এবং এরর রিকভারি স্ট্যাটাস ট্র্যাকার ও কন্ট্রোলার।
    Failure fingerprints Redis-তে persist হয় (TTL ১ ঘণ্টা) dengan in-memory fallback।
    """

    _failures: dict[str, int] = {}
    _health_score = 100.0
    _REDIS_KEY_PREFIX = "reliability:fingerprint:"
    _REDIS_TTL = 3600

    @classmethod
    async def initialize(cls) -> None:
        logger.info("⚡ Reliability Control Plane initialized.")

    @classmethod
    @with_error_bus("_persist_fingerprint")
    async def _persist_fingerprint(cls, fingerprint: str, count: int) -> None:
        try:
            from core.cache.redis_manager import redis_manager

            if redis_manager and redis_manager.client:
                import json

                key = f"{cls._REDIS_KEY_PREFIX}{fingerprint}"
                await redis_manager.client.set(
                    key,
                    json.dumps({"count": count, "last_seen": time.time()}),
                    ex=cls._REDIS_TTL,
                )
        except Exception as exc:
            error_event_bus.emit(
                ErrorEvent(
                    module="reliability_controller",
                    error_type="FINGERPRINT_PERSIST_FAILED",
                    message=str(exc)[:200],
                    severity="WARNING",
                    structured_context=ErrorContext(module="reliability_controller"),
                )
            )

    @classmethod
    @with_error_bus("_load_persisted_fingerprints")
    async def _load_persisted_fingerprints(cls) -> dict[str, int]:
        try:
            from core.cache.redis_manager import redis_manager

            if not redis_manager or not redis_manager.client:
                return {}

            pattern = f"{cls._REDIS_KEY_PREFIX}*"
            keys = await redis_manager.client.keys(pattern)
            if not keys:
                return {}

            import json

            result: dict[str, int] = {}
            pipe = redis_manager.client.pipeline()
            for key in keys:
                pipe.get(key)
            values = await pipe.execute()

            for key, raw in zip(keys, values, strict=False):
                if raw:
                    try:
                        data = json.loads(raw)
                        fp = key.replace(cls._REDIS_KEY_PREFIX, "")
                        result[fp] = data.get("count", 0)
                    except Exception as exc:
                        logger.debug(f"Failed to parse persisted fingerprint {key}: {exc}")
                        continue
            return result
        except Exception as exc:
            error_event_bus.emit(
                ErrorEvent(
                    module="reliability_controller",
                    error_type="FINGERPRINT_LOAD_FAILED",
                    message=str(exc)[:200],
                    severity="WARNING",
                    structured_context=ErrorContext(module="reliability_controller"),
                )
            )
            return {}

    @classmethod
    async def register_failure(cls, request: Request | None, exception: Exception) -> Any:
        fingerprint = make_fingerprint(exception)
        corr_id = "unknown"
        if request and hasattr(request.state, "correlation_id"):
            corr_id = request.state.correlation_id
        else:
            corr_id = get_correlation_id() or "unknown"

        cls._failures[fingerprint] = cls._failures.get(fingerprint, 0) + 1
        cls._health_score = max(0.0, cls._health_score - 1.0)

        count = cls._failures[fingerprint]
        await cls._persist_fingerprint(fingerprint, count)

        logger.warning(
            f"⚠️ Registered failure {fingerprint} under correlation {corr_id} (count={count})"
        )

        class FailureContext:
            def __init__(self, c_id, f_print):
                self.correlation_id = c_id
                self.fingerprint = f_print

            def to_log_dict(self):
                return {
                    "correlation_id": self.correlation_id,
                    "fingerprint": self.fingerprint,
                }

        return FailureContext(corr_id, fingerprint)

    @classmethod
    async def restore_from_persistence(cls) -> None:
        persisted = await cls._load_persisted_fingerprints()
        if persisted:
            cls._failures.update(persisted)
            logger.info(f"📦 Restored {len(persisted)} persisted failure fingerprints")

    @classmethod
    def health(cls) -> dict:
        return {
            "health_score": cls._health_score,
            "failures_tracked": len(cls._failures),
        }

    @classmethod
    def middleware_ok(cls) -> bool:
        return True

    @classmethod
    def failure_store_ok(cls) -> bool:
        return True
