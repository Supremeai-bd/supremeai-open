# backend/services/intent_deciphering.py
"""SupremeAI Intent Deciphering Service (Phase 6.1 - North Star Pillar 1).

Autonomous intent interpretation:
- Separates declarative 'What' (Ultimate Goal & Invariants) from probabilistic 'How' (Execution Strategy).
- Extracts latent constraints (Zero-Cost, Zero-Downtime, Security boundaries, Non-breaking).
- Integrates semantic vector memory recall (ai_memory / pgvector) to leverage past successful solutions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.llm.advanced_model_router import DomainExpertAnalyzer, TaskComplexityAnalyzer
from core.logging_config import logger
from services.memory_service import (
    CascadeMemoryService,
    hash_vectorize,
)
from services.memory_service import (
    memory_service as global_memory_service,
)


@dataclass
class IntentAnalysis:
    raw_request: str
    ultimate_goal: str
    invariants: list[str] = field(default_factory=list)
    latent_constraints: list[str] = field(default_factory=list)
    suggested_methodology: str = ""
    domain: str = "general"
    complexity: str = "medium"
    relevant_past_memories: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_request": self.raw_request,
            "ultimate_goal": self.ultimate_goal,
            "invariants": self.invariants,
            "latent_constraints": self.latent_constraints,
            "suggested_methodology": self.suggested_methodology,
            "domain": self.domain,
            "complexity": self.complexity,
            "relevant_past_memories": self.relevant_past_memories,
            "confidence_score": self.confidence_score,
        }


class IntentDecipheringService:
    """Interprets raw, ambiguous, or complex user/admin requests into structured execution goals."""

    def __init__(self, memory_service: CascadeMemoryService | None = None) -> None:
        self.memory_service = memory_service or global_memory_service
        self.domain_analyzer = DomainExpertAnalyzer()
        self.complexity_analyzer = TaskComplexityAnalyzer()

    async def decipher_intent(
        self,
        raw_request: str,
        session_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> IntentAnalysis:
        """Deciphers raw input into declarative goal, invariants, latent constraints, and past context."""
        cleaned_request = (raw_request or "").strip()
        if not cleaned_request:
            return IntentAnalysis(
                raw_request="",
                ultimate_goal="No-op / Idle",
                invariants=["system_stability"],
                latent_constraints=["zero_resource_consumption"],
                suggested_methodology="noop",
                domain="general",
                complexity="simple",
                confidence_score=1.0,
            )

        # 1. Goal vs Method Separation
        ultimate_goal, invariants, methodology = self._separate_goal_from_method(cleaned_request)

        # 2. Extract Latent Constraints
        latent_constraints = self._extract_latent_constraints(cleaned_request)

        # 3. Classify Domain & Task Complexity
        domain = self.domain_analyzer.classify_domain(cleaned_request)
        if hasattr(domain, "value"):
            domain = domain.value
        complexity = self.complexity_analyzer.analyze(cleaned_request)

        # 4. Recall Semantic Memory from ai_memory / pgvector
        past_memories = await self._recall_relevant_memories(ultimate_goal, limit=3)

        return IntentAnalysis(
            raw_request=cleaned_request,
            ultimate_goal=ultimate_goal,
            invariants=invariants,
            latent_constraints=latent_constraints,
            suggested_methodology=methodology,
            domain=domain,
            complexity=complexity,
            relevant_past_memories=past_memories,
            confidence_score=0.95 if past_memories else 0.85,
        )

    def _separate_goal_from_method(self, request: str) -> tuple[str, list[str], str]:
        """Separates the declarative target state ('What') from execution strategy ('How')."""
        lowered = request.lower()
        invariants = ["preserve_existing_contracts", "zero_regression", "security_fail_closed"]

        # Default fallback
        ultimate_goal = request
        methodology = "dynamic_dag_execution"

        # Pattern: Performance / Latency goals
        if any(
            w in lowered for w in ["slow", "speed up", "optimize latency", "পারফরম্যান্স", "ধীরগতি"]
        ):
            ultimate_goal = "Optimize system throughput, cache hits, and minimize execution latency"
            invariants.append("p99_latency_within_sla")
            methodology = "profile_bottlenecks_and_apply_caching"

        # Pattern: Bug Fix / Crash / Debugging
        elif any(
            w in lowered
            for w in [
                "fix",
                "bug",
                "crash",
                "error",
                "সমস্যা",
                "ভাঙা",
                "ইস্যু",
                "বাগ",
                "ত্রুটি",
                "সমাধান",
            ]
        ):
            ultimate_goal = f"Identify root cause and eliminate defect: {request}"
            invariants.append("all_test_suites_must_pass")
            methodology = "reproduce_localize_ast_patch_and_verify"

        # Pattern: Refactor / Consolidation / Structural Cleanup
        elif any(
            w in lowered
            for w in ["refactor", "cleanup", "consolidate", "একীভূত", "মুছে", "remove duplicate"]
        ):
            ultimate_goal = (
                "Unify redundant abstractions and remove duplicate code while maintaining parity"
            )
            invariants.append("strict_backward_compatibility")
            methodology = "single_source_of_truth_migration_with_facades"

        # Pattern: Security / RBAC / Auth hardening
        elif any(w in lowered for w in ["security", "auth", "rbac", "নিরাপত্তা", "guard", "protect"]):
            ultimate_goal = (
                "Harden endpoints with role-based access control and strict boundary enforcement"
            )
            invariants.append("zero_unauthenticated_admin_access")
            methodology = "inject_explicit_rbac_guards"

        # Pattern: Feature Addition / Skill Generation
        elif any(w in lowered for w in ["create", "build", "add feature", "বানাও", "তৈরি"]):
            ultimate_goal = f"Synthesize and integrate capability: {request}"
            methodology = "htn_dag_decomposition_and_tool_synthesis"

        return ultimate_goal, invariants, methodology

    def _extract_latent_constraints(self, request: str) -> list[str]:
        """Extracts implicit non-functional constraints from intent."""
        lowered = request.lower()
        constraints: list[str] = ["zero_infrastructure_cost", "fail_closed_security"]

        if any(w in lowered for w in ["fast", "quick", "তাড়াতাড়ি", "instant"]):
            constraints.append("low_latency_execution")

        if any(w in lowered for w in ["safe", "careful", "সাবধানে", "no downtime"]):
            constraints.append("zero_downtime_execution")

        if any(w in lowered for w in ["clean", "parsimonious", "সিম্পল", "no bloat"]):
            constraints.append("minimal_code_footprint")

        return constraints

    async def _recall_relevant_memories(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        """Recalls contextually similar past executions from CascadeMemoryService."""
        try:
            memories = self.memory_service.retrieve_memories()
            if not memories:
                return []

            query_vec = hash_vectorize(query)
            scored_memories = []

            for mem in memories:
                summary = mem.get("summary") or ""
                if not summary:
                    continue
                mem_vec = hash_vectorize(summary)
                # Cosine similarity
                dot_product = sum(a * b for a, b in zip(query_vec, mem_vec, strict=False))
                scored_memories.append((dot_product, mem))

            scored_memories.sort(key=lambda x: x[0], reverse=True)
            return [m[1] for m in scored_memories[:limit] if m[0] > 0.1]
        except Exception as exc:
            logger.warning(f"IntentDecipheringService: memory recall error: {exc}")
            return []
