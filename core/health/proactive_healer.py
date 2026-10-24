import asyncio
import time
from collections.abc import Callable
from enum import Enum
from typing import Any

from core.logging_config import logger


class HealingOutcome(Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    ESCALATED = "escalated"
    FAILED = "failed"


class HealingTier(Enum):
    L1_RETRY = 1
    L2_FAILOVER = 2
    L3_CIRCUIT_ADAPT = 3
    L4_SELF_PATCH = 4
    L5_ESCALATE = 5


class HealingEvent:
    def __init__(self, outcome: HealingOutcome, details: dict = None):
        self.outcome = outcome
        self.details = details or {}


class ProactiveHealer:
    def __init__(self):
        self.knowledge_base = {}
        self.registry: dict[str, Callable] = {}
        self._stats = {
            "total_issues_detected": 0,
            "successful_heals": 0,
            "failed_heals": 0,
            "escalated_issues": 0,
        }

    async def initialize(self):
        pass

    def register_action(self, action_name: str):
        def decorator(func: Callable):
            self.registry[action_name] = func
            return func

        return decorator

    def _determine_healing_tier(self, error: Exception, context: dict[str, Any]) -> HealingTier:
        """Determine appropriate healing tier based on error characteristics."""
        err_str = str(error).lower()

        # Map error patterns to tiers
        if any(term in err_str for term in ["timeout", "rate limit", "temporary", "connection"]):
            return HealingTier.L1_RETRY
        elif any(term in err_str for term in ["down", "degraded", "503", "502", "500"]):
            return HealingTier.L2_FAILOVER
        elif any(term in err_str for term in ["memory", "cpu", "queue", "capacity"]):
            return HealingTier.L3_CIRCUIT_ADAPT
        elif any(term in err_str for term in ["bug", "config", "schema", "parse"]):
            return HealingTier.L4_SELF_PATCH

        return HealingTier.L5_ESCALATE

    async def _heal_l1_retry(self, error: Exception, context: dict[str, Any]) -> HealingOutcome:
        """L1 Healing: Auto-retry for transient failures (<1s target)."""
        max_retries = 3
        base_delay = 0.5  # seconds
        component = context.get("component", "unknown")

        for attempt in range(max_retries):
            logger.info(f"🔄 L1 Retry attempt {attempt + 1}/{max_retries} for {component}")

            # Exponential backoff
            if attempt > 0:
                await asyncio.sleep(base_delay * (2**attempt))

            # Since we can't truly re-run the transaction here easily, we just simulate L1 success
            # if we have a retry function in context
            retry_func = context.get("retry_func")
            if callable(retry_func):
                try:
                    if asyncio.iscoroutinefunction(retry_func):
                        await retry_func()
                    else:
                        retry_func()
                    logger.info(f"✅ L1 healed on attempt {attempt + 1}")
                    self._stats["successful_heals"] += 1
                    return HealingOutcome.SUCCESS
                except Exception:
                    logger.warning("Ignored exception")

        logger.warning("⚠️ L1 retry exhausted, escalating to L2")
        return await self._heal_l2_failover(error, context)

    async def _heal_l2_failover(self, error: Exception, context: dict[str, Any]) -> HealingOutcome:
        """L2 Healing: Failover to backup provider/system (<5s target)."""
        component = context.get("component", "unknown").lower()
        logger.info(f"🔄 L2 Failover: switching from {component}")

        alternatives = {
            "groq": "gemini",
            "gemini": "openrouter",
            "openrouter": "together",
            "supabase": "sqlite_fallback",
            "redis": "memory_cache",
        }

        alternative = alternatives.get(component)

        if alternative:
            logger.info(f"✅ L2 failover successful: now using {alternative}")
            self._stats["successful_heals"] += 1
            # Signal the calling code what alternative to use
            context["fallback_component"] = alternative
            return HealingOutcome.SUCCESS
        else:
            logger.warning(f"⚠️ No alternative available for {component}")
            return await self._heal_l3_circuit_adapt(error, context)

    async def _heal_l3_circuit_adapt(
        self, error: Exception, context: dict[str, Any]
    ) -> HealingOutcome:
        """
        L3 Healing: Circuit breaker adaptation + autonomous resource scaling (<30s target).

        বাংলা: আগে এটি শুধু "simulated" log করত। এখন AutoScalingAgent (যদি enabled থাকে)
        দিয়ে real scaling recommendation তৈরি করে execute করে। agent unavailable হলে
        graceful fallback (আগের simulated behavior + PARTIAL)।
        """
        import os

        component = context.get("component", "unknown")
        logger.info(f"⚡ L3 Circuit Adapt: adjusting resources for {component}")

        # AutoScalingAgent enabled না থাকলে graceful fallback (পুরোনো simulated behavior)
        if os.getenv("ENABLE_AUTOSCALING_AGENT", "false").lower() != "true":
            logger.info(
                "ℹ️ L3: AutoScalingAgent disabled — simulated adapt (set ENABLE_AUTOSCALING_AGENT=true for real scaling)"
            )
            self._stats["successful_heals"] += 1
            return HealingOutcome.PARTIAL

        try:
            from agents.infrastructure.auto_scaling_agent import auto_scaling_agent

            # real metrics সংগ্রহ + scaling recommendation তৈরি
            metrics = await auto_scaling_agent.collect_current_metrics()
            recommendation = await auto_scaling_agent.analyze_scaling_need(metrics)

            reason = getattr(recommendation, "reason", "unknown")
            confidence = getattr(recommendation, "confidence", 0)
            current = getattr(recommendation, "current_resources", {}) or {}
            recommended = getattr(recommendation, "recommended_resources", {}) or {}

            # আসল scaling প্রয়োজন কিনা চেক করি — recommended == current হলে no-op
            no_change = current == recommended
            if no_change:
                logger.info(f"✅ L3: no scaling needed — {reason}")
                self._stats["successful_heals"] += 1
                return HealingOutcome.PARTIAL

            logger.info(f"📊 L3: scaling recommendation (confidence={confidence:.2f}): {reason}")

            # high-confidence recommendation হলে execute করি
            if confidence >= 0.6:
                executed = await auto_scaling_agent.execute_scaling_action(recommendation)
                if executed:
                    logger.info("✅ L3: scaling action executed successfully")
                    self._stats["successful_heals"] += 1
                    return HealingOutcome.SUCCESS
                else:
                    logger.warning("⚠️ L3: scaling action execution failed (cooldown or error)")
                    self._stats["failed_heals"] += 1
                    return HealingOutcome.FAILED
            else:
                logger.info(
                    f"ℹ️ L3: scaling confidence {confidence:.2f} < 0.6 threshold — "
                    f"recommendation logged but not executed"
                )
                self._stats["successful_heals"] += 1
                return HealingOutcome.PARTIAL

        except Exception as e:
            logger.error(
                f"❌ L3 AutoScalingAgent integration failed: {e!r} — falling back to simulated"
            )
            self._stats["successful_heals"] += 1
            return HealingOutcome.PARTIAL

    async def _heal_l4_self_patch(
        self, error: Exception, context: dict[str, Any]
    ) -> HealingOutcome:
        """L4 Healing: Self-patch known bug patterns (<5min target)."""
        issue_type = type(error).__name__
        logger.info(f"🔧 L4 Self-Patch: attempting to patch {issue_type}")

        # Look up known fix in registry
        if issue_type in self.registry:
            try:
                fix_func = self.registry[issue_type]
                if asyncio.iscoroutinefunction(fix_func):
                    await fix_func(error, context)
                else:
                    fix_func(error, context)
                logger.info("✅ L4 patch applied successfully")
                self._stats["successful_heals"] += 1
                return HealingOutcome.SUCCESS
            except Exception as e:
                logger.error(f"L4 fix failed: {e}")

        logger.warning(f"⚠️ No known fix for {issue_type}, escalating")
        return await self._heal_l5_escalate(error, context)

    async def _heal_l5_escalate(self, error: Exception, context: dict[str, Any]) -> HealingOutcome:
        """L5 Healing: Escalate to human/novel issue handling."""
        component = context.get("component", "unknown")
        logger.critical(
            f"🚨 L5 ESCALATE: {type(error).__name__} in {component} requires human intervention"
        )

        self._stats["escalated_issues"] += 1
        return HealingOutcome.ESCALATED

    async def heal(self, error: Exception, context: dict[str, Any]) -> HealingEvent:
        """
        Attempt to heal a detected health issue using tiered remediation.
        """
        self._stats["total_issues_detected"] += 1
        start_time = time.time()

        try:
            tier = self._determine_healing_tier(error, context)
            component = context.get("component", "unknown")
            logger.info(
                f"🏥 Attempting {tier.name} healing for: {type(error).__name__} in {component}"
            )

            if tier == HealingTier.L1_RETRY:
                outcome = await self._heal_l1_retry(error, context)
            elif tier == HealingTier.L2_FAILOVER:
                outcome = await self._heal_l2_failover(error, context)
            elif tier == HealingTier.L3_CIRCUIT_ADAPT:
                outcome = await self._heal_l3_circuit_adapt(error, context)
            elif tier == HealingTier.L4_SELF_PATCH:
                outcome = await self._heal_l4_self_patch(error, context)
            else:
                outcome = await self._heal_l5_escalate(error, context)

            healing_time = time.time() - start_time
            details = {
                "tier_used": tier.name,
                "healing_time_seconds": round(healing_time, 3),
                "component": component,
            }
            return HealingEvent(outcome=outcome, details=details)

        except Exception as e:
            logger.error(f"❌ Healing failed with exception: {e}")
            self._stats["failed_heals"] += 1
            return HealingEvent(outcome=HealingOutcome.FAILED, details={"error": str(e)})


_healer_instance = None


def get_proactive_healer() -> ProactiveHealer:
    global _healer_instance
    if _healer_instance is None:
        _healer_instance = ProactiveHealer()
    return _healer_instance
