"""
Multi-Agent Role Arbiter & Risk Policy Classifier — Core Decision Moat.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


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
    """
    Arbitrates agent role assignment and safety tier based on declared scope paths
    and operational boundaries.
    """

    CRITICAL_CORE_PATTERNS: ClassVar[set[str]] = {
        "core/",
        "security/",
        "auth/",
        "vault/",
        ".github/workflows/",
    }

    DOCS_PATTERNS: ClassVar[set[str]] = {"docs/", ".md", "README", "AGENTS"}

    TEST_PATTERNS: ClassVar[set[str]] = {"test", "tests/", "_test.py", ".test.ts"}

    @classmethod
    def classify_task(cls, title: str, scope_paths: list[str]) -> TaskClassification:
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
            any(
                p.endswith(ext) or pat in p
                for pat in cls.DOCS_PATTERNS
                for ext in [".md", ".txt"]
            )
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
            any(pat in p for pat in cls.TEST_PATTERNS) for p in normalized_paths
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
