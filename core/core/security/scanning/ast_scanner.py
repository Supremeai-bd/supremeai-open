"""
AST-based Sandbox Scanner — Pre-execution code validation for sandbox environments.

বাংলা: স্যান্ডবক্সে কোড এক্সিকিউট করার আগে AST স্ক্যান করে বিপজ্জনক প্যাটার্ন শনাক্ত করে।
This scanner detects and blocks:
- getattr() / hasattr() calls (potential sandbox escape)
- __import__ builtin usage
- eval() / exec() / compile() calls
- __subclasses__() traversal patterns
- os.system / subprocess calls
- File I/O operations (open, read, write)
- Network operations (socket, urllib, requests)
- Attribute access on dangerous objects

Usage:
    scanner = ASTSandboxScanner()
    result = scanner.scan(code_string)
    if result.is_safe:
        # Proceed with execution
    else:
        # Block execution, log findings
"""

import ast
import re
from dataclasses import dataclass, field

# ── Constants: Blocked patterns ────────────────────────────────────────────────
# Functions that are always blocked in sandbox execution
BLOCKED_BUILTIN_FUNCTIONS: frozenset[str] = frozenset(
    {
        "getattr",
        "hasattr",
        "setattr",
        "delattr",
        "__import__",
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "breakpoint",
    }
)

# Module imports that are always blocked
BLOCKED_MODULES: frozenset[str] = frozenset(
    {
        "os",
        "subprocess",
        "sys",
        "socket",
        "ctypes",
        "signal",
        "multiprocessing",
        "threading",
        "asyncio",
        "importlib",
        "inspect",
        "builtins",
        "pickle",
        "marshal",
        "shelve",
        "dbm",
        "sqlite3",
        "telnetlib",
        "ftplib",
        "http",
        "urllib",
        "requests",
        "aiohttp",
        "httpx",
        "webbrowser",
        "antigravity",
        "code",
        "codeop",
        "codecs",
        "pty",
        "tty",
        "termios",
        "fcntl",
        "mmap",
        "platform",
        "pdb",
        "profile",
        "cProfile",
        "trace",
        "traceback",
        "gc",
        "sysconfig",
        "distutils",
        "setuptools",
        "pkgutil",
        "pkg_resources",
    }
)

# Blocked dunder attribute patterns (e.g., __class__, __bases__, __subclasses__)
BLOCKED_DUNDER_PATTERNS: frozenset[str] = frozenset(
    {
        "__class__",
        "__bases__",
        "__subclasses__",
        "__globals__",
        "__code__",
        "__closure__",
        "__dict__",
        "__builtins__",
        "__import__",
        "__reduce__",
        "__reduce_ex__",
        "__getattribute__",
        "__setattr__",
        "__delattr__",
    }
)

# Patterns that indicate sandbox escape attempts
SANDBOX_ESCAPE_PATTERNS: list[re.Pattern] = [
    re.compile(r"__class__\.__bases__"),
    re.compile(r"__class__\.__mro__"),
    re.compile(r"__subclasses__\s*\("),
    re.compile(r"__globals__\s*\["),
    re.compile(r"__builtins__\s*\["),
    re.compile(r"\.__dict__\.get"),
    re.compile(r"\.__getattribute__\s*\("),
    re.compile(r"object\s*\(\)"),
    re.compile(r"\.__reduce__\s*\("),
    re.compile(r"\.__reduce_ex__\s*\("),
]


@dataclass
class ScanResult:
    """Result of an AST sandbox scan.

    Attributes:
        is_safe: True if code passes all safety checks.
        findings: List of safety violations found.
        severity: Maximum severity level ("CRITICAL", "HIGH", "MEDIUM", "LOW", or "PASS").
        blocked_builtins: List of blocked builtin functions used.
        blocked_imports: List of blocked module imports.
        dunder_accesses: List of dangerous dunder attribute accesses.
        escape_patterns: List of sandbox escape patterns matched.
    """

    is_safe: bool = True
    findings: list[str] = field(default_factory=list)
    severity: str = "PASS"
    blocked_builtins: list[str] = field(default_factory=list)
    blocked_imports: list[str] = field(default_factory=list)
    dunder_accesses: list[str] = field(default_factory=list)
    escape_patterns: list[str] = field(default_factory=list)


