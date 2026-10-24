"""Task Intelligence Router - Extended from existing IntelligenceRouter

SUPREMEAI Task Intelligence Router with decision tree for single vs multi-agent routing.

Key Principles:
- "If multi-agent collaboration provides measurable benefit, use it."
- Existing capability reuse before new code
- High Intelligence, Low Engineering

This module extends the existing IntelligenceRouter to provide:
1. Task complexity analysis
2. Multi-agent benefit calculation
3. Decision tree for routing strategy
4. Measurable benefit quantification
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from backend.monitoring.logging_config import logger
from core.agent_registry import AgentRegistry

from .router import (
    ExecutionBudget,
    IntelligenceRouter,
    IntelligenceTier,
    RoutingDecision,
    TaskClassification,
)


class TaskComplexity(Enum):
    """Task complexity levels for routing decisions"""

    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


class RoutingStrategy(Enum):
    """Routing strategies for task execution"""

    SINGLE_AGENT = "single"
    MULTI_AGENT_PARALLEL = "multi_parallel"
    MULTI_AGENT_SEQUENTIAL = "multi_sequential"
    STRONG_AGENT = "strong"


@dataclass
class TaskIntelligenceRoutingDecision:
    """Extended routing decision with task intelligence"""

    strategy: RoutingStrategy
    agents: list[str]
    reason: str
    measurable_benefit: float  # 0.0 to 1.0 scale
    classification: TaskClassification
    complexity: TaskComplexity
    tier: IntelligenceTier
    original_decision: RoutingDecision


@dataclass
class AgentCapability:
    """Agent capability information for routing"""

    id: str
    role: str
    capabilities: list[str]
    tier: IntelligenceTier
    current_load: int = 0
    max_capacity: int = 10


class TaskIntelligenceRouter:
    """
    Extended Task Intelligence Router with decision tree for single vs multi-agent routing.

    This router extends the existing IntelligenceRouter to provide intelligent task routing
    based on complexity analysis and measurable benefit calculation.

    Key Features:
    - Task complexity determination
    - Multi-agent benefit analysis
    - Decision tree for routing strategy
    - Existing capability reuse
    - Measurable benefit quantification

    Usage:
        router = TaskIntelligenceRouter()
        decision = router.route_with_intelligence(task_description)
        # decision.strategy - RoutingStrategy
        # decision.agents - List of agent IDs
        # decision.measurable_benefit - Benefit score (0.0-1.0)
    """

    def __init__(self, agent_registry: AgentRegistry | None = None):
        """
        Initialize TaskIntelligenceRouter.

        Args:
            agent_registry: Optional AgentRegistry instance. If None, creates new one.
        """
        self.intelligence_router = IntelligenceRouter()
        self.agent_registry = agent_registry or AgentRegistry()
        self._agent_capabilities: dict[str, AgentCapability] = {}
        self._load_agent_capabilities()
        logger.info(
            "[TaskIntelligenceRouter] Initialized with existing IntelligenceRouter and AgentRegistry"
        )

    def _load_agent_capabilities(self):
        """Load agent capabilities from registry"""
        try:
            agents = self.agent_registry.list_agents(active_only=True)
            for agent_record in agents:
                # Map IntelligenceTier from agent configuration
                agent_tier = IntelligenceTier.FAST  # Default
                if hasattr(agent_record, "provider") and agent_record.provider:
                    provider_lower = agent_record.provider.lower()
                    if "swarm" in provider_lower or "multi" in provider_lower:
                        agent_tier = IntelligenceTier.SWARM
                    elif "verified" in provider_lower:
                        agent_tier = IntelligenceTier.VERIFIED

                self._agent_capabilities[agent_record.id] = AgentCapability(
                    id=agent_record.id,
                    role=agent_record.role,
                    capabilities=[],  # To be populated from agent metadata
                    tier=agent_tier,
                    current_load=0,
                    max_capacity=10,
                )
            logger.info(
                f"[TaskIntelligenceRouter] Loaded {len(self._agent_capabilities)} agent capabilities"
            )
        except Exception as e:
            logger.error(f"[TaskIntelligenceRouter] Error loading agent capabilities: {e}")
            self._agent_capabilities = {}

    def route_with_intelligence(
        self, task_description: str, requested_tier: str | None = None
    ) -> TaskIntelligenceRoutingDecision:
        """
        Route task with intelligence using decision tree.

        This method:
        1. Uses existing IntelligenceRouter for classification
        2. Determines task complexity
        3. Checks if multi-agent provides measurable benefit
        4. Selects appropriate routing strategy

        Args:
            task_description: Description of the task to route
            requested_tier: Optional tier override

        Returns:
            TaskIntelligenceRoutingDecision with routing information
        """
        # Step 1: Use existing IntelligenceRouter for classification
        original_decision = self.intelligence_router.route(task_description, requested_tier)
        classification = original_decision.classification
        tier = original_decision.tier

        logger.debug(f"[TaskIntelligenceRouter] Classification: {classification}, Tier: {tier}")

        # Step 2: Determine complexity
        complexity = self._determine_complexity(task_description, classification)
        logger.debug(f"[TaskIntelligenceRouter] Complexity: {complexity}")

        # Step 3: Check if multi-agent is beneficial
        if self._multi_agent_beneficial(classification, complexity):
            # Step 4: Select multi-agent strategy
            agents, strategy = self._select_multi_agents(classification, complexity)
            benefit = self._calculate_benefit(classification, complexity)

            logger.info(
                f"[TaskIntelligenceRouter] Multi-agent {strategy.value} selected for {classification} task with benefit {benefit:.2f}"
            )

            return TaskIntelligenceRoutingDecision(
                strategy=strategy,
                agents=agents,
                reason=f"Multi-agent {strategy.value} collaboration provides measurable benefit ({benefit:.2f})",
                measurable_benefit=benefit,
                classification=classification,
                complexity=complexity,
                tier=tier,
                original_decision=original_decision,
            )
        else:
            # Single agent sufficient
            agent = self._select_single_agent(classification, tier)
            agent_id = agent.id if agent else "default"

            logger.info(f"[TaskIntelligenceRouter] Single agent selected for {classification} task")

            return TaskIntelligenceRoutingDecision(
                strategy=RoutingStrategy.SINGLE_AGENT,
                agents=[agent_id],
                reason="Single agent sufficient for this task",
                measurable_benefit=0.0,
                classification=classification,
                complexity=complexity,
                tier=tier,
                original_decision=original_decision,
            )

    def _determine_complexity(
        self, task_description: str, classification: TaskClassification
    ) -> TaskComplexity:
        """
        Determine task complexity based on description and classification.

        Args:
            task_description: Task description text
            classification: Task classification from IntelligenceRouter

        Returns:
            TaskComplexity level
        """
        # Simple complexity detection based on word count and classification
        word_count = len(task_description.split())

        if classification in [TaskClassification.IRREVERSIBLE, TaskClassification.SENSITIVE]:
            # High-risk tasks are always complex
            return TaskComplexity.COMPLEX
        elif classification == TaskClassification.CODING:
            if word_count > 50:
                return TaskComplexity.COMPLEX
            elif word_count > 20:
                return TaskComplexity.MEDIUM
            return TaskComplexity.SIMPLE
        elif classification == TaskClassification.RESEARCH:
            if word_count > 40:
                return TaskComplexity.COMPLEX
            elif word_count > 15:
                return TaskComplexity.MEDIUM
            return TaskComplexity.SIMPLE
        else:  # GENERAL
            if word_count > 30:
                return TaskComplexity.MEDIUM
            return TaskComplexity.SIMPLE

    def _multi_agent_beneficial(
        self, classification: TaskClassification, complexity: TaskComplexity
    ) -> bool:
        """
        Determine if multi-agent collaboration provides measurable benefit.

        Rule: Multi-agent is beneficial for complex tasks in specific categories.

        Args:
            classification: Task classification
            complexity: Task complexity

        Returns:
            True if multi-agent is beneficial
        """
        # Complex tasks always benefit from multi-agent
        if complexity == TaskComplexity.COMPLEX:
            return True

        # Medium complexity tasks in specific categories benefit
        if complexity == TaskComplexity.MEDIUM:
            return classification in [TaskClassification.CODING, TaskClassification.RESEARCH]

        # Simple tasks don't benefit from multi-agent
        return False

    def _select_multi_agents(
        self, classification: TaskClassification, complexity: TaskComplexity
    ) -> tuple[list[str], RoutingStrategy]:
        """
        Select agents for multi-agent collaboration.

        Args:
            classification: Task classification
            complexity: Task complexity

        Returns:
            Tuple of (agent_ids, routing_strategy)
        """
        agents: list[str] = []
        strategy = RoutingStrategy.MULTI_AGENT_PARALLEL

        # Get available agents
        available_agents = list(self._agent_capabilities.values())

        if not available_agents:
            logger.warning("[TaskIntelligenceRouter] No agents available for multi-agent routing")
            return ["default"], RoutingStrategy.SINGLE_AGENT

        if classification == TaskClassification.CODING:
            # For coding: Architect + Coder + Tester
            for agent in available_agents:
                if len(agents) >= 3:
                    break
                role_lower = agent.role.lower()
                if (
                    "architect" in role_lower
                    and agent.id not in agents
                    or "coder" in role_lower
                    and agent.id not in agents
                    or "tester" in role_lower
                    and agent.id not in agents
                    or "developer" in role_lower
                    and agent.id not in agents
                ):
                    agents.append(agent.id)
            strategy = RoutingStrategy.MULTI_AGENT_SEQUENTIAL

        elif classification == TaskClassification.RESEARCH:
            # For research: Researcher + Analyst + Validator
            for agent in available_agents:
                if len(agents) >= 3:
                    break
                role_lower = agent.role.lower()
                if (
                    "research" in role_lower
                    and agent.id not in agents
                    or "analyst" in role_lower
                    and agent.id not in agents
                    or "validator" in role_lower
                    and agent.id not in agents
                ):
                    agents.append(agent.id)

        elif classification in [TaskClassification.IRREVERSIBLE, TaskClassification.SENSITIVE]:
            # For sensitive tasks: Verifier + Approver + Auditor
            for agent in available_agents:
                if len(agents) >= 3:
                    break
                role_lower = agent.role.lower()
                if (
                    "verifier" in role_lower
                    and agent.id not in agents
                    or "approver" in role_lower
                    and agent.id not in agents
                    or "auditor" in role_lower
                    and agent.id not in agents
                    or "security" in role_lower
                    and agent.id not in agents
                ):
                    agents.append(agent.id)
            strategy = RoutingStrategy.MULTI_AGENT_SEQUENTIAL

        # Fallback: Select top 3 agents by capability match
        if not agents:
            sorted_agents = sorted(
                available_agents,
                key=lambda a: self._capability_match_score(a, classification),
                reverse=True,
            )
            agents = [agent.id for agent in sorted_agents[:3]]

        logger.debug(f"[TaskIntelligenceRouter] Selected agents: {agents}, Strategy: {strategy}")
        return agents, strategy

    def _select_single_agent(
        self, classification: TaskClassification, tier: IntelligenceTier
    ) -> AgentCapability | None:
        """
        Select the best single agent for the task.

        Args:
            classification: Task classification
            tier: Intelligence tier

        Returns:
            Best matching AgentCapability or None
        """
        available_agents = list(self._agent_capabilities.values())

        if not available_agents:
            return None

        # Filter by tier
        tier_agents = [a for a in available_agents if a.tier == tier]

        if not tier_agents:
            tier_agents = available_agents

        # Sort by capability match and load
        tier_agents.sort(
            key=lambda a: (-self._capability_match_score(a, classification), a.current_load)
        )

        selected = tier_agents[0]
        logger.debug(
            f"[TaskIntelligenceRouter] Selected single agent: {selected.id} for {classification}"
        )
        return selected

    def _capability_match_score(
        self, agent: AgentCapability, classification: TaskClassification
    ) -> int:
        """
        Calculate capability match score for agent selection.

        Args:
            agent: AgentCapability to score
            classification: Task classification

        Returns:
            Match score (higher is better)
        """
        score = 0
        role_lower = agent.role.lower()

        if classification == TaskClassification.CODING:
            if "coder" in role_lower or "developer" in role_lower:
                score += 10
            if "architect" in role_lower:
                score += 8
            if "programmer" in role_lower:
                score += 7

        elif classification == TaskClassification.RESEARCH:
            if "research" in role_lower:
                score += 10
            if "analyst" in role_lower:
                score += 8
            if "investigator" in role_lower:
                score += 7

        elif classification in [TaskClassification.IRREVERSIBLE, TaskClassification.SENSITIVE]:
            if "verifier" in role_lower or "security" in role_lower:
                score += 10
            if "approver" in role_lower or "auditor" in role_lower:
                score += 8

        # Bonus for higher tier agents
        if agent.tier == IntelligenceTier.SWARM:
            score += 5
        elif agent.tier == IntelligenceTier.VERIFIED:
            score += 3

        return score

    def _calculate_benefit(
        self, classification: TaskClassification, complexity: TaskComplexity
    ) -> float:
        """
        Calculate measurable benefit of multi-agent collaboration (0.0 to 1.0).

        Args:
            classification: Task classification
            complexity: Task complexity

        Returns:
            Benefit score between 0.0 and 1.0
        """
        benefit_map = {
            (TaskClassification.CODING, TaskComplexity.COMPLEX): 0.85,
            (TaskClassification.CODING, TaskComplexity.MEDIUM): 0.65,
            (TaskClassification.CODING, TaskComplexity.SIMPLE): 0.30,
            (TaskClassification.RESEARCH, TaskComplexity.COMPLEX): 0.80,
            (TaskClassification.RESEARCH, TaskComplexity.MEDIUM): 0.60,
            (TaskClassification.RESEARCH, TaskComplexity.SIMPLE): 0.25,
            (TaskClassification.IRREVERSIBLE, TaskComplexity.COMPLEX): 0.90,
            (TaskClassification.IRREVERSIBLE, TaskComplexity.MEDIUM): 0.75,
            (TaskClassification.IRREVERSIBLE, TaskComplexity.SIMPLE): 0.60,
            (TaskClassification.SENSITIVE, TaskComplexity.COMPLEX): 0.88,
            (TaskClassification.SENSITIVE, TaskComplexity.MEDIUM): 0.70,
            (TaskClassification.SENSITIVE, TaskComplexity.SIMPLE): 0.55,
            (TaskClassification.GENERAL, TaskComplexity.COMPLEX): 0.70,
            (TaskClassification.GENERAL, TaskComplexity.MEDIUM): 0.40,
            (TaskClassification.GENERAL, TaskComplexity.SIMPLE): 0.10,
        }

        return benefit_map.get((classification, complexity), 0.0)

    def get_routing_recommendation(self, task_description: str) -> dict:
        """
        Get comprehensive routing recommendation as dictionary.

        Args:
            task_description: Task description

        Returns:
            Dictionary with routing recommendation
        """
        decision = self.route_with_intelligence(task_description)

        return {
            "task_description": task_description,
            "strategy": decision.strategy.value,
            "agents": decision.agents,
            "agent_count": len(decision.agents),
            "classification": decision.classification.value,
            "complexity": decision.complexity.value,
            "tier": decision.tier.value,
            "measurable_benefit": decision.measurable_benefit,
            "reason": decision.reason,
            "original_decision": {
                "tier": decision.original_decision.tier.value,
                "classification": decision.original_decision.classification.value,
                "budget": {
                    "max_agents": decision.original_decision.budget.max_agents,
                    "max_refinements": decision.original_decision.budget.max_refinements,
                    "timeout_seconds": decision.original_decision.budget.timeout_seconds,
                    "requires_approval": decision.original_decision.budget.requires_approval,
                },
            },
        }


# Singleton instance
_task_intelligence_router: TaskIntelligenceRouter | None = None


def get_task_intelligence_router() -> TaskIntelligenceRouter:
    """
    Get singleton instance of TaskIntelligenceRouter.

    Returns:
        TaskIntelligenceRouter singleton instance
    """
    global _task_intelligence_router
    if _task_intelligence_router is None:
        _task_intelligence_router = TaskIntelligenceRouter()
    return _task_intelligence_router


# Convenience function for direct usage
def route_task_with_intelligence(
    task_description: str, requested_tier: str | None = None
) -> TaskIntelligenceRoutingDecision:
    """
    Route a task with intelligence using the singleton router.

    Args:
        task_description: Task description
        requested_tier: Optional tier override

    Returns:
        TaskIntelligenceRoutingDecision
    """
    router = get_task_intelligence_router()
    return router.route_with_intelligence(task_description, requested_tier)
