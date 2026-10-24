"""Convert `logger.info(f"x {y}")` → `logger.info('x %s', y)` (lazy logging)."""

from __future__ import annotations

import ast

from pyerrorfix.detectors.logging_err import _to_lazy_log
from pyerrorfix.fixers.base import BaseFixer


class FStringLogFixer(BaseFixer):
    name = "fstring-log"
    applies_to = {"fstring-in-logging"}

    def apply(self) -> str:
        issues = self.relevant_issues()
        if not issues:
            return self.source
        try:
            tree = ast.parse(self.source)
        except SyntaxError:
            return self.source
        # build map: (lineno, col) -> lazy replacement expression text
        edits: dict[tuple[int, int], str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.JoinedStr):
                if (node.lineno, node.col_offset) in {(i.line, i.col - 1) for i in issues}:
                    replacement = _to_lazy_log(node)
                    if replacement:
                        edits[(node.lineno, node.col_offset)] = replacement
        if not edits:
            return self.source
        # We need to replace the *whole* call expression, not just a prefix.
        # ast.Call end positions are reliable in 3.8+.
        lines = self._lines()
        # Apply from bottom up to keep offsets valid.
        for (lineno, col), repl in sorted(edits.items(), reverse=True):
            # find the matching call node to get end position
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.Call)
                    and node.lineno == lineno
                    and node.col_offset == col
                    and isinstance(node.args[0], ast.JoinedStr)
                ):
                    start_line, start_col = node.lineno - 1, node.col_offset
                    end_line, end_col = (
                        (node.end_lineno or node.lineno) - 1,
                        node.end_col_offset or 0,
                    )
                    break
            else:
                continue
            if start_line == end_line:
                line = lines[start_line]
                lines[start_line] = line[:start_col] + repl + line[end_col:]
            else:
                # multi-line call: replace the whole span
                first = lines[start_line][:start_col]
                last = lines[end_line][end_col:]
                lines[start_line : end_line + 1] = [first + repl + last]
        return "".join(lines)
