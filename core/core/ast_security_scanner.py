# AST Security Scanner
# বাংলা মন্তব্য: এআই জেনারেটেড কোডের সিকিউরিটি স্ক্যানার ও এএসটি ভ্যালিডেশন গেটকিপার।

import ast

from core.logging_config import logger


class SecuritySandboxError(Exception):
    """Exception thrown when code violates AST security constraints."""

    pass


class ASTSecurityScanner(ast.NodeVisitor):
    def __init__(self):
        # 🛑 ZERO-GAP: Extended Banned Imports
        self.banned_imports: set[str] = {
            "os",
            "sys",
            "subprocess",
            "pty",
            "shlex",
            "importlib",
            "code",
            "runpy",
            "multiprocessing",
            "pickle",
            "marshal",
            "tempfile",
            "socket",
            "urllib",
            "urllib3",
            "requests",
            "http",
            "ctypes",
            "builtins",
        }

        # 🛑 ZERO-GAP: Banned Built-in Functions for Introspection & Execution
        self.banned_functions: set[str] = {
            "eval",
            "exec",
            "compile",
            "globals",
            "locals",
            "vars",
            "dir",
            "breakpoint",
            "__import__",
            "getattr",
            "setattr",
            "delattr",
            "hasattr",
            "open",
        }

        # 🛑 ZERO-GAP: Prevent Sandbox Escapes via Dunder Attributes
        self.banned_attributes: set[str] = {
            "__class__",
            "__bases__",
            "__subclasses__",
            "__globals__",
            "__builtins__",
            "__dict__",
            "__mro__",
            "__code__",
            "__closure__",
            "__func__",
        }

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_module = alias.name.split(".")[0]
            if base_module in self.banned_imports:
                raise SecuritySandboxError(f"Banned import detected: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            base_module = node.module.split(".")[0]
            if base_module in self.banned_imports:
                raise SecuritySandboxError(f"Banned import detected: {node.module}")
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        """Block sandbox escape via subscript access: __builtins__['exec'](), builtins['eval'](), and dunder chains."""
        # Block builtins/__builtins__ subscript access
        if isinstance(node.value, ast.Name) and node.value.id in {
            "builtins",
            "__builtins__",
        }:
            raise SecuritySandboxError(
                "Sandbox escape via subscript blocked: builtins/__builtins__ access"
            )
        # Block chained dunder attribute access via subscript (e.g., obj.__class__.__bases__[0])
        if isinstance(node.value, ast.Attribute):
            if node.value.attr in self.banned_attributes:
                raise SecuritySandboxError(
                    f"Dunder attribute access via subscript blocked: {node.value.attr}"
                )
        # Block dunder subscript access that can lead to subclass enumeration: "".__class__.__bases__[0].__subclasses__()
        if isinstance(node.value, ast.Attribute) and hasattr(node.value, "attr"):
            # Check for patterns like __class__, __bases__, __subclasses__ in the chain
            current_node: ast.expr = node.value
            attr_chain = []
            while isinstance(current_node, ast.Attribute):
                attr_chain.append(current_node.attr)
                current_node = current_node.value
                if len(attr_chain) > 5:  # Prevent infinite loops
                    break

            # Check if the chain contains dangerous patterns
            if (
                "__subclasses__" in attr_chain
                and "__bases__" in attr_chain
                and "__class__" in attr_chain
            ):
                raise SecuritySandboxError(
                    "Dangerous dunder method chain detected: potential subclass enumeration attack"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Block all Attribute access to reflection methods (prevents sandbox escape)
        if isinstance(node.func, ast.Attribute):
            # Block getattr/hasattr/setattr/delattr - critical for RCE bypass
            if node.func.attr in {"getattr", "hasattr", "setattr", "delattr"}:
                raise SecuritySandboxError(
                    f"Banned reflection function call detected: {node.func.attr}"
                )
            # Block dangerous module methods
            if node.func.attr in {
                "import_module",
                "system",
                "popen",
                "spawn",
                "fork",
                "run",
                "run_async",
            }:
                raise SecuritySandboxError(f"Banned method invocation detected: {node.func.attr}")

        # Block direct function calls like eval(), __import__()
        if isinstance(node.func, ast.Name) and node.func.id in self.banned_functions:
            raise SecuritySandboxError(f"Banned function call detected: {node.func.id}")

        # Block subscript calls: builtins["exec"]("...")
        if isinstance(node.func, ast.Subscript):
            self.visit_Subscript(node.func)

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Block access to dunder attributes used for sandbox escapes
        if node.attr in self.banned_attributes:
            raise SecuritySandboxError(f"Sandbox escape pattern blocked: {node.attr}")
        # Block dangerous attribute access chains
        if hasattr(node, "value") and isinstance(node.value, ast.Attribute):
            # Look for patterns like obj.__class__.__bases__[0].__subclasses__()
            parent_attr: ast.expr = node.value
            attr_chain = [node.attr]
            depth = 0
            while isinstance(parent_attr, ast.Attribute) and depth < 5:
                attr_chain.append(parent_attr.attr)
                parent_attr = parent_attr.value
                depth += 1

            # Check if the chain contains dangerous combinations
            if (
                "__subclasses__" in attr_chain
                and "__bases__" in attr_chain
                and "__class__" in attr_chain
            ):
                raise SecuritySandboxError(
                    "Dangerous dunder attribute chain detected: potential sandbox escape"
                )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        # বাংলা মন্তব্য: নিষিদ্ধ ফাংশনের রেফারেন্স অন্য ভ্যারিয়েবলে অ্যাসাইন করা বা পাস করা ব্লক করতে এই চেকটি যোগ করা হলো।
        if node.id in self.banned_functions:
            raise SecuritySandboxError(f"Banned function reference detected: {node.id}")
        self.generic_visit(node)


class ASTSecurityScannerEngine:
    """
    Scans generated python code using AST parser to block execution of unsafe or malicious code before execution.
    """

    def __init__(self):
        # Preserve public interface configs if needed by test suite or other modules
        self.scanner = ASTSecurityScanner()

    def scan_code(self, code: str) -> dict:
        """
        Parses code string to check for banned keywords and modules.
        Returns a dict: {"safe": bool, "error": str | None}
        """
        try:
            tree = ast.parse(code)
            self.scanner.visit(tree)
            logger.info("AST Static code scan passed successfully. Code is safe for execution.")
            return {"safe": True, "error": None}
        except SecuritySandboxError as sse:
            logger.critical(f"🚨 [AST SECURITY SCANNER] Security threat defused: {sse}")
            # বাংলা মন্তব্ব: টেস্ট কেসের প্রত্যাশিত আউটপুট ম্যাচ করানোর সাথে কাস্টম এক্সপশন মাস্কিং বজায় রাখা হলো
            error_msg = str(sse)
            if "Banned import" in error_msg:
                user_error = "Security validation failed: Banned root import detected and blocked."
            elif "Banned function" in error_msg:
                user_error = (
                    "Security validation failed: Reference to banned security identifier blocked."
                )
            elif "Sandbox escape" in error_msg:
                user_error = "Security validation failed: Banned attribute or dunder reflection access blocked."
            else:
                user_error = "Security validation failed: Payload rejected by AST Security Scanner."
            return {"safe": False, "error": user_error}

        except SyntaxError as se:
            logger.error(f"Syntax validation failed: {se}")
            return {"safe": False, "error": f"SyntaxError: {se!s}"}
        except Exception as e:
            logger.error(f"Unexpected error during static analysis: {e}")
            return {"safe": False, "error": f"AnalysisException: {e!s}"}


# Primary alias
ImmuneSystemScanner = ASTSecurityScannerEngine
