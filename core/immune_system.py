"""Backward compatibility shim for core.immune_system.

Canonical domain module: core.ast_security_scanner
"""

from core.ast_security_scanner import (
    ASTSecurityScanner,
    ASTSecurityScannerEngine,
    ImmuneSystemScanner,
    SecuritySandboxError,
)

__all__ = [
    "SecuritySandboxError",
    "ASTSecurityScanner",
    "ASTSecurityScannerEngine",
    "ImmuneSystemScanner",
]
