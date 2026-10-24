"""backend.core.sandbox.base
=========================
Core abstraction and domain contracts for SupremeAI's Governed Execution Plane.

Vendor-Neutral Architecture:
- Core execution tools consume only `SandboxProvider`.
- All untrusted code execution flows through defense-in-depth security configuration (`SandboxConfig`).
- Downstream diagnostic agents inspect structured `ExecutionResult` for self-healing and failure delta analysis.
"""

from __future__ import annotations

import abc
import fnmatch
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Default sensitive environment variable patterns that must NEVER leak into sandboxes
DEFAULT_SENSITIVE_ENV_PATTERNS: tuple[str, ...] = (
    "SUPREMEAI_*",
    "DATABASE_URL*",
    "*SECRET*",
    "*PASSWORD*",
    "*TOKEN*",
    "*KEY*",
    "JWT_*",
    "INFISICAL_*",
    "REDIS_*",
    "RENDER_*",
    "GITHUB_*",
    "OPENAI_*",
    "ANTHROPIC_*",
    "GROQ_*",
    "GEMINI_*",
    "AWS_*",
    "STRIPE_*",
    "CLOUDFLARE_*",
    "SUPABASE_*",
)


@dataclass(frozen=True)
class SandboxConfig:
    """Defense-in-depth configuration governing sandbox resource limits and security boundaries."""

    cpu_limit: str = "1.0"
    memory_limit: str = "512MB"
    timeout_seconds: int = 30
    network_policy: str = "blocked"  # 'blocked' | 'egress_allowlist'
    filesystem_policy: str = "ephemeral"  # 'ephemeral' | 'read_only'
    max_output_bytes: int = 100_000  # 100 KB cap on stdout/stderr
    max_artifact_bytes: int = 10_000_000  # 10 MB cap on output files
    allowed_languages: tuple[str, ...] = ("python", "javascript", "bash")

    # Environment patterns to filter out
    sensitive_env_patterns: tuple[str, ...] = DEFAULT_SENSITIVE_ENV_PATTERNS

    # Explicit custom environment variables to provide (must not match sensitive patterns)
    custom_env: dict[str, str] = field(default_factory=dict)

    def sanitize_environment(self, base_env: dict[str, str] | None = None) -> dict[str, str]:
        """Strip all sensitive keys matching sensitive_env_patterns from the environment."""
        source = dict(base_env if base_env is not None else os.environ)
        sanitized: dict[str, str] = {}

        for key, value in source.items():
            if any(
                fnmatch.fnmatch(key.upper(), pattern.upper())
                for pattern in self.sensitive_env_patterns
            ):
                continue
            sanitized[key] = value

        # Merge allowed custom_env if they don't violate patterns
        for k, v in self.custom_env.items():
            if not any(
                fnmatch.fnmatch(k.upper(), pattern.upper())
                for pattern in self.sensitive_env_patterns
            ):
                sanitized[k] = v

        return sanitized


@dataclass
class ExecutionResult:
    """Structured telemetry returned from any sandbox execution."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False
    resource_exceeded: bool = False
    sandbox_id: str | None = None
    artifacts: dict[str, bytes] = field(default_factory=dict)
    provider_metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_failure(self) -> bool:
        return not self.success or self.exit_code != 0 or self.timed_out or self.resource_exceeded


class SandboxProvider(abc.ABC):
    """Abstract base class representing an isolated code execution environment."""

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """Unique identifier of the provider (e.g. 'codesandbox', 'e2b', 'local_dev')."""
        ...

    @property
    @abc.abstractmethod
    def is_trusted_boundary(self) -> bool:
        """True if the provider provides true hardware/microVM isolation (safe for untrusted code in production)."""
        ...

    @abc.abstractmethod
    async def execute(
        self,
        code: str,
        language: str = "python",
        config: SandboxConfig | None = None,
    ) -> ExecutionResult:
        """Execute code within an isolated sandbox and return structured telemetry."""
        ...

    @abc.abstractmethod
    async def health_check(self) -> bool:
        """Verify provider availability and operational readiness."""
        ...
