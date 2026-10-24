"""Base contract for experimental SupremeAI plugins.

M0-D (AUDIT F4): this module was referenced by every plugin under
core/plugins/experimental/ (`from .base import BasePlugin`) but was never
committed — 11 modules failed the import walk because of it. The contract
mirrors core/plugins/official/base.py exactly.

Why duplicated instead of re-exported from official: official/*.py are
back-compat shims that import the experimental implementations, so an
experimental->official import would close a package-level import cycle
(official/__init__ -> official.gmail_plugin -> experimental.gmail_plugin ->
experimental.base -> official.__init__). Keeping a small duplicated ABC here
is the zero-risk resolution; a future consolidation belongs to the plugin
subsystem owner, not to M0 hygiene.
"""

from abc import ABC, abstractmethod
from typing import Any


class BasePlugin(ABC):
    """Abstract base class for all SupremeAI plugins (experimental layer).

    Contract (identical to core/plugins/official/base.py):
    - a plugin identifies itself through the `plugin_id` property;
    - a plugin executes named tools asynchronously through `execute_tool`.

    Experimental plugins may be unimplemented; the capability-graph honesty
    layer treats NotImplementedError as "not yet connected" instead of a crash
    (lifecycle: IDEA -> measured -> connected, see MASTER_PLAN.md Phase 1
    health-probe promotion).
    """

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """Unique identifier for this plugin."""
        raise NotImplementedError

    @abstractmethod
    async def execute_tool(
        self, tool_name: str, params: dict[str, Any], context: dict[str, Any]
    ) -> Any:
        """Execute a specific tool provided by this plugin.

        :param tool_name: The name of the tool to execute.
        :param params: Arguments for the tool.
        :param context: Execution context (e.g., auth tokens, user info).
        """
        raise NotImplementedError
