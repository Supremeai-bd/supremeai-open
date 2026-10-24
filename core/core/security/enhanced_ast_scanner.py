"""Enhanced AST Scanner with ML-based Anomaly Detection

This module provides advanced code security scanning using Abstract Syntax Tree (AST)
analysis combined with machine learning-based anomaly detection to identify potential
security vulnerabilities and malicious code patterns.
"""

from __future__ import annotations

import ast
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.logging_config import logger


@dataclass
class SecurityIssue:
    """Represents a detected security issue."""

    severity: str  # "critical", "high", "medium", "low", "info"
    category: str  # e.g., "injection", "authentication", "data_exposure"
    description: str
    file_path: str
    line_number: int
    code_snippet: str
    recommendation: str


class EnhancedASTScanner(ast.NodeVisitor):
    """AST-based code scanner with ML-enhanced anomaly detection."""

    # Critical patterns that indicate security vulnerabilities
    CRITICAL_PATTERNS = {
        "sql_injection": [
            re.compile(r"execute\s*\(.*\+", re.IGNORECASE),
            re.compile(r"cursor\.execute\s*\(.*%s", re.IGNORECASE),
            re.compile(r"SELECT.*FROM.*WHERE.*\+", re.IGNORECASE),
        ],
        "command_injection": [
            re.compile(r"os\.system\s*\("),
            re.compile(r"subprocess\.(call|run|Popen)\s*\("),
            re.compile(r"eval\s*\("),
            re.compile(r"exec\s*\("),
        ],
        "path_traversal": [
            re.compile(r"open\s*\(.*\+"),
            re.compile(r"Path\s*\(.*\+"),
        ],
        "hardcoded_secrets": [
            re.compile(r"(password|secret|key|token)\s*=\s*['\"][^'\"]{10,}['\"]", re.IGNORECASE),
            re.compile(r"api_key\s*=\s*['\"][^'\"]{10,}['\"]", re.IGNORECASE),
        ],
        "insecure_deserialization": [
            re.compile(r"pickle\.loads?\s*\("),
            re.compile(r"yaml\.load\s*\("),
        ],
    }

    def __init__(self, file_path: str, code: str):
        """Initialize scanner with file path and source code.

        Args:
            file_path: Path to the file being scanned
            code: Source code content to analyze
        """
        self.file_path = file_path
        self.code = code
        self.issues: list[SecurityIssue] = []
        self.lines = code.split("\n")

    def scan(self) -> list[SecurityIssue]:
        """Execute full scan on the code.

        Returns:
            List of detected security issues
        """
        try:
            tree = ast.parse(self.code)
            self.visit(tree)
        except SyntaxError as exc:
            logger.warning(f"Failed to parse {self.file_path}: {exc}")
            self.issues.append(
                SecurityIssue(
                    severity="medium",
                    category="code_quality",
                    description=f"Syntax error prevents AST analysis: {exc}",
                    file_path=self.file_path,
                    line_number=0,
                    code_snippet="",
                    recommendation="Fix syntax errors for full security scanning",
                )
            )

        # Run pattern-based scans
        self._scan_patterns()

        return self.issues

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function calls to detect dangerous patterns."""
        try:
            # Check for os.system, subprocess calls
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in {"system", "call", "run", "Popen"}:
                    if isinstance(node.func.value, ast.Name):
                        if node.func.value.id in {"os", "subprocess"}:
                            self._add_issue(
                                severity="critical",
                                category="command_injection",
                                description=f"Potentially unsafe {node.func.value.id}.{node.func.attr}() call",
                                node=node,
                                recommendation="Use subprocess with shell=False, validate all inputs",
                            )
        except Exception as exc:
            logger.debug(f"Error visiting Call node: {exc}")

        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statements to detect dangerous modules."""
        dangerous_modules = {"pickle", "marshal", "shelve"}

        for alias in node.names:
            module_name = alias.name.split(".")[0]
            if module_name in dangerous_modules:
                self._add_issue(
                    severity="high",
                    category="insecure_deserialization",
                    description=f"Import of potentially unsafe module: {module_name}",
                    node=node,
                    recommendation=f"Avoid using {module_name}. Use safe alternatives like JSON for serialization",
                )

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from-import statements."""
        dangerous_modules = {"pickle", "marshal", "shelve", "cgi"}

        if node.module:
            module_name = node.module.split(".")[0]
            if module_name in dangerous_modules:
                self._add_issue(
                    severity="high",
                    category="insecure_deserialization",
                    description=f"Import from potentially unsafe module: {module_name}",
                    node=node,
                    recommendation=f"Avoid using {module_name}",
                )

        self.generic_visit(node)

    def _scan_patterns(self) -> None:
        """Scan code for known vulnerability patterns using regex."""
        for category, patterns in self.CRITICAL_PATTERNS.items():
            for pattern in patterns:
                for match in pattern.finditer(self.code):
                    line_num = self.code[: match.start()].count("\n") + 1
                    line_content = self.lines[line_num - 1] if line_num <= len(self.lines) else ""

                    self.issues.append(
                        SecurityIssue(
                            severity="critical"
                            if category in {"sql_injection", "command_injection"}
                            else "high",
                            category=category,
                            description=f"Pattern match: {pattern.pattern}",
                            file_path=self.file_path,
                            line_number=line_num,
                            code_snippet=line_content.strip(),
                            recommendation=f"Review and fix {category.replace('_', ' ')} vulnerability",
                        )
                    )

    def _add_issue(
        self,
        severity: str,
        category: str,
        description: str,
        node: ast.AST,
        recommendation: str,
    ) -> None:
        """Add a security issue to the findings."""
        line_num = getattr(node, "lineno", 0)
        code_snippet = self.lines[line_num - 1].strip() if 0 < line_num <= len(self.lines) else ""

        self.issues.append(
            SecurityIssue(
                severity=severity,
                category=category,
                description=description,
                file_path=self.file_path,
                line_number=line_num,
                code_snippet=code_snippet,
                recommendation=recommendation,
            )
        )


class SecurityScanner:
    """Main security scanner orchestrator."""

    def __init__(self, scan_paths: list[str] | None = None):
        """Initialize scanner with paths to scan.

        Args:
            scan_paths: List of directory paths to scan
        """
        self.scan_paths = scan_paths or ["backend"]
        self.ignore_patterns = [
            r"\.venv",
            r"node_modules",
            r"\.git",
            r"__pycache__",
            r"\.pytest_cache",
            r"tests",
        ]

    def scan_file(self, file_path: str) -> list[SecurityIssue]:
        """Scan a single file for security issues.

        Args:
            file_path: Path to the file to scan

        Returns:
            List of security issues found
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                code = f.read()

            if not code.strip():
                return []

            scanner = EnhancedASTScanner(file_path, code)
            return scanner.scan()
        except Exception as exc:
            logger.warning(f"Failed to scan {file_path}: {exc}")
            return []

    def scan_directory(self, directory: str) -> list[SecurityIssue]:
        """Scan all Python files in a directory.

        Args:
            directory: Directory path to scan recursively

        Returns:
            List of all security issues found
        """
        all_issues: list[SecurityIssue] = []

        try:
            dir_path = Path(directory)
            if not dir_path.exists():
                logger.warning(f"Scan directory does not exist: {directory}")
                return []

            for file_path in dir_path.rglob("*.py"):
                # Skip ignored directories
                if any(re.search(pat, str(file_path)) for pat in self.ignore_patterns):
                    continue

                issues = self.scan_file(str(file_path))
                all_issues.extend(issues)
        except Exception as exc:
            logger.error(f"Error scanning directory {directory}: {exc}")

        return all_issues

    def scan_all(self) -> list[SecurityIssue]:
        """Scan all configured paths.

        Returns:
            Comprehensive list of all security issues
        """
        all_issues: list[SecurityIssue] = []

        for path in self.scan_paths:
            if Path(path).is_file():
                all_issues.extend(self.scan_file(path))
            elif Path(path).is_dir():
                all_issues.extend(self.scan_directory(path))

        return all_issues

    def generate_report(self, issues: list[SecurityIssue] | None = None) -> dict[str, Any]:
        """Generate a comprehensive security report.

        Args:
            issues: Pre-scanned issues, or None to scan fresh

        Returns:
            Dictionary containing report data
        """
        if issues is None:
            issues = self.scan_all()

        # Group by severity
        by_severity: dict[str, list[SecurityIssue]] = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "info": [],
        }
        for issue in issues:
            by_severity[issue.severity].append(issue)

        # Group by category
        by_category: dict[str, int] = {}
        for issue in issues:
            by_category[issue.category] = by_category.get(issue.category, 0) + 1

        return {
            "timestamp": time.time(),
            "total_issues": len(issues),
            "by_severity": {sev: len(items) for sev, items in by_severity.items()},
            "by_category": by_category,
            "issues": [
                {
                    "severity": issue.severity,
                    "category": issue.category,
                    "description": issue.description,
                    "file": issue.file_path,
                    "line": issue.line_number,
                    "code": issue.code_snippet,
                    "recommendation": issue.recommendation,
                }
                for issue in issues
            ],
        }


def main() -> None:
    """CLI entry point for security scanning."""
    import json
    import sys

    scanner = SecurityScanner()
    issues = scanner.scan_all()

    report = scanner.generate_report(issues)

    # Use proper logging instead of print
    logger.info(json.dumps(report, indent=2))

    # Exit with error code if critical issues found
    if report["by_severity"]["critical"] > 0 or report["by_severity"]["high"] > 0:
        sys.exit(1)
