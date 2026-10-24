"""
SupremeAI — Layer 5: Data & Analytics — User Retention Risk Agent
================================================================
Predicts user churn risk from behavior signals and suggests retention
strategies. Zero-cost: uses behavioral scoring heuristics, no ML
training required. Scales via Firestore aggregation + caching.

Key Components:
- `UserRetentionRiskAgent` (formerly `ChurnProphet`): Core retention engine with risk scoring.
- `BehavioralScorer`: Heuristic-based churn risk calculation.
- `RetentionStrategist`: Strategy recommendation engine.
- `UserSegmenter`: Automatic user segmentation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.config_cache import config_cache
from core.logging_config import logger
from database.tenant_db import TenantAwareFirestore


# ── Enums & Constants ───────────────────────────────────────────────────────
class RiskLevel(StrEnum):
    """Churn risk severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class UserSegment(StrEnum):
    """Automatic user segments."""

    POWER_USER = "power_user"
    REGULAR = "regular"
    AT_RISK = "at_risk"
    DORMANT = "dormant"
    NEW = "new"


CHURN_WEIGHTS = {
    "days_since_last_active": 0.25,
    "session_frequency_drop": 0.20,
    "feature_usage_decline": 0.20,
    "support_ticket_spike": 0.15,
    "payment_delay": 0.20,
}

RETENTION_TEMPLATES = {
    RiskLevel.LOW: [
        "Continue engagement with loyalty rewards",
        "Request feedback for product improvement",
        "Offer early access to new features",
    ],
    RiskLevel.MEDIUM: [
        "Send personalized re-engagement email",
        "Offer limited-time discount or credit",
        "Schedule check-in call from account manager",
    ],
    RiskLevel.HIGH: [
        "Immediate proactive outreach from support team",
        "Offer significant retention incentive (30% off)",
        "Personalized demo of underutilized features",
    ],
    RiskLevel.CRITICAL: [
        "Executive escalation — CSM direct contact",
        "Maximum retention offer (free month + priority support)",
        "Exit interview offer to understand root cause",
    ],
}


@dataclass(frozen=True)
class ChurnRiskScore:
    """Immutable churn risk assessment."""

    user_id: str
    risk_level: RiskLevel
    score: float  # 0.0 - 1.0
    confidence: float
    factors: dict[str, float]
    segment: UserSegment
    predicted_churn_date: datetime | None


@dataclass(frozen=True)
class RetentionStrategy:
    """Immutable retention strategy recommendation."""

    user_id: str
    risk_level: RiskLevel
    strategies: list[str]
    personalized_message: str
    priority: int  # 1 = highest
    estimated_success_rate: float


class BehavioralScorer:
    """
    Heuristic-based behavioral scoring without ML training.

    Uses weighted signal aggregation from user activity data.
    """

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or CHURN_WEIGHTS

    def calculate(
        self,
        days_since_active: int,
        session_freq_change: float,  # Negative = decline
        feature_usage_change: float,  # Negative = decline
        support_tickets_recent: int,
        payment_delay_days: int,
        account_age_days: int,
    ) -> tuple[float, dict[str, float], RiskLevel]:
        """
        Calculate churn risk score from behavioral signals.

        Args:
            days_since_active: Days since last activity.
            session_freq_change: Percent change in session frequency.
            feature_usage_change: Percent change in feature usage.
            support_tickets_recent: Tickets in last 30 days.
            payment_delay_days: Days payment is delayed.
            account_age_days: Total account age.

        Returns:
            Tuple of (score, factor_breakdown, risk_level).
        """
        # Normalize each signal to 0-1 range
        signals = {
            "days_since_last_active": min(days_since_active / 30, 1.0),
            "session_frequency_drop": (
                max(-session_freq_change / 100, 0) if session_freq_change < 0 else 0
            ),
            "feature_usage_decline": (
                max(-feature_usage_change / 100, 0) if feature_usage_change < 0 else 0
            ),
            "support_ticket_spike": min(support_tickets_recent / 5, 1.0),
            "payment_delay": min(payment_delay_days / 14, 1.0),
        }

        # Account age dampening: newer accounts churn more easily
        age_dampening = 1.0 if account_age_days > 90 else 1.3

        # Weighted score
        score = sum(signals[k] * self.weights[k] for k in signals) * age_dampening
        score = min(score, 1.0)

        # Risk level classification
        if score < 0.3:
            risk_level = RiskLevel.LOW
        elif score < 0.5:
            risk_level = RiskLevel.MEDIUM
        elif score < 0.75:
            risk_level = RiskLevel.HIGH
        else:
            risk_level = RiskLevel.CRITICAL

        return score, signals, risk_level

    def segment_user(
        self,
        score: float,
        days_since_active: int,
        total_sessions: int,
        account_age_days: int,
    ) -> UserSegment:
        """Determine user segment from behavioral data."""
        if days_since_active > 30:
            return UserSegment.DORMANT
        if score > 0.6:
            return UserSegment.AT_RISK
        if total_sessions > 50 and account_age_days > 60:
            return UserSegment.POWER_USER
        if account_age_days < 14:
            return UserSegment.NEW
        return UserSegment.REGULAR


