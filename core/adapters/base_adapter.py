# backend/adapters/base_adapter.py
"""SupremeAI Domain Base Adapter (Phase 2 - Intelligence Layer).

Defines the abstract interface and performance tracking for all domain adapters.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdaptationResult:
    success: bool
    adapted_solution: Any
    domain_specific_metadata: dict[str, Any]
    confidence: float
    execution_time_ms: int
    suggestions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class BaseAdapter(ABC):
    """Abstract base class for all domain adapters.

    Each adapter handles a specific domain's unique requirements.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = config or {}
        self.domain_name: str = self.__class__.__name__.replace("Adapter", "").lower()
        self.capabilities: list[str] = self._define_capabilities()
        self.constraints: dict[str, Any] = self._define_constraints()

        # Performance tracking
        self.execution_stats: dict[str, Any] = {
            "total_executions": 0,
            "successful": 0,
            "failed": 0,
            "avg_confidence": 0.0,
        }

    @abstractmethod
    def _define_capabilities(self) -> list[str]:
        """Define what this adapter can do."""
        pass

    @abstractmethod
    def _define_constraints(self) -> dict[str, Any]:
        """Define domain-specific constraints."""
        pass

    @abstractmethod
    async def adapt(self, problem: Any, context: dict[str, Any] | None = None) -> AdaptationResult:
        """Main adaptation method - transforms generic problem into domain-specific solution."""
        pass

    @abstractmethod
    def validate_domain_input(self, input_data: Any) -> tuple[bool, list[str]]:
        """Validate input against domain requirements."""
        pass

    def can_handle(self, problem: Any) -> bool:
        """Check if this adapter can handle the given problem."""
        problem_str = str(problem).lower()
        domain_keywords: list[str] = self.config.get("domain_keywords", [])
        return any(kw in problem_str for kw in domain_keywords)

    def get_info(self) -> dict[str, Any]:
        """Return adapter information."""
        return {
            "domain": self.domain_name,
            "capabilities": self.capabilities,
            "constraints": self.constraints,
            "stats": self.execution_stats,
            "config": self.config,
        }

    def _update_stats(self, success: bool, confidence: float) -> None:
        """Update execution statistics."""
        self.execution_stats["total_executions"] += 1
        if success:
            self.execution_stats["successful"] += 1
        else:
            self.execution_stats["failed"] += 1

        total = self.execution_stats["total_executions"]
        current_avg = self.execution_stats["avg_confidence"]
        self.execution_stats["avg_confidence"] = (current_avg * (total - 1) + confidence) / total
