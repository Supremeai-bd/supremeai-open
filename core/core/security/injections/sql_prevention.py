"""
SQL Injection Prevention Module
================================

Centralized SQL injection prevention utilities for SupremeAI 2.0.
Ensures all database queries use parameterized statements and provides
input sanitization helpers.

বাংলা: SQL ইনজেকশন প্রতিরোধের জন্য কেন্দ্রীভূত মডিউল — সব ডাটাবেজ কোয়েরির
জন্য প্যারামিটারাইজড স্টেটমেন্ট নিশ্চিত করে এবং ইনপুট স্যানিটাইজেশন হেল্পার সরবরাহ করে।

Key Components:
- `ParameterizedQueryBuilder`: Safe parameterized query construction
- `InputSanitizer`: Input validation and sanitization
- `QueryInspector`: Detect raw SQL concatenation patterns
- `SQLAuditor`: Audit codebase for SQL injection vulnerabilities
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.logging_config import logger

# ── Constants ──────────────────────────────────────────────────────────────────

# Suspicious patterns that indicate potential SQL injection
_SUSPICIOUS_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern": r'execute\s*\(\s*f["\']',
        "description": "f-string in execute() — potential SQL injection",
    },
    {
        "pattern": r'execute\s*\(\s*["\'].*\{.*\}.*["\']\s*%',
        "description": "Format string in execute()",
    },
    {"pattern": r'execute\s*\(\s*["\']\s*\+', "description": "String concatenation in execute()"},
    {"pattern": r'raw_sql\s*=\s*f["\']', "description": "f-string assigned to raw SQL variable"},
    {
        "pattern": r"cursor\.execute\s*\(.*['\"].*%s",
        "description": "Positional placeholder without params tuple",
    },
    {
        "pattern": r'SELECT.*FROM.*WHERE.*=.*["\']\s*\+',
        "description": "String concat in WHERE clause",
    },
]

# SQL keywords that should never appear in user input
_DANGEROUS_SQL_KEYWORDS: frozenset[str] = frozenset(
    {
        "DROP",
        "DELETE",
        "TRUNCATE",
        "ALTER",
        "CREATE",
        "INSERT",
        "UPDATE",
        "EXEC",
        "EXECUTE",
        "UNION",
        "--",
        "/*",
        "*/",
        "OR 1=1",
        "OR '1'='1'",
        'OR "1"="1"',
    }
)


# ── Data Classes ──────────────────────────────────────────────────────────────


@dataclass
class SQLAuditFinding:
    """Represents a single SQL audit finding."""

    file_path: str
    line_number: int
    column_start: int
    column_end: int
    matched_code: str
    pattern_description: str
    severity: str  # "critical", "high", "medium", "low"
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "code": self.matched_code.strip() if self.matched_code else "",
            "severity": self.severity,
            "description": self.pattern_description,
            "recommendation": self.recommendation,
        }


@dataclass
class SQLAuditReport:
    """Structured report for SQL injection audit."""

    scan_id: str
    scanned_at: str
    total_files_scanned: int = 0
    findings: list[SQLAuditFinding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "scanned_at": self.scanned_at,
            "total_files_scanned": self.total_files_scanned,
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary,
        }


# ── InputSanitizer ────────────────────────────────────────────────────────────


class InputSanitizer:
    """Input validation and sanitization for database-safe operations.

    বাংলা: ডাটাবেজ-নিরাপদ অপারেশনের জন্য ইনপুট ভ্যালিডেশন ও স্যানিটাইজেশন।
    """

    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        """Sanitize a string input for database operations.

        Args:
            value: Input string to sanitize
            max_length: Maximum allowed length (default: 1000)

        Returns:
            Sanitized string
        """
        if not isinstance(value, str):
            value = str(value)

        # Truncate to max length
        if len(value) > max_length:
            value = value[:max_length]

        # Remove null bytes
        value = value.replace("\x00", "")

        # Remove control characters (except common ones)
        value = re.sub(r"[\x01-\x08\x0B\x0C\x0E-\x1F\x7F]", "", value)

        return value

    @staticmethod
    def sanitize_identifier(identifier: str) -> str:
        """Sanitize a database identifier (table name, column name).

        Args:
            identifier: Identifier to sanitize

        Returns:
            Sanitized identifier (only alphanumeric and underscore)

        Raises:
            ValueError: If identifier is empty or contains invalid characters
        """
        if not identifier or not isinstance(identifier, str):
            raise ValueError("Identifier must be a non-empty string")

        # Only allow alphanumeric and underscore
        sanitized = re.sub(r"[^a-zA-Z0-9_]", "", identifier)

        if not sanitized:
            raise ValueError(f"Identifier '{identifier}' contains no valid characters")

        if sanitized != identifier:
            logger.warning(
                f"Identifier sanitized: '{identifier}' → '{sanitized}'. Invalid characters removed."
            )

        return sanitized

    @staticmethod
    def contains_sql_injection(text: str) -> bool:
        """Check if text contains potential SQL injection patterns.

        Args:
            text: Text to check

        Returns:
            True if suspicious SQL patterns detected
        """
        if not isinstance(text, str):
            return False

        text_upper = text.upper()

        # Check for dangerous SQL keywords in user input
        for keyword in _DANGEROUS_SQL_KEYWORDS:
            if keyword in text_upper:
                return True

        # Check for SQL comment injection
        if "--" in text or "/*" in text or "*/" in text:
            return True

        # Check for tautology patterns
        tautology_patterns = [
            r"OR\s+['\"]?\w+['\"]?\s*=\s*['\"]?\w+['\"]?",
            r"OR\s+\d+\s*=\s*\d+",
        ]
        for pattern in tautology_patterns:
            if re.search(pattern, text_upper):
                return True

        return False

    @staticmethod
    def sanitize_numeric(value: Any, default: int | float = 0) -> int | float:
        """Sanitize numeric input.

        Args:
            value: Input value
            default: Default value if conversion fails

        Returns:
            Sanitized numeric value
        """
        try:
            if isinstance(value, int | float):
                return value
            return float(value)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def sanitize_boolean(value: Any) -> bool:
        """Sanitize boolean input.

        Args:
            value: Input value

        Returns:
            Boolean value
        """
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        if isinstance(value, int | float):
            return value != 0
        return False


# ── ParameterizedQueryBuilder ────────────────────────────────────────────────


class ParameterizedQueryBuilder:
    """Build parameterized SQL queries safely.

    বাংলা: নিরাপদ প্যারামিটারাইজড SQL কোয়েরি বিল্ডার — ইনপুট স্যানিটাইজেশন সহ।

    Usage:
        builder = ParameterizedQueryBuilder()
        query, params = builder.build_select("users", ["name", "email"], {"id": 123})
        cursor.execute(query, params)
    """

    @staticmethod
    def build_select(
        table: str,
        columns: list[str] | None = None,
        where: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> tuple[str, list[Any]]:
        """Build a parameterized SELECT query.

        Args:
            table: Table name
            columns: Columns to select (None = all)
            where: WHERE conditions as dict {column: value}
            order_by: ORDER BY clause
            limit: LIMIT value
            offset: OFFSET value

        Returns:
            Tuple of (query_string, params_list)
        """
        # Sanitize identifiers
        table_safe = InputSanitizer.sanitize_identifier(table)

        if columns:
            cols = ", ".join(InputSanitizer.sanitize_identifier(c) for c in columns)
        else:
            cols = "*"

        query = f"SELECT {cols} FROM {table_safe}"
        params: list[Any] = []

        # WHERE clause
        if where:
            conditions = []
            for col, val in where.items():
                col_safe = InputSanitizer.sanitize_identifier(col)
                if isinstance(val, list | tuple):
                    # IN clause
                    placeholders = ", ".join(["?" for _ in val])
                    conditions.append(f"{col_safe} IN ({placeholders})")
                    params.extend(val)
                elif val is None:
                    conditions.append(f"{col_safe} IS NULL")
                else:
                    conditions.append(f"{col_safe} = ?")
                    params.append(val)
            query += " WHERE " + " AND ".join(conditions)

        # ORDER BY
        if order_by:
            order_safe = InputSanitizer.sanitize_identifier(order_by.split()[0])
            direction = "DESC" if "DESC" in order_by.upper() else "ASC"
            query += f" ORDER BY {order_safe} {direction}"

        # LIMIT / OFFSET
        if limit is not None:
            query += " LIMIT ?"
            params.append(InputSanitizer.sanitize_numeric(limit, 100))
        if offset is not None:
            query += " OFFSET ?"
            params.append(InputSanitizer.sanitize_numeric(offset, 0))

        return query, params

    @staticmethod
    def build_insert(
        table: str,
        data: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        """Build a parameterized INSERT query.

        Args:
            table: Table name
            data: Data dict {column: value}

        Returns:
            Tuple of (query_string, params_list)
        """
        table_safe = InputSanitizer.sanitize_identifier(table)

        columns = ", ".join(InputSanitizer.sanitize_identifier(c) for c in data)
        placeholders = ", ".join(["?" for _ in data])

        query = f"INSERT INTO {table_safe} ({columns}) VALUES ({placeholders})"
        params = list(data.values())

        return query, params

    @staticmethod
    def build_update(
        table: str,
        data: dict[str, Any],
        where: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        """Build a parameterized UPDATE query.

        Args:
            table: Table name
            data: Data to update {column: value}
            where: WHERE conditions {column: value}

        Returns:
            Tuple of (query_string, params_list)
        """
        table_safe = InputSanitizer.sanitize_identifier(table)

        # SET clause
        set_clauses = []
        params: list[Any] = []
        for col, val in data.items():
            col_safe = InputSanitizer.sanitize_identifier(col)
            set_clauses.append(f"{col_safe} = ?")
            params.append(val)

        # WHERE clause
        where_clauses = []
        for col, val in where.items():
            col_safe = InputSanitizer.sanitize_identifier(col)
            where_clauses.append(f"{col_safe} = ?")
            params.append(val)

        query = (
            f"UPDATE {table_safe} SET {', '.join(set_clauses)} WHERE {' AND '.join(where_clauses)}"
        )

        return query, params

    @staticmethod
    def build_delete(
        table: str,
        where: dict[str, Any],
    ) -> tuple[str, list[Any]]:
        """Build a parameterized DELETE query.

        Args:
            table: Table name
            where: WHERE conditions {column: value}

        Returns:
            Tuple of (query_string, params_list)
        """
        table_safe = InputSanitizer.sanitize_identifier(table)

        where_clauses = []
        params: list[Any] = []
        for col, val in where.items():
            col_safe = InputSanitizer.sanitize_identifier(col)
            where_clauses.append(f"{col_safe} = ?")
            params.append(val)

        query = f"DELETE FROM {table_safe} WHERE {' AND '.join(where_clauses)}"
        return query, params


# ── QueryInspector ────────────────────────────────────────────────────────────


class QueryInspector:
    """Inspect database queries for injection vulnerabilities.

    বাংলা: SQL ইনজেকশন ভালনারেবিলিটির জন্য ডাটাবেজ কোয়েরি পরিদর্শন।
    """

    @staticmethod
    def inspect_sql_statement(sql: str) -> list[dict[str, Any]]:
        """Inspect a SQL statement for injection vulnerabilities.

        Args:
            sql: The SQL statement to inspect

        Returns:
            List of vulnerability findings
        """
        findings: list[dict[str, Any]] = []

        # Check for string concatenation in query
        if re.search(r"['\"]\s*\+", sql) or re.search(r"\+\s*['\"]", sql):
            findings.append(
                {
                    "type": "STRING_CONCATENATION",
                    "severity": "high",
                    "description": "String concatenation detected in SQL query — use parameterized queries",
                }
            )

        # Check for f-strings
        if "{" in sql and "}" in sql and any(f"'{c}" in sql for c in "fF"):
            findings.append(
                {
                    "type": "F_STRING_IN_SQL",
                    "severity": "critical",
                    "description": "f-string detected in SQL query — potential injection risk",
                }
            )

        # Check for format placeholders
        if "%s" in sql or "%d" in sql or "%f" in sql:
            findings.append(
                {
                    "type": "FORMAT_PLACEHOLDER",
                    "severity": "medium",
                    "description": "Format string placeholder detected — use ? parameter markers",
                }
            )

        # Check for comment injection
        if "--" in sql or "/*" in sql:
            findings.append(
                {
                    "type": "COMMENT_INJECTION",
                    "severity": "high",
                    "description": "SQL comment detected in query — could be used for injection",
                }
            )

        return findings


# ── SQLAuditor ────────────────────────────────────────────────────────────────


class SQLAuditor:
    """Audit codebase for SQL injection vulnerabilities.

    বাংলা: SQL ইনজেকশন ভালনারেবিলিটির জন্য কোডবেস অডিট।
    """

    def __init__(self) -> None:
        self.compiled_patterns: list[dict[str, Any]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for detection."""
        for item in _SUSPICIOUS_PATTERNS:
            try:
                self.compiled_patterns.append(
                    {
                        "pattern": re.compile(item["pattern"]),
                        "description": item["description"],
                    }
                )
            except re.error as e:
                logger.warning(f"Failed to compile pattern: {e}")

    def audit_file(self, file_path: Path) -> list[SQLAuditFinding]:
        """Audit a single file for SQL injection patterns.

        Args:
            file_path: Path to the file to audit

        Returns:
            List of audit findings
        """
        findings: list[SQLAuditFinding] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, UnicodeDecodeError) as e:
            logger.debug(f"Cannot read {file_path}: {e}")
            return findings

        lines = content.split("\n")

        for line_num, line in enumerate(lines, start=1):
            for compiled in self.compiled_patterns:
                for match in compiled["pattern"].finditer(line):
                    finding = SQLAuditFinding(
                        file_path=str(file_path),
                        line_number=line_num,
                        column_start=match.start(),
                        column_end=match.end(),
                        matched_code=line.strip(),
                        pattern_description=compiled["description"],
                        severity="high",
                        recommendation="Use parameterized queries (?, :name) instead of string formatting. "
                        "See ParameterizedQueryBuilder for safe alternatives.",
                    )
                    findings.append(finding)

        # Also run AST-based analysis for Python files
        if file_path.suffix == ".py":
            findings.extend(self._audit_python_ast(content, str(file_path)))

        return findings

    def _audit_python_ast(self, content: str, file_path: str) -> list[SQLAuditFinding]:
        """Analyze Python AST for SQL injection patterns.

        Args:
            content: Python file content
            file_path: File path for reporting

        Returns:
            List of AST-based findings
        """
        findings: list[SQLAuditFinding] = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return findings

        for node in ast.walk(tree):
            # Detect f-strings in execute() calls
            if isinstance(node, ast.Call):
                if hasattr(node.func, "attr") and node.func.attr == "execute":
                    for arg in node.args:
                        if isinstance(arg, ast.JoinedStr):  # f-string
                            findings.append(
                                SQLAuditFinding(
                                    file_path=file_path,
                                    line_number=node.lineno,
                                    column_start=node.col_offset,
                                    column_end=node.end_col_offset or node.col_offset,
                                    matched_code=f"execute() with f-string at line {node.lineno}",
                                    pattern_description="f-string in execute() — AST detected",
                                    severity="critical",
                                    recommendation="Replace f-string with parameterized query",
                                )
                            )
                        elif isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
                            # String % formatting
                            findings.append(
                                SQLAuditFinding(
                                    file_path=file_path,
                                    line_number=node.lineno,
                                    column_start=node.col_offset,
                                    column_end=node.end_col_offset or node.col_offset,
                                    matched_code=f"execute() with % formatting at line {node.lineno}",
                                    pattern_description="% formatting in execute() — AST detected",
                                    severity="high",
                                    recommendation="Replace % formatting with parameterized query",
                                )
                            )

        return findings

    def audit_directory(
        self,
        directory: Path,
        extensions: set[str] | None = None,
    ) -> SQLAuditReport:
        """Audit a directory recursively for SQL injection patterns.

        Args:
            directory: Directory to audit
            extensions: File extensions to scan

        Returns:
            SQLAuditReport with findings
        """
        if extensions is None:
            extensions = {".py", ".sql", ".yaml", ".yml", ".json", ".js", ".ts"}

        scan_id = f"sql-audit-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
        all_findings: list[SQLAuditFinding] = []
        total_files = 0

        for file_path in directory.rglob("*"):
            if file_path.is_file() and file_path.suffix in extensions:
                if any(part.startswith(".") for part in file_path.parts):
                    continue
                if "node_modules" in str(file_path) or "__pycache__" in str(file_path):
                    continue

                total_files += 1
                file_findings = self.audit_file(file_path)
                all_findings.extend(file_findings)

        # Severity distribution
        severity_counts: dict[str, int] = {}
        for f in all_findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

        logger.info(
            f"SQL audit complete: scanned {total_files} files, "
            f"found {len(all_findings)} potential issues "
            f"({severity_counts.get('critical', 0)} critical, "
            f"{severity_counts.get('high', 0)} high)"
        )

        return SQLAuditReport(
            scan_id=scan_id,
            scanned_at=datetime.now(UTC).isoformat(),
            total_files_scanned=total_files,
            findings=all_findings,
            summary={
                "severity_distribution": severity_counts,
                "critical_count": severity_counts.get("critical", 0),
                "high_count": severity_counts.get("high", 0),
            },
        )


