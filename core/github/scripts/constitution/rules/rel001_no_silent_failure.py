"""REL-001: No Silent Failure (Except/Catch Handlers Must Log or Re-raise)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ..models import AuditFinding, RuleCategory, RuleDefinition, Severity
from .base import BaseRule


class NoSilentFailureRule(BaseRule):
    """Detects empty exception handlers and silent failure patterns."""

    DEFINITION = RuleDefinition(
        rule_id="REL-001",
        category=RuleCategory.RELIABILITY,
        title="No Silent Failure",
        description="Exception handlers must not silently swallow errors; they must log or re-raise.",
        severity=Severity.BLOCK,
        fixable=False,
        details="Detected: except: pass, except Exception: pass, or catch {} blocks with no logging.",
    )

    def __init__(self):
        """Initialize the rule."""
        super().__init__(self.DEFINITION)

    def audit(self, files: list[Path]) -> list[AuditFinding]:
        """Scan files for silent failure patterns."""
        findings = []

        for file_path in files:
            if self.should_skip_file(file_path):
                continue

            # Determine file type
            if file_path.suffix == ".py":
                findings.extend(self._check_python_file(file_path))
            elif file_path.suffix in [".ts", ".tsx", ".js", ".jsx"]:
                findings.extend(self._check_typescript_file(file_path))

        return findings

    def _check_python_file(self, file_path: Path) -> list[AuditFinding]:
        """Check Python files for silent exception handlers."""
        findings = []

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read())

            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    # Check if handler body is just 'pass'
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        findings.append(
                            self._create_finding(
                                file_path,
                                line_number=node.lineno,
                                message="Silent exception handler detected (except: pass)",
                                remediation="Add logging: logger.exception(...) or re-raise the exception.",
                                confidence=0.98,
                            )
                        )
                    # Check for ellipsis-only handler
                    elif (
                        len(node.body) == 1
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and node.body[0].value.value is ...
                    ):
                        findings.append(
                            self._create_finding(
                                file_path,
                                line_number=node.lineno,
                                message="Silent exception handler detected (except: ...)",
                                remediation="Add logging or re-raise the exception.",
                                confidence=0.9,
                            )
                        )

        except SyntaxError:
            pass
        except Exception:
            pass

        return findings

    def _check_typescript_file(self, file_path: Path) -> list[AuditFinding]:
        """Check TypeScript/JavaScript files for silent catch handlers."""
        findings = []

        # Pattern for catch blocks with no body or only comments
        catch_pattern = re.compile(
            r"catch\s*\([^)]*\)\s*\{\s*(?://.*)?(?:/\*.*?\*/)?\s*\}",
            re.MULTILINE | re.DOTALL,
        )

        matches = self._find_in_file(file_path, catch_pattern)
        for line_num, line_text in matches:
            findings.append(
                self._create_finding(
                    file_path,
                    line_number=line_num,
                    message="Empty catch block detected",
                    remediation="Add error logging: console.error(...) or re-throw the error.",
                    confidence=0.85,
                )
            )

        return findings
