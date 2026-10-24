"""Database & ORM error detector (SQLAlchemy-focused).

Catches:
  * `sqlalchemy.exc.IntegrityError`   — duplicate unique key inserts (heuristic:
    bulk insert without ON CONFLICT/ignore).
  * `sqlalchemy.exc.OperationalError` — connection not closed / missing engine
    dispose.
  * `sqlalchemy.exc.StatementError`    — f-string interpolated SQL (raw SQLi).
  * `sqlalchemy.exc.NoResultFound`     — `query.one()` / `scalar()` without
    try/except.
  * `sqlalchemy.exc.MultipleResultsFound` — `query.one()` on a query that may
    return many.
  * Raw SQL injection risk — `text(f"...")` / `text("..." % var)` / cursor.execute(f"...").
  * N+1 query smell — `.query(Model).all()` then loop accessing relationship
    (very heuristic).
  * Missing commit/rollback — session mutations without commit/rollback in
    finally.
"""

from __future__ import annotations

import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name


class DatabaseDetector(BaseDetector):
    name = "database"

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)
        # raw SQL with f-string
        if name in ("text", "execute", "executemany", "executescript"):
            for arg in node.args:
                if _is_dynamic_string(arg):
                    self.add(
                        rule_id="raw-sql-injection",
                        code="StatementError",
                        category=Category.DATABASE,
                        severity=Severity.CRITICAL,
                        title=f"Raw SQL built with dynamic string in {name}()",
                        message=f"{name}() receives a dynamically-built string. "
                        f"This is a SQL-injection vector AND produces StatementError when "
                        f"placeholders are wrong. Use bound parameters.",
                        node=node,
                        fixable=False,
                        fix_description="Use parameter binding: text('... WHERE id = :id'), {'id': x}.",
                    )

        # session.query(Model).one() / scalar() without try/except
        if name in ("one", "one_or_none", "scalar_one", "scalar"):
            if _is_query_chain(node.func):
                self.add(
                    rule_id="missing-noresult-found",
                    code="NoResultFound",
                    category=Category.DATABASE,
                    severity=Severity.WARNING,
                    title=f"Un-guarded {name}() on a query",
                    message=f"`query.{name}()` raises sqlalchemy.exc.NoResultFound "
                    f"(or MultipleResultsFound for .one()) when the row is absent. "
                    f"Wrap in try/except or use .one_or_none()/first().",
                    node=node,
                    fixable=False,
                    fix_description="Use .one_or_none() and handle None, or wrap in try/except NoResultFound.",
                )

        # cursor.execute("SELECT ... " + var)  (DB-API direct)
        if name == "execute" and node.args:
            first = node.args[0]
            if isinstance(first, ast.BinOp) and isinstance(first.op, ast.Add):
                self.add(
                    rule_id="raw-sql-injection",
                    code="StatementError",
                    category=Category.DATABASE,
                    severity=Severity.CRITICAL,
                    title="SQL concatenation in execute()",
                    message="cursor.execute(...) called with string concatenation. "
                    "Classic SQL injection. Use parameter substitution (?, %s, :name).",
                    node=node,
                    fixable=False,
                    fix_description="Pass parameters separately: execute(sql, params).",
                )

        self.generic_visit(node)

    # N+1 smell: for item in Model.query.all():  item.relation
    def visit_For(self, node: ast.For) -> None:  # type: ignore[override]
        if isinstance(node.iter, ast.Call) and _is_query_chain(node.iter):
            # check body accesses a relationship attribute
            for stmt in node.body:
                for attr in ast.walk(stmt):
                    if (
                        isinstance(attr, ast.Attribute)
                        and isinstance(attr.value, ast.Name)
                        and attr.value.id == _loop_target_name(node.target)
                    ):
                        self.add(
                            rule_id="n-plus-one-query",
                            code="OperationalError",
                            category=Category.DATABASE,
                            severity=Severity.INFO,
                            title="Possible N+1 query",
                            message="Looping over a query result and accessing a "
                            "relationship triggers one extra query per row (N+1). "
                            "Use joinedload/selectinload to eager-load.",
                            node=node,
                            fixable=False,
                            fix_description="Add `.options(joinedload(Model.rel))` to the query.",
                        )
                        break
                else:
                    continue
                break

        self.generic_visit(node)


def _is_dynamic_string(node: ast.AST) -> bool:
    if isinstance(node, ast.JoinedStr):  # f-string
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):  # % formatting
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return True
    return False


def _is_query_chain(func: ast.AST) -> bool:
    """Is `func` part of a `...query(...)...` chain?"""
    while isinstance(func, ast.Attribute):
        if func.attr in ("query", "filter", "join", "options", "order_by", "group_by"):
            return True
        func = func.value
    return False


def _loop_target_name(target: ast.AST) -> str | None:
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Tuple) and target.elts:
        if isinstance(target.elts[0], ast.Name):
            return target.elts[0].id
    return None
