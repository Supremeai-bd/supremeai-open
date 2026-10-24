import logging

from sqlalchemy.ext.asyncio import AsyncSession

from core.plugins.lifecycle_manager import PluginLifecycleManager
from core.plugins.manifest_registry import PluginManifestRegistry

logger = logging.getLogger(__name__)


class CapabilityResolver:
    """
    Resolves the active toolset / capabilities for a user session
    by merging native tools, official plugin adapters, and MCP tools.
    """

    @staticmethod
    async def resolve_user_capabilities(session: AsyncSession, user_id: str) -> dict:
        """
        Returns a unified map of tools available to the user based on installed plugins.
        """
        installations = await PluginLifecycleManager.get_user_installations(session, user_id)
        active_tools = []

        for inst in installations:
            if not inst.is_enabled:
                continue

            manifest = await PluginManifestRegistry.get_manifest_by_id(session, inst.plugin_id)
            if not manifest or not manifest.is_active:
                continue

            # Here we would map the tools_provided to actual executable python callables
            # or MCP proxies based on execution_type.
            # For V1, we just aggregate the definitions.
            for tool in manifest.tools_provided:
                # Check permissions
                required_perms = tool.get("permissions", [])
                has_perms = all(
                    p in inst.granted_capabilities or "*" in inst.granted_capabilities
                    for p in required_perms
                )

                if has_perms:
                    tool_def = dict(tool)
                    tool_def["_source_plugin"] = manifest.id
                    tool_def["_execution_type"] = manifest.execution_type
                    active_tools.append(tool_def)

        return {"tools": active_tools}
