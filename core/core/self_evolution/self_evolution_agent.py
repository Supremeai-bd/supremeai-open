"""Manages the autonomous self-evolution of the AI system by monitoring skill fitness,
triggering refactoring of underperforming skills, and orchestrating the creation of new capabilities.

This module defines the `SelfEvolutionAgent`, which operates on a continuous loop to
evaluate the performance of existing skills. It identifies skills that fall below
defined fitness thresholds, initiating refactoring processes or generating new skills
to address missing functionalities. A critical component is the "Zero-Gap" pipeline,
which ensures the secure and validated integration of AI-generated code proposals
through AST security scanning, CI/CD dry runs, and atomic database transactions.
"""

import asyncio
import contextlib
import re
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

try:
    from core.self_evolution.auto_skill_creator import AutoSkillCreator
except ImportError:
    AutoSkillCreator = None  # type: ignore[misc,assignment]

try:
    from core.self_evolution.fitness_engine import FitnessEngine
except ImportError:
    FitnessEngine = None  # type: ignore[misc,assignment]

from core.immune_system import ImmuneSystemScanner
from models.evolution import CodeProposal


class SelfEvolutionAgent:
    """Autonomous agent that monitors skill fitness, triggers creation of missing
    capabilities, and self-refactors underperforming skills on a cron-like loop."""

    def __init__(
        self,
        fitness_engine: Any | None = None,
        auto_skill_creator: Any | None = None,
        interval_seconds: int = 300,
        fitness_threshold: float = 0.5,
        refactor_penalty_threshold: float = 0.3,
        min_runs_before_action: int = 5,
        max_consecutive_penalties: int = 3,
        max_refactors_per_skill: int = 3,
    ) -> None:
        # Conditional instantiation to avoid AttributeError when imports failed
        if fitness_engine is None:
            if FitnessEngine is None:
                raise RuntimeError(
                    "FitnessEngine failed to import - core.self_evolution.fitness_engine not available"
                )
            fitness_engine = FitnessEngine()
        if auto_skill_creator is None:
            if AutoSkillCreator is None:
                raise RuntimeError(
                    "AutoSkillCreator failed to import - core.self_evolution.auto_skill_creator not available"
                )
            auto_skill_creator = AutoSkillCreator()

        self.fitness_engine = fitness_engine
        self.auto_skill_creator = auto_skill_creator
        self.interval_seconds = interval_seconds
        self.fitness_threshold = fitness_threshold
        self.refactor_penalty_threshold = refactor_penalty_threshold
        self.min_runs_before_action = min_runs_before_action
        self.max_consecutive_penalties = max_consecutive_penalties
        # Issue #1686: একই skill কতবার refactor হয়েছে (lineage-ভিত্তিক) —
        # এর বেশি হলে freeze + human alert (infinite evolution loop guard)।
        self.max_refactors_per_skill = max_refactors_per_skill

        self._running: bool = False
        self._task: asyncio.Task | None = None
        self._consecutive_penalties: dict[str, int] = {}
        self._pending_demands: asyncio.Queue = asyncio.Queue()
        self.scanner = ImmuneSystemScanner()
        self._redis = None  # cached client — issue #1685 (avoid per-tick client leak)
        self._instance_id = uuid.uuid4().hex[:12]
        # Issue #1686 guards: per-lineage refactor counts + frozen skills
        self._refactor_counts: dict[str, int] = {}
        self._frozen_skills: set[str] = set()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(f"SelfEvolutionAgent started (interval={self.interval_seconds}s)")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("SelfEvolutionAgent stopped")

    @with_error_bus("_loop")
    async def _loop(self) -> None:
        # Runs continuously (24/7) by design, but each tick only does the
        # actual evolution work when free-tier memory headroom is good —
        # otherwise it skips this cycle and simply retries next interval.
        from core.memory_manager import get_memory_manager

        while self._running:
            start = time.time()
            try:
                if get_memory_manager().is_safe_for_heavy_task():
                    if await self._acquire_lock():
                        await self._tick()
                else:
                    logger.debug(
                        "SelfEvolutionAgent skipping tick — memory usage too high "
                        "right now, will retry next cycle."
                    )
            except Exception:
                logger.exception("Self-evolution tick failed")
            elapsed = time.time() - start
            try:
                await asyncio.sleep(max(0.0, self.interval_seconds - elapsed))
            except asyncio.CancelledError:
                break

    async def _get_redis(self):
        """Cached Redis client (issue #1685: আগে প্রতি tick-এ নতুন ক্লায়েন্ট
        বানাত — connection leak)। Unconfigured URL-এ সৎ RuntimeError।"""
        if not self._redis:
            import os

            import redis.asyncio as aioredis

            try:
                from core.config import settings

                redis_url = getattr(settings, "redis_url", None) or os.environ.get(
                    "REDIS_URL", "redis://<your-redis-url>"
                )
            except ImportError:
                import os

                redis_url = os.environ.get("REDIS_URL", None)
            if not redis_url or "<your-redis-url>" in str(redis_url):
                raise RuntimeError("Redis URL not configured — self-evolution lock UNAVAILABLE")
            self._redis = aioredis.from_url(redis_url, decode_responses=True)
        return self._redis

    async def _acquire_lock(self) -> bool:
        """Acquire a Redis distributed lock to prevent concurrent executions.

        Issue #1685 (CRITICAL): আগে Redis অনুপলব্ধ হলে `return True  # fail
        open` ছিল — মানে Redis-down = সব instance একসাথে evolve (race on
        code writes → corrupted production deploy)। এখন fail-CLOSED:
        lock যাচাই করা না গেলে কোনো instance-ই evolve করবে না (নিরাপদ
        কারণ evolution skip ক্ষতিকর নয়, duplicate/corrupt deploy ক্ষতিকর)।
        Stale-lock breaker: orphan key-র (TTL -1, অর্থাৎ expiry-বিহীন) ক্ষেত্রে
        তা ভেঙে পুনরায় চেষ্টা করা হয় — deadlock এড়াতে।
        """
        lock_key = "lock:self_evolution_agent"
        try:
            redis = await self._get_redis()
            # Lock expires slightly after the interval to prevent deadlock if instance dies
            acquired = await redis.set(
                lock_key,
                f"{self._instance_id}:{time.time()}",
                nx=True,
                ex=self.interval_seconds + 30,
            )
            if acquired:
                logger.debug("SelfEvolutionAgent acquired distributed lock.")
                return True

            # Stale-lock breaker: key exists WITHOUT any expiry (orphan —
            # cannot happen via our SET NX EX path) → break it and retry once.
            ttl = await redis.ttl(lock_key)
            if ttl == -1:
                logger.warning(
                    "SelfEvolutionAgent found ORPHAN lock (no expiry) — breaking stale lock"
                )
                await redis.delete(lock_key)
                acquired = await redis.set(
                    lock_key,
                    f"{self._instance_id}:{time.time()}",
                    nx=True,
                    ex=self.interval_seconds + 30,
                )
                if acquired:
                    return True
            logger.debug("SelfEvolutionAgent skipping tick (locked by another instance).")
            return False
        except Exception as e:
            # Issue #1685: fail-CLOSED — a verified-distribution lock is the
            # only safe precondition for mutating production code.
            logger.critical(
                "SelfEvolutionAgent lock UNAVAILABLE (Redis unreachable) — "
                "evolution SKIPPED this tick (fail-closed, issue #1685): "
                f"{type(e).__name__}: {e}"
            )
            return False

    async def _tick(self) -> None:
        # #1939: before evaluating skills, learn from recent merge_learning_reports.
        # Gated by settings.enable_evolution_learning (default False) — when enabled,
        # held merges penalize the lane's skill fitness, clean merges reward it.
        try:
            from core.config import settings

            if getattr(settings, "enable_evolution_learning", False):
                from core.evolution.merge_learning_learner import learn_from_merge_reports

                await learn_from_merge_reports(self.fitness_engine)
        except Exception as exc:  # noqa: BLE001 — learning must never break the tick
            logger.debug(f"SelfEvolutionAgent: merge-learning skip ({exc})")

        metrics = self.fitness_engine.metrics
        if not metrics:
            return

        for skill_name in list(metrics.keys()):
            await self._evaluate_skill(skill_name)

        while not self._pending_demands.empty():
            demand = await self._pending_demands.get()
            await self._process_demand(demand)

    async def _evaluate_skill(self, skill_name: str) -> None:
        # Issue #1686: frozen skill (refactor budget শেষ, human alert দেওয়া)
        # আর কোনো mutation-ও হয় না — evaluation loop-এ পুরো বাদ।
        if self._base_skill_name(skill_name) in self._frozen_skills:
            logger.debug(
                f"SelfEvolutionAgent: skill '{skill_name}' is FROZEN (refactor "
                "budget exhausted) — skipping evaluation"
            )
            return

        score = self.fitness_engine.calculate_fitness(skill_name)
        entry = self.fitness_engine.metrics.get(skill_name, {})
        total_runs = entry.get("success_count", 0) + entry.get("failure_count", 0)

        if total_runs > 0 and total_runs < self.min_runs_before_action:
            return

        if score < self.refactor_penalty_threshold:
            self._consecutive_penalties[skill_name] = (
                self._consecutive_penalties.get(skill_name, 0) + 1
            )
            if self._consecutive_penalties[skill_name] >= self.max_consecutive_penalties:
                await self._maybe_trigger_refactor(skill_name)
                # Issue #1686: reset-to-0 বাদ — DECAY। 0-reset হলে
                # refactor→bad-score→refactor চক্র কখনো শেষ হত না।
                self._consecutive_penalties[skill_name] = max(
                    0, self._consecutive_penalties[skill_name] - 1
                )
        else:
            # বাংলা মন্তব্য (issue #1686): good score-এও এখন hard reset নয়,
            # decay — কারণ বারবার সীমানায় দোদুল্যমান skill তখনই লুপ তৈরি করে।
            self._consecutive_penalties[skill_name] = max(
                0, self._consecutive_penalties.get(skill_name, 0) - 1
            )

        if score < self.fitness_threshold:
            self.fitness_engine.evaluate_and_prune(
                skill_name, self.fitness_threshold, self.min_runs_before_action
            )

    @staticmethod
    def _base_skill_name(skill_name: str) -> str:
        """`foo_v3` → `foo` — রিফ্যাক্টর লিনেজ এক skill হিসেবে গোনা হয়।"""
        return re.sub(r"_v\d+$", "", skill_name)

    def _next_refactor_name(self, skill_name: str) -> str:
        """`foo` → `foo_v2`, `foo_v2` → `foo_v3` (issue #1686)।"""
        base = self._base_skill_name(skill_name)
        lineage = self._refactor_counts.get(base, 0) + 1
        return f"{base}_v{lineage + 1}"

    async def _maybe_trigger_refactor(self, skill_name: str) -> None:
        """Issue #1686: refactor-এর আগে lineage budget যাচাই —
        শেষ হলে freeze + human alert, আর refactor নয়।"""
        base = self._base_skill_name(skill_name)
        refactors_done = self._refactor_counts.get(base, 0)

        if refactors_done >= self.max_refactors_per_skill:
            if base not in self._frozen_skills:
                self._frozen_skills.add(base)
                logger.critical(
                    f"[SelfEvolution] INFINITE-LOOP GUARD: skill lineage '{base}' "
                    f"has been refactored {refactors_done} times without improvement "
                    "— FROZEN, no further automatic refactors. Human intervention "
                    "required."
                )
                error_event_bus.emit(
                    ErrorEvent(
                        module="self_evolution",
                        error_type="EVOLUTION_LOOP_FROZEN",
                        message=(
                            f"Skill lineage '{base}' refactored {refactors_done}x "
                            "without improvement — frozen (issue #1686)"
                        ),
                        severity="ALERT",
                        structured_context=ErrorContext(module="self_evolution"),
                        context={
                            "skill": base,
                            "refactor_count": refactors_done,
                            "max_refactors": self.max_refactors_per_skill,
                        },
                    )
                )
            return

        self._refactor_counts[base] = refactors_done + 1
        await self._trigger_refactor(skill_name)

    async def _trigger_refactor(self, skill_name: str) -> None:
        logger.warning(f"Skill '{skill_name}' hit consecutive penalty threshold. Refactoring...")
        current_code = self._read_skill_code(skill_name)
        user_demand = (
            f"Refactor the existing skill '{skill_name}' to drastically improve its fitness score.\n"
            f"Current source code:\n{current_code}\n"
            "Preserve the public interface (class name and async execute(self, kwargs) -> dict method).\n"
        )
        refactored_name = self._next_refactor_name(skill_name)
        # In actual execution, we route through process_new_skill_proposal with DB session
        logger.info(f"Refactor triggered for {skill_name}. New proposal will be processed.")
        await self.auto_skill_creator.generate_and_deploy_skill(user_demand, refactored_name)

    def _read_skill_code(self, skill_name: str) -> str:
        base_dir = Path(__file__).resolve().parent.parent.parent
        candidates = [
            base_dir / "skills" / "dynamic" / skill_name / "main.py",
            base_dir / "skills" / "deprecated" / skill_name / "main.py",
        ]
        for path in candidates:
            if path.exists():
                return path.read_text(encoding="utf-8")
        return "// Source code not found"

    async def _process_demand(self, demand: dict[str, str]) -> None:
        task_demand = demand["task_demand"]
        skill_name = demand["skill_name"]
        logger.info(f"Processing demand for missing skill: {skill_name}")
        if not self._has_high_fitness_path(skill_name):
            await self.auto_skill_creator.generate_and_deploy_skill(task_demand, skill_name)

    async def _register_missing_path(self, task_demand: str, skill_name: str) -> None:
        # বাংলা মন্তব্য: async করা হয়েছে যাতে tests await করতে পারে এবং
        # auto_skill_creator.generate_and_deploy_skill() সরাসরি call হয়।
        if not self._has_high_fitness_path(skill_name):
            await self.auto_skill_creator.generate_and_deploy_skill(task_demand, skill_name)

    def _has_high_fitness_path(self, skill_name: str) -> bool:
        if not hasattr(self.fitness_engine, "registry"):
            return False
        return self.fitness_engine.registry.get_skill(skill_name) is not None

    # 🛑 ZERO-GAP: Core Database and Security validation pipeline
    async def process_new_skill_proposal(
        self,
        session: AsyncSession,
        skill_name: str,
        generated_code: str,
        metadata: dict | None = None,
    ) -> bool:
        """
        Zero-Gap Pipeline for evaluating and integrating AI-generated code atomically.
        """
        proposal_id = f"prop-{uuid.uuid4().hex[:8]}"
        metadata = metadata or {}

        # Step 1: Record Proposal
        async with session.begin():
            proposal = CodeProposal(
                proposal_id=proposal_id,
                skill_name=skill_name,
                generated_code=generated_code,
                status="proposed",
                metadata_json=metadata,
            )
            session.add(proposal)
            await session.flush()

            # Step 2: Strict AST Security Scan
            res = self.scanner.scan_code(generated_code)
            if not res["safe"]:
                logger.critical(
                    f"AST Scanner BLOCKED proposal {proposal_id}: {res.get('error', 'unsafe code')}"
                )
                proposal.status = "rejected_by_ast"
                proposal.ast_validated = False
                return False

            proposal.status = "ast_validated"
            proposal.ast_validated = True
            logger.success(f"Proposal {proposal_id} passed AST Security Scan.")

        # Step 3: CI/CD Real Dry Run (Isolated Sandbox Execution)
        ci_passed = await self._run_ci_cd_dry_run(proposal_id, skill_name, generated_code)

        async with session.begin():
            result = await session.execute(
                select(CodeProposal).where(CodeProposal.proposal_id == proposal_id)
            )
            p = result.scalars().first()
            if p:
                if not ci_passed:
                    logger.error(f"CI/CD dry-run FAILED for proposal {proposal_id}")
                    p.status = "rejected_by_ci"
                    p.ci_passed = False
                    return False

                # Step 4: Final Approval for Merge/Apply
                p.status = "ci_passed"
                p.ci_passed = True
                logger.success(
                    f"Evolution successful: {skill_name} ({proposal_id}) passed all zero-gap gates."
                )

        return True

    async def _update_proposal_status(
        self, session: AsyncSession, proposal_id: str, new_status: str, **kwargs
    ):
        """Helper method to atomically update proposal state"""
        async with session.begin():
            result = await session.execute(
                select(CodeProposal).where(CodeProposal.proposal_id == proposal_id)
            )
            proposal = result.scalars().first()
            if proposal:
                proposal.status = new_status
                if "ast_validated" in kwargs:
                    proposal.ast_validated = kwargs["ast_validated"]
                if "ci_passed" in kwargs:
                    proposal.ci_passed = kwargs["ci_passed"]

    async def _run_ci_cd_dry_run(self, proposal_id: str, skill_name: str, code: str) -> bool:
        """
        Executes isolated sandbox verification for evolved skill.
        """
        logger.info(f"Triggering Sandbox/CI dry run for {proposal_id} ({skill_name})...")
        try:
            from tools.code.local_code_executor import LocalCodeExecutor

            sandbox = LocalCodeExecutor()
            test_harness = (
                f"{code}\n\nimport sys\nif {skill_name!r} not in globals():\n    sys.exit(1)\n"
            )
            res = await sandbox.execute_local_code(test_harness, timeout=10)
            if not res.get("success"):
                logger.error(
                    f"Sandbox dry-run failed for {proposal_id}: {res.get('error', res.get('stderr'))}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Sandbox error in AI generated code: {e}")
            return False
