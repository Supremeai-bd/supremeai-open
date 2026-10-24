# SupremeAI 2.0 - Tree-of-Thought Meta-Reasoning Engine
# বাংলা মন্তব্য: এটি জটিল সমস্যায় ৩টি পৃথক যুক্তির শাখা (Reasoning Paths) তৈরি করে মূল্যায়ন করে এবং সেরা লজিক পথটি বেছে নেয়।

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from core.logging_config import logger


@dataclass
class ThoughtNode:
    thought_id: str
    content: str
    score: float
    depth: int
    parent_id: str | None = None


class TreeOfThoughtReasoner:
    """
    Tree-of-Thought (ToT) Meta-Reasoning Engine.
    Explores multiple reasoning branches (BFS/DFS) before selecting the optimal execution logic.
    """

    def __init__(self, max_depth: int = 3, num_branches: int = 3):
        self.max_depth = max_depth
        self.num_branches = num_branches

    async def reason(self, problem_statement: str) -> dict[str, Any]:
        """
        Generate multiple reasoning paths and evaluate the best reasoning chain.
        """
        logger.info(
            f"Tree-of-Thought reasoning initiated for problem: '{problem_statement[:60]}...'"
        )

        # Phase 1: Generate initial branches (LLM driven)
        branches = await self._generate_initial_thoughts(problem_statement)

        # Phase 2: Score thoughts (LLM driven)
        scored_nodes = await self._score_thoughts(problem_statement, branches)

        # Phase 3: Select top reasoning path
        if not scored_nodes:
            # Fallback if LLM fails
            scored_nodes = [
                ThoughtNode(
                    thought_id="fallback_1",
                    content="Proceed with standard execution.",
                    score=0.5,
                    depth=1,
                )
            ]

        best_node = max(scored_nodes, key=lambda x: x.score)

        result = {
            "problem": problem_statement,
            "best_thought": best_node.content,
            "confidence_score": best_node.score,
            "total_branches_explored": len(scored_nodes),
            "reasoning_path": [node.content for node in scored_nodes],
        }

        logger.info(f"Tree-of-Thought best path selected with score: {best_node.score:.2f}")
        return result

    async def _generate_initial_thoughts(self, problem: str) -> list[ThoughtNode]:
        """Generate 3 distinct reasoning perspectives for a problem using LLM."""
        try:
            from core.llm.llm_gateway import get_llm_gateway

            gateway = get_llm_gateway()

            if gateway:
                prompt = (
                    f"Generate 3 distinct, radically different strategies to solve this problem: '{problem}'.\n"
                    "Provide your response as a numbered list where each item is a single, concise strategy description."
                )
                resp = await gateway.acompletion(
                    prompt=prompt,
                    task_type="reasoning",
                    session_id="tot_generation",
                )
                text = ""
                if isinstance(resp, dict) and resp.get("text"):
                    text = resp["text"]
                elif hasattr(resp, "choices") and resp.choices:
                    text = resp.choices[0].message.content or ""

                if text:
                    lines = [
                        line.strip()
                        for line in text.split("\n")
                        if line.strip() and line[0].isdigit()
                    ]
                    if len(lines) >= 3:
                        return [
                            ThoughtNode(
                                thought_id=f"tot_{i + 1}", content=lines[i], score=0.0, depth=1
                            )
                            for i in range(3)
                        ]
        except Exception as exc:
            logger.warning(
                f"ToT _generate_initial_thoughts failed: {exc}. Falling back to hardcoded."
            )

        # Fallback if LLM fails
        return [
            ThoughtNode(
                thought_id="tot_1",
                content=f"Direct Algorithmic Strategy: Analyze requirements and construct modular solution for '{problem}'.",
                score=0.0,
                depth=1,
            ),
            ThoughtNode(
                thought_id="tot_2",
                content=f"Defensive & Resilience Strategy: Identify edge cases, error boundaries, and fallbacks for '{problem}'.",
                score=0.0,
                depth=1,
            ),
            ThoughtNode(
                thought_id="tot_3",
                content=f"Performance & Resource-Optimization Strategy: Focus on zero-cost HA and lightweight execution for '{problem}'.",
                score=0.0,
                depth=1,
            ),
        ]

    async def _score_thoughts(self, problem: str, nodes: list[ThoughtNode]) -> list[ThoughtNode]:
        """Evaluate and rank thought nodes using LLM."""
        try:
            from core.llm.llm_gateway import get_llm_gateway

            gateway = get_llm_gateway()

            if gateway:
                for node in nodes:
                    prompt = (
                        f"Rate the following strategy from 0.0 to 1.0 on how well it solves this problem: '{problem}'.\n"
                        f"Strategy: {node.content}\n"
                        "Respond ONLY with a decimal number between 0.0 and 1.0."
                    )
                    resp = await gateway.acompletion(
                        prompt=prompt,
                        task_type="reasoning",
                        session_id="tot_scoring",
                    )
                    text = ""
                    if isinstance(resp, dict) and resp.get("text"):
                        text = resp["text"]
                    elif hasattr(resp, "choices") and resp.choices:
                        text = resp.choices[0].message.content or ""

                    if text:
                        try:
                            score = float(text.strip())
                            node.score = max(0.0, min(1.0, score))
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            import logging

                            logging.getLogger(__name__).exception(f"Silenced error: {e}")
        except Exception as exc:
            logger.warning(f"ToT _score_thoughts failed: {exc}. Using heuristic fallback.")

        # Fallback heuristic
        for node in nodes:
            if node.score == 0.0:
                node.score = 0.5
                if "Resilience" in node.content:
                    node.score += 0.05
        return nodes
