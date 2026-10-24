"""SupremeAI 2.0 — Tier 7 Creative Agents Registration.

Registers all Tier-7 creative agents into the skill registry.
Follows the 8-layer architecture and integrates with:
    • backend.core.skills.base.BaseSkill
    • backend.core.skill_manager.SkillManager
    • backend.core.orchestration.orchestrator.Orchestrator

Usage:
    from tools.creative.creative_agents_registry import register_creative_agents
    register_creative_agents(skill_manager)
"""

# বাংলা মন্তব্য: Tier-7 ক্রিয়েটিভ এজেন্টগুলোকে স্কিল রেজিস্ট্রিতে রেজিস্টার করার মডিউল।

from __future__ import annotations

from typing import Any

from tools.creative.audio_engineering_agent import AudioEngineeringAgent
from tools.creative.brand_identity_agent import BrandIdentityAgent
from tools.creative.game_design_agent import GameDesignAgent
from tools.creative.video_production_agent import VideoProductionAgent

_AGENT_CLASSES: tuple[type, ...] = (
    VideoProductionAgent,
    GameDesignAgent,
    AudioEngineeringAgent,
    BrandIdentityAgent,
)


def register_creative_agents(manager: Any) -> dict[str, str]:
    """Register all Tier-7 creative agents with the skill manager.

    Args:
        manager: SkillManager instance (duck-typed to avoid circular imports).

    Returns:
        Mapping of agent name → registration status.
    """
    # বাংলা মন্তব্য: সব ক্রিয়েটিভ এজেন্টকে স্কিল ম্যানেজারে রেজিস্টার করার প্রসেস
    results: dict[str, str] = {}
    for cls in _AGENT_CLASSES:
        agent = cls()
        name = agent.name()
        try:
            manager.register_skill(name, agent)
            results[name] = "registered"
        except Exception as exc:
            results[name] = f"failed: {exc}"
    return results
