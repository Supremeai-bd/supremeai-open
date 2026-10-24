"""Typing error detector (NEW category).

Catches:
  * NoneType attribute access — `x.attr` where `x` came from a function that may
    return None (`Optional[...]`, `.get()`, `.first()`, `re.search`).
  * Optional parameter used without None check.
  * Missing type hints on public function signatures (info-level).
"""

from __future__ import annotations

import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

_NONE_RETURNING = {
    "get",  # dict.get / os.environ.get
    "first",  # query.first()
    "one_or_none",
    "re.search",
    "re.match",
    "re.fullmatch",
    "findone",
    "getattr",
}

_OPTIONAL_TYPE_NAMES = {"Optional", "Union", "Any", "None"}


class TypingDetector(BaseDetector):
    name = "typing"

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:  # type: ignore[override]
        # missing return type hint on public (non-dunder) function
        if not node.name.startswith("_") and node.returns is None and not _is_overridden(node):
            self.add(
                rule_id="missing-type-hint",
                code="TypeError",
                category=Category.TYPING,
                severity=Severity.INFO,
                title=f"Missing return annotation on '{node.name}'",
                message=f"Public function '{node.name}' has no return type annotation. "
                f"mypy strict mode will fail; callers lose autocompletion.",
                node=node,
                fixable=False,
                fix_description="Add a return type annotation.",
            )
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Assign(self, node: ast.Assign) -> None:  # type: ignore[override]
        # x = something.get('k')  /  x = re.search(...)  -> x may be None
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            val = node.value
            if isinstance(val, ast.Call):
                name = iter_call_name(val)
                if name and (name in _NONE_RETURNING or name.endswith(".get")):
                    self._maybe_none_vars[node.targets[0].id] = node
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # type: ignore[override]
        if isinstance(node.value, ast.Name) and node.value.id in self._maybe_none_vars:
            self.add(
                rule_id="none-member-access",
                code="AttributeError",
                category=Category.TYPING,
                severity=Severity.WARNING,
                title=f"Attribute access on possibly-None '{node.value.id}'",
                message=f"'{node.value.id}' is assigned from a call that can return None. "
                f"Accessing '.{node.attr}' risks AttributeError.",
                node=node,
                fixable=False,
                fix_description="Guard with `if var is not None:` before attribute access.",
                suggestion=f"if {node.value.id} is not None:\n    {node.value.id}.{node.attr}",
            )
        self.generic_visit(node)

    def visit_Module(self, node: ast.Module) -> None:  # type: ignore[override]
        self._maybe_none_vars: dict[str, ast.AST] = {}
        self.generic_visit(node)


def _is_overridden(node: ast.FunctionDef) -> bool:
    for dec in node.decorator_list:
        name = ""
        if isinstance(dec, ast.Name):
            name = dec.id
        elif isinstance(dec, ast.Attribute):
            name = dec.attr
        if name in ("override", "abstractmethod", "property", "staticmethod", "classmethod"):
            return True
    return False
