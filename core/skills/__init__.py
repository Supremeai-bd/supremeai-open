# backend/core/skills/__init__.py
"""SupremeAI Core Skills Package (Unified Single Source)."""

from __future__ import annotations

from core.skills.base import BaseSkill
from core.skills.core_skills import (
    CodeGenerationSkill,
    ExperiencePersistenceSkill,
    ResearchSkill,
    StaticAnalysisSkill,
    SystemDesignSkill,
    ToolExecutionSkill,
    ToolSynthesisSkill,
)
from core.skills.integrations import (
    GithubSyncSkill,
    NotionSyncSkill,
    SlackIntegrationSkill,
)

__all__ = [
    "BaseSkill",
    "SystemDesignSkill",
    "CodeGenerationSkill",
    "StaticAnalysisSkill",
    "ResearchSkill",
    "ToolSynthesisSkill",
    "ToolExecutionSkill",
    "ExperiencePersistenceSkill",
    "SlackIntegrationSkill",
    "NotionSyncSkill",
    "GithubSyncSkill",
]
