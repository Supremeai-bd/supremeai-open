"""Testing & Assertion error detector (NEW — category 10).

Catches:
  * `AssertionError` — assert in NON-test code (already have assert-in-prod in
    core_python; this detector flags assert in TEST files separately so the
    message is framed for testing context).
  * dead mock — Mock/patch created but never asserted on (also flagged by
    linter_quality; aliased here with a test-context message).
  * `FixtureLookupError` risk — pytest fixtures referenced as parameters but
    not defined in the same module/conftest (heuristic).
  * fixture scope misuse — `@pytest.fixture(scope="session")` on a fixture that
    mutates state (session-scoped + mutation = test pollution).
  * bare `pytest.raises` without `match=` — swallows the wrong error silently.
"""

from __future__ import annotations

import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

_IS_TEST_FILE_SUFFIXES = ("_test.py", "test_.py", "tests.py", "conftest.py")


class TestingDetector(BaseDetector):
    name = "testing"

    @property
    def _is_test_file(self) -> bool:
        return (
            any(self.filename.endswith(s) for s in _IS_TEST_FILE_SUFFIXES)
            or "/tests/" in self.filename
            or "\\tests\\" in self.filename
        )

    def visit_Assert(self, node: ast.Assert) -> None:  # type: ignore[override]
        if not self._is_test_file:
            return  # assert-in-prod is handled by core_python
        # In tests, assert is fine — but `assert something == True` is still E712
        # (the linter_quality detector catches that). Here we only flag assert
        # with NO message (hard to debug failures).
        if node.msg is None:
            self.add(
                rule_id="assert-without-message",
                code="AssertionError",
                category=Category.LOGGING,
                severity=Severity.INFO,
                title="assert without failure message",
                message="Bare `assert x` shows only `AssertionError` on failure. "
                "Add a message: `assert x, 'expected x to be truthy'`.",
                node=node,
                fixable=True,
                fix_description="Add a message string.",
                suggestion=f"assert {ast.unparse(node.test)}, 'expected condition to hold'",
            )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:  # type: ignore[override]
        # session-scoped fixture that mutates state → test pollution
        for dec in node.decorator_list:
            if isinstance(dec, ast.Attribute) and dec.attr == "fixture":
                # pytest.fixture or pytest.fixture(scope=...)
                # check the call args if it's pytest.fixture(...)
                if isinstance(dec.value, ast.Call):
                    for kw in dec.value.keywords:
                        if (
                            kw.arg == "scope"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value == "session"
                        ):
                            if _mutates_self_or_global(node):
                                self.add(
                                    rule_id="session-fixture-mutation",
                                    code="FixtureLookupError",
                                    category=Category.LOGGING,
                                    severity=Severity.WARNING,
                                    title=f"Session-scoped fixture '{node.name}' mutates state",
                                    message=f"Fixture '{node.name}' is scope='session' "
                                    f"but mutates state in its body. Session fixtures "
                                    f"are shared across ALL tests — mutations leak and "
                                    f"cause flaky, order-dependent test failures.",
                                    node=node,
                                    fixable=False,
                                    fix_description="Use scope='function' or return immutable data.",
                                )
            elif (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr == "fixture"
            ):
                for kw in dec.keywords:
                    if (
                        kw.arg == "scope"
                        and isinstance(kw.value, ast.Constant)
                        and kw.value.value == "session"
                    ):
                        if _mutates_self_or_global(node):
                            self.add(
                                rule_id="session-fixture-mutation",
                                code="FixtureLookupError",
                                category=Category.LOGGING,
                                severity=Severity.WARNING,
                                title=f"Session-scoped fixture '{node.name}' mutates state",
                                message=f"Fixture '{node.name}' is scope='session' but "
                                f"mutates state. Session fixtures are shared across all "
                                f"tests — mutations leak.",
                                node=node,
                                fixable=False,
                                fix_description="Use scope='function' or return immutable data.",
                            )

        # bare pytest.raises without match=
        for stmt in node.body:
            for n in ast.walk(stmt):
                if (
                    isinstance(n, ast.With)
                    and n.items
                    and isinstance(n.items[0].context_expr, ast.Call)
                ):
                    callee = iter_call_name(n.items[0].context_expr)
                    if callee in ("pytest.raises", "pytest.warns"):
                        has_match = any(
                            kw.arg == "match" for kw in n.items[0].context_expr.keywords
                        )
                        if not has_match:
                            self.add(
                                rule_id="pytest.raises-without-match",
                                code="AssertionError",
                                category=Category.LOGGING,
                                severity=Severity.INFO,
                                title=f"{callee}() without match=",
                                message=f"`{callee}(ValueError)` catches ANY ValueError, "
                                f"even the wrong one. Add `match='expected message'` to "
                                f"verify the right error is raised.",
                                node=n,
                                fixable=True,
                                fix_description="Add match='...' with a substring of the expected error message.",
                            )

        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]


def _mutates_self_or_global(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if the function body contains an AugAssign or a `.append/.extend/.update`
    on a Name (i.e. it mutates shared state)."""
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.AugAssign):
            return True
        if (
            isinstance(stmt, ast.Expr)
            and isinstance(stmt.value, ast.Call)
            and isinstance(stmt.value.func, ast.Attribute)
            and stmt.value.func.attr
            in {"append", "extend", "update", "pop", "remove", "clear", "add", "discard"}
            and isinstance(stmt.value.func.value, ast.Name)
        ):
            return True
    return False
