"""Detect obvious privilege-bypass patterns in application source."""
from pathlib import Path
import re
from ..models import RuleCategory, RuleDefinition, Severity
from .base import BaseRule


class UnsafePrivilegeElevationRule(BaseRule):
    def __init__(self):
        super().__init__(RuleDefinition(
            rule_id="SEC-003",
            category=RuleCategory.SECURITY,
            title="No Unsafe Privilege Elevation",
            description="Privilege elevation requires explicit authorization and least-privilege controls.",
            severity=Severity.BLOCK,
        ))

    def audit(self, files: list[Path]):
        findings = []
        patterns = [
            re.compile(r"\bchmod\s*\([^\n]*0?777"),
            re.compile(r"\bsudo\s+"),
            re.compile(r"\b(is_admin|is_superuser)\s*=\s*True\b"),
        ]
        for path in files:
            if self.should_skip_file(path):
                continue
            for pattern in patterns:
                for line, text in self._find_in_file(path, pattern):
                    findings.append(self._create_finding(path, line, "Potential privilege elevation or bypass detected; require explicit backend authorization.", text, "Replace the bypass with a centrally audited authorization dependency.", 0.9))
        return findings


__all__ = ["UnsafePrivilegeElevationRule"]