class ASTSandboxScanner:
    """
    AST-based scanner that validates Python code before sandbox execution.

    বাংলা: স্যান্ডবক্সে কোড রান করার আগে AST পার্স করে বিপজ্জনক প্যাটার্ন খুঁজে বের করে।
    This prevents getattr/hasattr bypass, __import__ injection, and other sandbox escape techniques.
    """

    def __init__(self, strict_mode: bool = True) -> None:
        """
        Initialize the scanner.

        Args:
            strict_mode: If True, blocks ALL dangerous patterns including imports.
                         If False, allows safe imports (like math, json) but still blocks
                         dangerous builtins and sandbox escape patterns.
        """
        self.strict_mode = strict_mode
        # বাংলা মন্তব্য: অনুমোদিত মডিউল — strict_mode=False হলে এগুলো allow করা হবে
        self._safe_imports: frozenset[str] = frozenset(
            {
                "math",
                "json",
                "re",
                "collections",
                "itertools",
                "functools",
                "typing",
                "dataclasses",
                "enum",
                "decimal",
                "fractions",
                "random",
                "statistics",
                "string",
                "textwrap",
                "pprint",
                "copy",
                "bisect",
                "heapq",
                "array",
                "struct",
                "hashlib",
                "base64",
                "datetime",
                "calendar",
                "time",
                "zoneinfo",
                "pathlib",
                "fnmatch",
                "glob",
                "tempfile",
                "uuid",
                "warnings",
                "abc",
                "contextlib",
            }
        )

    def scan(self, code: str) -> ScanResult:
        """
        Scan Python code for dangerous patterns before sandbox execution.

        Args:
            code: The Python source code string to scan.

        Returns:
            ScanResult with safety assessment and detailed findings.
        """
        result = ScanResult()

        if not code or not code.strip():
            result.is_safe = True
            return result

        # Step 1: Try to parse AST
        try:
            tree = ast.parse(code, mode="exec")
        except SyntaxError as e:
            result.is_safe = False
            result.severity = "HIGH"
            result.findings.append(f"Syntax error in code: {e}")
            return result

        # Step 2: Walk the AST and check for dangerous patterns
        visitor = _SandboxVisitor(self.strict_mode, self._safe_imports)
        visitor.visit(tree)

        # Step 3: Aggregate findings
        result.blocked_builtins = list(visitor.blocked_builtins)
        result.blocked_imports = list(visitor.blocked_imports)
        result.dunder_accesses = list(visitor.dunder_accesses)
        result.escape_patterns = list(visitor.escape_patterns)

        if visitor.escape_patterns:
            result.is_safe = False
            result.severity = "CRITICAL"
            result.findings.append(
                f"Sandbox escape attempt detected: {', '.join(visitor.escape_patterns)}"
            )

        if visitor.blocked_builtins:
            result.is_safe = False
            result.severity = result.severity if result.severity != "PASS" else "HIGH"
            result.findings.append(
                f"Blocked builtin functions used: {', '.join(visitor.blocked_builtins)}"
            )

        if visitor.blocked_imports:
            if self.strict_mode:
                result.is_safe = False
                result.severity = result.severity if result.severity != "PASS" else "MEDIUM"
                result.findings.append(
                    f"Blocked module imports detected: {', '.join(visitor.blocked_imports)}"
                )
            else:
                # Non-strict mode: still log but don't block
                result.findings.append(
                    f"Blocked imports (non-strict mode, logged only): {', '.join(visitor.blocked_imports)}"
                )

        if visitor.dunder_accesses:
            if self.strict_mode:
                result.is_safe = False
                result.severity = result.severity if result.severity != "PASS" else "HIGH"
                result.findings.append(
                    f"Dangerous dunder attribute access: {', '.join(visitor.dunder_accesses)}"
                )
            else:
                # বাংলা মন্তব্য: Non-strict mode-তেও dunder access লগ করা হয় কিন্তু ব্লক নয়
                result.findings.append(
                    f"Dunder access detected (non-strict mode, logged only): {', '.join(visitor.dunder_accesses)}"
                )

        # Step 4: Text-based pattern matching for additional detection
        text_findings = self._scan_text_patterns(code)
        if text_findings:
            for finding in text_findings:
                result.findings.append(finding)
                if "escape" in finding.lower():
                    result.is_safe = False
                    result.severity = "CRITICAL"
                    result.escape_patterns.append(finding)

        if result.is_safe and result.severity == "PASS":
            result.severity = "PASS"

        return result

    def _scan_text_patterns(self, code: str) -> list[str]:
        """
        Text-based pattern scanning for sandbox escape attempts that
        might bypass AST parsing (e.g., via string obfuscation).

        বাংলা মন্তব্য: টেক্সট-ভিত্তিক স্ক্যানিং — AST বাইপাস করার চেষ্টা শনাক্ত করে।
        """
        findings: list[str] = []

        for pattern in SANDBOX_ESCAPE_PATTERNS:
            if pattern.search(code):
                findings.append(f"Sandbox escape pattern detected: {pattern.pattern}")

        # Check for base64-encoded or hex-encoded dangerous calls
        # যা AST বাইপাস করার জন্য encode করা হতে পারে
        encoded_indicators = ["base64", "b64decode", "bytes.fromhex", "decode('hex')"]
        for indicator in encoded_indicators:
            if indicator in code.lower():
                findings.append(
                    f"Encoded payload indicator detected: '{indicator}' — possible AST bypass attempt"
                )

        return findings


