"""SEC-002: No Secret Hardcoding (API Keys, Tokens, Passwords)."""

from __future__ import annotations

import re
from pathlib import Path

from ..models import AuditFinding, RuleCategory, RuleDefinition, Severity
from .base import BaseRule


class NoSecretHardcodingRule(BaseRule):
    """Detects hardcoded secrets, API keys, tokens, and credentials."""

    DEFINITION = RuleDefinition(
        rule_id="SEC-002",
        category=RuleCategory.SECURITY,
        title="No Secret Hardcoding",
        description="Code must not contain hardcoded API keys, tokens, passwords, or private credentials.",
        severity=Severity.BLOCK,
        fixable=False,
        details="Secrets must be stored in environment variables or secure vaults like Infisical.",
    )

    # Patterns to detect hardcoded secrets
    SECRET_PATTERNS = [
        (r'["\']sk[-_]?[a-z0-9]{20,}["\']', "OpenAI/Stripe secret key"),
        (r'["\']pk[-_]?[a-z0-9]{20,}["\']', "Stripe public key"),
        (r'["\']ghp_[a-zA-Z0-9]{36}["\']', "GitHub Personal Access Token"),
        (r'["\']ghu_[a-zA-Z0-9]{36}["\']', "GitHub OAuth token"),
        (r'api[_-]?key\s*[=:]\s*["\'][^"\']{20,}["\']', "API key assignment"),
        (r'password\s*[=:]\s*["\'][^"\']{8,}["\']', "Password assignment"),
        (r'token\s*[=:]\s*["\'][^"\']{20,}["\']', "Token assignment"),
        (r'secret\s*[=:]\s*["\'][^"\']{20,}["\']', "Secret assignment"),
        (r'Authorization:\s*Bearer\s+[a-zA-Z0-9._-]{20,}', "Bearer token"),
    ]

    def __init__(self):
        """Initialize the rule."""
        super().__init__(self.DEFINITION)

    def audit(self, files: list[Path]) -> list[AuditFinding]:
        """Scan files for hardcoded secrets."""
        findings = []

        for file_path in files:
            if self.should_skip_file(file_path):
                continue

            # Skip certain non-code files
            if file_path.suffix in [".md", ".txt", ".json", ".yml", ".yaml"]:
                continue

            findings.extend(self._check_file(file_path))

        return findings

    def _check_file(self, file_path: Path) -> list[AuditFinding]:
        """Check a single file for hardcoded secrets."""
        findings = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    # Skip comments
                    if line.strip().startswith("#"):
                        continue

                    for pattern, description in self.SECRET_PATTERNS:
                        if re.search(pattern, line, re.IGNORECASE):
                            # Reduce false positives by checking context
                            if self._is_false_positive(line):
                                continue

                            findings.append(
                                self._create_finding(
                                    file_path,
                                    line_number=line_num,
                                    message=f"Potential hardcoded secret detected ({description}): {line.strip()[:60]}...",
                                    remediation="Move to environment variable or use a secret manager (Infisical, AWS Secrets Manager, etc.)",
                                    confidence=0.85,
                                )
                            )

        except Exception:
            pass

        return findings

    def _is_false_positive(self, line: str) -> bool:
        """Check if this is likely a false positive."""
        # Mock/test values
        if any(x in line.lower() for x in ["mock", "test", "fake", "example", "dummy"]):
            return True

        # Variable definitions in examples
        if "=" in line and any(x in line for x in ["example", "demo", "tutorial"]):
            return True

        return False
