"""Add missing `await` before known-coroutine calls."""

from __future__ import annotations

import ast

from pyerrorfix.fixers.base import BaseFixer


class AwaitFixer(BaseFixer):
    name = "await"
    applies_to = {"missing-await"}

    def apply(self) -> str:
        issues = self.relevant_issues()
        if not issues:
            return self.source
        try:
            tree = ast.parse(self.source)
        except SyntaxError:
            return self.source
        # build a set of (line, col) offsets where a coroutine call is missing await
        targets: set[tuple[int, int]] = set()
        for i in issues:
            if i.line and i.col:
                targets.add((i.line, i.col))
        if not targets:
            return self.source
        lines = self._lines()
        # Walk to find Call nodes whose position matches a flagged target
        # and insert 'await ' before them.
        edits: list[tuple[int, int]] = []  # (line_index, col_offset)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if (node.lineno, node.col_offset + 1) in targets or (
                    node.lineno,
                    node.col_offset,
                ) in targets:
                    if not _is_already_awaited(tree, node):
                        edits.append((node.lineno, node.col_offset))
        if not edits:
            return self.source
        edits.sort(reverse=True)  # apply from bottom up so offsets stay valid
        out = lines[:]
        for lineno, col in edits:
            idx = lineno - 1
            if 0 <= idx < len(out):
                line = out[idx]
                out[idx] = line[:col] + "await " + line[col:]
        return "".join(out)


def _is_already_awaited(tree: ast.AST, call: ast.Call) -> bool:
    for n in ast.walk(tree):
        if isinstance(n, ast.Await) and _contains(n.value, call):
            return True
    return False


def _contains(haystack: ast.AST, needle: ast.AST) -> bool:
    if haystack is needle:
        return True
    for child in ast.iter_child_nodes(haystack):
        if _contains(child, needle):
            return True
    return False
