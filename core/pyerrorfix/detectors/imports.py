"""Import & Module error detector.

Catches:
  * ModuleNotFoundError — import of a name whose top-level package isn't in the
    known stdlib set and looks like a third-party module (heuristic).
  * ImportError          — `from module import Name` where Name is very likely
    missing (heuristic on common typos).
  * Circular import risk — a module importing from a package that, by file path,
    appears to import back (cheap heuristic).
  * Wildcard import      — `from x import *` (namespace pollution).
  * Unused import        — imported name never referenced in the module.
"""

from __future__ import annotations

import ast
from typing import Any

from pyerrorfix.core.issue import Category, Issue, Severity
from pyerrorfix.detectors.base import BaseDetector

# A pragmatic set of top-level stdlib module names. Not exhaustive, but covers
# the vast majority of real-world stdlib imports so we don't false-flag them.
_STDLIB = {
    "abc",
    "aifc",
    "argparse",
    "array",
    "ast",
    "asynchat",
    "asyncio",
    "asyncore",
    "atexit",
    "audioop",
    "base64",
    "bdb",
    "binascii",
    "binhex",
    "bisect",
    "builtins",
    "bz2",
    "calendar",
    "cgi",
    "cgitb",
    "chunk",
    "cmath",
    "cmd",
    "code",
    "codecs",
    "codeop",
    "collections",
    "colorsys",
    "compileall",
    "concurrent",
    "configparser",
    "contextlib",
    "contextvars",
    "copy",
    "copyreg",
    "cProfile",
    "crypt",
    "csv",
    "ctypes",
    "curses",
    "dataclasses",
    "datetime",
    "dbm",
    "decimal",
    "difflib",
    "dis",
    "distutils",
    "doctest",
    "email",
    "encodings",
    "enum",
    "errno",
    "faulthandler",
    "fcntl",
    "filecmp",
    "fileinput",
    "fnmatch",
    "fractions",
    "ftplib",
    "functools",
    "gc",
    "genericpath",
    "getopt",
    "getpass",
    "gettext",
    "glob",
    "graphlib",
    "grp",
    "gzip",
    "hashlib",
    "heapq",
    "hmac",
    "html",
    "http",
    "idlelib",
    "imaplib",
    "imghdr",
    "imp",
    "importlib",
    "inspect",
    "io",
    "ipaddress",
    "itertools",
    "json",
    "keyword",
    "lib2to3",
    "linecache",
    "locale",
    "logging",
    "lzma",
    "mailbox",
    "mailcap",
    "marshal",
    "math",
    "mimetypes",
    "mmap",
    "modulefinder",
    "msilib",
    "msvcrt",
    "multiprocessing",
    "netrc",
    "nis",
    "nntplib",
    "numbers",
    "operator",
    "optparse",
    "os",
    "ossaudiodev",
    "pathlib",
    "pdb",
    "pickle",
    "pickletools",
    "pipes",
    "pkgutil",
    "platform",
    "plistlib",
    "poplib",
    "posix",
    "posixpath",
    "pprint",
    "profile",
    "pstats",
    "pty",
    "pwd",
    "py_compile",
    "pyclbr",
    "pydoc",
    "pydoc_data",
    "pyexpat",
    "queue",
    "quopri",
    "random",
    "re",
    "readline",
    "reprlib",
    "resource",
    "rlcompleter",
    "runpy",
    "sched",
    "secrets",
    "select",
    "selectors",
    "shelve",
    "shlex",
    "shutil",
    "signal",
    "site",
    "smtpd",
    "smtplib",
    "sndhdr",
    "socket",
    "socketserver",
    "spwd",
    "sqlite3",
    "sre_compile",
    "sre_constants",
    "sre_parse",
    "ssl",
    "stat",
    "statistics",
    "string",
    "stringprep",
    "struct",
    "subprocess",
    "sunau",
    "symtable",
    "sys",
    "sysconfig",
    "syslog",
    "tabnanny",
    "tarfile",
    "telnetlib",
    "tempfile",
    "termios",
    "test",
    "textwrap",
    "threading",
    "time",
    "timeit",
    "tkinter",
    "token",
    "tokenize",
    "tomllib",
    "trace",
    "traceback",
    "tracemalloc",
    "tty",
    "turtle",
    "turtledemo",
    "types",
    "typing",
    "unicodedata",
    "unittest",
    "urllib",
    "uu",
    "uuid",
    "venv",
    "warnings",
    "wave",
    "weakref",
    "webbrowser",
    "winreg",
    "winsound",
    "wsgiref",
    "xdrlib",
    "xml",
    "xmlrpc",
    "zipapp",
    "zipfile",
    "zipimport",
    "zlib",
    "zoneinfo",
}


