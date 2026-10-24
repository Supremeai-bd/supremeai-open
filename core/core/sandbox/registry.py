"""backend.core.sandbox.registry
=============================
Vendor-neutral registry for discovering and routing to Sandbox Providers.
"""

from __future__ import annotations

import os
from typing import Optional

from core.logging_config import logger
from core.sandbox.base import SandboxProvider


class SandboxRegistry:
    """Central registry for pluggable SandboxProvider implementations."""

    def __init__(self) -> None:
        self._providers: dict[str, SandboxProvider] = {}
        self._default_provider_name: str | None = None

    def register(self, provider: SandboxProvider, set_default: bool = False) -> None:
        """Register a SandboxProvider instance."""
        name = provider.provider_name.lower().strip()
        self._providers[name] = provider
        logger.info(
            "Registered sandbox provider: %s (trusted_boundary=%s)",
            name,
            provider.is_trusted_boundary,
        )
        if set_default or self._default_provider_name is None:
            self._default_provider_name = name

    def unregister(self, name: str) -> None:
        """Unregister a provider by name."""
        name = name.lower().strip()
        self._providers.pop(name, None)
        if self._default_provider_name == name:
            self._default_provider_name = next(iter(self._providers), None)

    def get(self, name: str | None = None) -> SandboxProvider | None:
        """Resolve a provider by name or return the active default."""
        if name:
            return self._providers.get(name.lower().strip())

        # Check environment override
        env_provider = os.getenv("SUPREMEAI_SANDBOX_PROVIDER")
        if env_provider and env_provider.lower().strip() in self._providers:
            return self._providers[env_provider.lower().strip()]

        if self._default_provider_name:
            return self._providers.get(self._default_provider_name)

        return None

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def clear(self) -> None:
        """Clear all registered providers (primarily for testing)."""
        self._providers.clear()
        self._default_provider_name = None


# Global registry singleton
sandbox_registry = SandboxRegistry()
