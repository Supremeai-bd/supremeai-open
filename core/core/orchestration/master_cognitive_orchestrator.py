"""Compatibility bridge: re-export all from cognitive_pipeline_dispatcher.py."""

from core.orchestration.cognitive_pipeline_dispatcher import (  # noqa: F401
    CognitiveIntent,
    CognitivePipelineDispatcher,
    MasterCognitiveOrchestrator,
    PipelineExecutionResult,
    get_cognitive_pipeline_dispatcher,
    get_master_orchestrator,
)

__all__ = [
    "CognitiveIntent",
    "PipelineExecutionResult",
    "MasterCognitiveOrchestrator",
    "CognitivePipelineDispatcher",
    "get_master_orchestrator",
    "get_cognitive_pipeline_dispatcher",
]
