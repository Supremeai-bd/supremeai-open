"""backend.tools.safe_executor
================================
A thin wrapper around **RestrictedPython** that provides a safe execution
environment for dynamic Python code.

Only a curated whitelist of built‑ins is exposed; everything else (e.g.
``open``, ``__import__``) is blocked. The function returns the locals dictionary
so callers can retrieve a ``result`` variable if they set one.

Issue #682 (fail-closed codegen gate): ``run_restricted`` executes dynamically
supplied source — the CoT reasoner feeds it model-generated thought code
(``tools.code.cot_reasoner.safe_execute``). RestrictedPython / AST whitelisting
is NOT a security boundary, so in-process exec here is **fail-closed by
default**: with ``SUPREMEAI_ALLOW_INPROCESS_CODEGEN`` unset (the
production/staging default) nothing is executed and the call site's existing
``(False, error_message)`` convention is returned with a structured denial.
The exec path only runs when the gate is explicitly enabled (local development
only), matching the #704 gate pattern in ``core/security/codegen_gate.py``.
"""

import ast
from typing import Any

try:
    from RestrictedPython import compile_restricted
    from RestrictedPython.Eval import default_globals

    HAS_RESTRICTED = True
except ImportError:
    HAS_RESTRICTED = False
    compile_restricted = None
    default_globals = {}

from core.logging_config import logger
from core.security.codegen_gate import (
    denied_reason,
    inprocess_codegen_enabled,
    warn_inprocess_codegen_boot,
)

# Issue #682: loud one-time boot warning when the in-process exec escape hatch
# is explicitly enabled (local development only).
if inprocess_codegen_enabled():
    warn_inprocess_codegen_boot("tools.code.safe_executor.run_restricted")

# Define a minimal safe builtins whitelist. Adjust as needed for the
# application – currently only ``range`` and ``len`` are allowed because the
# CoT reasoner does not rely on any other built‑ins.
SAFE_BUILTINS = {
    "range": range,
    "len": len,
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "int": int,
    "float": float,
    "str": str,
    "list": list,
    "dict": dict,
    "set": set,
    # Add more safe functions here if required.
}

ALLOWED_NODE_TYPES = {
    ast.Module,
    ast.Assign,
    ast.AugAssign,
    ast.Name,
    ast.Constant,
    ast.Expr,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.BoolOp,
    ast.If,
    ast.List,
    ast.Dict,
    ast.Set,
    ast.Tuple,
    ast.Subscript,
    ast.Slice,
    ast.Pass,
    ast.Call,
    ast.Load,
    ast.Store,
    ast.Del,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Pow,
    ast.LShift,
    ast.RShift,
    ast.BitOr,
    ast.BitXor,
    ast.BitAnd,
    ast.FloorDiv,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Invert,
    ast.UAdd,
    ast.USub,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Is,
    ast.IsNot,
    ast.In,
    ast.NotIn,
}


def validate_ast(source: str) -> None:
    """Validate that the source code contains only whitelisted AST nodes and safe calls."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ValueError(f"Syntax error during validation: {e}") from e

    for node in ast.walk(tree):
        # 1. Check node type
        if type(node) not in ALLOWED_NODE_TYPES:
            raise ValueError(f"Security error: AST node type {type(node).__name__} is not allowed")

        # 2. Prevent import statements entirely (Imports are not in ALLOWED_NODE_TYPES, but check as safety net)
        if isinstance(node, ast.Import | ast.ImportFrom):
            raise ValueError("Security error: Import statements are strictly forbidden")

        # 3. Prevent all attribute access to be safer
        if isinstance(node, ast.Attribute):
            raise ValueError("Security error: Attribute access is forbidden")

        # 4. Restrict Calls to only SAFE_BUILTINS
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
                if func_name not in SAFE_BUILTINS:
                    raise ValueError(
                        f"Security error: Function call '{func_name}' is not in the allowed list"
                    )
            else:
                raise ValueError("Security error: Non-name function calls are not allowed")


def run_restricted(
    source: str, locals_: dict[str, Any] | None = None
) -> tuple[bool, dict[str, Any] | str]:
    """Execute *source* in a RestrictedPython sandbox after AST validation.

    Parameters
    ----------
    source:
        The Python code to execute. It should be a string containing a valid
        Python block (e.g. ``"result = 2 + 2"``).
    locals_:
        Optional dictionary that will be used as the locals namespace. If not
        provided a fresh dict is created.

    Returns
    -------
    tuple[bool, dict[str, Any] | str]
        A tuple containing a success flag and either the locals dictionary
        on success or an error message string on failure.
    """
    # Issue #682 fail-closed gate: refuse in-process exec of dynamically
    # supplied code unless explicitly enabled (SUPREMEAI_ALLOW_INPROCESS_CODEGEN).
    # Returns the file's existing (False, error_message) failure convention.
    if not inprocess_codegen_enabled():
        error_message = denied_reason("tools.code.safe_executor.run_restricted")
        logger.error(error_message)
        return False, error_message

    if locals_ is None:
        locals_ = {}

    try:
        # Pre-execution AST verification
        validate_ast(source)

        # Compile the code. Use RestrictedPython if available, otherwise native compilation
        # protected by our strict validate_ast AST-filter and SAFE_BUILTINS sandbox.
        if HAS_RESTRICTED and compile_restricted is not None:
            byte_code = compile_restricted(source, "<string>", "exec")
            globals_ = dict(default_globals)
            globals_["__builtins__"] = SAFE_BUILTINS
        else:
            byte_code = compile(source, "<string>", "exec")
            globals_ = {"__builtins__": SAFE_BUILTINS}

        # Execute the sandboxed code.
        exec(byte_code, globals_, locals_)  # noqa: S102 -- Sandboxed bytecode with strict AST whitelist & builtins filter
        return True, locals_

    except (ValueError, SyntaxError, NameError, TypeError) as e:
        error_message = f"Restricted execution failed: {type(e).__name__}: {e}"
        logger.error(error_message)
        return False, error_message
    except Exception as e:
        error_message = f"An unexpected error occurred during restricted execution: {e}"
        logger.error(error_message)
        return False, error_message
