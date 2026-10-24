"""
Backward compatibility bridge: re-export all from launchdarkly_agent_adapter.
Preserves legacy imports for 'tools.langchain_agent_example' and 'backend.tools.langchain_agent_example'.
"""

from tools.launchdarkly_agent_adapter import (  # noqa: F401
    INTEGRATION_OK,
    handle_agent_call_langchain,
)

__all__ = [
    "INTEGRATION_OK",
    "handle_agent_call_langchain",
]
