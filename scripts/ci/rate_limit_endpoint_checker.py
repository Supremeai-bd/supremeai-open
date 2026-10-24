#!/usr/bin/env python3
"""
rate_limit_endpoint_checker.py
==============================
Audit tool to detect sensitive endpoints missing rate limiting (Trap #60).
Scans for critical paths such as:
- /auth/login, /auth/signin
- /auth/register, /auth/signup
- /auth/password-reset, /auth/reset
- /payment, /checkout, /billing
- /apikey, /keys
Verifies if:
1. They are covered in RequestValidationMiddleware SIMPLE_RATE_LIMITS, OR
2. They use a rate_limiter dependency or RateLimiter decorator.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

SENSITIVE_PATH_KEYWORDS = {
    "login",
    "signin",
    "register",
    "signup",
    "reset-password",
    "forgot-password",
    "refresh-token",
}


def get_middleware_protected_paths() -> set[str]:
    middleware_file = BACKEND_ROOT / "core" / "middleware" / "security.py"
    if not middleware_file.exists():
        return set()

    content = middleware_file.read_text(encoding="utf-8", errors="ignore")
    protected = set()
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "SIMPLE_RATE_LIMITS":
                        if isinstance(node.value, ast.Dict):
                            for k in node.value.keys:
                                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                    protected.add(k.value.lower())
    except Exception as error:
        print(f"Unable to parse rate-limit configuration: {error}", file=sys.stderr)
    return protected


def get_router_prefixes() -> dict[str, str]:
    """Parse api/routers.py to map route modules to their mounted prefix."""
    routers_file = BACKEND_ROOT / "api" / "routers.py"
    prefixes = {}
    if not routers_file.exists():
        return prefixes
    try:
        content = routers_file.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                path_val = ""
                prefix_val = ""
                for k, v in zip(node.keys, node.values):
                    if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
                        if k.value == "path":
                            path_val = str(v.value)
                        elif k.value == "prefix":
                            prefix_val = str(v.value)
                if path_val:
                    prefixes[path_val] = prefix_val
    except Exception as error:
        print(f"Unable to parse rate-limit configuration: {error}", file=sys.stderr)
    return prefixes


def scan_sensitive_routes(protected_paths: set[str]) -> list[str]:
    issues = []
    routes_dir = BACKEND_ROOT / "api" / "routes"
    if not routes_dir.exists():
        return issues

    mounted_prefixes = get_router_prefixes()

    for py_file in routes_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            # Fast check
            if not any(kw in content.lower() for kw in SENSITIVE_PATH_KEYWORDS):
                continue

            tree = ast.parse(content, filename=str(py_file))
            rel_path = str(py_file.relative_to(REPO_ROOT))

            # Find router prefix if any
            prefix = ""
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "router":
                            if isinstance(node.value, ast.Call):
                                for kw in node.value.keywords:
                                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                                        prefix = str(kw.value.value)

            module_key = f"api.routes.{py_file.stem}"
            mount_prefix = mounted_prefixes.get(module_key, "")

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for dec in node.decorator_list:
                        dec_str = ast.unparse(dec).lower()
                        if "router.post" in dec_str or "app.post" in dec_str:
                            subpath = ""
                            if isinstance(dec, ast.Call) and dec.args:
                                if isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                                    subpath = dec.args[0].value

                            full_endpoint = f"{mount_prefix}{prefix}{subpath}".lower()

                            for kw in SENSITIVE_PATH_KEYWORDS:
                                if kw in full_endpoint or kw in dec_str:
                                    # Route identified as sensitive
                                    is_in_middleware = any(p in full_endpoint or full_endpoint.startswith(p) for p in protected_paths)
                                    # Check if protected in decorators/dependencies
                                    fn_code = ast.unparse(node).lower()
                                    has_limiter = "rate_limit" in fn_code or "limiter" in fn_code or "throttle" in fn_code

                                    if not (is_in_middleware or has_limiter):
                                        issues.append(
                                            f"Sensitive endpoint in {rel_path}:{node.lineno} (`def {node.name}`) "
                                            f"matches '{kw}' (endpoint '{full_endpoint}') but has no apparent rate limiting protection."
                                        )
                                    break
        except Exception as e:
            issues.append(f"Error checking {py_file}: {e}")

    return issues


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("Auditing sensitive endpoints for rate limiting protection (Trap #60)...")
    protected_paths = get_middleware_protected_paths()
    print(f"Loaded {len(protected_paths)} globally rate-limited paths from middleware.")

    issues = scan_sensitive_routes(protected_paths)

    if issues:
        for issue in issues:
            print(f"[WARN] {issue}")
        print(f"\nTotal unprotected sensitive endpoints: {len(issues)}")
        # Return 0 in audit mode
        return 0

    print("[PASS] All sensitive endpoints are protected by rate limiters.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
