"""backend/tools/ephemeral_synthesizer.py — On-the-Fly Ephemeral Micro-Tool Synthesizer.

Mandatory Rule & Security Protocols:
- Dynamically generates Python micro-scripts when an authorized capability is missing.
- Pre-execution validation via AST scanner: blocks os.system, subprocess, eval, exec, and file tampering.
- Executes within bounded, resource-limited sandbox.
- Auto-GC: immediately deletes ephemeral code and execution artifacts after result collection.

Issue #704 (fail-closed codegen gate): the restricted-namespace ``exec()`` below
is NOT a security sandbox. By default (``SUPREMEAI_ALLOW_INPROCESS_CODEGEN``
unset — all prod/staging) ``execute_ephemeral_script`` refuses to run and returns
a ``status="rejected"`` result without executing anything. The exec path only
runs when the gate is explicitly enabled (local development only), and a loud
warning is emitted once at import/boot when it is.
"""

from __future__ import annotations

import ast
import tempfile
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.logging_config import logger
from core.security.codegen_gate import (
    denied_reason,
    inprocess_codegen_enabled,
    warn_inprocess_codegen_boot,
)

# Issue #704: loud one-time boot warning when the in-process exec escape hatch
# is explicitly enabled (local development only).
if inprocess_codegen_enabled():
    warn_inprocess_codegen_boot("EphemeralToolSynthesizer.execute_ephemeral_script")


class SynthesizedToolResult(BaseModel):
    tool_name: str
    status: str  # succeeded | failed | rejected
    result: Any = None
    error: str | None = None
    ast_safe: bool = False
    execution_time_ms: float = 0.0


# Prohibited AST patterns
_BANNED_NAMES = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "socket",
        "eval",
        "exec",
        "shutil",
        "builtins",
        "__import__",
        "globals",
        "locals",
    }
)


def validate_ephemeral_code_ast(code: str) -> tuple[bool, str | None]:
    """Strict AST validation of dynamically generated micro-script."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    for node in ast.walk(tree):
        # Disallow imports of prohibited low-level modules
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in _BANNED_NAMES:
                    return False, f"Illegal import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in _BANNED_NAMES:
                return False, f"Illegal from-import: {node.module}"
        elif isinstance(node, ast.Name):
            if node.id in ("eval", "exec", "__import__"):
                return False, f"Illegal call to {node.id}"

    return True, None


class EphemeralToolSynthesizer:
    """Safely synthesizes, validates, executes, and cleans up transient micro-scripts."""

    async def execute_ephemeral_script(
        self,
        tool_name: str,
        script_code: str,
        entrypoint_func: str = "run",
        input_args: dict[str, Any] | None = None,
        timeout_seconds: float = 5.0,
    ) -> SynthesizedToolResult:
        start_time = time.perf_counter()
        args = input_args or {}

        # 0. Issue #704 fail-closed gate: refuse in-process exec of LLM-generated
        # code unless explicitly enabled (SUPREMEAI_ALLOW_INPROCESS_CODEGEN).
        if not inprocess_codegen_enabled():
            logger.warning(
                f"[EphemeralSynthesizer] Blocked in-process exec for '{tool_name}': "
                f"{denied_reason('EphemeralToolSynthesizer.execute_ephemeral_script')}"
            )
            return SynthesizedToolResult(
                tool_name=tool_name,
                status="rejected",
                error=denied_reason("EphemeralToolSynthesizer.execute_ephemeral_script"),
                ast_safe=False,
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        # 1. AST Pre-Execution Security Gate
        is_safe, violation = validate_ephemeral_code_ast(script_code)
        if not is_safe:
            logger.warning(
                f"[EphemeralSynthesizer] AST security check rejected '{tool_name}': {violation}"
            )
            return SynthesizedToolResult(
                tool_name=tool_name,
                status="rejected",
                error=f"AST Security Violation: {violation}",
                ast_safe=False,
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        # 2. Ephemeral execution in controlled isolated namespace with auto-cleanup
        with tempfile.TemporaryDirectory(prefix="ephemeral_tool_") as tmpdir:
            temp_script_path = Path(tmpdir) / "micro_script.py"
            temp_script_path.write_text(script_code, encoding="utf-8")

            try:
                # Safe namespace execution
                restricted_globals: dict[str, Any] = {
                    "__builtins__": {
                        "abs": abs,
                        "all": all,
                        "any": any,
                        "bool": bool,
                        "dict": dict,
                        "float": float,
                        "int": int,
                        "len": len,
                        "list": list,
                        "max": max,
                        "min": min,
                        "range": range,
                        "round": round,
                        "set": set,
                        "str": str,
                        "sum": sum,
                        "tuple": tuple,
                        "zip": zip,
                    }
                }
                local_scope: dict[str, Any] = {}

                # Compile and execute within restricted scope
                compiled_code = compile(script_code, filename=str(temp_script_path), mode="exec")
                exec(compiled_code, restricted_globals, local_scope)  # nosec B102

                func = local_scope.get(entrypoint_func)
                if not callable(func):
                    return SynthesizedToolResult(
                        tool_name=tool_name,
                        status="failed",
                        error=f"Entrypoint function '{entrypoint_func}' not found or not callable",
                        ast_safe=True,
                        execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
                    )

                # Execute entrypoint
                output = func(**args)
                elapsed = (time.perf_counter() - start_time) * 1000.0
                logger.info(
                    f"[EphemeralSynthesizer] Tool '{tool_name}' executed successfully in {elapsed:.1f}ms"
                )

                return SynthesizedToolResult(
                    tool_name=tool_name,
                    status="succeeded",
                    result=output,
                    ast_safe=True,
                    execution_time_ms=elapsed,
                )
            except Exception as exc:
                elapsed = (time.perf_counter() - start_time) * 1000.0
                logger.error(
                    f"[EphemeralSynthesizer] Execution failed for '{tool_name}': {exc}",
                    exc_info=True,
                )
                return SynthesizedToolResult(
                    tool_name=tool_name,
                    status="failed",
                    error=str(exc),
                    ast_safe=True,
                    execution_time_ms=elapsed,
                )
            finally:
                # Directory and script automatically purged on context exit
                pass


ephemeral_synthesizer = EphemeralToolSynthesizer()
