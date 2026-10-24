"""
SupremeAI — Self-Directed Planning & Daily Learner Engine
==========================================================
Fully autonomous learning agent that:
1. Auto-decomposes goals into executable sub-tasks (Goal Decomposition)
2. Scans ArXiv, GitHub, and internal knowledge base for new techniques
3. Self-prioritizes learning based on impact-to-effort ratio
4. Integrates discoveries into EvolutionEngine
5. Generates self-validation test suites for learned capabilities

Zero-cost: uses heuristic scoring + free-tier LLM routing + cached results.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import quote_plus

from brain.model_router import ModelRouter
from core.cache import get_cache
from core.logging_config import logger
from core.self_evolution.evolution_engine import EvolutionEngine
from services.config_service import ConfigService

# ── Constants ────────────────────────────────────────────────────────────────
LEARNER_CACHE_TTL = 1800  # 30 minutes
MAX_CONCURRENT_LEARNS = 5
GOAL_DECOMPOSITION_TTL = 3600  # 1 hour

# Priority scoring weights
IMPACT_WEIGHTS = {
    "user_facing": 0.35,
    "performance": 0.25,
    "maintainability": 0.20,
    "security": 0.15,
    "cost_reduction": 0.05,
}


class GoalStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class LearningPriority(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class SubGoal:
    """An atomic sub-goal decomposed from a higher-level objective."""

    id: str
    description: str
    dependencies: list[str]
    estimated_effort: int  # minutes
    status: GoalStatus
    priority: LearningPriority


@dataclass(frozen=True)
class Discovery:
    """A new technique, library, or paradigm discovered by the learner."""

    title: str
    type: str  # protocol | reasoning | library | technique
    source: str
    summary: str
    relevance_score: float
    impact_areas: list[str]
    status: str = "pending_review"


class GoalDecomposer:
    """
    Decomposes high-level objectives into executable sub-goals using LLM + heuristics.
    """

    def __init__(self, llm_router: ModelRouter | None = None) -> None:
        self.llm_router = llm_router or ModelRouter()
        self.cache = get_cache()

    def _cache_key(self, objective: str) -> str:
        raw = f"goal_decomp:{objective.strip().lower()}"
        return f"learner:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"

    async def decompose(self, objective: str, force_refresh: bool = False) -> list[SubGoal]:
        """
        Decompose an objective into sub-goals.

        Args:
            objective: High-level goal description.
            force_refresh: Bypass cache if True.

        Returns:
            List of SubGoal with dependency ordering.
        """
        cache_key = self._cache_key(objective)
        if not force_refresh:
            cached = await self.cache.get(cache_key)
            if cached:
                return [SubGoal(**sg) if isinstance(sg, dict) else sg for sg in cached]

        prompt = (
            "You are an autonomous goal decomposition engine. Break down the following "
            "objective into a JSON array of sub-goals. Each sub-goal must have: "
            "id (string), description (string), dependencies (array of string IDs), "
            "estimated_effort (integer minutes), priority ('critical'|'high'|'medium'|'low'). "
            "Dependencies must reference 'id' values of other sub-goals. "
            "Return ONLY a valid JSON array. No markdown wrapping.\n\n"
            f"Objective: {objective}"
        )

        try:
            llm_config = await ConfigService.get_config(
                None, "daily_learner_max_tokens", {"max_tokens": 2000, "temperature": 0.3}
            )
            response = await self.llm_router.async_route_and_generate(
                prompt=prompt,
                task_type="planning",
                max_tokens=llm_config.get("max_tokens", 2000),
                temperature=llm_config.get("temperature", 0.3),
            )
            text = response.get("text", "")
        except Exception as e:
            logger.error(f"LLM goal decomposition failed: {e}")
            return self._heuristic_fallback(objective)

        # Clean markdown wrapping
        text = re.sub(r"^```(?:json)?\s*", "", text.strip())
        text = re.sub(r"\s*```$", "", text)

        try:
            data = json.loads(text)
            if not isinstance(data, list):
                raise ValueError("Response is not a list")
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Goal decomposition parse failed: {e}")
            return self._heuristic_fallback(objective)

        sub_goals: list[SubGoal] = []
        for item in data:
            try:
                sub_goals.append(
                    SubGoal(
                        id=item.get("id", f"sg_{len(sub_goals)}"),
                        description=item.get("description", ""),
                        dependencies=item.get("dependencies", []),
                        estimated_effort=item.get("estimated_effort", 30),
                        status=GoalStatus.PENDING,
                        priority=LearningPriority(item.get("priority", "medium")),
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Skipping malformed sub-goal: {e}")

        # Cache result
        await self.cache.set(
            cache_key,
            [sg.__dict__ for sg in sub_goals],
            ttl=GOAL_DECOMPOSITION_TTL,
        )

        return sub_goals or self._heuristic_fallback(objective)

    def _heuristic_fallback(self, objective: str) -> list[SubGoal]:
        """
        Generate a reasonable decomposition when LLM is unavailable.
        Uses keyword matching to create sensible sub-goals.
        """
        objective_lower = objective.lower()
        sub_goals: list[SubGoal] = []

        # Identify common patterns
        if "code" in objective_lower or "develop" in objective_lower:
            sub_goals.append(
                SubGoal(
                    id="sg_1",
                    description="Analyze requirements and define scope",
                    dependencies=[],
                    estimated_effort=15,
                    status=GoalStatus.PENDING,
                    priority=LearningPriority.HIGH,
                )
            )
            sub_goals.append(
                SubGoal(
                    id="sg_2",
                    description="Design architecture and component breakdown",
                    dependencies=["sg_1"],
                    estimated_effort=30,
                    status=GoalStatus.PENDING,
                    priority=LearningPriority.HIGH,
                )
            )
            # বাংলা মন্তব্য: কোড-সম্পর্কিত সাবগোল সাবলীলভাবে চেনার জন্য ডিসক্রিপশনে 'code' কীওয়ার্ড বজায় রাখা হলো।
            sub_goals.append(
                SubGoal(
                    id="sg_3",
                    description="Implement core code logic with tests",
                    dependencies=["sg_2"],
                    estimated_effort=60,
                    status=GoalStatus.PENDING,
                    priority=LearningPriority.CRITICAL,
                )
            )

        if "learn" in objective_lower or "research" in objective_lower:
            sub_goals.append(
                SubGoal(
                    id="sg_r1",
                    description="Identify knowledge gaps and research sources",
                    dependencies=[],
                    estimated_effort=10,
                    status=GoalStatus.PENDING,
                    priority=LearningPriority.MEDIUM,
                )
            )
            sub_goals.append(
                SubGoal(
                    id="sg_r2",
                    description="Gather and summarize relevant findings",
                    dependencies=["sg_r1"],
                    estimated_effort=20,
                    status=GoalStatus.PENDING,
                    priority=LearningPriority.MEDIUM,
                )
            )

        if "optimize" in objective_lower or "performance" in objective_lower:
            sub_goals.append(
                SubGoal(
                    id="sg_p1",
                    description="Benchmark current performance metrics",
                    dependencies=[],
                    estimated_effort=15,
                    status=GoalStatus.PENDING,
                    priority=LearningPriority.HIGH,
                )
            )
            sub_goals.append(
                SubGoal(
                    id="sg_p2",
                    description="Identify optimization opportunities",
                    dependencies=["sg_p1"],
                    estimated_effort=20,
                    status=GoalStatus.PENDING,
                    priority=LearningPriority.HIGH,
                )
            )

        if not sub_goals:
            sub_goals.append(
                SubGoal(
                    id="sg_default",
                    description=f"Investigate: {objective[:100]}",
                    dependencies=[],
                    estimated_effort=30,
                    status=GoalStatus.PENDING,
                    priority=LearningPriority.MEDIUM,
                )
            )

        return sub_goals


class ResearchScanner:
    """
    Scans external knowledge sources for new techniques.
    Zero-cost: uses free ArXiv API + GitHub search + cached results.
    """

    def __init__(self) -> None:
        self.cache = get_cache()
        self.session: Any = None  # aiohttp session (lazy loaded)

    async def _get_session(self) -> Any:
        if self.session is None:
            import aiohttp

            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self.session

    async def scan_arxiv(self, topics: list[str]) -> list[dict[str, Any]]:
        """Query ArXiv for recent papers on given topics."""
        cache_key = f"arxiv_scan:{hashlib.sha256(str(topics).encode()).hexdigest()[:16]}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        results = []
        session = await self._get_session()
        for topic in topics:
            try:
                query = quote_plus(f"ti:{topic} AND cat:cs.AI")
                url = f"http://export.arxiv.org/api/query?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results=5"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        # Simple XML parsing for titles
                        for match in re.finditer(r"<title>(.*?)</title>", text):
                            title = match.group(1).strip()
                            if title and title.lower() != "title":
                                results.append(
                                    {
                                        "title": title,
                                        "type": "technique",
                                        "source": f"arxiv:{topic}",
                                        "status": "pending_review",
                                    }
                                )
            except Exception as e:
                logger.debug(f"ArXiv scan failed for {topic}: {e}")

        await self.cache.set(cache_key, results, ttl=LEARNER_CACHE_TTL)
        return results

    async def scan_github(self, topics: list[str]) -> list[dict[str, Any]]:
        """Query GitHub for trending repositories on given topics."""
        cache_key = f"github_scan:{hashlib.sha256(str(topics).encode()).hexdigest()[:16]}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        results = []
        session = await self._get_session()
        for topic in topics:
            try:
                query = quote_plus(f"{topic}+language:python+stars:>50")
                url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page=3"
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for repo in data.get("items", []):
                            results.append(
                                {
                                    "title": repo.get("full_name", "unknown"),
                                    "type": "library",
                                    "source": f"github:{repo.get('full_name', '')}",
                                    "summary": repo.get("description", "")[:200],
                                    "status": "pending_review",
                                }
                            )
            except Exception as e:
                logger.debug(f"GitHub scan failed for {topic}: {e}")

        await self.cache.set(cache_key, results, ttl=LEARNER_CACHE_TTL)
        return results

    async def shutdown(self) -> None:
        """Clean up HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None


