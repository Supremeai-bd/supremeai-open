"""Abstract base rule class for constitutional audit rules."""

from __future__ import annotations

import ast
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ..models import AuditFinding, RuleCategory, RuleDefinition, Severity


class BaseRule(ABC):
    """Abstract base for all constitutional rules."""

    def __init__(self, rule_definition: RuleDefinition):
        """Initialize with rule definition."""
        self.definition = rule_definition

    @abstractmethod
    def audit(self, files: list[Path]) -> list[AuditFinding]:
        """Run the audit on the given files. Must be implemented by subclass."""
        pass

    def _find_in_file(
        self,
        file_path: Path,
        pattern: str | re.Pattern,
        exclude_patterns: Optional[list[str | re.Pattern]] = None,
    ) -> list[tuple[int, str]]:
        """Find pattern matches in a file. Returns list of (line_number, line_text)."""
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        exclude_patterns = exclude_patterns or []
        compiled_excludes = [
            re.compile(p) if isinstance(p, str) else p for p in exclude_patterns
        ]

        matches = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line_num, line in enumerate(f, 1):
                    if pattern.search(line):
                        # Check if line should be excluded
                        if any(exc.search(line) for exc in compiled_excludes):
                            continue
                        matches.append((line_num, line.rstrip()))
        except Exception:
            # Silently skip files we can't read
            pass

        return matches

    def _extract_ast_nodes(
        self, file_path: Path, node_type: type
    ) -> list[tuple[ast.AST, int]]:
        """Extract AST nodes of a given type. Returns list of (node, line_number)."""
        nodes = []
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                tree = ast.parse(f.read())
            for node in ast.walk(tree):
                if isinstance(node, node_type):
                    nodes.append((node, node.lineno if hasattr(node, "lineno") else 1))
        except SyntaxError:
            # Skip files with syntax errors
            pass
        except Exception:
            # Skip files we can't parse
            pass

        return nodes

    def _get_git_diff_files(self, base_ref: str = "HEAD~1") -> list[Path]:
        """Get list of modified files from git diff. Returns absolute paths."""
        import subprocess

        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", base_ref, "HEAD"],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
                timeout=10,
            )
            if result.returncode == 0:
                files = [Path(line.strip()) for line in result.stdout.splitlines()]
                return [f for f in files if f.exists()]
        except Exception:
            pass

        return []

    def _create_finding(
        self,
        file_path: Path,
        line_number: Optional[int] = None,
        message: str = "",
        code_snippet: Optional[str] = None,
        remediation: Optional[str] = None,
        confidence: float = 1.0,
    ) -> AuditFinding:
        """Create a finding record."""
        return AuditFinding(
            rule_id=self.definition.rule_id,
            severity=self.definition.severity,
            file_path=str(file_path),
            line_number=line_number,
            message=message or self.definition.description,
            code_snippet=code_snippet,
            remediation=remediation,
            confidence=confidence,
        )

    def should_skip_file(self, file_path: Path) -> bool:
        """Override to skip certain file patterns. Default: skip tests and fixtures."""
        name = file_path.name.lower()
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or "fixture" in name
            or ".github" in str(file_path)
        )
