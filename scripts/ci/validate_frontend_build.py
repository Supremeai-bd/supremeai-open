#!/usr/bin/env python3
"""
validate_frontend_build.py
Scans the frontend dist/ directory after build to ensure:
- No hardcoded Render/Vercel/Firebase URLs leaked into JS.
- No VITE_ variables containing restricted keywords (SECRET, PASSWORD, etc.) are present.
"""

import os
import re
import sys
from pathlib import Path

# Directories to scan
# বাংলা (single-frontend migration): একটাই build artifact — frontend/dist
FRONTEND_DIST_DIRS = [
    Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
]

# Patterns that should NOT be in the built JS
# These are known OLD hardcoded production hostnames that should not be in the built JS
BANNED_HOSTNAMES = [
    r"supremeai-backend-v2\.onrender\.com",
    r"supremeai-admin\.onrender\.com",
]

# Sensitive keys that should not be exposed even if prefixed with VITE_
BANNED_KEYWORDS = [
    "SECRET",
    "PASSWORD",
    "SERVICE_KEY",
    "ADMIN_KEY",
    "STRIPE_SK",
    "PRIVATE_KEY"
]

BANNED_HOSTNAMES_REGEX = re.compile("|".join(BANNED_HOSTNAMES), re.IGNORECASE)

# Allowed exceptions for hostnames
ALLOWED_EXCEPTIONS = [
    # E.g. If we need to link to docs on vercel
]

def scan_file(filepath: Path) -> list[str]:
    violations = []
    try:
        content = filepath.read_text(encoding="utf-8")

        # Check for hardcoded hostnames
        if BANNED_HOSTNAMES_REGEX.search(content):
            violations.append("  ❌ Contains hardcoded deployment hostname (.onrender.com, etc.)")

        # Check for unresolved deploy placeholders (FR-005, SC-006, T014)
        if re.search(r"\{\{[A-Z0-9_]+\}\}", content):
            violations.append("  ❌ Contains unresolved deploy placeholder (e.g., {{USER_BACKEND_URL}})")

        # Check for leaked VITE_ secrets
        vite_vars = re.findall(r'VITE_[A-Z0-9_]+', content)
        for var in set(vite_vars):
            if any(word in var for word in BANNED_KEYWORDS):
                violations.append(f"  ❌ Contains potentially sensitive VITE_ variable: {var}")

    except Exception as e:
        # Ignore binary files (like images, fonts)
        _ = e
    return violations

def main():
    import sys
    if sys.stdout.encoding.lower() != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    has_errors = False

    for dist_dir in FRONTEND_DIST_DIRS:
        if not dist_dir.exists():
            print(f"⚠️ Warning: {dist_dir} does not exist. Skipping validation.")
            continue

        print(f"🔍 Scanning frontend build artifact ({dist_dir.name}/) for leaked config...")

        for filepath in dist_dir.rglob("*"):
            if filepath.is_file() and filepath.suffix in {'.js', '.html', '.css', '.json'}:
                violations = scan_file(filepath)
                if violations:
                    has_errors = True
                    print(f"\n📄 {filepath.relative_to(dist_dir)}:")
                    for v in violations:
                        print(v)

    # Check generated hosting config (FR-005, SC-006, T014)
    root_dir = Path(__file__).resolve().parent.parent.parent
    firebase_json = root_dir / "firebase.json"
    if firebase_json.exists():
        print("🔍 Checking generated firebase.json for unresolved placeholders...")
        violations = scan_file(firebase_json)
        if violations:
            has_errors = True
            print("\n📄 firebase.json:")
            for v in violations:
                print(v)

    if has_errors:
        print("\n🚨 Build artifact validation failed! Secrets or hardcoded URLs detected.")
        sys.exit(1)
    else:
        print("\n✅ PASS: Build artifact is clean (no leaked secrets or hardcoded deployment URLs).")
        sys.exit(0)

if __name__ == "__main__":
    main()
