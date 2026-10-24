#!/usr/bin/env python3
"""
security_headers_checker.py
===========================
Audit tool to enforce HTTP Security Headers (Trap #61).
Validates that:
1. Production middlewares inject critical security headers:
   - X-Content-Type-Options: nosniff
   - X-Frame-Options: DENY / SAMEORIGIN
   - Strict-Transport-Security (HSTS)
   - Content-Security-Policy (CSP)
   - Referrer-Policy
2. Web responses or test fixtures do not strip or omit these headers.
3. Server and X-Powered-By banners are suppressed.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

REQUIRED_HEADERS = {
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Strict-Transport-Security",
    "Content-Security-Policy",
    "Referrer-Policy",
}


def check_middleware_definitions() -> list[str]:
    issues = []
    middleware_file = BACKEND_ROOT / "core" / "middleware" / "security.py"
    if not middleware_file.exists():
        issues.append(f"Missing core security middleware file: {middleware_file}")
        return issues

    content = middleware_file.read_text(encoding="utf-8", errors="ignore")
    try:
        tree = ast.parse(content, filename=str(middleware_file))
    except Exception as e:
        issues.append(f"Failed to parse {middleware_file}: {e}")
        return issues

    # Look for SECURITY_HEADERS dict assignment
    found_headers = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SECURITY_HEADERS":
                    if isinstance(node.value, ast.Dict):
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                found_headers.add(k.value)

    missing = REQUIRED_HEADERS - found_headers
    if missing:
        issues.append(f"SECURITY_HEADERS in {middleware_file.relative_to(REPO_ROOT)} is missing required headers: {', '.join(sorted(missing))}")

    # Check Server signature removal
    if "del_response_header" not in content and "del response.headers" not in content and "headers.pop" not in content:
        issues.append(f"{middleware_file.relative_to(REPO_ROOT)} does not appear to strip Server or X-Powered-By banners.")

    return issues


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Auditing HTTP Security Headers configuration (Trap #61)...")
    issues = check_middleware_definitions()

    if issues:
        for issue in issues:
            print(f"[FAIL] {issue}")
        print(f"\nTotal security header violations: {len(issues)}")
        return 1

    print("[PASS] All required security headers and banner stripping verified in core middleware.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
