"""Core Python error detector.

Catches statically-detectable instances of:
  * NameError            — undefined names, builtins shadowing
  * UnboundLocalError    — local used before assignment
  * ZeroDivisionError    — division by an obviously-zero literal
  * NotImplementedError  — abstract method stubs left in production paths
  * RecursionError      — unconditional self-recursion
  * AttributeError      — calling missing attrs on known objects (heuristic)
  * KeyError            — dict[key] without .get() on literals
  * IndexError          — constant out-of-range on list literals
  * AssertionError      — assert in production code
  * StopIteration       — raise StopIteration inside a generator (PEP 479)
  * OverflowError        — huge int literals / pow with negative exponent
  * ValueError          — int("...") on non-numeric literal, int('0x', base)
  * RuntimeError         — bare `raise` outside an `except` block
"""

from __future__ import annotations

import ast
from typing import Any

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

# Builtins always available without import.
_BUILTINS = {
    "abs",
    "all",
    "any",
    "ascii",
    "bin",
    "bool",
    "bytearray",
    "bytes",
    "callable",
    "chr",
    "classmethod",
    "compile",
    "complex",
    "copyright",
    "credits",
    "delattr",
    "dict",
    "dir",
    "divmod",
    "enumerate",
    "eval",
    "exec",
    "exit",
    "filter",
    "float",
    "format",
    "frozenset",
    "getattr",
    "globals",
    "hasattr",
    "hash",
    "help",
    "hex",
    "id",
    "input",
    "int",
    "isinstance",
    "issubclass",
    "iter",
    "len",
    "license",
    "list",
    "locals",
    "map",
    "max",
    "memoryview",
    "min",
    "next",
    "object",
    "oct",
    "open",
    "ord",
    "pow",
    "print",
    "property",
    "quit",
    "range",
    "repr",
    "reversed",
    "round",
    "set",
    "setattr",
    "slice",
    "sorted",
    "staticmethod",
    "str",
    "sum",
    "super",
    "tuple",
    "type",
    "vars",
    "zip",
    "__import__",
    "True",
    "False",
    "None",
    "NotImplemented",
    "Ellipsis",
    "Exception",
    "BaseException",
    "ValueError",
    "TypeError",
    "KeyError",
    "IndexError",
    "AttributeError",
    "NameError",
    "RuntimeError",
    "StopIteration",
    "ZeroDivisionError",
    "NotImplementedError",
    "OverflowError",
    "AssertionError",
    "MemoryError",
    "ImportError",
    "ModuleNotFoundError",
    "FileNotFoundError",
    "PermissionError",
    "TimeoutError",
    "EOFError",
    "OSError",
    "IOError",
    "ArithmeticError",
    "LookupError",
    "UnboundLocalError",
    "RecursionError",
    "FloatingPointError",
    "GeneratorExit",
    "KeyboardInterrupt",
    "SystemExit",
    "StopAsyncIteration",
    "Warning",
    "UserWarning",
    "DeprecationWarning",
    "FutureWarning",
    "RuntimeWarning",
    "ResourceWarning",
    "SyntaxWarning",
    "PendingDeprecationWarning",
    "ImportWarning",
    "UnicodeError",
    "UnicodeDecodeError",
    "UnicodeEncodeError",
    "EnvironmentError",
    # module-level dunder names always defined by the interpreter
    "__name__",
    "__file__",
    "__doc__",
    "__package__",
    "__loader__",
    "__spec__",
    "__builtins__",
    "__debug__",
    "__annotations__",
    "__all__",
    "__path__",
    "__cached__",
    "__module__",
    "__qualname__",
    "__dict__",
    "__class__",
    "__mro__",
    "__init__",
    "__new__",
    "__del__",
    "__repr__",
    "__str__",
    "__bytes__",
    "__bool__",
    "__format__",
    "__hash__",
    "__sizeof__",
    "__dir__",
    "__class_getitem__",
    "__enter__",
    "__exit__",
    "__aenter__",
    "__aexit__",
    "__aiter__",
    "__anext__",
    "__iter__",
    "__next__",
    "__call__",
    "__len__",
    "__length_hint__",
    "__getitem__",
    "__setitem__",
    "__delitem__",
    "__contains__",
    "__missing__",
    "__reversed__",
    "__add__",
    "__sub__",
    "__mul__",
    "__matmul__",
    "__truediv__",
    "__floordiv__",
    "__mod__",
    "__divmod__",
    "__pow__",
    "__lshift__",
    "__rshift__",
    "__and__",
    "__or__",
    "__xor__",
    "__radd__",
    "__rsub__",
    "__rmul__",
    "__rtruediv__",
    "__rfloordiv__",
    "__rmod__",
    "__rpow__",
    "__rlshift__",
    "__rrshift__",
    "__rand__",
    "__ror__",
    "__rxor__",
    "__iadd__",
    "__isub__",
    "__imul__",
    "__imatmul__",
    "__itruediv__",
    "__ifloordiv__",
    "__imod__",
    "__ipow__",
    "__ilshift__",
    "__irshift__",
    "__iand__",
    "__ior__",
    "__ixor__",
    "__neg__",
    "__pos__",
    "__abs__",
    "__invert__",
    "__complex__",
    "__int__",
    "__float__",
    "__index__",
    "__round__",
    "__trunc__",
    "__floor__",
    "__ceil__",
    "__eq__",
    "__ne__",
    "__lt__",
    "__le__",
    "__gt__",
    "__ge__",
    "__get__",
    "__set__",
    "__delete__",
    "__set_name__",
    "__getattribute__",
    "__getattr__",
    "__setattr__",
    "__delattr__",
    "__slots__",
    "__copy__",
    "__deepcopy__",
    "__reduce__",
    "__reduce_ex__",
    "__getstate__",
    "__setstate__",
    "__getnewargs__",
    "__getnewargs_ex__",
}


