#!/usr/bin/env python3
import sys
import ast
import os
from pathlib import Path

# Common blocking functions that shouldn't be in async routes
BLOCKING_CALLS = {
    'time.sleep',
    'requests.get',
    'requests.post',
    'requests.put',
    'requests.delete',
    'requests.request',
    'urllib.request.urlopen',
}

class BlockingCallVisitor(ast.NodeVisitor):
    def __init__(self, filepath):
        self.filepath = filepath
        self.has_error = False
        self.in_async_func = False

    def visit_AsyncFunctionDef(self, node):
        self.in_async_func = True
        self.generic_visit(node)
        self.in_async_func = False

    def visit_FunctionDef(self, node):
        # We don't care about sync functions for this trap
        self.in_async_func = False
        self.generic_visit(node)

    def visit_Call(self, node):
        if self.in_async_func:
            call_name = self._get_full_call_name(node.func)
            if call_name in BLOCKING_CALLS:
                print(f"[WARN] [blocking-call-detector] Blocking call in async route in {self.filepath}:{node.lineno}")
                print(f"   Found: '{call_name}()' inside async function")
                print(f"   Trap #2: Blocking Event Loop. Use async equivalent instead (e.g., httpx, asyncio.sleep).")
                self.has_error = True
        self.generic_visit(node)

    def _get_full_call_name(self, node):
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            base = self._get_full_call_name(node.value)
            if base:
                return f"{base}.{node.attr}"
            return node.attr
        return None

def scan_directory(directory):
    overall_error = False
    for root, dirs, files in os.walk(directory):
        # Prune virtual environments and test directories in-place
        dirs[:] = [d for d in dirs if d not in (".venv", "venv", "site-packages", "__pycache__", "tests", "examples")]
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    try:
                        source = f.read()
                        tree = ast.parse(source, filename=filepath)
                        visitor = BlockingCallVisitor(filepath)
                        visitor.visit(tree)
                        if visitor.has_error:
                            overall_error = True
                    except Exception as parse_error:
                        print(f"Skipping unparsable file {filepath}: {parse_error}", file=sys.stderr)
    return overall_error

def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    target_dir = sys.argv[1] if len(sys.argv) > 1 else "backend"
    print(f"[INFO] Scanning {target_dir} for blocking calls in async functions...")

    overall_error = scan_directory(target_dir)

    if overall_error:
        print("\nFix: Replace blocking calls with async equivalents.")
        print("[Audit Mode]: Logged warning, returning 0.")
        return 0

    print("[PASS] No blocking calls found in async functions.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
