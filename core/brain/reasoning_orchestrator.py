from __future__ import annotations

import json
import re
from typing import Any

from core.logging_config import logger
from memory.episodic_memory import EpisodicMemory
from memory.long_term_memory import LongTermMemory
from tools.code.cot_reasoner import ChainOfThoughtReasoner


class ReasoningOrchestrator:
    def __init__(
        self,
        long_term_memory: LongTermMemory | None = None,
        cot_reasoner: ChainOfThoughtReasoner | None = None,
        episodic_memory: EpisodicMemory | None = None,
        model_router: Any | None = None,
    ) -> None:
        self.long_term_memory = long_term_memory or LongTermMemory()
        self.cot_reasoner = cot_reasoner or ChainOfThoughtReasoner(max_iterations=2)
        self.episodic_memory = episodic_memory or EpisodicMemory()
        self._model_router = model_router

    @property
    def model_router(self) -> Any:
        if self._model_router is None:
            try:
                from brain.model_router import ModelRouter

                self._model_router = ModelRouter()
            except Exception as exc:
                logger.warning(f"Could not initialize ModelRouter: {exc}")
                self._model_router = None
        return self._model_router

    def plan(self, task_description: str, context: str | None = None) -> dict[str, Any]:
        lowered = (task_description or "").lower()
        words = lowered.split()
        is_simple = len(words) <= 2 and any(
            w in {"hello", "hi", "hey", "status", "health"} for w in words
        )
        is_reasoning = any(
            word in lowered
            for word in [
                "prove",
                "proof",
                "math",
                "logic",
                "analyze",
                "plan",
                "reason",
                "optimize",
            ]
        )
        is_advanced_reasoning = any(
            word in lowered
            for word in [
                "tree",
                "mcts",
                "monte carlo",
                "multi-step",
                "strategy",
                "tradeoff",
            ]
        )
        if is_simple:
            return {
                "mode": "direct",
                "complexity": "simple",
                "reason": "Greeting or status-like request",
            }
        if is_advanced_reasoning:
            return {
                "mode": "tot_mcts",
                "complexity": "complex",
                "reason": "Detected advanced reasoning keywords",
            }
        if is_reasoning:
            return {
                "mode": "cot",
                "complexity": "complex",
                "reason": "Detected reasoning keywords",
            }
        return {
            "mode": "standard",
            "complexity": "medium",
            "reason": "Default task routing",
        }

    def build_enriched_prompt(self, task_description: str, context: str | None = None) -> str:
        plan = self.plan(task_description, context)
        memory_context = self.long_term_memory.build_context()
        episodic_context = self.episodic_memory.summarize_recent(limit=3)
        parts = [task_description]
        if memory_context:
            parts.append(f"Memory context:\n{memory_context}")
        if episodic_context:
            parts.append(f"Recent interaction memory:\n{episodic_context}")
        if plan["mode"] in {"cot", "tot_mcts"}:
            return self.cot_reasoner.build_prompt("\n\n".join(parts), context)
        return "\n\n".join(parts)

    def route(self, task_description: str, context: str | None = None) -> dict[str, Any]:
        plan = self.plan(task_description, context)
        logger.info(f"Reasoning plan: {plan}")
        reasoning_trace = None
        if plan["mode"] in {"cot", "tot_mcts"}:
            reasoning_trace = self.cot_reasoner.tree_search(
                problem=task_description,
                branches=3,
                depth=2,
                context=context,
            )
            if plan["mode"] == "tot_mcts":
                reasoning_trace["mcts"] = self.cot_reasoner.monte_carlo_search(
                    problem=task_description,
                    branches=3,
                    depth=3,
                    simulations=8,
                    context=context,
                )
        return {
            "use_cot": plan["mode"] in {"cot", "tot_mcts"},
            "plan": plan,
            "prompt": self.build_enriched_prompt(task_description, context),
            "reasoning_trace": reasoning_trace,
        }

    _instance: ReasoningOrchestrator | None = None

    @classmethod
    def get_instance(cls) -> ReasoningOrchestrator:
        """Singleton accessor for ReasoningOrchestrator."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def decide(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        tools: list[str] | None = None,
    ) -> dict[str, Any]:
        """Decide next action for autonomous agents using a true ReAct reasoning loop."""
        available_tools: dict[str, str] = {}
        if tools:
            for t in tools:
                available_tools[t] = f"Tool identifier: {t}"
        else:
            try:
                from tools.agent_tools import SUPREME_TOOLS

                for fn in SUPREME_TOOLS:
                    doc = (fn.__doc__ or "").strip().split("\n")[0]
                    available_tools[fn.__name__] = doc or fn.__name__
            except Exception as exc:
                logger.debug(f"Could not load SUPREME_TOOLS: {exc}")

        tool_specs = "\n".join(f"- {name}: {desc}" for name, desc in available_tools.items())
        context_str = json.dumps(context, ensure_ascii=False) if context else "None"

        prompt = (
            f"You are the SupremeAI reasoning orchestrator.\n"
            f"Task: {task}\n"
            f"Context: {context_str}\n"
            f"Available Tools:\n{tool_specs}\n- done: Task is completed or no further tool is required.\n\n"
            f"Respond with a single raw JSON object matching this schema:\n"
            f'{{"thought": "reasoning about current state", "tool": "tool_name_or_done", "args": {{}}, "reasoning": "summary"}}\n'
        )

        if self.model_router is not None:
            try:
                res = await self.model_router.async_route_and_generate(
                    prompt=prompt,
                    task_type="reasoning",
                    max_cost=0.01,
                )
                if res and res.get("success") and res.get("text"):
                    raw_text = res["text"].strip()
                    if "```" in raw_text:
                        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
                        raw_text = re.sub(r"\s*```$", "", raw_text, flags=re.MULTILINE).strip()
                    data = json.loads(raw_text)
                    if isinstance(data, dict) and "tool" in data:
                        chosen_tool = data.get("tool", "done")
                        return {
                            "tool": chosen_tool,
                            "args": data.get("args", {}),
                            "thought": data.get("thought", ""),
                            "reasoning": data.get(
                                "reasoning", f"Selected '{chosen_tool}' via ReAct loop"
                            ),
                            "source": "llm_react",
                        }
            except Exception as exc:
                logger.debug(f"ReAct LLM decision skipped or failed: {exc}")

        # Deterministic fallback based on task semantics (Strict False-Assurance Ban)
        lowered = (task or "").lower()
        if any(w in lowered for w in ["health", "status", "cpu", "ram", "memory", "ping"]):
            selected_tool = "check_system_health"
        elif any(w in lowered for w in ["search", "query", "find", "database", "select"]):
            selected_tool = "search_database"
        elif any(w in lowered for w in ["code", "execute", "python", "calc", "run"]):
            selected_tool = "execute_python_code"
        else:
            selected_tool = "done"

        return {
            "tool": selected_tool,
            "args": {"target": task},
            "thought": f"Assessed task requirements for '{task}'",
            "reasoning": f"Deterministic routing: selected '{selected_tool}' based on task semantics",
            "source": "deterministic_fallback",
        }

    async def decide_and_execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        tools: list[str] | None = None,
    ) -> dict[str, Any]:
        """M09 P-A: decide() + governed execution — ReAct-লুপের অনুপস্থিত অর্ধেক।

        বাংলা: সিদ্ধান্ত এখানেই শেষ নয় — নির্বাচিত টুল ``core.tool_loop``
        (ফ্ল্যাগ + রেজিস্ট্রি + পলিসি গেট) পার হয়ে সত্যিই চলে এবং
        ``observation``-এ প্রকৃত ফল ফেরত আসে। ফ্ল্যাগ-অফ বা পলিসি-ব্লকে
        সৎ অবস্থা থাকে, কোনো ভান নয়।
        """
        decision = await self.decide(task, context=context, tools=tools)

        from core.tool_loop import execute_tool_decision

        outcome = await execute_tool_decision(decision)
        return {
            "task": task,
            "decision": decision,
            "outcome": outcome,
        }

    async def synthesize(
        self,
        task: str,
        findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Synthesize multi-agent swarm exploration findings into an actionable consensus."""
        if not findings:
            return {
                "task": task,
                "total_findings": 0,
                "summary": "No findings provided to synthesize.",
                "consolidated": [],
                "source": "empty",
            }

        findings_json = json.dumps(findings, indent=2, ensure_ascii=False)
        prompt = (
            f"You are the SupremeAI consensus synthesizer.\n"
            f"Task: {task}\n"
            f"Agent Findings ({len(findings)} reports):\n{findings_json}\n\n"
            f"Synthesize these findings into a concise, actionable summary highlighting key consensus, anomalies, and recommended next steps."
        )

        summary_text = ""
        is_llm = False
        if self.model_router is not None:
            try:
                res = await self.model_router.async_route_and_generate(
                    prompt=prompt,
                    task_type="reasoning",
                    max_cost=0.01,
                )
                if res and res.get("success") and res.get("text"):
                    summary_text = res["text"].strip()
                    is_llm = True
            except Exception as exc:
                logger.debug(f"LLM synthesis unavailable: {exc}")

        if not summary_text:
            outcomes = [f.get("outcome") or f.get("status") or "recorded" for f in findings]
            summary_text = (
                f"Consolidated {len(findings)} agent findings for '{task}'. "
                f"Recorded outcomes: {', '.join(sorted(set(str(o) for o in outcomes)))}."
            )

        return {
            "task": task,
            "total_findings": len(findings),
            "summary": summary_text,
            "consolidated": findings,
            "source": "llm_consensus" if is_llm else "deterministic_summary",
        }

    async def execute_decomposed_tasks(self, task_graph: dict[str, Any]) -> dict[str, Any]:
        """Execute a DAG of decomposed tasks sequentially based on dependencies."""
        from brain.task_execution_engine import TaskExecutionEngine

        engine = TaskExecutionEngine()
        return await engine.execute_decomposed_tasks(task_graph)
