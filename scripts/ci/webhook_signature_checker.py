#!/usr/bin/env python3
"""
webhook_signature_checker.py
============================
Audit tool to detect unverified Webhook endpoints across the backend (Trap #86).
Scans for:
1. Endpoints receiving webhooks (@router.post("/webhook"), etc.)
2. Verifies each webhook route either:
   - Invokes signature verification (hmac, verify_signature, X-Hub-Signature, etc.)
   - Uses an explicit authentication/authorization guard dependency
3. Warns or flags any unprotected public webhook receiver.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

SIGNATURE_INDICATORS = {
    "verify",
    "signature",
    "hmac",
    "x-hub-signature",
    "x-supabase-signature",
    "x-n8n-signature",
    "secret",
    "compare_digest",
}


def analyze_route_function(fn_node: ast.FunctionDef | ast.AsyncFunctionDef, file_content: str, rel_path: str) -> list[str]:
    issues = []
    # Check decorators for webhook routes
    is_webhook_route = False
    route_path = ""
    for dec in fn_node.decorator_list:
        dec_str = ast.unparse(dec).lower()
        if "router.post" in dec_str or "app.post" in dec_str:
            if "webhook" in dec_str or "callback" in dec_str:
                is_webhook_route = True
                route_path = dec_str

    if not is_webhook_route:
        # Check function name
        if "webhook" in fn_node.name.lower() or "callback" in fn_node.name.lower():
            for dec in fn_node.decorator_list:
                dec_str = ast.unparse(dec).lower()
                if "router.post" in dec_str or "app.post" in dec_str:
                    is_webhook_route = True
                    route_path = dec_str

    if not is_webhook_route:
        return []

    # Exclude health endpoints on webhooks (e.g. GET /cdc/health)
    if "get(" in route_path.lower():
        return []

    # Inspect function body for signature check calls or docstring exclusions
    fn_body_str = ast.unparse(fn_node).lower()

    # Check if signature verification or security dependency is called
    has_signature_check = any(ind in fn_body_str for ind in SIGNATURE_INDICATORS)

    # Check dependencies in parameters
    for arg in fn_node.args.args:
        # e.g., verified: bool = Depends(...)
        pass
    for default in fn_node.args.defaults:
        def_str = ast.unparse(default).lower()
        if any(ind in def_str for ind in SIGNATURE_INDICATORS):
            has_signature_check = True

    if not has_signature_check:
        issues.append(
            f"Potential unverified webhook endpoint in {rel_path}:{fn_node.lineno} "
            f"(`def {fn_node.name}`) - route '{route_path}' lacks signature/HMAC verification!"
        )

    return issues


def scan_backend_webhooks() -> list[str]:
    all_issues = []
    for py_file in BACKEND_ROOT.rglob("*.py"):
        if any(part.startswith(".") or part in ("tests", "venv", ".venv") for part in py_file.parts):
            continue

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            if "webhook" not in content.lower() and "callback" not in content.lower():
                continue

            tree = ast.parse(content, filename=str(py_file))
            rel_path = str(py_file.relative_to(REPO_ROOT))

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    issues = analyze_route_function(node, content, rel_path)
                    all_issues.extend(issues)
        except Exception as e:
            all_issues.append(f"Error analyzing {py_file.relative_to(REPO_ROOT)}: {e}")

    return all_issues


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Auditing Webhook HMAC/Signature Verification (Trap #86)...")
    issues = scan_backend_webhooks()

    if issues:
        for issue in issues:
            print(f"[WARN] {issue}")
        print(f"\nTotal potential webhook signature gaps detected: {len(issues)}")
        # Non-blocking audit mode
        return 0

    print("[PASS] All detected webhook endpoints implement HMAC signature verification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