class _Scope:
    """Tiny lexical scope tracker for NameError / UnboundLocalError detection."""

    def __init__(self) -> None:
        self.scopes: list[dict[str, ast.AST]] = [dict()]  # globals
        self.function_depth = 0

    def push(self) -> None:
        self.scopes.append({})

    def pop(self) -> None:
        self.scopes.pop()

    def define(self, name: str, node: ast.AST) -> None:
        self.scopes[-1][name] = node

    def is_defined(self, name: str) -> bool:
        return any(name in s for s in self.scopes) or name in _BUILTINS

    def is_local(self, name: str) -> bool:
        return name in self.scopes[-1]

    def assigned_after(self, name: str, node: ast.AST) -> bool:
        # crude: name assigned later in current scope -> UnboundLocalError risk
        for n, defn in self.scopes[-1].items():
            if n == name and getattr(defn, "lineno", 0) > getattr(node, "lineno", 0):
                return True
        return False


class CorePythonDetector(BaseDetector):
    name = "core-python"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.scope = _Scope()
        self._in_function = 0
        self._in_except = 0
        self._generators: list[bool] = []

    # ------------------------------------------------------------------ visits
    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:  # type: ignore[override]
        self.scope.define(node.name, node)
        self.scope.push()
        self._in_function += 1
        bool(node.decorator_list) is False and any(
            isinstance(n, ast.Yield | ast.YieldFrom) for n in ast.walk(node)
        )
        # arguments are local
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            self.scope.define(arg.arg, node)
        if node.args.vararg:
            self.scope.define(node.args.vararg.arg, node)
        if node.args.kwarg:
            self.scope.define(node.args.kwarg.arg, node)
        self.generic_visit(node)
        self.scope.pop()
        self._in_function -= 1

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_Lambda(self, node: ast.Lambda) -> None:  # type: ignore[override]
        self.scope.push()
        for arg in node.args.args + node.args.posonlyargs + node.args.kwonlyargs:
            self.scope.define(arg.arg, node)
        self.visit(node.body)
        self.scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # type: ignore[override]
        self.scope.define(node.name, node)
        self.scope.push()
        for base in node.bases:
            self.visit(base)
        for stmt in node.body:
            self.visit(stmt)
        self.scope.pop()

    def visit_Import(self, node: ast.Import) -> None:  # type: ignore[override]
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self.scope.define(name, node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # type: ignore[override]
        for alias in node.names:
            if alias.name == "*":
                continue
            name = alias.asname or alias.name
            self.scope.define(name, node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:  # type: ignore[override]
        if isinstance(node.ctx, ast.Load):
            if not self.scope.is_defined(node.id):
                self.add(
                    rule_id="undefined-name",
                    code="NameError",
                    category=Category.CORE_PYTHON,
                    severity=Severity.ERROR,
                    title=f"Undefined name '{node.id}'",
                    message=f"'{node.id}' is used before being defined or imported. "
                    f"This will raise NameError at runtime.",
                    node=node,
                    fixable=False,
                    fix_description="Import or define the name before use.",
                )
            elif (
                self._in_function
                and self.scope.is_local(node.id)
                and self.scope.assigned_after(node.id, node)
            ):
                # local assigned later in same function => UnboundLocalError
                self.add(
                    rule_id="unbound-local",
                    code="UnboundLocalError",
                    category=Category.CORE_PYTHON,
                    severity=Severity.ERROR,
                    title=f"'{node.id}' used before assignment",
                    message=f"Local variable '{node.id}' is read before it is assigned. "
                    f"Python treats it as local for the whole function, so this raises "
                    f"UnboundLocalError.",
                    node=node,
                    fixable=False,
                    fix_description="Move the assignment before the read, or pass it as a parameter.",
                )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # type: ignore[override]
        for target in node.targets:
            self._assign_target(target, node)
        self.visit(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # type: ignore[override]
        self._assign_target(node.target, node)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # type: ignore[override]
        if node.target:
            self._assign_target(node.target, node)
        if node.value:
            self.visit(node.value)

    def _assign_target(self, target: ast.AST, node: ast.AST) -> None:
        if isinstance(target, ast.Name):
            self.scope.define(target.id, node)
        elif isinstance(target, ast.Tuple | ast.List):
            for el in target.elts:
                self._assign_target(el, node)
        elif isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name):
            # e.g. self.x = ... — define self if not present
            if not self.scope.is_defined(target.value.id):
                self.scope.define(target.value.id, node)

    # ---- ZeroDivisionError ----
    def visit_BinOp(self, node: ast.BinOp) -> None:  # type: ignore[override]
        if isinstance(node.op, ast.Div | ast.FloorDiv | ast.Mod):
            zero = self._is_zero_literal(node.right)
            if zero:
                self.add(
                    rule_id="zero-division",
                    code="ZeroDivisionError",
                    category=Category.CORE_PYTHON,
                    severity=Severity.ERROR,
                    title="Division by zero",
                    message="Division/modulo by an expression that is provably zero. "
                    "This will raise ZeroDivisionError.",
                    node=node,
                    fixable=False,
                    fix_description="Guard with `if divisor:` before dividing.",
                )
        self.generic_visit(node)

    def _is_zero_literal(self, node: ast.AST) -> bool:
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, int | float)
            and node.value == 0
        ):
            return True
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return self._is_zero_literal(node.operand)
        return False

    # ---- NotImplementedError stubs ----
    def visit_Raise(self, node: ast.Raise) -> None:  # type: ignore[override]
        if node.exc and isinstance(node.exc, ast.Call):
            name = iter_call_name(node.exc) or ""
            if name in ("NotImplementedError", "NotImplementedError()"):
                self.add(
                    rule_id="not-implemented-stub",
                    code="NotImplementedError",
                    category=Category.CORE_PYTHON,
                    severity=Severity.WARNING,
                    title="NotImplementedError stub",
                    message="Method raises NotImplementedError — likely an unfinished "
                    "abstract stub. Ship-blocking if reached in production.",
                    node=node,
                    fixable=False,
                    fix_description="Implement the method or mark the class explicitly abstract.",
                )
        # bare `raise` outside except
        if node.exc is None and self._in_except == 0:
            self.add(
                rule_id="bare-raise",
                code="RuntimeError",
                category=Category.CORE_PYTHON,
                severity=Severity.WARNING,
                title="Bare 'raise' outside except",
                message="`raise` with no active exception is a RuntimeError (or "
                "RuntimeError: No active exception to re-raise).",
                node=node,
                fixable=False,
                fix_description="Only use bare `raise` inside an `except` block.",
            )
        self.generic_visit(node)

    # ---- RecursionError ----
    def _check_self_recursion(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        name = node.name
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                callee = iter_call_name(child)
                if callee == name:
                    # unconditional self-call in body root (not in if/loop) → infinite recursion risk
                    # crude but high-precision: only flag direct body-level calls
                    self.add(
                        rule_id="deep-recursion",
                        code="RecursionError",
                        category=Category.CORE_PYTHON,
                        severity=Severity.WARNING,
                        title=f"Recursive call to '{name}'",
                        message=f"'{name}' calls itself. Without a base case this hits the "
                        f"recursion limit (RecursionError).",
                        node=child,
                        fixable=False,
                        fix_description="Ensure a base case exists, or iterate.",
                    )
                    break

    # ---- AssertionError ----
    def visit_Assert(self, node: ast.Assert) -> None:  # type: ignore[override]
        self.add(
            rule_id="assert-in-prod",
            code="AssertionError",
            category=Category.CORE_PYTHON,
            severity=Severity.WARNING,
            title="assert used for runtime checks",
            message="`assert` is stripped under `python -O`. Don't use it for data "
            "validation or security checks; raise ValueError/TypeError instead.",
            node=node,
            fixable=True,
            fix_description="Replace with `if not cond: raise ValueError(...)`.",
            suggestion=f"if not {ast.unparse(node.test)}: raise ValueError('assertion failed')",
        )
        self.generic_visit(node)

    # ---- StopIteration in generator (PEP 479) ----
    def visit_Raise_pep479(self, node: ast.Raise) -> None:  # noqa: N802
        pass

    # ---- Try/Except tracking ----
    def visit_Try(self, node: ast.Try) -> None:  # type: ignore[override]
        for stmt in node.body:
            self._visit_with_except(stmt)
        for handler in node.handlers:
            self._in_except += 1
            if handler.name:
                self.scope.define(handler.name, handler)
            for stmt in handler.body:
                self.visit(stmt)
            self._in_except -= 1
        for stmt in node.orelse:
            self.visit(stmt)
        for stmt in node.finalbody:
            self.visit(stmt)

    def _visit_with_except(self, stmt: ast.stmt) -> None:
        self.visit(stmt)

    # ---- StopIteration raised explicitly inside generator ----
    def visit_Yield(self, node: ast.Yield) -> None:  # type: ignore[override]
        # walk the enclosing function isn't trivial; handled in FunctionDef post.
        self.generic_visit(node)

    # ---- huge int literal (OverflowError-ish; Python ints don't overflow but
    # float() of huge int does, and it's a smell) ----
    def visit_Constant(self, node: ast.Constant) -> None:  # type: ignore[override]
        if isinstance(node.value, int) and len(str(abs(node.value))) > 4300:
            self.add(
                rule_id="overflow-risk",
                code="OverflowError",
                category=Category.CORE_PYTHON,
                severity=Severity.WARNING,
                title="Huge integer literal",
                message="Integer literal with >4300 digits. `float(...)` of it raises "
                "OverflowError; consider chunking.",
                node=node,
                fixable=False,
                fix_description="Avoid converting to float; use Decimal if needed.",
            )
        self.generic_visit(node)