class RetentionStrategist:
    """
    Generates personalized retention strategies using zero-cost LLM routing.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm_router = llm_router or ModelRouter()

    async def generate_strategy(
        self,
        user_id: str,
        risk_level: RiskLevel,
        factors: dict[str, float],
        segment: UserSegment,
        user_context: dict[str, Any],
    ) -> RetentionStrategy:
        """
        Generate personalized retention strategy.

        Args:
            user_id: Target user ID.
            risk_level: Calculated risk level.
            factors: Risk factor breakdown.
            segment: User segment.
            user_context: Additional user context.

        Returns:
            RetentionStrategy with recommendations.
        """
        # Base strategies from templates
        base_strategies = RETENTION_TEMPLATES.get(risk_level, RETENTION_TEMPLATES[RiskLevel.LOW])

        # Generate personalized message via LLM for high/critical risk
        personalized = ""
        if risk_level in {RiskLevel.HIGH, RiskLevel.CRITICAL}:
            prompt = self._build_personalization_prompt(
                user_id,
                risk_level,
                factors,
                segment,
                user_context,
            )
            try:
                response = await self.llm_router.async_route_and_generate(
                    prompt=prompt,
                    task_type="retention_strategy",
                    max_tokens=config_cache.get("churn_prophet_max_tokens", 500),
                    temperature=config_cache.get("churn_prophet_temperature", 0.4),
                )
                personalized = response.get("text", "")
            except Exception as e:
                logger.warning("LLM personalization failed for %s: %s", user_id, e)
                personalized = ""

        priority_map = {
            RiskLevel.LOW: 4,
            RiskLevel.MEDIUM: 3,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 1,
        }

        # Estimate success rate based on segment and risk
        base_success = {
            UserSegment.POWER_USER: 0.85,
            UserSegment.REGULAR: 0.70,
            UserSegment.NEW: 0.60,
            UserSegment.AT_RISK: 0.55,
            UserSegment.DORMANT: 0.40,
        }
        success_rate = base_success.get(segment, 0.50) * (1 - sum(factors.values()) / len(factors))

        return RetentionStrategy(
            user_id=user_id,
            risk_level=risk_level,
            strategies=base_strategies,
            personalized_message=personalized,
            priority=priority_map.get(risk_level, 3),
            estimated_success_rate=round(success_rate, 2),
        )

    def _build_personalization_prompt(
        self,
        user_id: str,
        risk_level: RiskLevel,
        factors: dict[str, float],
        segment: UserSegment,
        user_context: dict[str, Any],
    ) -> str:
        """Build LLM prompt for personalized retention message."""
        return f"""\
You are UserRetentionRiskAgent, the Retention AI of SupremeAI. Write a personalized, empathetic retention message.

