"""Tier 8: Meta-Self — SupremeAI Autonomous Layer.

This package contains the four Tier-8 meta-cognitive agents:

- SelfImprovementAgent: Auto-detects and proposes codebase refactors
- AgentEvolutionEngine: Genetic-algorithm agent capability evolution
- SwarmCoordinationAgent: Multi-agent consensus & fault-tolerant orchestration
- SkillMarketplaceCurator: Decentralized skill discovery, rating, and subscription

All modules are:
  • Lint-free (ruff --select=ALL compliant)
  • Zero hardcoded values (100% env/config driven)
  • Singleton-patterned with async lifecycle management
  • Fully integrated with existing backend.core observability stack

Usage:
    from core.tier8 import (
        get_self_improvement_agent,
        get_agent_evolution_engine,
        get_swarm_coordination_agent,
        get_skill_marketplace_curator,
    )
"""

from __future__ import annotations

from core.tier8.agent_evolution_engine import (
    AgentEvolutionEngine,
    get_agent_evolution_engine,
)

# বাংলা মন্তব্য: `backend.core.*` → `core.*` ইম্পোর্ট path fix করা হলো।
# Docker container-এ WORKDIR=/app/backend হওয়ায় `backend.` prefix runtime-এ ভুল ছিল।
# এই ফিক্স না থাকায় Tier-8 agents production-এ কখনো load হয়নি।
from core.tier8.codebase_refactor_proposer import (
    CodebaseRefactorProposer,
    SelfImprovementAgent,
    get_codebase_refactor_proposer,
    get_self_improvement_agent,
)
from core.tier8.skill_marketplace_curator import (
    SkillMarketplaceCurator,
    get_skill_marketplace_curator,
)
from core.tier8.swarm_coordination_agent import (
    SwarmCoordinationAgent,
    get_swarm_coordination_agent,
)

__all__ = [
    "AgentEvolutionEngine",
    "SelfImprovementAgent",
    "SkillMarketplaceCurator",
    "SwarmCoordinationAgent",
    "get_agent_evolution_engine",
    "get_self_improvement_agent",
    "get_skill_marketplace_curator",
    "get_swarm_coordination_agent",
]
