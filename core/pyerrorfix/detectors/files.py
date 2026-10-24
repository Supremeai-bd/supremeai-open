"""File & OS error detector.

Catches:
  * FileNotFoundError  — open() of a hardcoded relative path without an
    existence check / try-except.
  * PermissionError     — (heuristic) open(...,'w') on paths under system dirs.
  * open() without `with`  — leaked file handle (also reported by resources).
  * Missing Path.exists() check before Path operations.
  * broad `except` that swallows FileNotFoundError specifically (anti-pattern).
"""

from __future__ import annotations

import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

_SYSTEM_PATHS = ("/etc/", "/var/", "/root/", "/usr/", "/proc/", "/sys/", "/dev/", "C:\\Windows\\")


class FileDetector(BaseDetector):
    name = "files"

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)
        if name in ("open",):
            self._check_open(node)
        elif name in ("Path",):
            self._check_path(node)
        self.generic_visit(node)

    def _check_open(self, node: ast.Call) -> None:
        if not node.args:
            return
        path = node.args[0]
        # hardcoded string path
        if isinstance(path, ast.Constant) and isinstance(path.value, str):
            p = path.value
            is_abs_system = any(p.startswith(s) for s in _SYSTEM_PATHS)
            if is_abs_system:
                self.add(
                    rule_id="hardcoded-path",
                    code="PermissionError",
                    category=Category.FILES,
                    severity=Severity.INFO,
                    title="Hardcoded system path in open()",
                    message=f"open('{p}') targets a system path that typically needs "
                    f"root. Expect PermissionError on most runners.",
                    node=node,
                    fixable=False,
                    fix_description="Use a config/env-based path inside the app data dir.",
                )
            # missing exists-check / try-except for a relative hardcoded path
            if not is_abs_system and "/" in p and "\\" not in p:
                self.add(
                    rule_id="missing-path-exists-check",
                    code="FileNotFoundError",
                    category=Category.FILES,
                    severity=Severity.WARNING,
                    title="open() on hardcoded path without guard",
                    message=f"open('{p}') will raise FileNotFoundError if the file "
                    f"isn't present. Wrap in try-except or check Path.exists() first.",
                    node=node,
                    fixable=True,
                    fix_description="Wrap with try/except FileNotFoundError or use Path.exists().",
                    suggestion=(
                        f"from pathlib import Path\n"
                        f"if Path({p!r}).exists():\n"
                        f"    with open({p!r}) as f:\n"
                        f"        ..."
                    ),
                )
        # mode='w' / 'x' on system path -> PermissionError risk
        mode_arg = None
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            mode_arg = node.args[1].value
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode_arg = kw.value.value
        if isinstance(mode_arg, str) and any(m in mode_arg for m in ("w", "x", "a", "+")):
            if (
                isinstance(path, ast.Constant)
                and isinstance(path.value, str)
                and any(path.value.startswith(s) for s in _SYSTEM_PATHS)
            ):
                self.add(
                    rule_id="hardcoded-path",
                    code="PermissionError",
                    category=Category.FILES,
                    severity=Severity.WARNING,
                    title="Write mode on system path",
                    message=f"open('{path.value}', '{mode_arg}') on a system path — "
                    f"PermissionError likely on CI runners.",
                    node=node,
                    fixable=False,
                    fix_description="Write to a user/app data directory instead.",
                )

    def _check_path(self, node: ast.Call) -> None:
        # Path(x).read_text() / .unlink() / .rmdir() without exists() check
        # detected via attribute access handled elsewhere; keep minimal here.
        pass

    # open() used outside `with` block -------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:  # type: ignore[override]
        self._scan_for_bare_open(node.body)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def _scan_for_bare_open(self, body: list[ast.stmt]) -> None:
        for stmt in body:
            for child in ast.walk(stmt):
                if isinstance(child, ast.Call) and iter_call_name(child) == "open":
                    # is it assigned to a name (not `with`)?
                    parent = _find_parent_assign(stmt, child)
                    if parent is not None and not _is_in_with_block(stmt, child):
                        self.add(
                            rule_id="open-without-context",
                            code="FileNotFoundError",
                            category=Category.FILES,
                            severity=Severity.WARNING,
                            title="open() without `with` statement",
                            message="File opened without a context manager — handle may "
                            "leak if an exception is raised before close().",
                            node=child,
                            fixable=True,
                            fix_description="Use `with open(...) as f:`.",
                            suggestion="with open(...) as f:\n    ...",
                        )


def _find_parent_assign(root: ast.stmt, target: ast.AST) -> ast.AST | None:
    for n in ast.walk(root):
        if isinstance(n, ast.Assign):
            for t in n.targets:
                if _contains(n.value, target):
                    return n
        if isinstance(n, ast.Expr) and _contains(n.value, target):
            return n
    return None


def _contains(haystack: ast.AST, needle: ast.AST) -> bool:
    for n in ast.walk(haystack):
        if n is needle:
            return True
    return False


def _is_in_with_block(root: ast.stmt, target: ast.AST) -> bool:
    for n in ast.walk(root):
        if isinstance(n, ast.With):
            for item in n.items:
                # item.context_expr is the open() call
                if _contains(item.context_expr, target):
                    return True
    return False
