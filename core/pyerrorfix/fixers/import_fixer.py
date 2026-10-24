"""Remove unused imports + sort imports (isort-lite, zero-dependency)."""

from __future__ import annotations

import ast
import re

from pyerrorfix.fixers.base import BaseFixer


class UnusedImportFixer(BaseFixer):
    name = "unused-import"
    applies_to = {"unused-import"}

    def apply(self) -> str:
        issues = self.relevant_issues()
        if not issues:
            return self.source
        # gather (line, name) of unused imports flagged
        to_remove: set[tuple[int, str]] = set()
        for i in issues:
            # crude: the suggestion contains the import name; otherwise use line only
            to_remove.add((i.line, i.rule_id))
        lines = self._lines()
        out: list[str] = []
        for idx, line in enumerate(lines, start=1):
            # skip whole-line removal only if it's an unused import *and* single-name import
            if (idx, "unused-import") in to_remove and _is_single_import(line):
                continue
            out.append(line)
        return "".join(out)


class ImportSortFixer(BaseFixer):
    name = "import-sort"
    applies_to: set[str] = set()

    def apply(self) -> str:
        try:
            tree = ast.parse(self.source)
        except SyntaxError:
            return self.source
        lines = self._lines()
        # collect leading import block
        first_import: int | None = None
        last_import: int | None = None
        for node in tree.body:
            if isinstance(node, ast.Import | ast.ImportFrom):
                if first_import is None:
                    first_import = node.lineno
                last_import = node.end_lineno or node.lineno
        if first_import is None:
            return self.source
        # extract the block
        block = lines[first_import - 1 : last_import]
        # split into stdlib / third-party / local groups
        stdlib, thirdparty, local = [], [], []
        for ln in block:
            stripped = ln.lstrip()
            if not stripped or stripped.startswith("#"):
                continue
            mod = _module_of(stripped)
            if mod in _STDLIB_TOP:
                stdlib.append(ln)
            elif mod and (mod.startswith(".") or mod.startswith("src")):
                local.append(ln)
            else:
                thirdparty.append(ln)
        # sort each group
        stdlib.sort()
        thirdparty.sort()
        local.sort()
        new_block: list[str] = []
        if stdlib:
            new_block.extend(sorted(stdlib))
            new_block.append("\n")
        if thirdparty:
            new_block.extend(sorted(thirdparty))
            new_block.append("\n")
        if local:
            new_block.extend(sorted(local))
        # ensure trailing newline consistency
        if not new_block or not new_block[-1].endswith("\n"):
            new_block.append("\n" if new_block else "")
        return (
            "".join(lines[: first_import - 1]) + "".join(new_block) + "".join(lines[last_import:])
        )


def _is_single_import(line: str) -> bool:
    s = line.strip()
    return s.startswith("import ") or s.startswith("from ")


def _module_of(import_line: str) -> str:
    m = re.match(r"from\s+([a-zA-Z0-9_\.]+)\s+import", import_line)
    if m:
        return m.group(1).split(".")[0]
    m = re.match(r"import\s+([a-zA-Z0-9_\.]+)", import_line)
    if m:
        return m.group(1).split(".")[0]
    return ""


# Subset of stdlib top-level names used for grouping (see detectors/imports.py for full set).
_STDLIB_TOP = {
    "abc",
    "argparse",
    "ast",
    "asyncio",
    "base64",
    "binascii",
    "collections",
    "concurrent",
    "contextlib",
    "contextvars",
    "copy",
    "csv",
    "dataclasses",
    "datetime",
    "decimal",
    "difflib",
    "enum",
    "functools",
    "hashlib",
    "heapq",
    "html",
    "http",
    "importlib",
    "inspect",
    "io",
    "ipaddress",
    "itertools",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "pickle",
    "re",
    "secrets",
    "shutil",
    "signal",
    "socket",
    "sqlite3",
    "ssl",
    "statistics",
    "string",
    "struct",
    "subprocess",
    "sys",
    "tempfile",
    "textwrap",
    "threading",
    "time",
    "timeit",
    "token",
    "tokenize",
    "traceback",
    "types",
    "typing",
    "unicodedata",
    "unittest",
    "urllib",
    "uuid",
    "warnings",
    "weakref",
    "xml",
    "zipfile",
    "zlib",
    "zoneinfo",
}
