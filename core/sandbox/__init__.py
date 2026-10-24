"""backend.core.sandbox
====================
SupremeAI Governed Execution Plane: Vendor-neutral sandbox abstraction and registry.
"""

from core.sandbox.base import (
    DEFAULT_SENSITIVE_ENV_PATTERNS,
    ExecutionResult,
    SandboxConfig,
    SandboxProvider,
)
from core.sandbox.cloud_sandbox_provider import CloudSandboxProvider
from core.sandbox.local_dev_provider import LocalDevSandboxProvider
from core.sandbox.registry import SandboxRegistry, sandbox_registry

# Register default providers into the global registry
sandbox_registry.register(LocalDevSandboxProvider(), set_default=True)
sandbox_registry.register(CloudSandboxProvider(name="codesandbox"))
sandbox_registry.register(CloudSandboxProvider(name="e2b"))

__all__ = [
    "DEFAULT_SENSITIVE_ENV_PATTERNS",
    "ExecutionResult",
    "SandboxConfig",
    "SandboxProvider",
    "SandboxRegistry",
    "sandbox_registry",
    "LocalDevSandboxProvider",
    "CloudSandboxProvider",
]
