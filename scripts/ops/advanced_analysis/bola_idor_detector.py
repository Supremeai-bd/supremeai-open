#!/usr/bin/env python3
import sys
import ast
import os

class BolaIdorVisitor(ast.NodeVisitor):
    def __init__(self, filepath):
        self.filepath = filepath
        self.has_error = False
        self.in_endpoint = False

    def visit_FunctionDef(self, node):
        # Look for FastAPI/HTTP route decorators
        self.in_endpoint = self._has_route_decorator(node)
        self.generic_visit(node)
        self.in_endpoint = False

    def visit_AsyncFunctionDef(self, node):
        self.in_endpoint = self._has_route_decorator(node)
        self.generic_visit(node)
        self.in_endpoint = False

    def _has_route_decorator(self, node):
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                if decorator.func.attr in ['get', 'post', 'put', 'delete', 'patch']:
                    return True
        return False

    def visit_Call(self, node):
        if self.in_endpoint:
            # Check for direct object queries by ID without tenant/user context
            # Simplistic heuristic: query.filter(Model.id == some_id) without current_user
            # This is a very rough heuristic for demonstration in Phase 1
            call_name = self._get_full_call_name(node.func)
            if call_name and 'filter_by' in call_name:
                args_keys = [kw.arg for kw in node.keywords if kw.arg]
                if 'id' in args_keys and 'tenant_id' not in args_keys and 'user_id' not in args_keys:
                    print(f"[WARN] [bola-idor-detector] Potential BOLA/IDOR vulnerability in {self.filepath}:{node.lineno}")
                    print(f"   Found query by 'id' without tenant/user context in endpoint.")
                    print(f"   Trap #47/48: BOLA/IDOR. Ensure queries are scoped to the current user/tenant.")
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
        dirs[:] = [d for d in dirs if d not in (".venv", "venv", "site-packages", "__pycache__", "tests", "examples")]
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    try:
                        source = f.read()
                        tree = ast.parse(source, filename=filepath)
                        visitor = BolaIdorVisitor(filepath)
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
    print(f"[INFO] Scanning {target_dir} for BOLA/IDOR vulnerabilities...")

    overall_error = scan_directory(target_dir)

    if overall_error:
        print("\nFix: Ensure all database queries in endpoints are scoped with tenant_id or user_id.")
        print("[Audit Mode]: Logged warning, returning 0.")
        return 0

    print("[PASS] No obvious BOLA/IDOR patterns found.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
