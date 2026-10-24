"""Behavioral Analysis Module for Anomaly Detection (Optimized)

This module provides real-time behavioral analysis and anomaly detection
with significantly improved performance using deque-based circular buffers,
memory-bounded operations, and pre-computed hourly distributions.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


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


class OptimizedBehaviorTracker:
    """Tracks user behavior patterns over time, optimized for high throughput."""

    def __init__(self, window_size_hours: int = 24, max_events_per_user: int = 1000):
        """Initialize optimized behavior tracker.

        Args:
            window_size_hours: Time window for pattern analysis
            max_events_per_user: Memory bound per user
        """
        self.window_size_seconds = window_size_hours * 3600
        self.max_events_per_user = max_events_per_user

        # User-specific event deques for O(1) cleanup and boundedness
        self.user_events: dict[str, deque[BehaviorEvent]] = defaultdict(
            lambda: deque(maxlen=self.max_events_per_user)
        )

        # O(1) lookup profiles
        self.user_profiles: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "ip_addresses": defaultdict(int),
                "actions": defaultdict(int),
                "last_seen": 0.0,
                "first_seen": time.time(),
                "total_events": 0,
                # For pre-computed hourly distributions
                "hourly_counts": defaultdict(int),
            }
        )

    def record_event(self, event: BehaviorEvent) -> None:
        """Record a behavior event with O(1) complexity.

        Args:
            event: Behavior event to record
        """
        # Append to user's deque (automatically bounded by max_events_per_user)
        user_deque = self.user_events[event.user_id]
        user_deque.append(event)

        # Update user profile incrementally
        profile = self.user_profiles[event.user_id]
        profile["ip_addresses"][event.ip_address] += 1
        profile["actions"][event.action] += 1
        profile["last_seen"] = event.timestamp
        profile["total_events"] += 1

        # Pre-compute hour distribution
        hour = datetime.fromtimestamp(event.timestamp).hour
        profile["hourly_counts"][hour] += 1

        # Periodic cleanup per user is much cheaper
        self._cleanup_old_events(event.user_id)

    def _cleanup_old_events(self, user_id: str) -> None:
        """Remove events outside the analysis window for a specific user.
        O(1) amortized cleanup from the left side of the deque.
        """
        cutoff = time.time() - self.window_size_seconds
        user_deque = self.user_events[user_id]

        while user_deque and user_deque[0].timestamp <= cutoff:
            user_deque.popleft()
            # We optionally could decrement counters here if absolute precision
            # within the exact window is needed, but typically keeping historical
            # profile stats is fine for overall profiling.

    def get_user_pattern(self, user_id: str) -> dict[str, Any]:
        """Get behavior pattern for a user."""
        return dict(self.user_profiles.get(user_id, {}))

    def get_recent_ips(self, user_id: str, hours: int = 1) -> list[str]:
        """Get recent IP addresses for a user efficiently."""
        cutoff = time.time() - (hours * 3600)
        recent_ips = set()
        user_deque = self.user_events.get(user_id)
        if not user_deque:
            return []

        # Iterate backwards (recent events first)
        for event in reversed(user_deque):
            if event.timestamp <= cutoff:
                break
            recent_ips.add(event.ip_address)

        return list(recent_ips)


class OptimizedAnomalyDetector:
    """Detects anomalies in user behavior patterns efficiently."""

    def __init__(self, tracker: OptimizedBehaviorTracker):
        """Initialize anomaly detector."""
        self.tracker = tracker
        self.ip_churn_threshold = 5  # IPs per hour
        self.unusual_hour_threshold = 2  # Std devs from mean

    def detect_ip_churn(self, user_id: str, current_ip: str) -> AnomalyAlert | None:
        """Detect IP churn (multiple IPs in short time)."""
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
        """Detect activity at unusual times using pre-computed distributions."""
        profile = self.tracker.user_profiles.get(user_id)
        if not profile or profile["total_events"] < 5:
            return None

        hourly_counts = profile["hourly_counts"]
        total_tracked = sum(hourly_counts.values())
        if total_tracked == 0:
            return None

        # Calculate mean hour
        sum_hours = sum(h * count for h, count in hourly_counts.items())
        avg_hour = sum_hours / total_tracked

        # Calculate variance and std dev
        variance = (
            sum(count * ((h - avg_hour) ** 2) for h, count in hourly_counts.items()) / total_tracked
        )
        std_dev = variance**0.5

        current_hour = datetime.now().hour

        if std_dev > 0 and abs(current_hour - avg_hour) > (self.unusual_hour_threshold * std_dev):
            user_deque = self.tracker.user_events.get(user_id)
            last_ip = user_deque[-1].ip_address if user_deque else "unknown"

            return AnomalyAlert(
                severity="medium",
                user_id=user_id,
                anomaly_type="unusual_time",
                description=f"Activity at unusual hour: {current_hour}:00 (typical: {avg_hour:.1f}±{std_dev:.1f})",
                ip_address=last_ip,
                timestamp=time.time(),
                confidence=0.6,
                recommended_action="monitor_closely",
            )

        return None

    def detect_rapid_actions(
        self, user_id: str, action: str, window_seconds: int = 60
    ) -> AnomalyAlert | None:
        """Detect rapid repeated actions efficiently."""
        cutoff = time.time() - window_seconds
        user_deque = self.tracker.user_events.get(user_id)

        if not user_deque:
            return None

        action_count = 0
        for event in reversed(user_deque):
            if event.timestamp <= cutoff:
                break
            if event.action == action:
                action_count += 1

            if action_count > 10:
                return AnomalyAlert(
                    severity="high",
                    user_id=user_id,
                    anomaly_type="rapid_actions",
                    description=f"Rapid {action} actions: {action_count} times in {window_seconds}s",
                    ip_address=event.ip_address,
                    timestamp=time.time(),
                    confidence=0.8,
                    recommended_action="rate_limit",
                )

        return None

    def detect_new_user_pattern(self, user_id: str) -> AnomalyAlert | None:
        """Detect if a user is exhibiting patterns inconsistent with their history."""
        profile = self.tracker.user_profiles.get(user_id)
        if not profile:
            return None

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


# Factory functions & backward compatibility aliases
BehaviorTracker = OptimizedBehaviorTracker


def create_optimized_tracker(
    window_size_hours: int = 24,
) -> tuple[OptimizedBehaviorTracker, OptimizedAnomalyDetector]:
    """Create and return an optimized tracker and detector pair."""
    tracker = OptimizedBehaviorTracker(window_size_hours=window_size_hours)
    detector = OptimizedAnomalyDetector(tracker)
    return tracker, detector
