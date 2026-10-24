#!/usr/bin/env python3
"""
check_single_frontend.py — CI Gate A/D (roadmap §19: SUPREMEAI_SINGLE_FRONTEND_ROLE_BASED_ROADMAP.md)

Fails CI if the codebase regresses into the portal-split architecture:

Gate A — Single frontend:
  - `import.meta.env.VITE_PORTAL_TYPE` / `process.env.VITE_PORTAL_TYPE` anywhere in the
    frontend runtime surface (src, config) or build scripts.
  - Portal-specific production build scripts/artifacts: `build:admin`, `build:user`,
    `dev:admin`, `dev:user`, `dist-admin`, `dist-user`.

Gate D — Navigation integrity:
  - Duplicate navigation item ids in NAVIGATION_REGISTRY.
  - Duplicate command ids in COMMAND_REGISTRY (light structural check via src scan).

Exit codes: 0 = pass, 1 = regression detected.
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND = REPO_ROOT / "frontend"

# --- Gate A: forbidden runtime access patterns -------------------------------
GATE_A_PATTERNS = [
    re.compile(r"import\.meta\.env\.VITE_PORTAL_TYPE"),
    re.compile(r"process\.env\.VITE_PORTAL_TYPE"),
]

# Files/dirs where the pattern must never appear (runtime + build surface)
GATE_A_TARGETS = [
    FRONTEND / "src",
    FRONTEND / "vite.config.ts",
    FRONTEND / "package.json",
    REPO_ROOT / "scripts" / "render_build_frontend.sh",
    REPO_ROOT / "turbo.json",
]

# Portal-specific build scripts / artifacts (any occurrence = fail)
GATE_A_LITERAL_STRINGS = ["build:admin", "build:user", "dev:admin", "dev:user", "dist-admin", "dist-user"]

GATE_A_LITERAL_FILES = [
    FRONTEND / "package.json",
    FRONTEND / "vite.config.ts",
    REPO_ROOT / "package.json",
    REPO_ROOT / "turbo.json",
]

# --- Gate D: registry integrity ----------------------------------------------

def check_registry_ids() -> list[str]:
    """Parse the nav registry + command registry for duplicate ids."""
    problems: list[str] = []

    nav_file = FRONTEND / "src" / "config" / "navigationRegistry.ts"
    if nav_file.exists():
        ids = re.findall(r"id:\s*'([^']+)'", nav_file.read_text(encoding="utf-8"))
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            problems.append(f"NAVIGATION_REGISTRY duplicate ids: {sorted(dupes)}")

    cmd_file = FRONTEND / "src" / "config" / "commandRegistry.ts"
    if cmd_file.exists():
        src = cmd_file.read_text(encoding="utf-8")
        ids = re.findall(r"id:\s*'([^']+)'", src)
        ids += re.findall(r"\[\s*'([^']+)',\s*'Admin:", src)
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            problems.append(f"COMMAND_REGISTRY duplicate ids: {sorted(dupes)}")

    return problems


def main() -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    failures: list[str] = []

    # Gate A — runtime access
    for target in GATE_A_TARGETS:
        if not target.exists():
            continue
        paths = [target] if target.is_file() else list(target.rglob("*"))
        for p in paths:
            if not p.is_file() or p.suffix not in {".ts", ".tsx", ".js", ".jsx", ".json", ".sh"}:
                continue
            try:
                content = p.read_text(encoding="utf-8")
            except Exception:
                continue
            for pattern in GATE_A_PATTERNS:
                if pattern.search(content):
                    failures.append(
                        f"Gate A: portal-split runtime access '{pattern.pattern}' found in {p.relative_to(REPO_ROOT)}"
                    )

    # Gate A — portal-specific build scripts/artifacts
    for f in GATE_A_LITERAL_FILES:
        if not f.exists():
            continue
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for literal in GATE_A_LITERAL_STRINGS:
            if literal in content:
                failures.append(
                    f"Gate A: portal-specific build artifact/script '{literal}' found in {f.relative_to(REPO_ROOT)}"
                )

    # Gate D — registry integrity
    failures.extend(check_registry_ids())

    if failures:
        print("🚨 Single-frontend regression detected!\n")
        for f in failures:
            print(f"  ❌ {f}")
        print(
            "\nSee docs/frontend-migration/PHASE0_INVENTORY.md and\n"
            "SUPREMEAI_SINGLE_FRONTEND_ROLE_BASED_ROADMAP.md §19 (Gates A/D).\n"
            "The app must be ONE frontend build with ONE route graph and ONE nav registry."
        )
        return 1

    print("✅ PASS: single-frontend gates (A/D) clean — no portal split, registries consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
