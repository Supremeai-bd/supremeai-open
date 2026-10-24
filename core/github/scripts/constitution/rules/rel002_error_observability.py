"""Detect broad exception handlers without observable handling."""
from pathlib import Path
import ast
from ..models import RuleCategory, RuleDefinition, Severity
from .base import BaseRule


class ErrorObservabilityRule(BaseRule):
    def __init__(self):
        super().__init__(RuleDefinition(
            rule_id="REL-002",
            category=RuleCategory.RELIABILITY,
            title="Errors Must Be Observable",
            description="Production-critical exception paths must log, report, or re-raise errors.",
            severity=Severity.WARN,
        ))

    def audit(self, files: list[Path]):
        findings = []
        for path in files:
            if self.should_skip_file(path):
                continue
            for node, line in self._extract_ast_nodes(path, ast.Try):
                for handler in node.handlers:
                    if not handler.body or not any(isinstance(n, (ast.Raise, ast.Call)) for stmt in handler.body for n in ast.walk(stmt)):
                        findings.append(self._create_finding(path, line, "Exception handler has no observable action.", "except block", "Log with context, emit telemetry, or re-raise the exception."))
        return findings


__all__ = ["ErrorObservabilityRule"]
