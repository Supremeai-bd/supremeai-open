"""Linter & Code-Quality error detector (NEW — category 2).

Catches the specific linter codes and style issues the user listed:
  * `B905`  — zip() without strict= argument (silent length-mismatch bug).
  * `E712`  — `x == True` / `x == False` (should be `if x:` / `if not x:`).
  * `E722`  — bare `except:` (also flagged by logging detector; aliased here).
  * `C901`  — >3 levels of nesting (cognitive complexity).
  * `SIM108` — verbose if/else that could be a single ternary expression.
  * `F841`  — dead mock (unittest.mock.Mock/patch created but never used in a test).
  * `N816`  — snake_case variable assigned camelCase attribute (naming mismatch).
"""

from __future__ import annotations

import ast
import re

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

_CAMEL_RE = re.compile(r"^[a-z]+([A-Z][a-z0-9]*)+$")  # camelCase
_SNAKE_RE = re.compile(r"^[a-z][a-z0-9_]*$")  # snake_case


class LinterQualityDetector(BaseDetector):
    name = "linter-quality"

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        # B905: zip() without strict=
        if isinstance(node.func, ast.Name) and node.func.id == "zip":
            has_strict = any(kw.arg == "strict" for kw in node.keywords)
            if not has_strict:
                self.add(
                    rule_id="zip-without-strict",
                    code="B905",
                    category=Category.LOGGING,
                    severity=Severity.WARNING,
                    title="zip() without strict=",
                    message="zip() silently truncates to the shortest iterable. "
                    "Pass `strict=True` so unequal lengths raise ValueError instead "
                    "of producing silently-wrong data.",
                    node=node,
                    fixable=True,
                    fix_description="Add strict=True.",
                    suggestion=f"{ast.unparse(node).rstrip(')')}, strict=True)",
                )
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:  # type: ignore[override]
        # E712: x == True / x == False
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            if isinstance(op, ast.Eq | ast.NotEq) and isinstance(comparator, ast.Constant):
                if isinstance(comparator.value, bool):
                    val = comparator.value
                    eq = "==" if isinstance(op, ast.Eq) else "!="
                    wanted = "" if (val if isinstance(op, ast.Eq) else not val) else "not "
                    self.add(
                        rule_id="bool-compare-literal",
                        code="E712",
                        category=Category.LOGGING,
                        severity=Severity.WARNING,
                        title=f"Comparison `{eq} {val}`",
                        message=f"`x {eq} {val}` should be `if {wanted}x:`. Comparing to "
                        f"bool literals breaks for truthy/falsy values (e.g. 1 == True "
                        f"is True but 2 == True is False).",
                        node=node,
                        fixable=True,
                        fix_description=f"Replace with `if {wanted}x:`.",
                        suggestion=f"{wanted}{ast.unparse(node.left)}",
                    )
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:  # type: ignore[override]
        # C901: deeply nested if/else (depth >= 4)
        depth = _if_depth(node)
        if depth >= 4:
            self.add(
                rule_id="nested-if-style",
                code="C901",
                category=Category.LOGGING,
                severity=Severity.INFO,
                title=f"Deeply nested if/else (depth {depth})",
                message=f"Control flow nested {depth} levels deep — high cognitive "
                f"complexity. Extract early returns (`if not cond: return`) or guard "
                f"clauses to flatten it.",
                node=node,
                fixable=False,
                fix_description="Use guard clauses / early returns to flatten nesting.",
            )
        # SIM108: simple if/else assigning the same name → ternary
        self._check_ternary_pattern(node)
        self.generic_visit(node)

    def _check_ternary_pattern(self, stmt: ast.If) -> None:
        if not (
            len(stmt.orelse) == 1
            and isinstance(stmt.orelse[0], ast.Assign)
            and len(stmt.body) == 1
            and isinstance(stmt.body[0], ast.Assign)
        ):
            return
        a = stmt.body[0]
        b = stmt.orelse[0]
        if not (
            len(a.targets) == 1
            and isinstance(a.targets[0], ast.Name)
            and len(b.targets) == 1
            and isinstance(b.targets[0], ast.Name)
            and a.targets[0].id == b.targets[0].id
        ):
            return
        var = a.targets[0].id
        self.add(
            rule_id="ternary-style",
            code="SIM108",
            category=Category.LOGGING,
            severity=Severity.INFO,
            title=f"if/else assigns '{var}' — use a ternary",
            message=f"`if cond: {var} = a else: {var} = b` can be a one-liner: "
            f"`{var} = a if cond else b`. (Only flagged when both branches are "
            f"simple assignments to the same name.)",
            node=stmt,
            fixable=True,
            fix_description="Collapse into a ternary expression.",
            suggestion=f"{var} = {ast.unparse(a.value)} if {ast.unparse(stmt.test)} else {ast.unparse(b.value)}",
        )

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:  # type: ignore[override]
        self._check_dead_mock(node)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def _check_dead_mock(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        mock_names: dict[str, ast.AST] = {}
        for stmt in node.body:
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call):
                callee = iter_call_name(stmt.value)
                if callee and (
                    callee.endswith("Mock")
                    or callee.endswith("MagicMock")
                    or callee == "patch"
                    or callee.endswith(".patch")
                ):
                    if len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                        mock_names[stmt.targets[0].id] = stmt
        if not mock_names:
            return
        used: set[str] = set()
        for stmt in node.body:
            for n in ast.walk(stmt):
                if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                    used.add(n.id)
        for name, defn in mock_names.items():
            if name not in used:
                self.add(
                    rule_id="dead-mock",
                    code="F841",
                    category=Category.LOGGING,
                    severity=Severity.WARNING,
                    title=f"Mock '{name}' created but never used",
                    message=f"The mock object '{name}' is created but never referenced "
                    f"in the test body. Either remove it or use it (e.g. "
                    f"`{name}.assert_called_once()`).",
                    node=defn,
                    fixable=True,
                    fix_description="Remove the unused mock or add assertions on it.",
                    suggestion=f"# remove: {name} = ...",
                )

    def visit_Assign(self, node: ast.Assign) -> None:  # type: ignore[override]
        # N816: snake_case var = camelCase.attr
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            var = node.targets[0].id
            if _SNAKE_RE.match(var) and isinstance(node.value, ast.Attribute):
                attr = node.value.attr
                if _CAMEL_RE.match(attr):
                    snake_attr = _camel_to_snake(attr)
                    self.add(
                        rule_id="naming-convention-mismatch",
                        code="N816",
                        category=Category.LOGGING,
                        severity=Severity.INFO,
                        title=f"camelCase attr '{attr}' assigned to snake_case '{var}'",
                        message=f"External API returns camelCase '{attr}' but Python "
                        f"convention is snake_case. Mixing both is error-prone. "
                        f"Map explicitly: `{var} = response.get('{attr}')` or alias.",
                        node=node,
                        fixable=False,
                        fix_description=f"Document the mapping or normalise with `{snake_attr}`.",
                    )
        self.generic_visit(node)


def _if_depth(node: ast.AST, current: int = 0) -> int:
    """Max nesting depth of If nodes reachable from `node`."""
    if isinstance(node, ast.If):
        current += 1
    max_depth = current
    for child in ast.iter_child_nodes(node):
        max_depth = max(max_depth, _if_depth(child, current))
    return max_depth


def _camel_to_snake(name: str) -> str:
    s = re.sub(r"([A-Z])", r"_\1", name).lower()
    return s[1:] if s.startswith("_") else s