USER: {user_id}
SEGMENT: {segment.value}
RISK LEVEL: {risk_level.value}
RISK FACTORS: {json.dumps(factors, indent=2)}
CONTEXT: {json.dumps(user_context, indent=2, default=str)}

Write a 2-3 sentence message in Banglish (Bengali-English mix) that:
1. Acknowledges their value as a user
2. Addresses their specific concern (highest risk factor)
3. Offers a concrete, personalized solution

Be warm, genuine, and not pushy. Output ONLY the message text, no formatting.
"""


class UserRetentionRiskAgent:
    """
    Layer 5 Retention AI — Predicts churn and suggests retention strategies.

    Zero-cost design: heuristic scoring, no ML training, Firestore aggregation.
    """

    def __init__(
        self,
        db: TenantAwareFirestore | None = None,
        cache_ttl: int = 600,
    ) -> None:
        self.db = db
        self.cache = get_cache()
        self.cache_ttl = cache_ttl
        self.scorer = BehavioralScorer()
        self.strategist = RetentionStrategist()

    def _cache_key(self, tenant_id: str, user_id: str) -> str:
        """Generate cache key for user churn analysis."""
        raw = f"{tenant_id}:{user_id}:{datetime.now(UTC).strftime('%Y%m%d')}"
        return f"churn:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"

    async def _fetch_user_signals(
        self,
        tenant_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """
        Fetch user behavioral signals from Firestore.

        Args:
            tenant_id: Tenant identifier.
            user_id: User identifier.

        Returns:
            Dictionary of behavioral signals or None if not found.
        """
        if self.db is None:
            return None

        try:
            # Fetch user profile
            user_doc = await self.db.collection("users").document(user_id).get()
            if not user_doc.exists:
                return None

            user_data = user_doc.to_dict()

            # Fetch activity metrics
            thirty_days_ago = datetime.now(UTC) - timedelta(days=30)
            sixty_days_ago = datetime.now(UTC) - timedelta(days=60)

            # Recent sessions (last 30 days)
            recent_sessions = (
                await self.db.collection("user_sessions")
                .where("user_id", "==", user_id)
                .where("timestamp", ">=", thirty_days_ago)
                .where("_tenant_id", "==", tenant_id)
                .count()
                .get()
            )

            # Previous sessions (30-60 days ago)
            prev_sessions = (
                await self.db.collection("user_sessions")
                .where("user_id", "==", user_id)
                .where("timestamp", ">=", sixty_days_ago)
                .where("timestamp", "<", thirty_days_ago)
                .where("_tenant_id", "==", tenant_id)
                .count()
                .get()
            )

            # Recent support tickets
            recent_tickets = (
                await self.db.collection("support_tickets")
                .where("user_id", "==", user_id)
                .where("created_at", ">=", thirty_days_ago)
                .where("_tenant_id", "==", tenant_id)
                .count()
                .get()
            )

            # Payment status
            payment_doc = await self.db.collection("user_payments").document(user_id).get()

            # Calculate derived metrics
            recent_count = recent_sessions[0][0].value if recent_sessions else 0
            prev_count = prev_sessions[0][0].value if prev_sessions else 0

            session_freq_change = (
                ((recent_count - prev_count) / prev_count * 100) if prev_count > 0 else 0
            )

            last_active = user_data.get("last_active_at")
            if isinstance(last_active, str):
                last_active = datetime.fromisoformat(last_active.replace("Z", "+00:00"))

            days_since_active = (datetime.now(UTC) - last_active).days if last_active else 999

            created_at = user_data.get("created_at")
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            account_age = (datetime.now(UTC) - created_at).days if created_at else 0

            payment_data = payment_doc.to_dict() if payment_doc.exists else {}
            payment_delay = payment_data.get("delay_days", 0)

            # Feature usage (simplified: count distinct features)
            feature_usage = (
                await self.db.collection("feature_usage")
                .where("user_id", "==", user_id)
                .where("_tenant_id", "==", tenant_id)
                .distinct("feature_name")
                .get()
            )

            # Previous period feature usage
            prev_feature_usage = (
                await self.db.collection("feature_usage")
                .where("user_id", "==", user_id)
                .where("timestamp", ">=", sixty_days_ago)
                .where("timestamp", "<", thirty_days_ago)
                .where("_tenant_id", "==", tenant_id)
                .distinct("feature_name")
                .get()
            )

            feature_change = (
                ((len(feature_usage) - len(prev_feature_usage)) / len(prev_feature_usage) * 100)
                if len(prev_feature_usage) > 0
                else 0
            )

            return {
                "days_since_active": days_since_active,
                "session_freq_change": session_freq_change,
                "feature_usage_change": feature_change,
                "support_tickets_recent": (recent_tickets[0][0].value if recent_tickets else 0),
                "payment_delay_days": payment_delay,
                "account_age_days": account_age,
                "total_sessions": recent_count + prev_count,
                "user_context": {
                    "name": user_data.get("display_name", ""),
                    "email": user_data.get("email", ""),
                    "plan": user_data.get("subscription_plan", "free"),
                    "last_purchase": payment_data.get("last_payment_date"),
                },
            }

        except Exception as e:
            logger.error("Failed to fetch user signals for %s: %s", user_id, e)
            return None

    async def analyze_user(
        self,
        tenant_id: str,
        user_id: str,
        force_refresh: bool = False,
    ) -> ChurnRiskScore | None:
        """
        Analyze churn risk for a specific user.

        Args:
            tenant_id: Tenant identifier.
            user_id: User identifier.
            force_refresh: Bypass cache if True.

        Returns:
            ChurnRiskScore or None if user not found.
        """
        cache_key = self._cache_key(tenant_id, user_id)

        if not force_refresh:
            cached = await self.cache.get(cache_key)
            if cached:
                return ChurnRiskScore(
                    user_id=cached["user_id"],
                    risk_level=RiskLevel(cached["risk_level"]),
                    score=cached["score"],
                    confidence=cached["confidence"],
                    factors=cached["factors"],
                    segment=UserSegment(cached["segment"]),
                    predicted_churn_date=(
                        datetime.fromisoformat(cached["predicted_churn_date"])
                        if cached.get("predicted_churn_date")
                        else None
                    ),
                )

        signals = await self._fetch_user_signals(tenant_id, user_id)
        if signals is None:
            return None

        score, factors, risk_level = self.scorer.calculate(
            days_since_active=signals["days_since_active"],
            session_freq_change=signals["session_freq_change"],
            feature_usage_change=signals["feature_usage_change"],
            support_tickets_recent=signals["support_tickets_recent"],
            payment_delay_days=signals["payment_delay_days"],
            account_age_days=signals["account_age_days"],
        )

        segment = self.scorer.segment_user(
            score=score,
            days_since_active=signals["days_since_active"],
            total_sessions=signals["total_sessions"],
            account_age_days=signals["account_age_days"],
        )

        # Predict churn date: higher score = sooner churn
        if risk_level == RiskLevel.CRITICAL:
            days_to_churn = max(3, int(7 * (1 - score)))
        elif risk_level == RiskLevel.HIGH:
            days_to_churn = max(7, int(14 * (1 - score)))
        elif risk_level == RiskLevel.MEDIUM:
            days_to_churn = max(14, int(30 * (1 - score)))
        else:
            days_to_churn = 60

        predicted_churn = datetime.now(UTC) + timedelta(days=days_to_churn)

        # Confidence based on data quality
        confidence = min(0.95, 0.5 + (signals["account_age_days"] / 180))

        result = ChurnRiskScore(
            user_id=user_id,
            risk_level=risk_level,
            score=round(score, 3),
            confidence=round(confidence, 2),
            factors=factors,
            segment=segment,
            predicted_churn_date=predicted_churn,
        )

        # Cache result
        await self.cache.set(
            cache_key,
            {
                "user_id": result.user_id,
                "risk_level": result.risk_level.value,
                "score": result.score,
                "confidence": result.confidence,
                "factors": result.factors,
                "segment": result.segment.value,
                "predicted_churn_date": (
                    result.predicted_churn_date.isoformat() if result.predicted_churn_date else None
                ),
            },
            ttl=self.cache_ttl,
        )

        return result

    async def get_retention_strategy(
        self,
        tenant_id: str,
        user_id: str,
        force_refresh: bool = False,
    ) -> RetentionStrategy | None:
        """
        Get retention strategy for a user.

        Args:
            tenant_id: Tenant identifier.
            user_id: User identifier.
            force_refresh: Bypass cache if True.

        Returns:
            RetentionStrategy or None if user not found.
        """
        risk_score = await self.analyze_user(tenant_id, user_id, force_refresh)
        if risk_score is None:
            return None

        signals = await self._fetch_user_signals(tenant_id, user_id)
        user_context = signals.get("user_context", {}) if signals else {}

        return await self.strategist.generate_strategy(
            user_id=user_id,
            risk_level=risk_score.risk_level,
            factors=risk_score.factors,
            segment=risk_score.segment,
            user_context=user_context,
        )

    async def batch_analyze(
        self,
        tenant_id: str,
        user_ids: list[str],
        max_concurrent: int = 10,
    ) -> dict[str, ChurnRiskScore | None]:
        """
        Batch analyze multiple users with concurrency control.

        Args:
            tenant_id: Tenant identifier.
            user_ids: List of user IDs to analyze.
            max_concurrent: Maximum concurrent analyses.

        Returns:
            Dictionary mapping user_id to ChurnRiskScore or None.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _analyze_with_limit(uid: str) -> tuple[str, ChurnRiskScore | None]:
            async with semaphore:
                return uid, await self.analyze_user(tenant_id, uid)

        tasks = [_analyze_with_limit(uid) for uid in user_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output: dict[str, ChurnRiskScore | None] = {}
        for result in results:
            if isinstance(result, BaseException):
                logger.error("Batch analysis error: %s", result)
                continue
            if isinstance(result, tuple):
                uid, score = result
                output[uid] = score

        return output

    async def get_at_risk_users(
        self,
        tenant_id: str,
        min_risk: RiskLevel = RiskLevel.MEDIUM,
        limit: int = 100,
    ) -> list[ChurnRiskScore]:
        """
        Get all users at or above a risk threshold.

        Args:
            tenant_id: Tenant identifier.
            min_risk: Minimum risk level to include.
            limit: Maximum results.

        Returns:
            List of ChurnRiskScore for at-risk users.
        """
        if self.db is None:
            return []

        try:
            # Query users with recent activity but declining signals
            cutoff = datetime.now(UTC) - timedelta(days=45)

            users = (
                await self.db.collection("users")
                .where("last_active_at", "<", cutoff)
                .where("_tenant_id", "==", tenant_id)
                .limit(limit)
                .get()
            )

            at_risk: list[ChurnRiskScore] = []
            for doc in users:
                user_id = doc.id
                score = await self.analyze_user(tenant_id, user_id)
                if score and score.risk_level.value >= min_risk.value:
                    at_risk.append(score)

            return sorted(at_risk, key=lambda x: x.score, reverse=True)

        except Exception as e:
            logger.error("Failed to get at-risk users: %s", e)
            return []


# Canonical alias for backward compatibility
ChurnProphet = UserRetentionRiskAgent

# ── Singleton Instance ──────────────────────────────────────────────────────
_agent_instance: UserRetentionRiskAgent | None = None


def get_user_retention_risk_agent(db: TenantAwareFirestore | None = None) -> UserRetentionRiskAgent:
    """Get or create the singleton UserRetentionRiskAgent instance."""
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = UserRetentionRiskAgent(db=db)
    return _agent_instance


get_churn_prophet = get_user_retention_risk_agent
