"""SEC-001: Backend Authorization Is Final (No Client-Only Permission Checks)."""

from __future__ import annotations

import re
from pathlib import Path

from ..models import AuditFinding, RuleCategory, RuleDefinition, Severity
from .base import BaseRule


class BackendAuthFinalRule(BaseRule):
    """Detects potential client-side-only authorization that bypasses server validation."""

    DEFINITION = RuleDefinition(
        rule_id="SEC-001",
        category=RuleCategory.SECURITY,
        title="Backend Authorization Is Final",
        description="Authorization decisions must be enforced on the backend; client-side checks are insufficient.",
        severity=Severity.WARN,  # WARN instead of BLOCK; advisor rule
        fixable=False,
        details="Frontend permission checks must always be validated by the backend.",
    )

    def __init__(self):
        """Initialize the rule."""
        super().__init__(self.DEFINITION)

    def audit(self, files: list[Path]) -> list[AuditFinding]:
        """Scan frontend files for client-only permission patterns."""
        findings = []

        for file_path in files:
            # Only check frontend files
            if "frontend" not in str(file_path) and "apps" not in str(file_path):
                continue

            if self.should_skip_file(file_path):
                continue

            if file_path.suffix not in [".ts", ".tsx", ".js", ".jsx"]:
                continue

            findings.extend(self._check_frontend_file(file_path))

        return findings

    def _check_frontend_file(self, file_path: Path) -> list[AuditFinding]:
        """Check frontend files for client-only auth patterns."""
        findings = []

        # Patterns that indicate client-side-only permission logic
        suspicious_patterns = [
            (r"if\s*\(\s*user\.role\s*===\s*['\"]admin['\"]", "Client-side role check"),
            (
                r"if\s*\(\s*!hasPermission\(\s*['\"][^'\"]+['\"]",
                "Client-side permission check",
            ),
            (
                r"if\s*\(\s*localStorage\.getItem\(['\"]token['\"]",
                "Relying on localStorage for auth",
            ),
        ]

        matches = self._find_in_file(
            file_path,
            r"(if|return|throw).*(?:role|permission|admin|auth)",
            exclude_patterns=[r"//.*(?:role|permission|auth)", r"api.*role"],
        )

        for line_num, line_text in matches:
            # Check if this looks like client-only validation
            if any(pattern[0] for pattern in suspicious_patterns if re.search(pattern[0], line_text)):
                findings.append(
                    self._create_finding(
                        file_path,
                        line_number=line_num,
                        message="Potential client-side-only authorization check detected.",
                        remediation="Verify that the backend also validates this permission before granting access.",
                        confidence=0.7,  # Lower confidence for advisory
                    )
                )

        return findings
