# backend/core/security/governance_policy.py
"""Centralized Allowlist-First Governance Kernel for Self-Evolution Safety."""

from __future__ import annotations

import os
import re

from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

# ── Explicit Allowlist for Evolution Target Namespaces ──────────────────────
ALLOWED_EVOLUTION_NAMESPACES = (
    "skills",
    "core/skills",
    "prompt_templates",
    "brain",
    "brain/prompts",
    "adapters",
    "learning",
)

# ── Strict Denylist for Immutable Infrastructure & Security ───────────────────
PROTECTED_CRITICAL_PATHS = (
    "core/security",
    "api/dependencies.py",
    "core/config",
    ".env",
    "billing",
    "core/tenant_db.py",
    "runtime/budget_guard.py",
    "evolution/artifact_integrity.py",
    "core/security/governance_policy.py",
)


def normalize_module_path(path: str) -> str:
    """Normalize file or module path to prevent path traversal bypasses."""
    if not path or not isinstance(path, str):
        return ""
    # Strip leading backend/ or ./ or /
    cleaned = path.replace("\\", "/").strip()
    cleaned = re.sub(r"^(?:\.?/)*(?:backend/)*", "", cleaned)
    # Normalize path to resolve ../ and ./
    normalized = os.path.normpath(cleaned).replace("\\", "/")
    return normalized


class GovernancePolicy:
    """Centralized security governor enforcing immutable core boundaries on all self-modifications."""

    def __init__(
        self,
        allowed_namespaces: tuple[str, ...] = ALLOWED_EVOLUTION_NAMESPACES,
        protected_paths: tuple[str, ...] = PROTECTED_CRITICAL_PATHS,
    ) -> None:
        self.allowed_namespaces = allowed_namespaces
        self.protected_paths = protected_paths

    def validate_evolution_target(self, target_path: str) -> tuple[bool, str]:
        """Validate if a target module is eligible for autonomous self-modification.

        Returns (is_valid: bool, reason: str).
        """
        normalized = normalize_module_path(target_path)
        if not normalized:
            return False, "Target module path is empty or invalid."

        # 1. Check if path attempts directory traversal
        if ".." in normalized or normalized.startswith("/"):
            reason = f"Path traversal attempt detected in target: '{target_path}'"
            self._emit_security_violation(target_path, normalized, reason)
            return False, reason

        # 2. Check against strict protected denylist
        for protected in self.protected_paths:
            prot_norm = normalize_module_path(protected)
            if normalized == prot_norm or normalized.startswith(prot_norm.rstrip("/") + "/"):
                reason = f"Target '{target_path}' resides in protected security/auth namespace '{protected}'"
                self._emit_security_violation(target_path, normalized, reason)
                return False, reason

        # 3. Check against explicit allowlist
        is_allowed = any(
            normalized == normalize_module_path(allowed)
            or normalized.startswith(normalize_module_path(allowed).rstrip("/") + "/")
            for allowed in self.allowed_namespaces
        )

        if not is_allowed:
            reason = (
                f"Target '{target_path}' is not in an authorized evolution allowlist namespace."
            )
            logger.warning(f"🛡️ [GOVERNANCE GATE] Rejected: {reason}")
            return False, reason

        return True, "Authorized for autonomous evolution."

    def _emit_security_violation(self, raw_path: str, normalized_path: str, reason: str) -> None:
        logger.critical(f"🚨 [GOVERNANCE BREACH ATTEMPT] {reason}")
        try:
            error_event_bus.emit(
                ErrorEvent(
                    module="governance_policy",
                    error_type="SecurityBreachAttempt",
                    message=f"Unauthorized self-modification attempt on '{raw_path}' ({normalized_path}): {reason}",
                    severity="CRITICAL",
                    structured_context=ErrorContext(module="governance_policy"),
                    context={
                        "raw_path": raw_path,
                        "normalized_path": normalized_path,
                        "reason": reason,
                    },
                )
            )
        except Exception as e:
            logger.error(f"Failed to emit governance security event: {e}")


# Global Singleton
_governance_policy: GovernancePolicy | None = None


def get_governance_policy() -> GovernancePolicy:
    global _governance_policy
    if _governance_policy is None:
        _governance_policy = GovernancePolicy()
    return _governance_policy
