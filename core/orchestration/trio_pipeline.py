"""
SupremeAI Trio Pipeline Orchestrator
=====================================

Chains the three IDE agents into a single production pipeline:

    Stage 1:  Gemini   (Code Writer)
    Stage 2:  Kilo     (Code Reviewer)
    Stage 3:  Cline    (Production Checker)

The orchestrator exposes ``execute()`` which runs all three stages in
sequence and returns a structured ``TrioPipelineResult`` containing
the generated code, review findings, and production-readiness report.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from core.logging_config import logger


class AgentReviewWorkflow:
    """Run the reusable writer, reviewer, and checker workflow.

    Agent/provider selection is delegated to the configured adapters and runtime
    gateway; this module owns orchestration, not model identity.
    """

    def __init__(self) -> None:
        # Lazy imports avoid circular imports at module load
        from agents.ide.trio_adapters import (
            ClineChecker,
            GeminiWriter,
            KiloReviewer,
        )

        self.writer = GeminiWriter()
        self.reviewer = KiloReviewer()
        self.checker = ClineChecker()

    async def execute(
        self,
        prompt: str,
        language: str = "python",
        context: dict | None = None,
    ) -> dict:
        """
        Run the full pipeline: Writer → Reviewer → Checker.

        Returns a dict with keys:
            - pipeline_id
            - status
            - generated_code
            - writer / reviewer / checker results
            - ready_for_production
            - summary
        """
        pipeline_id = hashlib.sha256(
            f"{prompt}:{language}:{datetime.now(UTC).isoformat()}".encode()
        ).hexdigest()[:16]

        logger.info(f"[AgentReviewWorkflow] Starting workflow {pipeline_id}: {prompt[:100]}")

        # ── Stage 1: Gemini writes code ──────────────────────────────────
        ctx = context or {}
        if ctx.get("existingCode"):
            ctx_value = {
                "filePath": ctx.get("filePath", ""),
                "existingCode": ctx.get("existingCode"),
                "projectContext": ctx.get("projectContext"),
            }
        else:
            ctx_value = ctx

        writer_result = await self.writer.run(
            prompt=prompt,
            language=language,
            context=ctx_value,
        )

        if writer_result.confidence == 0.0 or writer_result.issues:
            return {
                "pipeline_id": pipeline_id,
                "status": "failed",
                "generated_code": "",
                "writer": writer_result.to_dict(),
                "reviewer": {},
                "checker": {},
                "ready_for_production": False,
                "summary": f"Writer stage failed: {writer_result.output[:200]}",
            }

        generated_code = writer_result.output

        # ── Stage 2: Kilo reviews the code ───────────────────────────────
        reviewer_result = await self.reviewer.run(
            code=generated_code,
            language=language,
            filepath=ctx.get("filePath", ""),
            writer_result=writer_result,
        )

        # ── Stage 3: Cline checks production readiness ──────────────────
        checker_result = await self.checker.run(
            code=generated_code,
            language=language,
            filepath=ctx.get("filePath", ""),
            reviewer_result=reviewer_result,
        )

        ready = bool(checker_result.metadata.get("ready_for_production", False))
        review_issue_count = len(reviewer_result.issues)
        len(checker_result.issues)
        status = (
            "ready"
            if ready and review_issue_count == 0
            else "needs_review"
            if review_issue_count > 0
            else "reviewed"
        )

        summary = (
            f"Stage 1 (Gemini): {len(generated_code.splitlines())} lines generated.  "
            f"Stage 2 (Kilo): {review_issue_count} issue(s) found.  "
            f"Stage 3 (Cline): {'READY for production' if ready else 'NOT READY'}"
        )

        result = {
            "pipeline_id": pipeline_id,
            "status": status,
            "generated_code": generated_code,
            "writer": writer_result.to_dict(),
            "reviewer": reviewer_result.to_dict(),
            "checker": checker_result.to_dict(),
            "ready_for_production": ready,
            "summary": summary,
        }

        logger.info(f"[AgentReviewWorkflow] {pipeline_id} complete - status={status}")
        return result


# Compatibility alias for existing callers during the migration window.
TrioPipeline = AgentReviewWorkflow
