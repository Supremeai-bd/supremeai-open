"""Decision Engine Module for SupremeAI 2.0
Provides intelligent decision-making for autonomous operations based on risk assessment.

বাংলা: SupremeAI ২.০-এর জন্য স্মার্ট ডিসিশন এঞ্জিন — রিস্ক অ্যাসেসমেন্টের উপর ভিত্তি করে স্বায়ত্তশাসিত枸成。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

try:
    from .monitoring.logging_config import logger
except ImportError:
    try:
        from core.monitoring.logging_config import logger
    except ImportError:
        from monitoring.logging_config import logger


class AgentRole(str, Enum):
    CODER = "CODER"  # Standard implementation agent
    SCOUT = "SCOUT"  # Reconnaissance and discovery
    AUDITOR = "AUDITOR"  # Security, sanitization and invariant checker
    BREAKER = "BREAKER"  # Adversarial unit & edge-case stress tester


@dataclass(frozen=True)
class TaskClassification:
    recommended_role: AgentRole
    risk_tier: str  # L1 (Low), L2 (Medium), L3 (High / Core)
    requires_approval: bool
    rationale: str


class DecisionEngine:
    """Intelligent decision engine for routing and approving autonomous operations.

    বাংলা: স্বায়ত্তশাসিত অপারেশনগুলো রাউট এবং অ্যাপ্রুভ করার জন্য বুদ্ধিমান ডিসিশন ইঞ্জিন।
    """

    CRITICAL_CORE_PATTERNS = {
        "core/",
        "security/",
        "auth/",
        "vault/",
        ".github/workflows/",
    }

    DOCS_PATTERNS = {"docs/", ".md", "README", "AGENTS"}

    TEST_PATTERNS = {"test", "tests/", "_test.py", ".test.ts"}

    @classmethod
    def classify_task(cls, title: str, scope_paths: list[str]) -> TaskClassification:
        """Arbitrate agent role assignment and safety tier based on declared scope paths."""
        normalized_paths = [p.lower() for p in scope_paths]

        # 1. Check if touches critical paths
        is_critical = any(
            any(pattern in p for pattern in cls.CRITICAL_CORE_PATTERNS)
            for p in normalized_paths
        )
        if is_critical or "p0" in title.lower():
            return TaskClassification(
                recommended_role=AgentRole.AUDITOR,
                risk_tier="L3",
                requires_approval=True,
                rationale="Touches critical security/orchestration paths; mandates AUDITOR role.",
            )

        # 2. Check if docs or recon only
        is_docs_only = normalized_paths and all(
            any(p.endswith(ext) or pat in p for pat in cls.DOCS_PATTERNS for ext in [".md", ".txt"])
            for p in normalized_paths
        )
        if is_docs_only:
            return TaskClassification(
                recommended_role=AgentRole.SCOUT,
                risk_tier="L1",
                requires_approval=False,
                rationale="Documentation or recon diff only; SCOUT role assigned.",
            )

        # 3. Check if test-focused
        is_test_focused = normalized_paths and all(
            any(pat in p for pat in cls.TEST_PATTERNS)
            for p in normalized_paths
        )
        if is_test_focused:
            return TaskClassification(
                recommended_role=AgentRole.BREAKER,
                risk_tier="L2",
                requires_approval=False,
                rationale="Verification & test-focused scope; BREAKER role assigned.",
            )

        # Default standard coder
        return TaskClassification(
            recommended_role=AgentRole.CODER,
            risk_tier="L2",
            requires_approval=False,
            rationale="Standard domain feature or bugfix; CODER role assigned.",
        )

    def __init__(self) -> None:
        """Initialize the decision engine with configuration from environment.

        বাংলা: এনভায়রনমেন্ট থেকে কনফিগারেশন লোড করে ডিসিশন ইঞ্জিন ইনিশিয়ালাইজ করে।
        """
        self.langsmith_api_key = os.getenv("LANGSMITH_API_KEY")
        self._min_confidence = float(os.getenv("DECISION_MIN_CONFIDENCE", "0.6"))

        # বাংলা: ডুপ্লিকেট ডিসিশন হিস্টোরি এবং ক্যাশ লিক প্রতিরোধের স্টোরেজ
        self.decision_history: list[dict[str, Any]] = []
        self._decision_cache: dict[str, dict[str, Any]] = {}

    async def decide(self, context: dict[str, Any]) -> dict[str, Any]:
        """Analyze request context and return a routing decision.

        Args:
            context: Dictionary containing:
                - risk_flags (list): List of risk flags detected
                - recent_error_rate (float): Recent error rate (0.0 to 1.0)
                - sandbox_passed (bool|None): Whether sandbox validation passed

        Returns:
            Dictionary with decision result containing:
                - action (str): One of "proceed", "review", "block"
                - confidence (float): Confidence score (0.0 to 1.0)
                - reason (str|None): Reason for the decision
                - trace (Any): Optional trace information

        Raises:
            None. All decisions are returned as dictionaries without exceptions.

        বাংলা: রিকোয়েস্ট কনটেক্সট অ্যানালাইজ করে একটি রাউটিং ডিসিশন রিটার্ন করে।

        Decision Matrix:
            - sandbox_failed → "block" (confidence: 1.0)
            - risk_flags present → "review" (confidence: 0.5)
            - confidence < min_confidence → "review"
            - otherwise → "proceed"
        """
        # বাংলা: কনটেক্সট থেকে ক্যাশ কী জেনারেট করে ক্যাশ হিট চেক করা
        context_key = str(sorted((k, str(v)) for k, v in context.items()))
        if context_key in self._decision_cache:
            logger.debug(
                "DecisionEngine: Cache hit, returning decision without duplicating history"
            )
            return self._decision_cache[context_key]

        risk_flags = context.get("risk_flags") or []
        error_rate = context.get("recent_error_rate", 0.0)
        sandbox_passed = context.get("sandbox_passed")

        if sandbox_passed is False:
            logger.warning("DecisionEngine: sandbox failed, blocking action")
            decision = {
                "action": "block",
                "confidence": 1.0,
                "reason": "sandbox_failed",
                "trace": None,
            }
            self.decision_history.append(decision)
            self._decision_cache[context_key] = decision
            return decision

        if risk_flags:
            logger.info(f"DecisionEngine: risk flags present {risk_flags}, routing to review")
            decision = {
                "action": "review",
                "confidence": 0.5,
                "reason": "risk_flags",
                "trace": None,
            }
            self.decision_history.append(decision)
            self._decision_cache[context_key] = decision
            return decision

        confidence = max(0.0, 1.0 - error_rate)
        action = "proceed" if confidence >= self._min_confidence else "review"
        logger.debug(f"DecisionEngine: action={action} confidence={confidence:.2f}")
        decision = {
            "action": action,
            "confidence": confidence,
            "reason": None,
            "trace": None,
        }
        self.decision_history.append(decision)
        self._decision_cache[context_key] = decision
        return decision
