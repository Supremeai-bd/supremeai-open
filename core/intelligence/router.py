from __future__ import annotations

import hashlib
import re
import uuid

from .models import (
    ExecutionBudget,
    IntelligenceTier,
    RoutingDecision,
    TaskClassification,
)


class IntelligenceRouter:
    """Deterministic, provider-independent routing with immutable safety ceilings."""

    _sensitive = re.compile(
        r"\b(password|secret|token|payment|delete|deploy|migration|rotate)\b", re.I
    )
    _coding = re.compile(r"\b(code|script|bug|refactor|implement|python|api)\b", re.I)
    _research = re.compile(r"\b(research|search|compare|analy[sz]e|investigate)\b", re.I)

    def classify(self, prompt: str) -> TaskClassification:
        if self._sensitive.search(prompt):
            return (
                TaskClassification.IRREVERSIBLE
                if re.search(r"\b(delete|deploy|payment|rotate)\b", prompt, re.I)
                else TaskClassification.SENSITIVE
            )
        if self._coding.search(prompt):
            return TaskClassification.CODING
        if self._research.search(prompt):
            return TaskClassification.RESEARCH
        return TaskClassification.GENERAL

    def route(self, prompt: str, requested_tier: str | None = None) -> RoutingDecision:
        classification = self.classify(prompt)
        if classification == TaskClassification.IRREVERSIBLE:
            tier, reason = (
                IntelligenceTier.VERIFIED,
                "Irreversible intent requires verification and human approval.",
            )
            budget = ExecutionBudget(max_agents=1, max_refinements=0, requires_approval=True)
        elif classification == TaskClassification.SENSITIVE:
            tier, reason = (
                IntelligenceTier.VERIFIED,
                "Sensitive intent is bounded to verified execution.",
            )
            budget = ExecutionBudget(max_agents=2, max_refinements=1, requires_approval=True)
        elif classification == TaskClassification.CODING:
            tier, reason = (
                IntelligenceTier.SWARM,
                "Coding work benefits from bounded architecture, implementation, and review.",
            )
            budget = ExecutionBudget(max_agents=6, max_refinements=3)
        elif classification == TaskClassification.RESEARCH:
            tier, reason = IntelligenceTier.VERIFIED, "Research requires evidence before synthesis."
            budget = ExecutionBudget(max_agents=3, max_refinements=1)
        else:
            tier, reason = (
                IntelligenceTier.FAST,
                "Low-risk general task uses the bounded fast path.",
            )
            budget = ExecutionBudget()

        allowed_tiers = {
            IntelligenceTier.FAST.value,
            IntelligenceTier.VERIFIED.value,
            IntelligenceTier.SWARM.value,
        }
        override_applied = False
        if (
            requested_tier in allowed_tiers
            and classification
            not in {TaskClassification.IRREVERSIBLE, TaskClassification.SENSITIVE}
            and requested_tier != tier.value
        ):
            tier = IntelligenceTier(requested_tier)
            budget = self._budget_for(tier)
            reason = "User tier override applied within immutable safety limits."
            override_applied = True
        return RoutingDecision(
            tier=tier,
            classification=classification,
            budget=budget,
            reason=reason,
            override_requested=requested_tier,
            override_applied=override_applied,
            audit_id=self._audit_id(prompt),
        )

    @staticmethod
    def _budget_for(tier: IntelligenceTier) -> ExecutionBudget:
        return {
            IntelligenceTier.FAST: ExecutionBudget(),
            IntelligenceTier.VERIFIED: ExecutionBudget(max_agents=3, max_refinements=1),
            IntelligenceTier.SWARM: ExecutionBudget(max_agents=6, max_refinements=3),
        }.get(tier, ExecutionBudget())

    @staticmethod
    def _audit_id(prompt: str) -> str:
        return hashlib.sha256(f"{uuid.uuid4()}:{prompt}".encode()).hexdigest()[:20]
