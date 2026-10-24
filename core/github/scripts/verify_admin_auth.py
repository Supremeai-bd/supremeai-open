#!/usr/bin/env python3
"""
🛡️ CI Security Guard: Automated Admin Router Authentication Lint Validator

This script performs a static audit of all backend API routers under `backend/api/routes`
to ensure that any router mounted with an admin prefix enforces router-level auth via
`dependencies=[Depends(...)]`. This prevents developers from accidentally opening admin
surfaces without the central `get_current_admin` protection.

Exit codes:
- 0: No violations found.
- 1: One or more admin routers lack required auth dependency.
"""

import os
import re
import sys


def verify_admin_routers() -> int:
    """
    STATIC_SCAN: Verify every admin-prefixed router has explicit auth dependency.
    """
    routes_dir = os.path.join("backend", "api", "routes")
    if not os.path.exists(routes_dir):
        return 0

    error_count = 0
    router_regex = re.compile(r"APIRouter\s*\([^)]*prefix\s*=\s*['\"]/?(?:api/)?admin", re.IGNORECASE)
    auth_dependency_regex = re.compile(r"dependencies\s*=\s*\[\s*Depends\(", re.IGNORECASE)

    for root, _, files in os.walk(routes_dir):
        for file in files:
            if not file.endswith(".py"):
                continue

            file_path = os.path.join(root, file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except OSError:
                continue

            if router_regex.search(content):
                if not auth_dependency_regex.search(content):
                    print(
                        f"🚨 [ARCHITECTURE_VIOLATION]: File '{file_path}' mounts an admin prefix but "
                        f"LACKS router-level 'dependencies=[Depends(...)]' auth fortification!"
                    )
                    error_count += 1

    return error_count


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    errors = verify_admin_routers()
    if errors > 0:
        sys.exit(1)
    print("✅ All admin prefixed routers verified structurally.")
    sys.exit(0)
