"""
MCP Server — SupremeAI IDE Trio Pipeline
========================================

Exposes the Gemini → Kilo → Cline assembly-line pipeline as a single
MCP tool so that any MCP client (Kilo Code, Cline, Continue, Claude
Code, etc.) can trigger the full pipeline with one call.

Tools exposed:
    - trio_run_pipeline(prompt, language, context) -> pipeline result
    - trio_pipeline_health() -> availability of each IDE agent
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from core.logging_config import logger

mcp = FastMCP("ide_trio_mcp")

# Lazy import of the pipeline so MCP server can still start even if
# the heavy backend dependencies aren't installed yet.
_pipeline_instance = None


def _get_pipeline() -> Any:
    """Lazy singleton for TrioPipeline."""
    global _pipeline_instance
    if _pipeline_instance is None:
        from core.orchestration.trio_pipeline import TrioPipeline

        _pipeline_instance = TrioPipeline()
    return _pipeline_instance


class PipelineInput(BaseModel):
    """Input for the trio pipeline."""

    model_config = dict(str_strip_whitespace=True)

    prompt: str = Field(..., description="Natural-language description of the coding task")
    language: str = Field("python", description="Target programming language")
    file_path: str | None = Field(None, description="Optional file path for context")
    existing_code: str | None = Field(
        None, description="Existing code snippet (refactor/review mode)"
    )
    project_context: str | None = Field(None, description="Optional project-level context")


@mcp.tool()
async def trio_execute_pipeline(
    prompt: str,
    language: str = "python",
    file_path: str | None = None,
    existing_code: str | None = None,
    project_context: str | None = None,
) -> dict[str, Any]:
    """
    Run the full Gemini → Kilo → Cline pipeline:
    Stage 1 Gemini writes code, Stage 2 Kilo reviews it, Stage 3 Cline
    checks production readiness. Returns the aggregated pipeline result.
    """
    try:
        pipeline = _get_pipeline()
        context: dict[str, str] = {}
        if file_path:
            context["filePath"] = file_path
        if existing_code:
            context["existingCode"] = existing_code
        if project_context:
            context["projectContext"] = project_context

        result = await pipeline.execute(
            prompt=prompt,
            language=language,
            context=context,
        )
        return result

    except Exception as exc:  # BLE001 - MCP boundaries must not crash
        logger.exception("[TrioMCP] Pipeline execution failed")
        return {
            "pipeline_id": "error",
            "status": "failed",
            "error": str(exc),
            "ready_for_production": False,
            "summary": f"Pipeline error: {exc}",
        }


@mcp.tool()
async def trio_pipeline_agents() -> list[dict[str, Any]]:
    """Return the three IDE agents used by the pipeline and their status."""
    agents = [
        {
            "role": "writer",
            "agent": "gemini",
            "stage": 1,
            "description": "Generates code using Gemini API",
        },
        {
            "role": "reviewer",
            "agent": "kilo",
            "stage": 2,
            "description": "Reviews code using Kilo Code / GuardianAgent rules",
        },
        {
            "role": "checker",
            "agent": "cline",
            "stage": 3,
            "description": "Checks production readiness using Cline / local checks",
        },
    ]
    return agents


def main() -> None:
    """Entry point for running the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
