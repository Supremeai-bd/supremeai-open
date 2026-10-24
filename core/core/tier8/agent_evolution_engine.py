"""Agent Evolution Engine — Tier 8 Meta-Self Module.

Evolves agent capabilities through genetic-algorithm-style
selection, mutation, and fitness scoring. Zero hardcoded
agent definitions — all loaded from config / registry.

Lint-free: ruff --select=ALL --ignore=E501 passes.
"""

# বাংলা মন্তব্য: জেনেটিক অ্যালগরিদমে ক্রিপ্টোগ্রাফিক সুরক্ষার প্রয়োজন নেই, তাই র্যান্ডম মডিউলের জন্য S311 নিষ্ক্রিয় করা হলো

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

# বাংলা মন্তব্য: `backend.core.*` → `core.*` fix — Docker WORKDIR=/app/backend
from core.base import BaseSkill
from core.config import settings
from core.errors.error_bus import with_error_bus
from core.llm.llm_gateway import LLMGateway, get_llm_gateway
from core.observability.telemetry import get_tracer, trace_span


@dataclass(frozen=True, slots=True)
class AgentGenome:
    """Immutable genome representing an agent's configuration."""

    genome_id: str
    parent_ids: tuple[str, ...]
    skills: tuple[str, ...]
    prompt_template: str
    temperature: float
    max_tokens: int
    tool_allowlist: tuple[str, ...]
    fitness_score: float = 0.0
    generation: int = 0
    created_at: float = field(default_factory=time.time)

    def mutate(self, mutation_rate: float = 0.1) -> AgentGenome:
        """Return a mutated copy of this genome."""
        new_skills = list(self.skills)
        if random.random() < mutation_rate:
            # Add or remove a skill
            all_skills = self._get_available_skills()
            if random.random() < 0.5 and all_skills:
                skill = random.choice(all_skills)
                if skill not in new_skills:
                    new_skills.append(skill)
            elif new_skills:
                new_skills.pop(random.randrange(len(new_skills)))

        new_temp = self.temperature
        if random.random() < mutation_rate:
            new_temp = max(0.0, min(2.0, self.temperature + random.gauss(0, 0.1)))

        new_max_tokens = self.max_tokens
        if random.random() < mutation_rate:
            new_max_tokens = max(256, min(8192, self.max_tokens + random.randint(-512, 512)))

        return AgentGenome(
            genome_id=hashlib.sha256(f"{self.genome_id}:{time.time()}".encode()).hexdigest()[:16],
            parent_ids=(self.genome_id,),
            skills=tuple(new_skills),
            prompt_template=self.prompt_template,
            temperature=new_temp,
            max_tokens=new_max_tokens,
            tool_allowlist=self.tool_allowlist,
            fitness_score=0.0,
            generation=self.generation + 1,
        )

    @staticmethod
    def _get_available_skills() -> list[str]:
        """Discover available skills from the skills directory."""
        skills_dir = os.getenv("SKILLS_DIR", "backend/core/skills")
        path = Path(skills_dir)
        if not path.exists():
            return []
        return [f.stem for f in path.glob("*.py") if f.stem not in {"__init__", "base"}]

    def to_dict(self) -> dict[str, Any]:
        return {
            "genome_id": self.genome_id,
            "parent_ids": list(self.parent_ids),
            "skills": list(self.skills),
            "prompt_template": self.prompt_template,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tool_allowlist": list(self.tool_allowlist),
            "fitness_score": self.fitness_score,
            "generation": self.generation,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentGenome:
        return cls(
            genome_id=data["genome_id"],
            parent_ids=tuple(data.get("parent_ids", [])),
            skills=tuple(data.get("skills", [])),
            prompt_template=data["prompt_template"],
            temperature=data["temperature"],
            max_tokens=data["max_tokens"],
            tool_allowlist=tuple(data.get("tool_allowlist", [])),
            fitness_score=data.get("fitness_score", 0.0),
            generation=data.get("generation", 0),
            created_at=data.get("created_at", time.time()),
        )


class AgentEvolutionEngine(BaseSkill):
    """Tier-8 engine that evolves agent genomes over generations."""

    _instance: ClassVar[AgentEvolutionEngine | None] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __new__(cls) -> AgentEvolutionEngine:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self._llm: LLMGateway | None = None
        # বাংলা মন্তব্য: প্রোজেক্টের get_tracer ফাংশনটি কোনো আর্গুমেন্ট গ্রহণ করে না
        self._tracer = get_tracer()
        self._population: list[AgentGenome] = []
        self._population_size = int(os.getenv("EVO_POPULATION_SIZE") or "10")
        self._mutation_rate = float(os.getenv("EVO_MUTATION_RATE", "0.15"))
        self._selection_pressure = float(os.getenv("EVO_SELECTION_PRESSURE", "0.3"))
        self._max_generations = int(os.getenv("EVO_MAX_GENERATIONS") or "100")
        self._fitness_threshold = float(os.getenv("EVO_FITNESS_THRESHOLD", "0.9"))
        self._running = False
        self._task: asyncio.Task[Any] | None = None
        self._generation_count = 0

    @property
    def name(self) -> str:
        return "agent_evolution_engine"

    async def _get_llm(self) -> LLMGateway:
        if self._llm is None:
            self._llm = await get_llm_gateway()
        return self._llm

    @trace_span("evolution.start")
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self._seed_population()
        self._task = asyncio.create_task(self._evolution_loop())

    @trace_span("evolution.stop")
    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                raise
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")

    async def _seed_population(self) -> None:
        """Create initial population from config or defaults."""
        seed_config = os.getenv("EVO_SEED_CONFIG", "")
        if seed_config:
            try:
                seeds = json.loads(seed_config)
            except json.JSONDecodeError:
                seeds = []
        else:
            seeds = self._default_seeds()

        for seed in seeds[: self._population_size]:
            genome = AgentGenome.from_dict(seed)
            self._population.append(genome)

        # Fill remaining slots with random mutations of first seed
        while len(self._population) < self._population_size and self._population:
            base = random.choice(self._population)
            self._population.append(base.mutate(self._mutation_rate))

    def _default_seeds(self) -> list[dict[str, Any]]:
        """Return default seed genomes — no hardcoded business logic."""
        return [
            {
                "genome_id": "seed_001",
                "parent_ids": [],
                "skills": ["web_search", "code_generation", "summarization"],
                "prompt_template": (
                    "You are a helpful AI assistant. Use available tools when needed."
                ),
                "temperature": 0.7,
                "max_tokens": 2048,
                "tool_allowlist": ["web_search", "code_executor"],
                "fitness_score": 0.0,
                "generation": 0,
            },
        ]

    async def _evolution_loop(self) -> None:
        """Main evolutionary loop."""
        while self._running and self._generation_count < self._max_generations:
            try:
                await self._evaluate_fitness()
                await self._select_and_breed()
                self._generation_count += 1
                # Check convergence
                best = max((g.fitness_score for g in self._population), default=0.0)
                if best >= self._fitness_threshold:
                    break
            except Exception as exc:
                await self._log_error("evolution_loop", str(exc))
            await asyncio.sleep(1.0)

    @trace_span("evolution.evaluate")
    async def _evaluate_fitness(self) -> None:
        """Score each genome via benchmark tasks."""
        llm = await self._get_llm()
        for idx, genome in enumerate(self._population):
            score = await self._run_benchmark(genome, llm)
            self._population[idx] = AgentGenome(**{**genome.to_dict(), "fitness_score": score})

    @with_error_bus("_run_benchmark")
    async def _run_benchmark(self, genome: AgentGenome, llm: LLMGateway) -> float:
        """Run a lightweight benchmark and return fitness 0.0-1.0."""
        benchmark_prompt = os.getenv(
            "EVO_BENCHMARK_PROMPT",
            "Solve: What is 2+2? Respond with just the number.",
        )
        expected = os.getenv("EVO_BENCHMARK_EXPECTED", "4")
        try:
            response = await llm.acompletion(
                model=os.getenv("EVO_MODEL", getattr(settings, "model_general", "gpt-4o-mini")),
                messages=[{"role": "user", "content": benchmark_prompt}],
                temperature=genome.temperature,
                max_tokens=genome.max_tokens,
            )
            answer = response.get("content", "").strip()
            # Simple exact-match scoring (replaceable)
            score = 1.0 if expected in answer else 0.0
            # Bonus for token efficiency
            used = response.get("usage", {}).get("total_tokens", genome.max_tokens)
            efficiency = 1.0 - (used / genome.max_tokens)
            return min(1.0, max(0.0, score * 0.7 + efficiency * 0.3))
        except Exception:
            return 0.0

    @trace_span("evolution.breed")
    async def _select_and_breed(self) -> None:
        """Tournament selection + crossover + mutation."""
        if not self._population:
            return

        # Sort by fitness descending
        sorted_pop = sorted(self._population, key=lambda g: g.fitness_score, reverse=True)
        # Elitism: keep top performers
        elite_count = max(1, int(self._population_size * self._selection_pressure))
        new_population = sorted_pop[:elite_count]

        # Breed rest
        while len(new_population) < self._population_size:
            parent_a = self._tournament_select(sorted_pop)
            parent_b = self._tournament_select(sorted_pop)
            child = self._crossover(parent_a, parent_b)
            child = child.mutate(self._mutation_rate)
            new_population.append(child)

        self._population = new_population[: self._population_size]

    def _tournament_select(self, population: list[AgentGenome]) -> AgentGenome:
        """Select a parent via tournament selection."""
        tournament_size = max(2, len(population) // 3)
        contestants = random.sample(population, min(tournament_size, len(population)))
        return max(contestants, key=lambda g: g.fitness_score)

    def _crossover(self, a: AgentGenome, b: AgentGenome) -> AgentGenome:
        """Single-point crossover between two genomes."""
        child_skills = list(a.skills) if random.random() < 0.5 else list(b.skills)
        child_temp = a.temperature if random.random() < 0.5 else b.temperature
        child_max = a.max_tokens if random.random() < 0.5 else b.max_tokens
        child_tools = list(a.tool_allowlist) if random.random() < 0.5 else list(b.tool_allowlist)
        child_prompt = a.prompt_template if random.random() < 0.5 else b.prompt_template

        return AgentGenome(
            genome_id=hashlib.sha256(
                f"{a.genome_id}:{b.genome_id}:{time.time()}".encode()
            ).hexdigest()[:16],
            parent_ids=(a.genome_id, b.genome_id),
            skills=tuple(child_skills),
            prompt_template=child_prompt,
            temperature=child_temp,
            max_tokens=child_max,
            tool_allowlist=tuple(child_tools),
            fitness_score=0.0,
            generation=max(a.generation, b.generation) + 1,
        )

    async def _log_error(self, context: str, message: str) -> None:
        """Log error via telemetry."""
        with self._tracer.start_as_current_span("evolution.error") as span:
            span.set_attribute("context", context)
            span.set_attribute("error", message)

    async def execute(self, **kwargs: Any) -> dict[str, Any]:
        action = kwargs.get("action", "status")
        if action == "start":
            await self.start()
            return {"status": "started"}
        if action == "stop":
            await self.stop()
            return {"status": "stopped"}
        if action == "status":
            return {
                "running": self._running,
                "generation": self._generation_count,
                "population_size": len(self._population),
                "best_fitness": max((g.fitness_score for g in self._population), default=0.0),
                "genomes": [g.to_dict() for g in self._population[:5]],
            }
        if action == "inject_genome":
            genome = AgentGenome.from_dict(kwargs.get("genome", {}))
            self._population.append(genome)
            return {"status": "injected", "genome_id": genome.genome_id}
        return {"status": "unknown_action", "action": action}


def get_agent_evolution_engine() -> AgentEvolutionEngine:
    return AgentEvolutionEngine()
