"""Detect likely runtime policy constants that should be registry-backed."""
from pathlib import Path
import re
from ..models import RuleCategory, RuleDefinition, Severity
from .base import BaseRule


class NoPolicyHardcodingRule(BaseRule):
    def __init__(self):
        super().__init__(RuleDefinition(
            rule_id="CFG-001",
            category=RuleCategory.CONFIGURATION,
            title="Configuration/Policy Over Hardcoding",
            description="Runtime policy values must be sourced from the configuration control plane.",
            severity=Severity.WARN,
        ))

    def audit(self, files: list[Path]):
        findings = []
        pattern = re.compile(r"^\s*[A-Z][A-Z0-9_]*(?:MAX|MIN|LIMIT|TIMEOUT|ENABLED|CONCURRENCY|RETRY|QUOTA)[A-Z0-9_]*\s*=\s*(?:[0-9]+|True|False|['\"])" )
        for path in files:
            if self.should_skip_file(path) or "config_registry.py" in str(path):
                continue
            for line, text in self._find_in_file(path, pattern, [r"os\.environ", r"settings\."]):
                findings.append(self._create_finding(path, line, "Possible hardcoded runtime policy value; register it in the configuration schema.", text, "Add a registry key with immutable bounds and read it through ConfigService.", 0.8))
        return findings

    def should_skip_file(self, file_path: Path) -> bool:
        return super().should_skip_file(file_path) or "migration" in str(file_path).lower()


__all__ = ["NoPolicyHardcodingRule"]
