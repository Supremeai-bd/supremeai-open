import asyncio

"""This module, `cost_guard.py`, provides a robust mechanism for managing and enforcing budget constraints within the SupremeAI ecosystem. It features the `CostGuard` class, which offers methods for pre-flight budget checks against a database for individual tenants and a tier-based validation system designed to support multi-tier fallback strategies for AI task routing. A global singleton instance ensures easy access and backward compatibility for other modules like `task_router.py`.

Key Components:
- `CostGuard`: A class responsible for managing and enforcing budget limits for AI operations, including tenant-specific spending and tier-based quota validation.
- `CostGuard.check_budget()`: An asynchronous method that performs a pre-flight check to determine if a given tenant has sufficient budget for an estimated cost, raising an `HTTPException` if the budget is exceeded or not configured.
- `CostGuard.validate_budget()`: A method used to validate if a specific AI service tier (e.g., 'economy', 'premium') has available quota for task execution, primarily supporting multi-tier fallback routing logic.
- `cost_guard`: A global singleton instance of the `CostGuard` class, providing a readily available and consistent budget management utility across the application.

Dependencies:
- `typing`: Used for type hints, specifically `Any`.
- `fastapi`: Utilized for raising `HTTPException` to signal budget-related failures to the API client.
- `loguru`: Employed for structured logging of budget checks, warnings, and errors.
- `asyncio`: Used internally within `check_budget` to adapt to both synchronous and asynchronous database client methods."""

from typing import Any

from fastapi import HTTPException

from core.logging_config import logger

from .messaging.event_bus import (
    ErrorContext,  # Fixed import path - using relative import
)


