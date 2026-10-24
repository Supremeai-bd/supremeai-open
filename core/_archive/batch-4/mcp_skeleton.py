"""MCP Skeleton — delegates to canonical adaptive_engine.mcp_skeleton.

Preserves backward-compatibility while eliminating code duplication.
"""

from __future__ import annotations

from adaptive_engine.mcp_skeleton import (
    MCPActionDenied,
    MCPOperationCategory,
    MCPOperationError,
    MCPOperationNotRegisteredError,
    MCPSkeleton,
    get_mcp_skeleton,
)

__all__ = [
    "MCPOperationCategory",
    "MCPSkeleton",
    "get_mcp_skeleton",
    "MCPOperationError",
    "MCPOperationNotRegisteredError",
    "MCPActionDenied",
]
