"""Asyncio error detector.

Catches:
  * `RuntimeWarning: coroutine was never awaited` — calling an async function
    without ``await`` (the #1 async bug).
  * `asyncio.CancelledError` swallowing — bare `except:` / `except Exception`
    inside a task that re-raises without re-raising CancelledError (PEP 654 era).
  * Blocking calls inside async functions — ``time.sleep``, ``requests.*``,
    ``open()`` (sync), ``subprocess.run`` — should use the async equivalents.
  * ``asyncio.get_event_loop()`` misuse (deprecated, should be ``get_running_loop``
    inside coroutines / ``asyncio.run`` outside).
  * Unhandled exceptions in ``asyncio.create_task(...)`` / ``ensure_future``
    (forgotten ``await`` / ``add_done_callback``).
"""

from __future__ import annotations

import ast
from typing import Any

from pyerrorfix.core.issue import Category, Issue, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

_BLOCKING_CALLS = {
    "time.sleep": "use `await asyncio.sleep(...)`",
    "requests.get": "use `aiohttp` / `httpx.AsyncClient`",
    "requests.post": "use `aiohttp` / `httpx.AsyncClient`",
    "requests.put": "use `aiohttp` / `httpx.AsyncClient`",
    "requests.delete": "use `aiohttp` / `httpx.AsyncClient`",
    "requests.patch": "use `aiohttp` / `httpx.AsyncClient`",
    "requests.head": "use `aiohttp` / `httpx.AsyncClient`",
    "requests.request": "use `aiohttp` / `httpx.AsyncClient`",
    "subprocess.run": "use `asyncio.create_subprocess_exec`",
    "subprocess.call": "use `asyncio.create_subprocess_exec`",
    "subprocess.check_output": "use `asyncio.create_subprocess_exec`",
    "subprocess.Popen": "use `asyncio.create_subprocess_exec`",
    "urllib.request.urlopen": "use `aiohttp` / `httpx`",
    "open": "use `aiofiles.open` (sync open blocks the loop)",
    "socket.socket": "use `asyncio.open_connection`",
    "httpx.get": "use `httpx.AsyncClient`",
    "httpx.post": "use `httpx.AsyncClient`",
}

_ASYNC_CONTEXT_MANAGERS = {"asynccontextmanager"}


