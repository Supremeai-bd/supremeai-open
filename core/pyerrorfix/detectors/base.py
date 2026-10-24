"""Base detector + shared AST helpers."""

from __future__ import annotations

import ast
import re

from pyerrorfix.core.issue import Category, Issue, Severity

# Pre-compiled common patterns ----------------------------------------------
_FSTRING_LOG_RE = re.compile(
    r"log(ger)?\.(debug|info|warning|warn|error|critical|exception)\(f[\"']"
)


class BaseDetector(ast.NodeVisitor):
    """Base class for AST-based detectors.

    Subclasses implement ``visit_*`` methods and call :meth:`add` for each
    finding. The :meth:`run` method compiles the source (capturing syntax
    errors), builds the AST and walks it.

    Detectors must be **pure**: no I/O, no network, deterministic. This is what
    makes them safe to run on untrusted user code in the dashboard.
    """

    name: str = "base"

    def __init__(self, source: str, filename: str = "<stdin>", config: dict | None = None) -> None:
        self.source = source
        self.filename = filename
        self.config = config or {}
        self._lines = source.splitlines()
        self.issues: list[Issue] = []

    # public API ------------------------------------------------------------
    def run(self) -> list[Issue]:
        try:
            tree = ast.parse(self.source, filename=self.filename)
        except SyntaxError:
            # SyntaxError is reported by the syntax detector, not here.
            return self.issues
        self.visit(tree)
        return self.issues

    # helpers ---------------------------------------------------------------
    def enabled(self, rule_id: str) -> bool:
        cfg = self.config.get(rule_id)
        if not cfg:
            return True
        return bool(cfg.get("enabled", True))

    def severity(self, rule_id: str, default: Severity) -> Severity:
        cfg = self.config.get(rule_id) or {}
        sev = cfg.get("severity")
        if sev and sev.upper() in Severity.__members__:
            return Severity[sev.upper()]
        return default

    def add(
        self,
        *,
        rule_id: str,
        code: str,
        category: Category,
        severity: Severity,
        title: str,
        message: str,
        node: ast.AST | None = None,
        snippet: str = "",
        fixable: bool = False,
        fix_description: str = "",
        suggestion: str = "",
    ) -> None:
        if not self.enabled(rule_id):
            return
        line, col, end_line, end_col = 0, 0, 0, 0
        if node is not None:
            line = getattr(node, "lineno", 0) or 0
            col = (getattr(node, "col_offset", 0) or 0) + 1
            end_line = getattr(node, "end_lineno", line) or line
            end_col = getattr(node, "end_col_offset", col) or col
        if not snippet and line and line - 1 < len(self._lines):
            snippet = self._lines[line - 1]
        self.issues.append(
            Issue(
                rule_id=rule_id,
                code=code,
                category=category,
                severity=self.severity(rule_id, severity),
                title=title,
                message=message,
                file=self.filename,
                line=line,
                col=col,
                end_line=end_line,
                end_col=end_col,
                snippet=snippet,
                fixable=fixable,
                fix_description=fix_description,
                suggestion=suggestion,
                detector=self.name,
            )
        )

    # source-line helpers ---------------------------------------------------
    def line_text(self, lineno: int) -> str:
        if 0 < lineno <= len(self._lines):
            return self._lines[lineno - 1]
        return ""

    def full_node_text(self, node: ast.AST) -> str:
        if not hasattr(node, "lineno"):
            return ""
        start = (getattr(node, "lineno", 1) or 1) - 1
        end = getattr(node, "end_lineno", start + 1) or start + 1
        return "\n".join(self._lines[start:end])


def iter_call_name(node: ast.AST) -> str | None:
    """Return dotted call name for ``foo.bar.baz()`` style calls, else None."""
    if isinstance(node, ast.Call):
        func = node.func
        parts: list[str] = []
        while isinstance(func, ast.Attribute):
            parts.append(func.attr)
            func = func.value
        if isinstance(func, ast.Name):
            parts.append(func.id)
            return ".".join(reversed(parts))
    return None
