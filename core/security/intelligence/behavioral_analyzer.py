"""Behavioral Analysis Module for Anomaly Detection

This module provides real-time behavioral analysis and anomaly detection
to identify potential security threats based on user behavior patterns.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from core.logging_config import logger


@dataclass
class BehaviorEvent:
    """Represents a user behavior event."""

    user_id: str
    ip_address: str
    action: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnomalyAlert:
    """Represents a detected behavioral anomaly."""

    severity: str  # "critical", "high", "medium", "low"
    user_id: str
    anomaly_type: str
    description: str
    ip_address: str
    timestamp: float
    confidence: float  # 0.0 to 1.0
    recommended_action: str


class BehaviorTracker:
    """Tracks user behavior patterns over time."""

    def __init__(self, window_size_hours: int = 24):
        """Initialize behavior tracker.

        Args:
            window_size_hours: Time window for pattern analysis
        """
        self.window_size = timedelta(hours=window_size_hours)
        self.events: list[BehaviorEvent] = []
        self.user_profiles: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "ip_addresses": defaultdict(int),
                "actions": defaultdict(int),
                "last_seen": 0.0,
                "first_seen": time.time(),
                "total_events": 0,
            }
        )

    def record_event(self, event: BehaviorEvent) -> None:
        """Record a behavior event.

        Args:
            event: Behavior event to record
        """
        self.events.append(event)

        # Update user profile
        profile = self.user_profiles[event.user_id]
        profile["ip_addresses"][event.ip_address] += 1
        profile["actions"][event.action] += 1
        profile["last_seen"] = event.timestamp
        profile["total_events"] += 1

        # Clean old events
        self._cleanup_old_events()

    def _cleanup_old_events(self) -> None:
        """Remove events outside the analysis window."""
        cutoff = time.time() - self.window_size.total_seconds()
        self.events = [e for e in self.events if e.timestamp > cutoff]

    def get_user_pattern(self, user_id: str) -> dict[str, Any]:
        """Get behavior pattern for a user.

        Args:
            user_id: User identifier

        Returns:
            User behavior profile
        """
        return dict(self.user_profiles.get(user_id, {}))

    def get_recent_ips(self, user_id: str, hours: int = 1) -> list[str]:
        """Get recent IP addresses for a user.

        Args:
            user_id: User identifier
            hours: Time window in hours

        Returns:
            List of recent IP addresses
        """
        cutoff = time.time() - (hours * 3600)
        recent_ips = set()
        for event in self.events:
            if event.user_id == user_id and event.timestamp > cutoff:
                recent_ips.add(event.ip_address)
        return list(recent_ips)


class AnomalyDetector:
    """Detects anomalies in user behavior patterns."""

    def __init__(self, tracker: BehaviorTracker):
        """Initialize anomaly detector.

        Args:
            tracker: Behavior tracker instance
        """
        self.tracker = tracker
        self.ip_churn_threshold = 5  # IPs per hour
        self.unusual_hour_threshold = 2  # Std devs from mean

    def detect_ip_churn(self, user_id: str, current_ip: str) -> AnomalyAlert | None:
        """Detect IP churn (multiple IPs in short time).

        Args:
            user_id: User identifier
            current_ip: Current IP address

        Returns:
            Anomaly alert if detected, None otherwise
        """
        recent_ips = self.tracker.get_recent_ips(user_id, hours=1)

        if len(recent_ips) > self.ip_churn_threshold:
            return AnomalyAlert(
                severity="high",
                user_id=user_id,
                anomaly_type="ip_churn",
                description=f"User switched IPs {len(recent_ips)} times in 1 hour (threshold: {self.ip_churn_threshold})",
                ip_address=current_ip,
                timestamp=time.time(),
                confidence=min(1.0, len(recent_ips) / 10.0),
                recommended_action="require_additional_authentication",
            )

        return None

    def detect_unusual_time(self, user_id: str) -> AnomalyAlert | None:
        """Detect activity at unusual times.

        Args:
            user_id: User identifier

        Returns:
            Anomaly alert if detected, None otherwise
        """
        profile = self.tracker.user_profiles.get(user_id)
        if not profile:
            return None

        # Analyze typical active hours
        user_events = [e for e in self.tracker.events if e.user_id == user_id]
        if len(user_events) < 5:
            return None

        current_hour = datetime.now().hour
        active_hours = [datetime.fromtimestamp(e.timestamp).hour for e in user_events]

        # Simple heuristic: check if current hour is outside typical range
        avg_hour = sum(active_hours) / len(active_hours)
        std_dev = (sum((h - avg_hour) ** 2 for h in active_hours) / len(active_hours)) ** 0.5

        if std_dev > 0 and abs(current_hour - avg_hour) > (self.unusual_hour_threshold * std_dev):
            return AnomalyAlert(
                severity="medium",
                user_id=user_id,
                anomaly_type="unusual_time",
                description=f"Activity at unusual hour: {current_hour}:00 (typical: {avg_hour:.1f}±{std_dev:.1f})",
                ip_address=user_events[-1].ip_address if user_events else "unknown",
                timestamp=time.time(),
                confidence=0.6,
                recommended_action="monitor_closely",
            )

        return None

    def detect_rapid_actions(
        self, user_id: str, action: str, window_seconds: int = 60
    ) -> AnomalyAlert | None:
        """Detect rapid repeated actions (potential automation/bot).

        Args:
            user_id: User identifier
            action: Action type to check
            window_seconds: Time window in seconds

        Returns:
            Anomaly alert if detected, None otherwise
        """
        cutoff = time.time() - window_seconds
        action_count = sum(
            1
            for e in self.tracker.events
            if e.user_id == user_id and e.action == action and e.timestamp > cutoff
        )

        # Threshold: more than 10 actions in 1 minute
        if action_count > 10:
            return AnomalyAlert(
                severity="high",
                user_id=user_id,
                anomaly_type="rapid_actions",
                description=f"Rapid {action} actions: {action_count} times in {window_seconds}s",
                ip_address="",
                timestamp=time.time(),
                confidence=0.8,
                recommended_action="rate_limit",
            )

        return None

    def detect_new_user_pattern(self, user_id: str) -> AnomalyAlert | None:
        """Detect if a user is exhibiting patterns inconsistent with their history.

        Args:
            user_id: User identifier

        Returns:
            Anomaly alert if detected, None otherwise
        """
        profile = self.tracker.user_profiles.get(user_id)
        if not profile:
            return None

        # Check for first-time user patterns
        if profile["total_events"] < 3:
            return AnomalyAlert(
                severity="low",
                user_id=user_id,
                anomaly_type="new_user",
                description="New user with limited history",
                ip_address="",
                timestamp=time.time(),
                confidence=0.3,
                recommended_action="standard_monitoring",
            )

        return None


class BehavioralAnalyzer:
    """Main behavioral analysis orchestrator."""

    def __init__(self):
        """Initialize behavioral analyzer."""
        self.tracker = BehaviorTracker()
        self.detector = AnomalyDetector(self.tracker)
        self.alert_handlers: list[callable] = []

    def record_event(
        self, user_id: str, ip_address: str, action: str, metadata: dict[str, Any] | None = None
    ) -> None:
        """Record a behavior event and check for anomalies.

        Args:
            user_id: User identifier
            ip_address: IP address of the request
            action: Action being performed
            metadata: Additional event metadata
        """
        event = BehaviorEvent(
            user_id=user_id,
            ip_address=ip_address,
            action=action,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self.tracker.record_event(event)

        # Run anomaly detection
        anomalies = self._check_anomalies(user_id, ip_address, action)

        # Trigger alerts
        for anomaly in anomalies:
            self._trigger_alert(anomaly)

    def _check_anomalies(self, user_id: str, ip_address: str, action: str) -> list[AnomalyAlert]:
        """Run all anomaly detection checks.

        Args:
            user_id: User identifier
            ip_address: IP address
            action: Current action

        Returns:
            List of detected anomalies
        """
        anomalies = []

        # IP churn detection
        if anomaly := self.detector.detect_ip_churn(user_id, ip_address):
            anomalies.append(anomaly)

        # Unusual time detection
        if anomaly := self.detector.detect_unusual_time(user_id):
            anomalies.append(anomaly)

        # Rapid action detection
        if anomaly := self.detector.detect_rapid_actions(user_id, action):
            anomalies.append(anomaly)

        return anomalies

    def _trigger_alert(self, anomaly: AnomalyAlert) -> None:
        """Trigger alert for detected anomaly.

        Args:
            anomaly: Detected anomaly
        """
        logger.warning(
            f"🚨 Anomaly detected: {anomaly.anomaly_type} "
            f"for user {anomaly.user_id} "
            f"(severity: {anomaly.severity}, confidence: {anomaly.confidence:.2f})"
        )

        # Execute alert handlers
        for handler in self.alert_handlers:
            try:
                handler(anomaly)
            except Exception as exc:
                logger.error(f"Alert handler failed: {exc}")

    def register_alert_handler(self, handler: callable) -> None:  # type: ignore
        """Register a custom alert handler.

        Args:
            handler: Callable that accepts AnomalyAlert
        """
        self.alert_handlers.append(handler)

    def get_user_risk_score(self, user_id: str) -> float:
        """Calculate risk score for a user (0.0 to 1.0).

        Args:
            user_id: User identifier

        Returns:
            Risk score between 0.0 and 1.0
        """
        profile = self.tracker.user_profiles.get(user_id)
        if not profile:
            return 0.0

        # Factors that increase risk
        risk_factors = []

        # New user
        if profile["total_events"] < 5:
            risk_factors.append(0.3)

        # Multiple IPs
        ip_count = len(profile["ip_addresses"])
        if ip_count > 3:
            risk_factors.append(min(0.4, ip_count * 0.1))

        # Calculate average risk
        if risk_factors:
            return min(1.0, sum(risk_factors) / len(risk_factors))

        return 0.0

    def get_stats(self) -> dict[str, Any]:
        """Get behavioral analysis statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_events": len(self.tracker.events),
            "total_users": len(self.tracker.user_profiles),
            "events_window_hours": self.tracker.window_size.total_seconds() / 3600,
            "ip_churn_threshold": self.ip_churn_threshold,
        }


# Global analyzer instance
_analyzer: BehavioralAnalyzer | None = None


def get_analyzer() -> BehavioralAnalyzer:
    """Get or create global behavioral analyzer instance.

    Returns:
        BehavioralAnalyzer instance
    """
    global _analyzer
    if _analyzer is None:
        _analyzer = BehavioralAnalyzer()
    return _analyzer
