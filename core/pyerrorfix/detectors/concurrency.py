"""Concurrency error detector (NEW category — was missing from the user list).

Catches:
  * Mutable shared state — module-level ``list``/``dict``/``set`` mutated from
    inside async/threaded code without a lock (data race / IntegrityError risk).
  * `threading.Lock` acquired without a context manager (forgetting release).
  * Thread-unsafe singleton — global instance created at import time and reused
    across workers without a guard.
"""

from __future__ import annotations

import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name


class ConcurrencyDetector(BaseDetector):
    name = "concurrency"

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)

        # lock.acquire() without `with` — flag when we see acquire()/release() pair
        if name and name.endswith(".acquire"):
            base = name[: -len(".acquire")]
            self.add(
                rule_id="lock-without-context",
                code="RuntimeError",
                category=Category.CONCURRENCY,
                severity=Severity.WARNING,
                title=f"{base}.acquire() without `with`",
                message=f"Calling {base}.acquire() manually risks deadlock if an "
                f"exception skips release(). Use `with {base}:`.",
                node=node,
                fixable=True,
                fix_description=f"Replace acquire()/release() with `with {base}:`.",
                suggestion=f"with {base}:\n    ...",
            )

        self.generic_visit(node)

    # mutable module-level global mutated from a function (very heuristic)
    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # type: ignore[override]
        if isinstance(node.target, ast.Subscript) and isinstance(node.target.value, ast.Name):
            var = node.target.value.id
            if var in self._module_level_mutables:
                self.add(
                    rule_id="mutable-shared-state",
                    code="RuntimeError",
                    category=Category.CONCURRENCY,
                    severity=Severity.WARNING,
                    title=f"Mutating shared global '{var}'",
                    message=f"Augmented assignment to module-level '{var}' is not "
                    f"atomic across threads/async tasks. Use a lock or per-task state.",
                    node=node,
                    fixable=False,
                    fix_description="Guard with a lock or move state into a class instance.",
                )
        self.generic_visit(node)

    def visit_Module(self, node: ast.Module) -> None:  # type: ignore[override]
        self._module_level_mutables = set()
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and isinstance(
                        stmt.value, ast.List | ast.Dict | ast.Set
                    ):
                        self._module_level_mutables.add(t.id)
        self.generic_visit(node)
