"""Syntax / Indentation / Tab error detector.

These cannot be caught by AST visitors (the AST never builds), so this detector
parses with a real compile() and inspects the resulting SyntaxError details.
It also uses ``tokenize`` to find mixed tab/space usage.
"""

from __future__ import annotations

import asyncio
import io
import tokenize

from pyerrorfix.core.issue import Category, Issue, Severity
from pyerrorfix.detectors.base import BaseDetector


class SyntaxDetector(BaseDetector):
    name = "syntax"

    def run(self) -> list[Issue]:  # type: ignore[override]
        self._check_compile()
        self._check_token_consistency()
        return self.issues

    def _check_compile(self) -> None:
        # Only syntax-check Python files — Dockerfiles/Nginx configs/etc. are
        # handled by their own detectors (e.g. InfraDeployDetector).
        if not _is_python_file(self.filename):
            return
        try:
            compile(self.source, self.filename, "exec")
            return
        except SyntaxError as exc:
            # Classify: IndentationError vs TabError vs generic SyntaxError.
            text = exc.msg or ""
            if isinstance(exc, IndentationError) and not isinstance(exc, TabError):
                code = "IndentationError"
                rule = "indentation-error"
                title = "Indentation error"
                msg = f"Wrong indentation: {text}. Use 4 spaces per level consistently."
                fix = "Re-indent to 4 spaces per level."
            elif isinstance(exc, TabError):
                code = "TabError"
                rule = "tab-error"
                title = "Mixed tabs and spaces"
                msg = f"Tabs and spaces mixed: {text}. Pick one (spaces recommended)."
                fix = "Convert all tabs to spaces."
            else:
                code = "SyntaxError"
                rule = "syntax-error"
                title = "Syntax error"
                msg = f"Grammar mistake or typo: {text}"
                fix = "Fix the syntax as described."
            line = exc.lineno or 0
            snippet = (exc.text or "").rstrip("\n")
            self.issues.append(
                Issue(
                    rule_id=rule,
                    code=code,
                    category=Category.CORE_PYTHON,
                    severity=self.severity(rule, Severity.ERROR),
                    title=title,
                    message=msg,
                    file=self.filename,
                    line=line,
                    col=exc.offset or 0,
                    end_line=line,
                    end_col=(exc.offset or 0)
                    + (len(exc.text) - (exc.text or "").lstrip().count(" ") if exc.text else 0),
                    snippet=snippet,
                    fixable=True,
                    fix_description=fix,
                    suggestion="",
                    detector=self.name,
                )
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")

    def _check_token_consistency(self) -> None:
        """tokenize catches inconsistent leading whitespace that compile misses."""
        if not _is_python_file(self.filename):
            return
        try:
            tokens = tokenize.generate_tokens(io.StringIO(self.source).readline)
            for tok in tokens:
                if tok.type == tokenize.ERRORTOKEN:
                    # Already surfaced as SyntaxError typically; skip to avoid dupes.
                    break
                if tok.type == tokenize.INDENT and "\t" in tok.string and " " in tok.string:
                    self.issues.append(
                        Issue(
                            rule_id="tab-error",
                            code="TabError",
                            category=Category.CORE_PYTHON,
                            severity=Severity.ERROR,
                            title="Mixed tabs and spaces in indent",
                            message="Indent mixes tabs and spaces. Convert to spaces only.",
                            file=self.filename,
                            line=tok.start[0],
                            col=tok.start[1],
                            end_line=tok.end[0],
                            end_col=tok.end[1],
                            snippet=self.line_text(tok.start[0]),
                            fixable=True,
                            fix_description="Replace tabs with 4 spaces.",
                            detector=self.name,
                        )
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")


def _is_python_file(filename: str) -> bool:
    """Return True for .py files or stdin/inline sources.

    Other files (Dockerfile, *.conf, *.yml) are handled by their own detectors.
    """
    if not filename or filename in ("<stdin>", "<fixed>", "<string>"):
        return True
    lower = filename.lower()
    if lower.endswith(".py"):
        return True
    # anything with a non-python extension or named Dockerfile / *.conf / *.yml
    return False