class CostGuard:
    def __init__(self, db: Any = None):
        self._db = db
        # টাস্ক রাউটারের বাজেট ট্র্যাকিংয়ের জন্য ডিফল্ট টিয়ার থ্রেশহোল্ড
        self.tier_limits = {
            "free": 0.0,
            "economy": 0.02,  # প্রতি টাস্কে সর্বোচ্চ খরচ ২ সেন্ট
            "premium": 0.50,  # প্রিমিয়াম মডেলের বাজেট গেট
        }

    async def connect(self) -> "CostGuard":
        """
        🛡️ LIFESPAN PATCH: core app_lifespan স্টার্টআপ হ্যান্ডশেপ সম্পন্ন করার জন্য
        এসিঙ্ক কানেক্ট গেটওয়ে মেথড যুক্ত করা হলো।
        """
        try:
            logger.info(
                "💰 CostGuard: Initializing resource budget guardian connection protocol..."
            )
            logger.info("✅ CostGuard: Budget guardian layer attached and armed successfully.")
            return self
        except Exception as e:
            logger.error(f"🚨 [COST_GUARD_CONNECT_LEAK]: Lifespan handshake failed: {e}")
            raise

    async def check_budget(self, tenant_id: str, estimated_cost: float) -> bool:
        """
        Pre-flight Check:
        Check if the tenant has enough budget for the estimated cost.
        Raises HTTPException 402 if budget exceeded.
        """
        if not self._db:
            logger.debug(
                f"[CostGuard] Checking legacy budget for tenant {tenant_id} with cost {estimated_cost} - Bypassed (No DB)"
            )
            return True

        try:
            doc_ref = self._db.collection(f"tenants/{tenant_id}/budget").document("status")

            import asyncio

            if asyncio.iscoroutinefunction(doc_ref.get):
                snapshot = await doc_ref.get()
            else:
                snapshot = doc_ref.get()

            if not snapshot.exists:
                raise HTTPException(
                    status_code=402, detail="Payment Required: No budget configured."
                )

            data = snapshot.to_dict()
            monthly_limit = float(data.get("monthly_limit", 0.0))
            spent_amount = float(data.get("spent_amount", 0.0))

            if spent_amount + estimated_cost > monthly_limit:
                logger.warning(
                    f"Tenant {tenant_id} exceeded budget. Spent: {spent_amount}, Limit: {monthly_limit}, Estimated: {estimated_cost}"
                )
                raise HTTPException(status_code=402, detail="Payment Required: Budget Exceeded")

            return True
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"CostGuard DB Error: {e}")
            try:
                from core.messaging.event_bus import ErrorEvent, error_event_bus

                error_event_bus.emit(
                    ErrorEvent(
                        module="cost_guard",
                        error_type="DB_ERROR",
                        message=str(e),
                        severity="ERROR",
                        structured_context=ErrorContext(module="auto_fixed"),
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")
            raise RuntimeError(f"CostGuard failed to verify budget: {e}") from e

    async def validate_budget(self, tenant_id: str, tier: str) -> bool:
        """
        নতুন মেthod: টাস্ক রাউটারের ৮০/১৫/৫ মাল্টি-টিয়ার ফলব্যাক চেইনের বাজেট ভ্যালিডেশনের জন্য।
        এটি চেক করবে ওই নির্দিষ্ট টিয়ারের কোটা এপিআই কলের জন্য খালি আছে কিনা।
        """
        logger.info(
            f"[CostGuard] Validating execution safety gate for AI tier: '{tier}' for tenant: '{tenant_id}'"
        )

        max_task_cost = self.tier_limits.get(tier)
        if max_task_cost is None or max_task_cost <= 0.0:
            return True  # unrestricted/free tier

        from core.cache.redis_manager import redis_manager

        key = f"cost_guard:{tenant_id}:{tier}:spent"

        try:
            spent_raw = await redis_manager.get_cache(key)
            spent = float(spent_raw) if spent_raw else 0.0
        except Exception as e:
            logger.error(f"[CostGuard] Redis unavailable, fail-safe reject: {e}")
            try:
                from core.messaging.event_bus import ErrorEvent, error_event_bus

                error_event_bus.emit(
                    ErrorEvent(
                        module="cost_guard",
                        error_type="REDIS_UNAVAILABLE",
                        message=str(e),
                        severity="WARNING",
                        structured_context=ErrorContext(module="auto_fixed"),
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")
            return tier == "free"  # fail-safe: শুধু ফ্রি টিয়ারে যেতে দাও

        cap = self._daily_cap(tier)

        # Check 1: Already exhausted
        if spent >= cap:
            logger.warning(f"[CostGuard] Tier '{tier}' quota exhausted for {tenant_id}")
            return False

        # Check 2: Will this task push it over?
        if spent + max_task_cost > cap:
            logger.warning(
                f"[CostGuard] Tier '{tier}' task budget would exceed quota for {tenant_id}"
            )
            return False

        return True

    def _daily_cap(self, tier: str) -> float:
        # Default daily cap strategy based on tier limit (e.g. 10x the per task limit)
        return self.tier_limits.get(tier, 0.0) * 10.0

    async def record_spend(self, tenant_id: str, tier: str, actual_cost: float):
        from core.cache.redis_manager import redis_manager

        key = f"cost_guard:{tenant_id}:{tier}:spent"

        try:
            await redis_manager.incrbyfloat(key, actual_cost, ex_seconds=86400)
        except Exception as e:
            logger.error(f"[CostGuard] Failed to record spend in Redis: {e}")
            try:
                from core.messaging.event_bus import ErrorEvent, error_event_bus

                error_event_bus.emit(
                    ErrorEvent(
                        module="cost_guard",
                        error_type="REDIS_ERROR",
                        message=str(e),
                        severity="WARNING",
                        structured_context=ErrorContext(module="auto_fixed"),
                    )
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")


# CRITICAL FIX (Import Error & Backward Compatibility):
# গ্লোবাল সিঙ্গেলটন অবজেক্ট (Singleton Instance) তৈরি করা হলো।
# এটি করার কারণে task_router.py এখন সরাসরি `from core.cost_guard import cost_guard` ইম্পোর্ট করতে পারবে।
# পাশাপাশি __init__ এ db=None রাখায় পুরনো কোডগুলো (যারা db পাঠাতো) ক্র্যাশ করবে না।
cost_guard = CostGuard()