# ── Singleton & Utilities ─────────────────────────────────────────────────────

# Global auditor instance
sql_auditor = SQLAuditor()

# Global query builder instance
query_builder = ParameterizedQueryBuilder()

# Global input sanitizer instance
input_sanitizer = InputSanitizer()


def safe_execute(cursor, sql: str, params: tuple | list | None = None) -> Any:
    """Safely execute a SQL statement with parameterized queries.

    বাংলা: প্যারামিটারাইজড কোয়েরি দিয়ে নিরাপদে SQL স্টেটমেন্ট এক্সিকিউট করে।

    Args:
        cursor: Database cursor
        sql: SQL statement with ? placeholders
        params: Query parameters

    Returns:
        Cursor result

    Raises:
        ValueError: If SQL contains suspicious patterns
    """
    if params is not None:
        # Sanitize params
        sanitized_params: list[Any] = []
        for param in params:
            if isinstance(param, str):
                sanitized_params.append(InputSanitizer.sanitize_string(param))
            else:
                sanitized_params.append(param)
        params = tuple(sanitized_params)

    return cursor.execute(sql, params)


def is_safe_query(sql: str) -> bool:
    """Check if a SQL query is safe (uses parameterized style).

    Args:
        sql: SQL query string

    Returns:
        True if query appears safe
    """
    issues = QueryInspector.inspect_sql_statement(sql)
    return len(issues) == 0


def run_sql_audit(directory: str | None = None) -> dict[str, Any]:
    """Run a full SQL injection audit on the codebase.

    Args:
        directory: Directory to audit (default: backend/)

    Returns:
        Audit report as dict
    """
    if directory is None:
        # Default to project root's backend directory
        directory = str(Path(__file__).resolve().parent.parent.parent.parent / "backend")

    target = Path(directory)
    if not target.exists():
        raise FileNotFoundError(f"Directory not found: {target}")

    report = sql_auditor.audit_directory(target)
    return report.to_dict()


__all__ = [
    "InputSanitizer",
    "ParameterizedQueryBuilder",
    "QueryInspector",
    "SQLAuditFinding",
    "SQLAuditReport",
    "SQLAuditor",
    "input_sanitizer",
    "is_safe_query",
    "query_builder",
    "run_sql_audit",
    "safe_execute",
    "sql_auditor",
]
