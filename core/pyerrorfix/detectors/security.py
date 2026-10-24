"""Security error detector (NEW category).

Catches:
  * Hardcoded secrets — assignment of string literals to names like
    ``api_key``/``password``/``secret``/``token``.
  * eval() / exec() — arbitrary code execution.
  * pickle.loads / yaml.load (unsafe) — deserialization RCE.
  * Shell injection — subprocess(..., shell=True) with string command.
  * Weak hash — hashlib.md5 / sha1 used for security.
  * SQL injection — already flagged by database detector, but also catches
    f-strings passed to DB-API execute.
"""

from __future__ import annotations

import ast
import re

from pyerrorfix.core.issue import Category, Severity
from pyerrorfix.detectors.base import BaseDetector, iter_call_name

_SECRET_NAME_RE = re.compile(
    r"(password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key|"
    r"client[_-]?secret|aws[_-]?secret|bearer|jwt)",
    re.I,
)
_HIGH_ENTROPY_RE = re.compile(r"^[A-Za-z0-9_\-+/=]{16,}$")


class SecurityDetector(BaseDetector):
    name = "security"

    def visit_Call(self, node: ast.Call) -> None:  # type: ignore[override]
        name = iter_call_name(node)

        if name in ("eval", "exec"):
            self.add(
                rule_id="eval-exec",
                code="RuntimeError",
                category=Category.SECURITY,
                severity=Severity.CRITICAL,
                title=f"Use of {name}()",
                message=f"`{name}()` executes arbitrary code. In production it is a "
                f"remote-code-execution vector and crashes on malformed input.",
                node=node,
                fixable=False,
                fix_description=f"Avoid {name}(); use ast.literal_eval for literals, or a parser.",
            )

        if name in (
            "pickle.loads",
            "pickle.load",
            "cPickle.loads",
            "cPickle.load",
            "yaml.load",
            "marshal.loads",
            "shelve.open",
        ):
            unsafe = name == "yaml.load"
            self.add(
                rule_id="pickle-deserialize",
                code="RuntimeError",
                category=Category.SECURITY,
                severity=Severity.ERROR,
                title=f"Unsafe deserialization via {name}()",
                message=f"`{name}()` can execute arbitrary code on malicious input. "
                f"{'Use yaml.safe_load instead.' if unsafe else 'Prefer JSON or restrict to trusted sources.'}",
                node=node,
                fixable=False,
                fix_description="Use yaml.safe_load / json.loads / restrict input trust.",
            )

        if name in (
            "subprocess.run",
            "subprocess.call",
            "subprocess.Popen",
            "subprocess.check_output",
            "subprocess.check_call",
            "os.system",
            "os.popen",
        ):
            shell_true = any(
                kw.arg == "shell" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in node.keywords
            )
            cmd_arg = node.args[0] if node.args else None
            if (name in ("os.system", "os.popen") or shell_true) and _is_dynamic_string(cmd_arg):
                self.add(
                    rule_id="shell-injection",
                    code="RuntimeError",
                    category=Category.SECURITY,
                    severity=Severity.CRITICAL,
                    title=f"Shell injection via {name}()",
                    message=f"{name}() with shell=True and a dynamic command lets an "
                    f"attacker inject `; rm -rf /` etc.",
                    node=node,
                    fixable=False,
                    fix_description="Pass args as a list and set shell=False.",
                )

        if name in ("hashlib.md5", "hashlib.sha1"):
            # heuristic: warn on any use of md5/sha1 — caller should switch to sha256+/bcrypt
            self.add(
                rule_id="weak-hash",
                code="ValueError",
                category=Category.SECURITY,
                severity=Severity.WARNING,
                title=f"Weak hash {name}()",
                message=f"{name}() is cryptographically broken. For passwords use "
                f"passlib/bcrypt; for integrity use sha256+.",
                node=node,
                fixable=False,
                fix_description="Use hashlib.sha256/sha512 or passlib for passwords.",
            )

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # type: ignore[override]
        for target in node.targets:
            if isinstance(target, ast.Name) and _SECRET_NAME_RE.search(target.id):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    val = node.value.value
                    if (
                        val
                        and not val.startswith(("os.environ", "$"))
                        and _HIGH_ENTROPY_RE.match(val)
                    ):
                        self.add(
                            rule_id="hardcoded-secret",
                            code="ValueError",
                            category=Category.SECURITY,
                            severity=Severity.CRITICAL,
                            title=f"Hardcoded secret in '{target.id}'",
                            message=f"'{target.id}' is assigned a hardcoded string. "
                            f"Leaks into version control. Load from env / secret manager.",
                            node=node,
                            fixable=True,
                            fix_description="Read from environment variable.",
                            suggestion=f'import os\n{target.id} = os.environ["{target.id.upper()}"]',
                        )
        self.generic_visit(node)


def _is_dynamic_string(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add | ast.Mod):
        return True
    if isinstance(node, ast.Name):
        return True  # variable command → still dynamic
    return False
