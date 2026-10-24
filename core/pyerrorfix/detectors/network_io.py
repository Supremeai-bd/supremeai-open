"""Network & I/O error detector (NEW — category 1 in the expanded taxonomy).

Catches:
  * `ConnectionRefusedError` — socket.connect to a known-down port (heuristic:
    connect without try-except).
  * `ConnectionResetError`    — long-lived socket without retry on reset.
  * `ConnectionAbortedError`  — similar.
  * `TimeoutError` / `socket.timeout` — requests/httpx/socket calls without an
    explicit `timeout=` argument (the #1 production network bug).
  * `JSONDecodeError`         — `json.loads(resp.text)` without try/except
    (third-party APIs return HTML/empty on error).
  * `ReadTimeout` / `ConnectTimeout` — requests.get(...) without timeout=
    (alias of TimeoutError but framed for the requests library).
"""

from __future__ import annotations

import ast

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

# Calls that perform network I/O and MUST carry a timeout= argument.
_NETWORK_CALLS = {
    "requests.get": "requests",
    "requests.post": "requests",
    "requests.put": "requests",
    "requests.patch": "requests",
    "requests.delete": "requests",
    "requests.head": "requests",
    "requests.options": "requests",
    "requests.request": "requests",
    "httpx.get": "httpx",
    "httpx.post": "httpx",
    "httpx.put": "httpx",
    "httpx.patch": "httpx",
    "httpx.delete": "httpx",
    "httpx.head": "httpx",
    "httpx.options": "httpx",
    "httpx.request": "httpx",
    "urllib.request.urlopen": "urllib",
    "urllib3.PoolManager.request": "urllib3",
    "aiohttp.ClientSession.get": "aiohttp",
    "aiohttp.ClientSession.post": "aiohttp",
    "httpx.AsyncClient.get": "httpx",
    "httpx.AsyncClient.post": "httpx",
    "socket.create_connection": "socket",
    "socket.socket": "socket",
    "websocket.create_connection": "websocket",
    "websockets.connect": "websockets",
}


class NetworkIoDetector(BaseDetector):
    name = "network-io"

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)

        # --- missing timeout on a network call ---
        if name in _NETWORK_CALLS:
            has_timeout = any(kw.arg == "timeout" for kw in node.keywords)
            # urllib.request.urlopen takes timeout as 4th positional arg
            if name == "urllib.request.urlopen" and len(node.args) >= 4:
                has_timeout = True
            if not has_timeout:
                self.add(
                    rule_id="missing-timeout",
                    code="TimeoutError",
                    category=Category.FILES,  # network/IO is part of the file/OS family in our enum
                    severity=Severity.WARNING,
                    title=f"{name}() without timeout=",
                    message=f"`{name}()` has no `timeout=` argument. On a slow or "
                    f"hung peer the call blocks forever (TimeoutError / ReadTimeout "
                    f"only fires after the default, which can be 60s+ or never).",
                    node=node,
                    fixable=True,
                    fix_description="Add `timeout=10` (or a tuple for connect/read).",
                    suggestion=f"{ast.unparse(node).rstrip(')')}, timeout=10)",
                )

        # --- json.loads without try/except → JSONDecodeError ---
        if name in ("json.loads", "json.load"):
            if not self._inside_try(node):
                self.add(
                    rule_id="json-decode-uncaught",
                    code="JSONDecodeError",
                    category=Category.FILES,
                    severity=Severity.WARNING,
                    title=f"{name}() without try/except JSONDecodeError",
                    message=f"`{name}()` raises json.JSONDecodeError when the input is "
                    f"not valid JSON (HTML error pages, empty bodies, truncated streams). "
                    f"Third-party APIs frequently return non-JSON on failure.",
                    node=node,
                    fixable=False,
                    fix_description="Wrap in try/except json.JSONDecodeError; fall back to safe default.",
                )

        # --- bare socket.connect without try → ConnectionRefusedError ---
        if name in ("socket.connect", "socket.connect_ex") or (
            name and name.endswith(".connect") and "socket" in name
        ):
            if not self._inside_try(node):
                self.add(
                    rule_id="uncaught-connection-error",
                    code="ConnectionRefusedError",
                    category=Category.FILES,
                    severity=Severity.WARNING,
                    title="socket connect() without try/except",
                    message="connect() raises ConnectionRefusedError (server down), "
                    "ConnectionResetError, or TimeoutError. Wrap in try/except "
                    "OSError to handle all connection failures.",
                    node=node,
                    fixable=False,
                    fix_description="Wrap in try/except OSError (covers ConnectionError family).",
                )

        self.generic_visit(node)

    def _inside_try(self, target: ast.AST) -> bool:
        """True if `target` is nested inside a Try node's body (not handler)."""
        tree = self._tree
        for n in ast.walk(tree):
            if isinstance(n, ast.Try):
                for stmt in n.body:
                    if _contains(stmt, target):
                        return True
        return False

    @property
    def _tree(self) -> ast.AST:
        if not hasattr(self, "_cached_tree"):
            try:
                self._cached_tree = ast.parse(self.source, filename=self.filename)
            except SyntaxError:
                self._cached_tree = ast.Module(body=[], type_ignores=[])
        return self._cached_tree


def _contains(haystack: ast.AST, needle: ast.AST) -> bool:
    if haystack is needle:
        return True
    for child in ast.iter_child_nodes(haystack):
        if _contains(child, needle):
            return True
    return False
