# backend/services/tool_forge.py
"""SupremeAI Tool Forge Service (Phase 7.1 - North Star Pillar 3).

Dynamic on-the-fly Python tool synthesis with zero-RCE AST isolation:
- Verifies synthesized Python code using ASTSandboxScanner before execution.
- Blocks dangerous primitives (os, subprocess, eval, exec, socket, dunder traversal).
- Executes verified tools in an ephemeral restricted execution namespace.

Issue #704 (fail-closed codegen gate): the restricted-namespace ``exec()`` in
``execute_tool`` is NOT a security sandbox. By default
(``SUPREMEAI_ALLOW_INPROCESS_CODEGEN`` unset — all prod/staging) it refuses to
execute and raises ``ToolForgeError`` (the caller's existing error convention;
``services/living_engine.py`` steps run under self-healing which handles it).
The exec path only runs when the gate is explicitly enabled (local development
only), with a loud one-time warning emitted at import/boot when it is.
"""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass, field
from typing import Any

from core.logging_config import logger
from core.security.codegen_gate import (
    denied_reason,
    inprocess_codegen_enabled,
    warn_inprocess_codegen_boot,
)
from core.security.scanning.ast_scanner import ASTSandboxScanner

# Issue #704: loud one-time boot warning when the in-process exec escape hatch
# is explicitly enabled (local development only).
if inprocess_codegen_enabled():
    warn_inprocess_codegen_boot("ToolForgeService.execute_tool")


class ToolForgeError(Exception):
    """Base exception for ToolForge operations."""


class SecurityViolationError(ToolForgeError):
    """Raised when synthesized code fails AST safety validation."""


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, str] = field(default_factory=dict)
    return_type: str = "dict"
    category: str = "dynamic_synthesized"


@dataclass
class SynthesizedTool:
    spec: ToolSpec
    source_code: str
    is_safe: bool = False
    compiled_code: Any = field(default=None, repr=False)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.spec.name,
            "description": self.spec.description,
            "parameters": self.spec.parameters,
            "return_type": self.spec.return_type,
            "is_safe": self.is_safe,
            "created_at": self.created_at,
        }


# Safe builtins allowed in execution sandbox
SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "pow": pow,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
}