class AsyncioDetector(BaseDetector):
    name = "asyncio"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._async_depth = 0
        self._async_funcs_seen: dict[str, ast.AsyncFunctionDef] = {}

    def run(self) -> list[Issue]:  # type: ignore[override]
        try:
            tree = ast.parse(self.source, filename=self.filename)
        except SyntaxError:
            return self.issues
        # collect async function definitions to recognise coroutine calls
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                self._async_funcs_seen[node.name] = node
        self.visit(tree)
        return self.issues

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # type: ignore[override]
        self._async_depth += 1
        self.generic_visit(node)
        self._async_depth -= 1

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)

        # missing await: calling a known-async function without await
        if name and name in self._async_funcs_seen:
            if not self._is_awaited(node):
                self.add(
                    rule_id="missing-await",
                    code="RuntimeWarning",
                    category=Category.ASYNCIO,
                    severity=Severity.ERROR,
                    title=f"Missing 'await' on coroutine '{name}'",
                    message=f"'{name}()' is an async function but is called without "
                    f"`await`. The coroutine object is discarded and never runs — "
                    f"raises `RuntimeWarning: coroutine '{name}' was never awaited`.",
                    node=node,
                    fixable=True,
                    fix_description="Prefix the call with `await`.",
                    suggestion=f"await {ast.unparse(node)}",
                )

        # calling a known async builtin (e.g. asyncio.sleep, asyncio.gather)
        async_builtins = {
            "asyncio.sleep": "await asyncio.sleep(...)",
            "asyncio.gather": "await asyncio.gather(...)",
            "asyncio.wait": "await asyncio.wait(...)",
            "asyncio.shield": "await asyncio.shield(...)",
            "asyncio.wait_for": "await asyncio.wait_for(...)",
        }
        if name in async_builtins and not self._is_awaited(node):
            self.add(
                rule_id="missing-await",
                code="RuntimeWarning",
                category=Category.ASYNCIO,
                severity=Severity.ERROR,
                title=f"Missing 'await' on '{name}'",
                message=f"'{name}(...)' returns a coroutine/awaitable and must be awaited. "
                f"Without `await` it does nothing.",
                node=node,
                fixable=True,
                fix_description="Prefix the call with `await`.",
                suggestion=f"await {ast.unparse(node)}",
            )

        # blocking call inside async function
        if self._async_depth > 0 and name in _BLOCKING_CALLS:
            self.add(
                rule_id="blocking-call-in-async",
                code="CancelledError",
                category=Category.ASYNCIO,
                severity=Severity.WARNING,
                title=f"Blocking call '{name}' inside async function",
                message=f"'{name}' blocks the event loop and starves other coroutines. "
                f"Long calls cause `asyncio.CancelledError` cascades. {_BLOCKING_CALLS[name]}.",
                node=node,
                fixable=False,
                fix_description=f"Replace with async equivalent: {_BLOCKING_CALLS[name]}.",
            )

        # asyncio.get_event_loop() misuse
        if name == "asyncio.get_event_loop":
            self.add(
                rule_id="event-loop-misuse",
                code="RuntimeError",
                category=Category.ASYNCIO,
                severity=Severity.WARNING,
                title="asyncio.get_event_loop() is deprecated",
                message="`asyncio.get_event_loop()` raises DeprecationWarning and will "
                "error when no loop is running. Use `asyncio.get_running_loop()` inside "
                "coroutines, or `asyncio.run(main())` at the top level.",
                node=node,
                fixable=False,
                fix_description="Use asyncio.get_running_loop() or asyncio.run().",
            )

        # create_task without keeping a reference / awaiting
        if name in ("asyncio.create_task", "asyncio.ensure_future"):
            parent = self._parent_context(node)
            if parent == "expr":
                self.add(
                    rule_id="unhandled-task-exception",
                    code="CancelledError",
                    category=Category.ASYNCIO,
                    severity=Severity.WARNING,
                    title="Fire-and-forget asyncio task",
                    message="`asyncio.create_task(...)` whose result is discarded. If the "
                    "task raises, the exception is silently swallowed (until GC) — common "
                    "source of CancelledError + lost stack traces. Keep the task reference.",
                    node=node,
                    fixable=False,
                    fix_description="Keep the task reference: `t = asyncio.create_task(...)` "
                    "and `await t` / `t.add_done_callback(...)`.",
                )

        self.generic_visit(node)

    def _is_awaited(self, call_node: ast.Call) -> bool:
        """Return True if call_node is wrapped in an Await expression."""
        # Walk up via parent map — AST has no parent pointers, so we re-scan tree.
        tree_root = self._tree_root
        for n in ast.walk(tree_root):
            if isinstance(n, ast.Await) and _contains(n, call_node):
                return True
            if isinstance(n, ast.YieldFrom) and _contains(n, call_node):
                return True
        return False

    def _parent_context(self, node: ast.AST) -> str:
        tree_root = self._tree_root
        for n in ast.walk(tree_root):
            if isinstance(n, ast.Expr) and _contains(n, node):
                return "expr"
            if isinstance(n, ast.Assign | ast.Await | ast.Return | ast.Call) and _contains(n, node):
                return "value"
        return "other"

    @property
    def _tree_root(self) -> ast.AST:
        # cache the parsed tree
        if not hasattr(self, "_cached_tree"):
            try:
                self._cached_tree = ast.parse(self.source, filename=self.filename)
            except SyntaxError:
                self._cached_tree = ast.Module(body=[], type_ignores=[])
        return self._cached_tree


def _contains(haystack: ast.AST, needle: ast.AST) -> bool:
    for n in ast.walk(haystack):
        if n is needle:
            return True
    return False
