"""Core data model: Issue, Severity, Category, ScanResult.

The Issue dataclass is the single contract consumed by every detector, every
fixer, every reporter and every external caller (the Next.js dashboard, the
GitHub Action, SARIF output, etc.). Keeping it stable and self-describing is
what makes the tool reusable across projects and pipelines.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    """Issue severity, ordered low → high. Inherits str so JSON-serialisable."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Category(StrEnum):
    """Top-level error families. Mirrors the user's Bengali taxonomy + added ones."""

    CORE_PYTHON = "core-python"
    IMPORTS = "imports"
    FILES = "files"
    ASYNCIO = "asyncio"
    DATABASE = "database"
    WEB_API = "web-api"
    CONCURRENCY = "concurrency"  # NEW
    TYPING = "typing"  # NEW
    SECURITY = "security"  # NEW
    RESOURCES = "resources"  # NEW
    DEPRECATION = "deprecation"  # NEW
    LOGGING = "logging"  # NEW


@dataclass
class Issue:
    """A single detected problem with optional auto-fix metadata.

    Fields are intentionally flat & primitive so the object round-trips cleanly
    through JSON for the dashboard, SARIF for GitHub, and console for humans.
    """

    rule_id: str  # e.g. "missing-await"
    code: str  # canonical exception/error name e.g. "RuntimeWarning"
    category: Category
    severity: Severity
    title: str  # short one-liner
    message: str  # human-readable explanation
    file: str  # filename or "<stdin>"
    line: int  # 1-based
    col: int = 0  # 1-based, 0 if unknown
    end_line: int = 0
    end_col: int = 0
    snippet: str = ""  # offending source line(s)
    fixable: bool = False
    fix_description: str = ""  # what the fixer will do
    suggestion: str = ""  # suggested replacement (code)
    detector: str = ""  # which detector produced it

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["severity"] = self.severity.value
        return d


@dataclass
class ScanResult:
    """Aggregated output of a scan: the issues + the (optionally) fixed source."""

    issues: list[Issue] = field(default_factory=list)
    fixed_source: str | None = None  # set when --fix requested
    files_scanned: int = 0
    elapsed_ms: int = 0

    @property
    def summary(self) -> dict[str, int]:
        total = len(self.issues)
        by_sev = {s.value: 0 for s in Severity}
        fixable = 0
        for i in self.issues:
            by_sev[i.severity.value] += 1
            if i.fixable:
                fixable += 1
        return {
            "total": total,
            "errors": by_sev[Severity.ERROR.value] + by_sev[Severity.CRITICAL.value],
            "warnings": by_sev[Severity.WARNING.value],
            "info": by_sev[Severity.INFO.value],
            "fixable": fixable,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "fixed_code": self.fixed_source,
            "files_scanned": self.files_scanned,
            "summary": self.summary,
        }