class _SandboxVisitor(ast.NodeVisitor):
    """
    AST NodeVisitor that collects dangerous patterns in Python code.

    বাংলা মন্তব্য: AST নোড ওয়াক করে বিপজ্জনক ফাংশন কল, ইম্পোর্ট এবং অ্যাট্রিবিউট অ্যাক্সেস শনাক্ত করে।
    """

    def __init__(self, strict_mode: bool, safe_imports: frozenset[str]) -> None:
        self.strict_mode = strict_mode
        self.safe_imports = safe_imports
        self.blocked_builtins: set[str] = set()
        self.blocked_imports: set[str] = set()
        self.dunder_accesses: set[str] = set()
        self.escape_patterns: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function/method calls and check for dangerous builtins."""
        # Check for direct function name calls (e.g., `getattr(obj, 'attr')`)
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name in BLOCKED_BUILTIN_FUNCTIONS:
                self.blocked_builtins.add(func_name)

        # Check for method calls on objects (e.g., `obj.__getattribute__('attr')`)
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr
            if attr_name in BLOCKED_BUILTIN_FUNCTIONS:
                self.blocked_builtins.add(attr_name)

        # Check for object.__reduce__(), object.__reduce_ex__() patterns
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ("__reduce__", "__reduce_ex__"):
                self.dunder_accesses.add(node.func.attr)
                self.escape_patterns.add(f"{node.func.attr}() call")

        # Check for getattr with __class__ pattern: getattr(obj, '__class__')
        if isinstance(node.func, ast.Name) and node.func.id == "getattr":
            if node.args and len(node.args) >= 2:
                second_arg = node.args[1]
                if isinstance(second_arg, ast.Constant) and isinstance(second_arg.value, str):
                    if second_arg.value in BLOCKED_DUNDER_PATTERNS:
                        self.blocked_builtins.add("getattr")
                        self.escape_patterns.add(
                            f"getattr(..., '{second_arg.value}') — sandbox escape attempt"
                        )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Visit attribute accesses and check for dangerous dunder patterns."""
        # Check for __class__, __bases__, __subclasses__ etc.
        if node.attr in BLOCKED_DUNDER_PATTERNS:
            self.dunder_accesses.add(node.attr)

        # Recursively check the value part for chained dunder access
        # e.g., obj.__class__.__bases__
        if isinstance(node.value, ast.Attribute):
            if node.value.attr in BLOCKED_DUNDER_PATTERNS:
                self.dunder_accesses.add(f"{node.value.attr}.{node.attr}")
                if node.attr in BLOCKED_DUNDER_PATTERNS:
                    self.escape_patterns.add(
                        f"Chained dunder access: ...{node.value.attr}.{node.attr}"
                    )

        # Check for attribute access on dangerous patterns via `getattr`
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statements and check for blocked modules."""
        for alias in node.names:
            module_name = alias.name
            base_module = module_name.split(".")[0]

            if base_module in BLOCKED_MODULES:
                self.blocked_imports.add(module_name)
            elif self.strict_mode and base_module not in self.safe_imports:
                # In strict mode, only allow explicitly safe imports
                self.blocked_imports.add(module_name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit 'from X import Y' statements and check for blocked modules."""
        if node.module:
            base_module = node.module.split(".")[0]

            if (
                base_module in BLOCKED_MODULES
                or self.strict_mode
                and base_module not in self.safe_imports
            ):
                self.blocked_imports.add(node.module)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Visit subscript accesses and check for __globals__[], __builtins__[] patterns."""
        # Check for `something['__globals__']` or `something['__builtins__']`
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            if node.slice.value in ("__globals__", "__builtins__", "__dict__"):
                self.dunder_accesses.add(f"subscript[{node.slice.value!r}]")
                self.escape_patterns.add(
                    f"Dict access to '{node.slice.value}' — sandbox escape attempt"
                )

        self.generic_visit(node)

    def visit_Try(self, node: ast.Try) -> None:
        """Visit try/except blocks — exception-based introspection attempts."""
        # বাংলা মন্তব্য: try/except ব্লক নিজেই বিপজ্জনক নয়, কিন্তু এর ভেতরে
        # exception handling দিয়ে introspection attempt হতে পারে।
        # ভিজিট চালিয়ে যান — children check হবে
        self.generic_visit(node)


# ── Convenience Functions ─────────────────────────────────────────────────────


def scan_code(code: str, strict_mode: bool = True) -> ScanResult:
    """
    Convenience function to scan Python code for sandbox safety.

    Args:
        code: Python source code string.
        strict_mode: Enable strict scanning (blocks all non-safe imports).

    Returns:
        ScanResult with safety assessment.

    Example:
        >>> result = scan_code("print('hello')")
        >>> result.is_safe
        True

        >>> result = scan_code("getattr(obj, '__class__')")
        >>> result.is_safe
        False
        >>> result.blocked_builtins
        ['getattr']
    """
    scanner = ASTSandboxScanner(strict_mode=strict_mode)
    return scanner.scan(code)


def validate_code_for_sandbox(code: str, strict_mode: bool = True) -> tuple[bool, str]:
    """
    Validate code for sandbox execution. Returns (is_safe, reason).

    বাংলা মন্তব্য: স্যান্ডবক্স এক্সিকিউশনের আগে কোড ভ্যালিডেট করে।
    This is the primary API for sandbox environments to call before execution.

    Args:
        code: Python source code string.
        strict_mode: Enable strict scanning.

    Returns:
        Tuple of (is_safe: bool, reason: str).
        If safe, reason is empty string.
        If unsafe, reason contains details of findings.
    """
    result = scan_code(code, strict_mode=strict_mode)
    if result.is_safe:
        return True, ""
    return False, "; ".join(result.findings)
