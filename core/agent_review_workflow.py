"""Canonical reusable Agent Review Workflow facade."""

from __future__ import annotations

from typing import Any

from core.orchestration.trio_pipeline import AgentReviewWorkflow

__all__ = ["AgentReviewWorkflow", "run_agent_review_workflow"]


async def run_agent_review_workflow(
    prompt: str,
    language: str = "python",
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute the canonical workflow without exposing provider/model identity."""
    return await AgentReviewWorkflow().execute(
        prompt=prompt,
        language=language,
        context=context,
    )
