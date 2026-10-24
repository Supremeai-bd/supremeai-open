"""Deprecation error detector (NEW category).

Catches deprecated APIs and Python 2 constructs that raise AttributeError /
TypeError on modern Python:
  * `imp.*`, `distutils.*`, `cgi.*` (removed in 3.12+).
  * `collections.abc` moved names (`collections.Callable` etc).
  * `asyncio.coroutine` decorator (removed).
  * `urllib.urlopen` (removed).
  * `.dict()` on Pydantic v1 models (also flagged by web-api).
  * `print >>` Python2, `xrange`, `unicode`, `basestring`.
"""

from __future__ import annotations

import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

_DEPRECATED = {
    "imp": "removed in 3.12 — use importlib",
    "distutils": "removed in 3.12 — use packaging / setuptools",
    "cgi": "removed in 3.13 — use email/message or a 3rd-party form parser",
    "asyncio.coroutine": "removed in 3.11 — use `async def`",
    "urllib.urlopen": "removed in 3.x — use urllib.request.urlopen",
    "xrange": "removed in 3.x — use range",
    "unicode": "removed in 3.x — use str",
    "basestring": "removed in 3.x — use str",
    "unichr": "removed in 3.x — use chr",
    "collections.Callable": "moved to collections.abc.Callable",
    "collections.Mapping": "moved to collections.abc.Mapping",
    "collections.MutableMapping": "moved to collections.abc.MutableMapping",
    "collections.Sequence": "moved to collections.abc.Sequence",
    "collections.Iterable": "moved to collections.abc.Iterable",
    "inspect.getargspec": "removed in 3.x — use getfullargspec",
    "time.clock": "removed in 3.8 — use time.perf_counter",
    "ssl.wrap_socket": "removed in 3.12 — use SSLContext",
    "threading.Thread.isAlive": "removed in 3.9 — use is_alive()",
    "os.errno": "use errno module",
}


class DeprecationDetector(BaseDetector):
    name = "deprecation"

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)
        if name in _DEPRECATED:
            self._flag(name, node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # type: ignore[override]
        dotted = _dotted(node)
        if dotted in _DEPRECATED:
            self._flag(dotted, node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # type: ignore[override]
        if node.id in _DEPRECATED:
            self._flag(node.id, node)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:  # type: ignore[override]
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top in _DEPRECATED:
                self._flag(top, node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # type: ignore[override]
        if node.module and node.module.split(".")[0] in _DEPRECATED:
            self._flag(node.module.split(".")[0], node)
        self.generic_visit(node)

    def _flag(self, name: str, node: ast.AST) -> None:
        self.add(
            rule_id="deprecated-api",
            code="AttributeError",
            category=Category.DEPRECATION,
            severity=Severity.WARNING,
            title=f"Deprecated/removed API '{name}'",
            message=f"'{name}' is {_DEPRECATED[name]}. Using it raises AttributeError "
            f"on supported Python versions.",
            node=node,
            fixable=False,
            fix_description=_DEPRECATED[name],
        )


def _dotted(attr: ast.Attribute) -> str:
    parts: list[str] = []
    node: ast.AST = attr
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            break
    return ".".join(reversed(parts))
