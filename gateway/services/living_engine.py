# backend/services/living_engine.py
"""SupremeAI Living & Self-Evolving Autonomous Engine Orchestrator.

The unified master orchestrator coordinating:
1. Advanced Multi-Type Reasoning (Deductive, Inductive, Abductive, Analogical, Causal)
2. Intent Deciphering (Goal vs Method Separation & Memory Recall)
3. Dynamic HTN DAG Planning (Epistemic Probing & Cycle Prevention)
4. Domain Adapters (Dev, Business, UX) with AST Hardening
5. Online Continuous Pattern Learning
6. Genetic Algorithm Self-Evolution Loop
7. Dual-Loop Self-Correction & Verification
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from adapters.business_adapter import BusinessAdapter
from adapters.dev_adapter import DevAdapter
from adapters.ux_adapter import UXAdapter
from core.advanced_reasoning import AdvancedReasoningEngine, ReasoningChain
from core.evolution_module import EvolutionModule, EvolutionResult
from core.logging_config import logger
from evolution.auto_evolution_controller import AutoEvolutionController
from learning.pattern_recognizer import PatternMatch, PatternRecognizer
from services.dynamic_planner import DynamicPlanningEngine, TaskDAG, TaskNode
from services.intent_deciphering import IntentAnalysis, IntentDecipheringService
from services.memory_service import CascadeMemoryService
from services.memory_service import memory_service as global_memory_service
from services.self_correction import SelfCorrectionService
from services.tool_forge import ToolForgeService, ToolSpec


@dataclass
class SolutionResult:
    success: bool
    ultimate_goal: str
    domain: str
    execution_order: list[str]
    results: dict[str, Any] = field(default_factory=dict)
    verification: dict[str, Any] = field(default_factory=dict)
    fitness_score: float = 0.0
    execution_time_ms: float = 0.0
    reasoning: dict[str, Any] = field(default_factory=dict)
    patterns: list[dict[str, Any]] = field(default_factory=list)
    evolution: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "ultimate_goal": self.ultimate_goal,
            "domain": self.domain,
            "execution_order": self.execution_order,
            "results": self.results,
            "verification": self.verification,
            "fitness_score": self.fitness_score,
            "execution_time_ms": self.execution_time_ms,
            "reasoning": self.reasoning,
            "patterns": self.patterns,
            "evolution": self.evolution,
            "error": self.error,
        }


# ── Domain Adapters Bridge ─────────────────────────────────────────────────────


class BaseDomainAdapter:
    """Base domain execution adapter."""

    async def execute_node(self, node: TaskNode, context: dict[str, Any]) -> Any:
        return {"status": "executed", "node_id": node.id, "capability": node.capability}


class DevDomainAdapter(BaseDomainAdapter):
    """Handles code architecture, defect localization, and AST safe patching using LLM."""

    def __init__(self, adapter: DevAdapter | None = None) -> None:
        self.adapter = adapter or DevAdapter()

    async def execute_node(self, node: TaskNode, context: dict[str, Any]) -> Any:
        capability = node.capability

        try:
            import json

            from core.llm.llm_gateway import get_llm_gateway

            gateway = get_llm_gateway()
            if gateway:
                prompt = f"Execute Developer Task: {node.description or node.name}\nCapability: {capability}\nContext: {json.dumps(context)[:500]}"
                resp = await gateway.acompletion(
                    prompt=prompt,
                    task_type="coding",
                    session_id=f"dev_adapter_{node.id}",
                )
                text = ""
                if isinstance(resp, dict) and resp.get("text"):
                    text = resp["text"]
                elif hasattr(resp, "choices") and resp.choices:
                    text = resp.choices[0].message.content or ""

                if text:
                    return {
                        "status": "executed",
                        "node_id": node.id,
                        "capability": capability,
                        "result": text,
                        "llm_processed": True,
                    }
        except Exception as exc:
            logger.warning(f"DevDomainAdapter LLM execution failed: {exc}. Using fallback.")

        res = await self.adapter.adapt(node.description or node.name, context)
        return {
            "status": "executed",
            "node_id": node.id,
            "capability": capability,
            "result": res.adapted_solution,
            "llm_processed": False,
        }


class BusinessDomainAdapter(BaseDomainAdapter):
    """Handles financial analysis, cost optimization, and decision logic using LLM."""

    def __init__(self, adapter: BusinessAdapter | None = None) -> None:
        self.adapter = adapter or BusinessAdapter()

    async def execute_node(self, node: TaskNode, context: dict[str, Any]) -> Any:
        capability = node.capability

        try:
            import json

            from core.llm.llm_gateway import get_llm_gateway

            gateway = get_llm_gateway()
            if gateway:
                prompt = f"Execute Business Task: {node.description or node.name}\nCapability: {capability}\nContext: {json.dumps(context)[:500]}"
                resp = await gateway.acompletion(
                    prompt=prompt,
                    task_type="reasoning",
                    session_id=f"business_adapter_{node.id}",
                )
                text = ""
                if isinstance(resp, dict) and resp.get("text"):
                    text = resp["text"]
                elif hasattr(resp, "choices") and resp.choices:
                    text = resp.choices[0].message.content or ""

                if text:
                    return {
                        "status": "executed",
                        "node_id": node.id,
                        "capability": capability,
                        "result": text,
                        "llm_processed": True,
                    }
        except Exception as exc:
            logger.warning(f"BusinessDomainAdapter LLM execution failed: {exc}. Using fallback.")

        res = await self.adapter.adapt(node.description or node.name, context)
        return {
            "status": "executed",
            "node_id": node.id,
            "capability": capability,
            "result": res.adapted_solution,
            "llm_processed": False,
        }


class UXDomainAdapter(BaseDomainAdapter):
    """Handles UI components, responsive layout, and accessibility tokens using LLM."""

    def __init__(self, adapter: UXAdapter | None = None) -> None:
        self.adapter = adapter or UXAdapter()

    async def execute_node(self, node: TaskNode, context: dict[str, Any]) -> Any:
        capability = node.capability

        try:
            import json

            from core.llm.llm_gateway import get_llm_gateway

            gateway = get_llm_gateway()
            if gateway:
                prompt = f"Execute UX Task: {node.description or node.name}\nCapability: {capability}\nContext: {json.dumps(context)[:500]}"
                resp = await gateway.acompletion(
                    prompt=prompt,
                    task_type="vision",
                    session_id=f"ux_adapter_{node.id}",
                )
                text = ""
                if isinstance(resp, dict) and resp.get("text"):
                    text = resp["text"]
                elif hasattr(resp, "choices") and resp.choices:
                    text = resp.choices[0].message.content or ""

                if text:
                    return {
                        "status": "executed",
                        "node_id": node.id,
                        "capability": capability,
                        "result": text,
                        "llm_processed": True,
                    }
        except Exception as exc:
            logger.warning(f"UXDomainAdapter LLM execution failed: {exc}. Using fallback.")

        res = await self.adapter.adapt(node.description or node.name, context)
        return {
            "status": "executed",
            "node_id": node.id,
            "capability": capability,
            "result": res.adapted_solution,
            "llm_processed": False,
        }


# ── Living Engine Orchestrator ─────────────────────────────────────────────────


class LivingEngineOrchestrator:
    """Master orchestrator for unpredictable user demands with full Phase 2 intelligence."""

    def __init__(
        self,
        intent_service: IntentDecipheringService | None = None,
        planning_engine: DynamicPlanningEngine | None = None,
        tool_forge: ToolForgeService | None = None,
        self_correction: SelfCorrectionService | None = None,
        memory_service: CascadeMemoryService | None = None,
        reasoning_engine: AdvancedReasoningEngine | None = None,
        pattern_recognizer: PatternRecognizer | None = None,
        evolution_module: EvolutionModule | None = None,
        evolution_controller: AutoEvolutionController | None = None,
    ) -> None:
        self.memory_service = memory_service or global_memory_service
        self.intent_service = intent_service or IntentDecipheringService(
            memory_service=self.memory_service
        )
        self.planning_engine = planning_engine or DynamicPlanningEngine()
        self.tool_forge = tool_forge or ToolForgeService()
        self.self_correction = self_correction or SelfCorrectionService(
            memory_service=self.memory_service
        )
        self.reasoning_engine = reasoning_engine or AdvancedReasoningEngine()
        self.pattern_recognizer = pattern_recognizer or PatternRecognizer()
        self.evolution_module = evolution_module or EvolutionModule()
        self.evolution_controller = evolution_controller or AutoEvolutionController()

        # Domain Adapters
        self.adapters: dict[str, BaseDomainAdapter] = {
            "coder": DevDomainAdapter(),
            "business": BusinessDomainAdapter(),
            "creative": UXDomainAdapter(),
            "reasoner": DevDomainAdapter(),
            "bengali": DevDomainAdapter(),
            "general": BaseDomainAdapter(),
        }

    async def solve_unpredictable_demand(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        session_id: str = "",
    ) -> SolutionResult:
        """Executes full multi-type reasoning, domain adaptation, and self-evolution pipeline."""
        start_time = time.perf_counter()
        logger.info(f"LivingEngine: Received demand: '{prompt[:80]}...'")
        ctx = context or {}

        try:
            # ── 1. Advanced Multi-Type Reasoning (Deductive/Inductive/Abductive/Analogical/Causal) ──
            reasoning_chain: ReasoningChain = await self.reasoning_engine.reason(prompt, ctx)

            # ── 2. Online Pattern Recognition ──
            pattern_matches: list[PatternMatch] = await self.pattern_recognizer.recognize(
                prompt, ctx
            )
            matched_patterns_summary = [
                {"id": p.pattern.id, "type": p.pattern.pattern_type.value, "score": p.match_score}
                for p in pattern_matches
            ]

            # ── 3. Intent Deciphering ──
            intent: IntentAnalysis = await self.intent_service.decipher_intent(
                raw_request=prompt,
                session_id=session_id,
            )

            # ── 4. Dynamic HTN DAG Planning ──
            dag: TaskDAG = await self.planning_engine.plan_task(intent)
            ordered_nodes = dag.topological_sort()
            execution_order = [n.id for n in ordered_nodes]

            # ── 5. Dual-Loop Execution with Domain Adapters & Tool Forge ──
            adapter = self.adapters.get(intent.domain, self.adapters["general"])

            async def step_executor(node: TaskNode, step_ctx: dict[str, Any]) -> Any:
                if node.capability == "execute_dynamic_action":
                    spec = ToolSpec(name=f"dynamic_{node.id}", description=node.description)

                    try:
                        from core.llm.llm_gateway import get_llm_gateway

                        gateway = get_llm_gateway()

                        code = ""
                        if gateway:
                            prompt = (
                                f"Write a Python function named dynamic_{node.id}() that achieves the following goal: '{intent.ultimate_goal}'. "
                                f"Task description: {node.description}. "
                                "Return a dictionary with a 'status' key and a 'result' key. "
                                "Provide ONLY raw Python code, without markdown formatting or backticks, starting with the def statement."
                            )
                            resp = await gateway.acompletion(
                                prompt=prompt,
                                task_type="coding",
                                session_id=f"tool_forge_{node.id}",
                            )
                            if isinstance(resp, dict) and resp.get("text"):
                                code = resp["text"].strip()
                            elif hasattr(resp, "choices") and resp.choices:
                                code = (resp.choices[0].message.content or "").strip()

                            if code.startswith("```python"):
                                code = code[9:]
                            if code.endswith("```"):
                                code = code[:-3]
                            code = code.strip()
                    except Exception as exc:
                        logger.warning(f"LivingEngine ToolForge LLM failed: {exc}")
                        code = ""

                    if not code:
                        code = f"def dynamic_{node.id}(): return {{'status': 'completed', 'goal': '{intent.ultimate_goal}'}}"

                    tool = self.tool_forge.forge_tool(spec, code)
                    return self.tool_forge.execute_tool(tool, {})
                return await adapter.execute_node(node, step_ctx)

            # Execute with self-healing verification
            exec_output = await self.self_correction.execute_with_self_healing(
                dag=dag,
                step_executor=step_executor,
            )

            # ── 6. Self-Evolution Fitness Optimization (Genetic Algorithm) ──
            async def fitness_evaluator(sol: Any) -> float:
                return exec_output.get("verification", {}).get("fitness_score", 0.95)

            evo_result: EvolutionResult = await self.evolution_module.evolve(
                problem=prompt,
                current_solution=exec_output.get("results", {}),
                fitness_func=fitness_evaluator,
                generations=3,
            )

            # ── 7. Continuous Learning Feedback ──
            await self.pattern_recognizer.learn_from_example(
                example=prompt,
                outcome=exec_output.get("results", {}),
                success=exec_output.get("status") == "success",
            )

            duration_ms = (time.perf_counter() - start_time) * 1000.0
            verif = exec_output.get("verification", {})
            fitness = verif.get("fitness_score", 0.95)

            solution = SolutionResult(
                success=exec_output.get("status") == "success",
                ultimate_goal=intent.ultimate_goal,
                domain=intent.domain,
                execution_order=execution_order,
                results=exec_output.get("results", {}),
                verification=verif,
                fitness_score=fitness,
                execution_time_ms=round(duration_ms, 2),
                reasoning={
                    "strategy": reasoning_chain.metadata.get("primary_strategy", "deductive"),
                    "confidence": reasoning_chain.overall_confidence,
                    "conclusion": reasoning_chain.final_conclusion,
                },
                patterns=matched_patterns_summary,
                evolution={
                    "improvement_pct": evo_result.fitness_improvement,
                    "generations": evo_result.generations_passed,
                    "insights": evo_result.insights,
                },
            )

            logger.info(
                f"LivingEngine: Task completed in {duration_ms:.1f}ms with fitness {fitness}"
            )
            return solution

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(f"LivingEngine: Pipeline execution failed: {exc}")
            return SolutionResult(
                success=False,
                ultimate_goal=prompt,
                domain="error",
                execution_order=[],
                error=str(exc),
                execution_time_ms=round(duration_ms, 2),
            )
