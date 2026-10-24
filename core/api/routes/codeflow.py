"""
Backward compatibility bridge: re-export all from code_dependency_graph.
Preserves legacy imports for 'api.routes.codeflow' and 'backend.api.routes.codeflow'.
"""

from api.routes.code_dependency_graph import (  # noqa: F401
    CodeFlowEdge,
    CodeFlowNode,
    CodeFlowRequest,
    CodeFlowResponse,
    analyze,
    router,
)

__all__ = [
    "CodeFlowEdge",
    "CodeFlowNode",
    "CodeFlowRequest",
    "CodeFlowResponse",
    "analyze",
    "router",
]
