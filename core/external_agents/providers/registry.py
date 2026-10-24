"""
backend/external_agents/providers/registry.py
=============================================
ISSUE-1573 (Part 4): the dynamic provider capability registry.

Built-in capability matrix (per the issue):

    provider | native_mcp | goal_mode | browser_channel
    ---------+------------+-----------+----------------
    zcode    | true       | true      | false (DISALLOWED)
    chatgpt  | false      | false     | policy_checked
    gemini   | false      | false     | policy_checked
    lovable  | false      | false     | policy_checked
    bolt     | false      | false     | policy_checked

The registry is the single source of truth the Policy Engine consults
before any dispatch — unknown providers fail closed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from external_agents.contracts.task_contract import AgentProvider

__all__ = [
    "ChannelPolicy",
    "ExecutionMode",
    "ProviderCapabilities",
    "ProviderRegistry",
    "build_default_registry",
]


class ExecutionMode(StrEnum):
    """How work is delivered to / driven through an external provider."""

    NATIVE_MCP = "native_mcp"
    GOAL_MODE = "goal_mode"
    BROWSER_CHANNEL = "browser_channel"


class ChannelPolicy(StrEnum):
    """Tri-state policy for a capability."""

    ALLOWED = "allowed"
    POLICY_CHECKED = "policy_checked"
    DISALLOWED = "disallowed"


class ProviderCapabilities(BaseModel):
    provider: AgentProvider
    native_mcp: bool = False
    goal_mode: bool = False
    browser_channel: ChannelPolicy = ChannelPolicy.DISALLOWED
    display_name: str | None = None
    notes: str = ""

    def supports(self, mode: ExecutionMode) -> bool:
        if mode is ExecutionMode.NATIVE_MCP:
            return self.native_mcp
        if mode is ExecutionMode.GOAL_MODE:
            return self.goal_mode
        if mode is ExecutionMode.BROWSER_CHANNEL:
            return self.browser_channel is not ChannelPolicy.DISALLOWED
        return False

    def preferred_mode(self) -> ExecutionMode:
        """Most automated channel available (native MCP > goal mode > browser)."""
        if self.native_mcp:
            return ExecutionMode.NATIVE_MCP
        if self.goal_mode:
            return ExecutionMode.GOAL_MODE
        return ExecutionMode.BROWSER_CHANNEL


_BUILTIN_MATRIX: dict[AgentProvider, dict] = {
    AgentProvider.ZCODE: {
        "native_mcp": True,
        "goal_mode": True,
        "browser_channel": ChannelPolicy.DISALLOWED,
        "display_name": "ZCode",
        "notes": "Native SupremeAI MCP + /goal autonomous mode (#1574)",
    },
    AgentProvider.CHATGPT: {
        "native_mcp": False,
        "goal_mode": False,
        "browser_channel": ChannelPolicy.POLICY_CHECKED,
        "display_name": "ChatGPT",
    },
    AgentProvider.GEMINI: {
        "native_mcp": False,
        "goal_mode": False,
        "browser_channel": ChannelPolicy.POLICY_CHECKED,
        "display_name": "Gemini",
    },
    AgentProvider.LOVABLE: {
        "native_mcp": False,
        "goal_mode": False,
        "browser_channel": ChannelPolicy.POLICY_CHECKED,
        "display_name": "Lovable",
    },
    AgentProvider.BOLT: {
        "native_mcp": False,
        "goal_mode": False,
        "browser_channel": ChannelPolicy.POLICY_CHECKED,
        "display_name": "Bolt",
    },
}


class ProviderRegistry:
    """Register / query provider capabilities. Unknown providers fail closed."""

    def __init__(self, capabilities: list[ProviderCapabilities] | None = None) -> None:
        self._caps: dict[AgentProvider, ProviderCapabilities] = {}
        for cap in capabilities or []:
            self.register(cap)

    def register(self, capabilities: ProviderCapabilities) -> None:
        self._caps[capabilities.provider] = capabilities

    def _normalise(self, provider: AgentProvider | str) -> AgentProvider:
        if isinstance(provider, AgentProvider):
            return provider
        try:
            return AgentProvider(provider)
        except ValueError as exc:
            raise KeyError(f"provider '{provider}' is not registered (fail-closed)") from exc

    def get(self, provider: AgentProvider | str) -> ProviderCapabilities:
        provider = self._normalise(provider)
        cap = self._caps.get(provider)
        if cap is None:
            raise KeyError(f"provider '{provider.value}' is not registered (fail-closed)")
        return cap

    def has(self, provider: AgentProvider | str) -> bool:
        try:
            return self._normalise(provider) in self._caps
        except KeyError:
            return False

    def all(self) -> list[ProviderCapabilities]:
        return list(self._caps.values())

    def supports(self, provider: AgentProvider, mode: ExecutionMode) -> bool:
        return self.has(provider) and self.get(provider).supports(mode)

    def preferred_mode(self, provider: AgentProvider) -> ExecutionMode:
        return self.get(provider).preferred_mode()


def build_default_registry() -> ProviderRegistry:
    """The issue-mandated baseline capability matrix."""
    return ProviderRegistry(
        [ProviderCapabilities(provider=p, **spec) for p, spec in _BUILTIN_MATRIX.items()]
    )