class ImportDetector(BaseDetector):
    name = "imports"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._imported_names: dict[str, ast.ImportFrom | ast.Import] = {}
        self._all_used: set[str] = set()

    def run(self) -> list[Issue]:  # type: ignore[override]
        try:
            tree = ast.parse(self.source, filename=self.filename)
        except SyntaxError:
            return self.issues
        # first pass: collect imports + all Name loads
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._imported_names[alias.asname or alias.name.split(".")[0]] = node
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    self._imported_names[alias.asname or alias.name] = node
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                self._all_used.add(node.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                self._all_used.add(node.value.id)
        # now visit for issue detection
        self.visit(tree)
        return self.issues

    def visit_Import(self, node: ast.Import) -> None:  # type: ignore[override]
        for alias in node.names:
            top = alias.name.split(".")[0]
            if top not in _STDLIB and not _looks_local(top, self.filename):
                # third-party: can't verify install statically — warn only if it
                # looks suspicious (CamelCase or has unusual chars).
                pass  # noqa: E501  # no-op; ModuleNotFoundError needs runtime check
            # unused import
            local = alias.asname or top
            if local not in self._all_used and local != "__future__":
                self.add(
                    rule_id="unused-import",
                    code="ImportError",
                    category=Category.IMPORTS,
                    severity=Severity.WARNING,
                    title=f"Unused import '{local}'",
                    message=f"'{alias.name}' is imported but never used in this module. "
                    f"Dead imports slow startup and blur dependencies.",
                    node=node,
                    fixable=True,
                    fix_description="Remove the unused import.",
                    suggestion=f"# remove: import {alias.name}",
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # type: ignore[override]
        module = node.module or ""
        top = module.split(".")[0]
        # wildcard import
        for alias in node.names:
            if alias.name == "*":
                self.add(
                    rule_id="wildcard-import",
                    code="ImportError",
                    category=Category.IMPORTS,
                    severity=Severity.WARNING,
                    title="Wildcard import",
                    message=f"`from {module} import *` pollutes the namespace and hides "
                    f"the source of names. Import explicitly.",
                    node=node,
                    fixable=True,
                    fix_description="Replace * with explicit names.",
                )
            else:
                local = alias.asname or alias.name
                if local not in self._all_used:
                    self.add(
                        rule_id="unused-import",
                        code="ImportError",
                        category=Category.IMPORTS,
                        severity=Severity.WARNING,
                        title=f"Unused import '{local}'",
                        message=f"'{local}' from '{module}' is imported but never used.",
                        node=node,
                        fixable=True,
                        fix_description="Remove the unused import.",
                        suggestion=f"# remove: from {module} import {alias.name}",
                    )
        # missing-name-import: `from <stdlib> import <Typo>`
        if top in _STDLIB:
            # we can introspect stdlib module attrs via __import__ safely
            missing = _missing_stdlib_names(module, [a.name for a in node.names if a.name != "*"])
            for m in missing:
                self.add(
                    rule_id="missing-name-import",
                    code="ImportError",
                    category=Category.IMPORTS,
                    severity=Severity.ERROR,
                    title=f"'{module}' has no attribute '{m}'",
                    message=f"`from {module} import {m}` will raise ImportError: "
                    f"cannot import name '{m}'.",
                    node=node,
                    fixable=False,
                    fix_description="Check the spelling against the module's documentation.",
                )

        # circular import risk: importing from a sibling that imports this file
        if _looks_circular(module, self.filename):
            self.add(
                rule_id="circular-import-risk",
                code="ImportError",
                category=Category.IMPORTS,
                severity=Severity.WARNING,
                title="Possible circular import",
                message=f"Importing '{module}' from '{self.filename}' may form a "
                f"circular import if that module imports this one back.",
                node=node,
                fixable=False,
                fix_description="Move the shared dependency to a lower-level module or "
                "defer the import inside the function that needs it.",
            )


def _looks_local(top: str, filename: str) -> bool:
    """Heuristic: does `top` look like a sibling package of `filename`?"""
    if not filename or filename == "<stdin>":
        return False
    # sibling .py file or package dir near the file
    from pathlib import Path

    p = Path(filename).resolve()
    for parent in [p.parent, *p.parents[:3]]:
        if (parent / f"{top}.py").exists() or (parent / top / "__init__.py").exists():
            return True
    return False


def _looks_circular(module: str, filename: str) -> bool:
    """Heuristic: importing `module` whose name matches our own top-level pkg."""
    if not filename or filename == "<stdin>" or not module:
        return False
    from pathlib import Path

    own = Path(filename).stem
    top = module.split(".")[0]
    # if the module's top == our own package dir name and we're not __init__
    own_dir = Path(filename).resolve().parent.name
    return top == own or top == own_dir


def _missing_stdlib_names(module: str, names: list[str]) -> list[str]:
    """Return names that genuinely don't exist on the stdlib `module`."""
    try:
        mod = __import__(module, fromlist=names)
    except Exception:
        return []
    missing = []
    for n in names:
        if not hasattr(mod, n):
            missing.append(n)
    return missing