class ToolForgeService:
    """Synthesizes, audits, and safely executes dynamic tools inside AST-isolated environments."""

    def __init__(self, scanner: ASTSandboxScanner | None = None) -> None:
        self.scanner = scanner or ASTSandboxScanner()
        self._tool_registry: dict[str, SynthesizedTool] = {}

    def verify_code_safety(self, code: str) -> bool:
        """Runs static AST analysis to ensure code contains no dangerous calls or escapes."""
        if not code or not code.strip():
            return False

        try:
            scan_result = self.scanner.scan(code)
            return scan_result.is_safe
        except Exception as exc:
            logger.warning(f"AST scan exception: {exc}")
            return False

    def forge_tool(self, spec: ToolSpec, code: str) -> SynthesizedTool:
        """Synthesizes and registers an audited dynamic tool."""
        cleaned_code = code.strip()

        # 1. AST Static Security Audit
        if not self.verify_code_safety(cleaned_code):
            scan_res = self.scanner.scan(cleaned_code)
            findings = scan_res.findings
            logger.critical(f"ToolForge security violation blocked for '{spec.name}': {findings}")
            raise SecurityViolationError(f"Code violated sandbox safety rules: {findings}")

        # 2. Syntax & Bytecode Compilation
        try:
            compiled = compile(cleaned_code, f"<synthesized_tool_{spec.name}>", "exec")
        except SyntaxError as exc:
            raise ToolForgeError(f"Syntax error in synthesized tool code: {exc}") from exc

        tool = SynthesizedTool(
            spec=spec,
            source_code=cleaned_code,
            is_safe=True,
            compiled_code=compiled,
        )

        self._tool_registry[spec.name] = tool
        logger.info(f"ToolForge: Successfully forged and registered secure tool '{spec.name}'")
        return tool

    def execute_tool(
        self,
        tool: SynthesizedTool,
        params: dict[str, Any],
        timeout_seconds: float = 5.0,
    ) -> Any:
        """Executes a forged tool in a restricted sandbox namespace."""
        if not tool.is_safe or not tool.compiled_code:
            raise SecurityViolationError(f"Tool '{tool.spec.name}' is unverified or unsafe.")

        # Issue #704 fail-closed gate: refuse in-process exec of LLM-generated
        # code unless explicitly enabled (SUPREMEAI_ALLOW_INPROCESS_CODEGEN).
        # ToolForgeError matches this service's existing failure convention.
        if not inprocess_codegen_enabled():
            logger.warning(
                f"[ToolForge] Blocked in-process exec for '{tool.spec.name}': "
                f"{denied_reason('ToolForgeService.execute_tool')}"
            )
            raise ToolForgeError(denied_reason("ToolForgeService.execute_tool"))

        # Restricted execution scope
        sandbox_globals = {
            "__builtins__": SAFE_BUILTINS,
            "__name__": "__tool_forge__",
        }
        sandbox_locals: dict[str, Any] = {}

        # Issue #1589: enforce the time budget the signature always promised.
        # ``timeout_seconds`` was previously accepted but never applied, so a
        # runaway/looping tool could hang the API process indefinitely (even in
        # local-dev gate-on mode). SIGALRM is POSIX + main-thread only; where it
        # is unavailable we still execute (gate + AST scanner remain the primary
        # controls) — the limit is defense-in-depth, not the sandbox itself.
        timeout_seconds = max(0.1, float(timeout_seconds))
        alarm_active = hasattr(signal, "SIGALRM")
        if alarm_active:

            def _alarm_timeout(signum: int, frame: Any) -> None:
                raise TimeoutError(
                    f"tool '{tool.spec.name}' exceeded {timeout_seconds}s execution budget"
                )

            try:
                signal.signal(signal.SIGALRM, _alarm_timeout)
            except ValueError:
                # Not on the main thread — SIGALRM cannot be installed here.
                alarm_active = False
        if alarm_active:
            signal.setitimer(signal.ITIMER_REAL, timeout_seconds)

        try:
            exec(tool.compiled_code, sandbox_globals, sandbox_locals)

            # Defense-in-depth (#1589): reject dunder-level globals injected by
            # the executed code itself (sandbox-escape staging attempts).
            staged_dunders = [k for k in sandbox_locals if k.startswith("__") and k.endswith("__")]
            if staged_dunders:
                raise SecurityViolationError(
                    f"Tool '{tool.spec.name}' staged dunder-level globals: {staged_dunders}"
                )

            # Target function matching spec.name or 'main' or 'run' or the only callable
            func = (
                sandbox_locals.get(tool.spec.name)
                or sandbox_locals.get("run")
                or sandbox_locals.get("main")
            )

            if not func:
                callables = [v for v in sandbox_locals.values() if callable(v)]
                if callables:
                    func = callables[0]

            if not callable(func):
                raise ToolForgeError(f"No executable entrypoint found in tool '{tool.spec.name}'")

            # Execute tool logic with parameters
            result = func(**params) if params else func()
            return result

        except TimeoutError as exc:
            logger.error(f"Execution budget exceeded for tool '{tool.spec.name}': {exc}")
            raise ToolForgeError(str(exc)) from exc
        except SecurityViolationError:
            raise
        except Exception as exc:
            logger.error(f"Execution error in tool '{tool.spec.name}': {exc}")
            raise ToolForgeError(f"Tool execution failed: {exc}") from exc
        finally:
            if alarm_active:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, signal.SIG_DFL)

    def get_tool(self, name: str) -> SynthesizedTool | None:
        return self._tool_registry.get(name)

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self._tool_registry.values()]
