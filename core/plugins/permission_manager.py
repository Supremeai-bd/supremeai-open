import logging

logger = logging.getLogger(__name__)


class PluginPermissionManager:
    """
    Validates that a plugin or an agent acting on behalf of a plugin
    is authorized to use the requested capabilities.
    """

    @staticmethod
    def validate_capability_access(user_installation, required_capability: str) -> bool:
        if not user_installation.is_enabled:
            return False

        # For V1, simple exact match or wildcard
        return (
            required_capability in user_installation.granted_capabilities
            or "*" in user_installation.granted_capabilities
        )
