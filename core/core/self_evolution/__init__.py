"""SupremeAI Core Evolution Engine & Subsystems.

Provides unified exports for:
- Self-Evolution & Continuous Learning (EvolutionEngine, FitnessEngine, SelfEvolutionAgent, DailyLearner)
- Auto Skill Creation & Graph Reasoning (AutoSkillCreator, SkillGraph, AgentBreeder)
- Advanced Evolutionary Research (DigitalTwin, AdversarialDefense, NeuralSymbolic, FederatedLearning, TheoryOfMind, TemporalAbstraction)
"""

from __future__ import annotations

# Core Production Evolution Components
from .agent_breeder import AgentBreeder
from .auto_skill_creator import AutoSkillCreator
from .daily_learner import DailyLearner
from .evolution_engine import EvolutionEngine
from .fitness_engine import FitnessEngine
from .performance_oracle import PerformanceOracle
from .self_evolution_agent import SelfEvolutionAgent
from .self_updater import SelfUpdater
from .skill_graph import EvolutionSkillGraph

__all__ = [
    "AgentBreeder",
    "AutoSkillCreator",
    "DailyLearner",
    "EvolutionEngine",
    "FitnessEngine",
    "PerformanceOracle",
    "SelfEvolutionAgent",
    "SelfUpdater",
    "EvolutionSkillGraph",
]
