#!/usr/bin/env python3
import sys
import re
import ast

class TruthyEnvVisitor(ast.NodeVisitor):
    def __init__(self, filepath):
        self.filepath = filepath
        self.has_error = False

    def visit_Compare(self, node):
        # We are looking for something like: os.getenv("X") == "true" or os.environ.get("X") == "True"
        # without a .lower() call

        # Simplistic AST check for string literal "true" or "false" in a comparison
        has_boolean_string = False
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                val = comparator.value.lower()
                if val in ("true", "false"):
                    has_boolean_string = True
                    break

        if getattr(node, 'left', None):
            if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                val = node.left.value.lower()
                if val in ("true", "false"):
                    has_boolean_string = True

        if has_boolean_string:
            # Let's check if there is a .lower() call
            has_lower_call = False

            # Helper to check if a node is a .lower() method call
            def is_lower_call(n):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
                    if n.func.attr == 'lower':
                        return True
                return False

            if is_lower_call(node.left):
                has_lower_call = True
            for comp in node.comparators:
                if is_lower_call(comp):
                    has_lower_call = True

            if not has_lower_call:
                print(f"[WARN] [truthy-env-checker] Risky boolean string comparison in {self.filepath}:{node.lineno}")
                print(f"   String boolean check without .lower(): trap #83 (String 'false' vs Bool)")
                self.has_error = True

        self.generic_visit(node)


def main():
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if len(sys.argv) < 2:
        return 0

    overall_error = False

    for filepath in sys.argv[1:]:
        if not filepath.endswith(".py"):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()

        try:
            tree = ast.parse(source, filename=filepath)
            visitor = TruthyEnvVisitor(filepath)
            visitor.visit(tree)
            if visitor.has_error:
                overall_error = True
        except SyntaxError as exc:
            print(
                f"[truthy-env] {filepath}: SyntaxError skipped (ruff reports it): {exc}",
                file=sys.stderr,
            )

    if overall_error:
        print("\n💡 Fix: Always use `.lower() == 'true'` when comparing environment variables.")
        print("⚠️ [Audit Mode]: This would normally block the commit, but returning 0 for now.")
        return 0

    return 0

if __name__ == "__main__":
    sys.exit(main())
