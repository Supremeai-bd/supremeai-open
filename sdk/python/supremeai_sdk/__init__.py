"""supremeai-sdk-py — official async Python SDK for the SupremeAI MCP Tower.

Zero runtime dependencies (stdlib asyncio only). Typed public surface:

    from supremeai_sdk import SupremeAIClient, ToolInvocation

Re-exports the validated client core (``supremeai_sdk.client``, issue #33
reference impl, packaged per issue #338). ``__all__`` is the complete public
contract; anything not listed here is internal and may change.
"""
from __future__ import annotations

from .client import (
    DEFAULT_BASE_URL,
    DEFAULT_CLIENT_NAME,
    MCP_ACCEPT,
    SdkAuthError,
    SdkError,
    SdkForbidden,
    SdkNotFound,
    SdkRateLimited,
    StatusFrame,
    SupremeAIClient,
    TaskDispatchRequest,
    TaskDispatchResult,
    ToolInvocation,
    ToolResult,
)

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_CLIENT_NAME",
    "MCP_ACCEPT",
    "SdkAuthError",
    "SdkError",
    "SdkForbidden",
    "SdkNotFound",
    "SdkRateLimited",
    "StatusFrame",
    "SupremeAIClient",
    "TaskDispatchRequest",
    "TaskDispatchResult",
    "ToolInvocation",
    "ToolResult",
    "__version__",
]