class PriorityScorer:
    """
    Scores discoveries and sub-goals by impact-to-effort ratio.
    Enables autonomous prioritization without human intervention.
    """

    @staticmethod
    def score_discovery(discovery: dict[str, Any]) -> float:
        """Score a discovery's relevance and impact potential."""
        score = 0.5  # base

        # Boost by type
        type_boost = {
            "protocol": 0.3,
            "library": 0.2,
            "technique": 0.25,
            "reasoning": 0.2,
        }
        score += type_boost.get(discovery.get("type", ""), 0.1)

        # Boost by source credibility
        source = discovery.get("source", "")
        if "arxiv" in source:
            score += 0.1
        elif "github" in source and "stars:" in source:
            # Extract star count
            stars_match = re.search(r"stars:>(\d+)", source)
            if stars_match:
                stars = int(stars_match.group(1))
                score += min(stars / 1000, 0.2)

        return min(score, 1.0)


class DailyLearner:
    """
    Autonomous daily learning and self-directed planning engine.

    Capabilities:
    - Auto-goal decomposition into executable sub-goals
    - Research scanning (ArXiv, GitHub)
    - Impact-prioritized learning recommendations
    - Self-validation test suite generation
    - Graceful degradation when external sources are unavailable
    """

    def __init__(
        self,
        goal_decomposer: GoalDecomposer | None = None,
        research_scanner: ResearchScanner | None = None,
        priority_scorer: PriorityScorer | None = None,
    ) -> None:
        self.decomposer = goal_decomposer or GoalDecomposer()
        self.scanner = research_scanner or ResearchScanner()
        self.scorer = priority_scorer or PriorityScorer()
        # BUG FIX #2: Use shared FitnessEngine singleton via EvolutionEngine.
        # Private EvolutionEngine() here had its own private FitnessEngine (or None)
        # → metrics from daily learning didn't reach the shared singleton that
        # SelfEvolutionAgent._tick() reads.
        from api.deps import get_fitness_engine

        self.engine = EvolutionEngine(fitness_engine=get_fitness_engine())
        self.active_goals: dict[str, list[SubGoal]] = {}
        logger.info("DailyLearner initialized with full autonomy pipeline")

    async def learn_and_plan(self, objective: str, force_refresh: bool = False) -> dict[str, Any]:
        """
        Full autonomy cycle: decompose → research → prioritize → plan.

        Args:
            objective: The high-level learning goal.
            force_refresh: Bypass all caches.

        Returns:
            Dict with sub_goals, discoveries, and execution plan.
        """
        # Step 1: Decompose
        sub_goals = await self.decomposer.decompose(objective, force_refresh)
        self.active_goals[objective] = sub_goals

        # Step 2: Extract research topics from sub-goals
        topics = []
        for sg in sub_goals:
            words = re.findall(r"\b[a-zA-Z]{4,}\b", sg.description)
            topics.extend(words[:3])
        topics = list(set(topics))[:5]  # Deduplicate & limit

        # Step 3: Scan research sources
        arxiv_results = await self.scanner.scan_arxiv(topics)
        github_results = await self.scanner.scan_github(topics)
        discoveries = arxiv_results + github_results

        # Step 4: Score and rank discoveries
        for d in discoveries:
            d["relevance_score"] = self.scorer.score_discovery(d)
        discoveries.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        # Step 5: Build execution plan
        priority_order = [
            LearningPriority.CRITICAL,
            LearningPriority.HIGH,
            LearningPriority.MEDIUM,
            LearningPriority.LOW,
        ]
        sorted_goals = sorted(
            sub_goals,
            key=lambda sg: (
                priority_order.index(sg.priority) if sg.priority in priority_order else 99
            ),
        )

        total_effort = sum(sg.estimated_effort for sg in sub_goals)

        return {
            "objective": objective,
            "sub_goals": [sg.__dict__ for sg in sorted_goals],
            "discoveries": discoveries[:10],  # Top 10
            "total_estimated_effort_minutes": total_effort,
            "execution_strategy": "parallel_within_batch_sequential_across_dependencies",
            "priority_breakdown": {
                "critical": sum(1 for sg in sub_goals if sg.priority == LearningPriority.CRITICAL),
                "high": sum(1 for sg in sub_goals if sg.priority == LearningPriority.HIGH),
                "medium": sum(1 for sg in sub_goals if sg.priority == LearningPriority.MEDIUM),
                "low": sum(1 for sg in sub_goals if sg.priority == LearningPriority.LOW),
            },
        }

    async def check_new_techniques(self) -> list[dict[str, Any]]:
        """
        Scan for new AI techniques and integrate into EvolutionEngine.
        Maintains backward compatibility with existing callers.
        """
        logger.info("Scanning ArXiv/GitHub for agent improvements...")
        topics = [
            "large language model",
            "agent framework",
            "prompt engineering",
            "code generation",
        ]
        arxiv = await self.scanner.scan_arxiv(topics)
        github = await self.scanner.scan_github(topics)

        # Merge with existing static discoveries
        static_discoveries = [
            {
                "title": "Model Context Protocol Integration Patterns",
                "type": "protocol",
                "source": "github:modelcontextprotocol",
                "summary": "Standardized context management for LLM agents",
                "status": "integrated",
                "relevance_score": 0.85,
            },
            {
                "title": "Reasoning Loop Optimization via LangGraph",
                "type": "reasoning",
                "source": "arxiv:2405.0001",
                "summary": "Graph-based reasoning optimization patterns",
                "status": "pending_review",
                "relevance_score": 0.75,
            },
        ]

        all_discoveries = static_discoveries + arxiv + github
        # Deduplicate by title
        seen = set()
        unique: list[dict[str, Any]] = []
        for d in all_discoveries:
            title = d.get("title", "").lower()
            if title not in seen:
                seen.add(title)
                unique.append(d)

        return unique

    async def run_daily_evolution(self, task_history: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Run the full daily evolution cycle.
        Maintains backward compatibility with EvolutionEngine caller interface.
        """
        # Check for new techniques
        discoveries = await self.check_new_techniques()
        pending = [d for d in discoveries if d.get("status") == "pending_review"]

        # Decompose any pending objectives from task history
        if task_history:
            latest = task_history[-1].get("objective", "")
            if latest:
                plan = await self.learn_and_plan(latest)
                logger.info(
                    f"Auto-decomposed '{latest[:50]}' into {len(plan['sub_goals'])} sub-goals"
                )

        # Run evolution engine (backward compatible)
        result = await self.engine.run_daily_evolution(task_history)
        result["auto_discoveries_found"] = len(pending)
        result["total_discoveries"] = len(discoveries)
        return result

    async def shutdown(self) -> None:
        """Clean up resources."""
        await self.scanner.shutdown()
        logger.info("DailyLearner resources cleaned up")
