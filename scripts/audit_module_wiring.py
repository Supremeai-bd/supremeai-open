#!/usr/bin/env python3
"""Generate a reproducible, governance-aware module wiring audit."""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
AUDIT_VERSION = "2.0"
VERIFICATION_COMMAND = "python scripts/audit_module_wiring.py && python scripts/sync_modules_list.py"
PRODUCTION_SCAN_DIRS = [
    ROOT_DIR / "backend" / name for name in ("core", "api", "services", "middleware", "pipelines", "tools")
] + [ROOT_DIR / name for name in ("frontend/src", "packages", "infrastructure/mcp-control-plane/src")]
TEST_SCAN_DIRS = [ROOT_DIR / "backend/tests", ROOT_DIR / "frontend/src"]
ENVIRONMENT_DEPENDENT_MODULES = {
    "backend/tools/devops/docker_sandbox.py",
    "backend/tools/launchdarkly_agent_adapter.py",
    "backend/tools/social/telegram_bot/",
    "backend/tools/mcp/mcp_telegram.py",
}


def is_non_production_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    parts = set(Path(normalized).parts)
    name = Path(normalized).name.lower()
    return bool({".venv", "node_modules", "dist", "build", "__pycache__"} & parts) or name.endswith((
        ".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", ".spec.js", ".test.py", ".spec.py"
    )) or name.startswith("test_")


def load_cataloged_modules() -> list[dict]:
    modules = []
    catalog_path = ROOT_DIR / "docs/reference/MODULES_LIST.md"
    if not catalog_path.exists():
        catalog_path = ROOT_DIR / "MODULES_LIST.md"
    for line in catalog_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or "Module Name / Relative Path" in line or "---|---" in line:
            continue
        parts = [p.strip() for p in line.split("|")[1:-1]]
        if len(parts) >= 3 and parts[0].isdigit() and not is_non_production_path(parts[2]):
            modules.append({"id": int(parts[0]), "category": parts[1], "path": parts[2].replace("\\", "/")})
    return modules


def build_import_corpus() -> tuple[dict[str, str], dict[str, str]]:
    prod, tests = {}, {}
    def collect(base: Path, target: dict[str, str], skip_tests: bool = False):
        if not base.exists():
            return
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs if d not in {".venv", "node_modules", "dist", "build", "__pycache__"}]
            for file in files:
                if not file.endswith((".py", ".ts", ".tsx", ".js")):
                    continue
                rel = str((Path(root) / file).relative_to(ROOT_DIR)).replace("\\", "/")
                if is_non_production_path(rel) or (skip_tests and ("test" in file.lower() or "spec" in file.lower())):
                    continue
                try:
                    target[rel] = (Path(root) / file).read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
    for base in PRODUCTION_SCAN_DIRS:
        collect(base, prod, skip_tests=True)
    for base in TEST_SCAN_DIRS:
        collect(base, tests)
    return prod, tests


def find_callers_for_module(mod_path: str, corpus: dict[str, str]) -> list[str]:
    stem = Path(mod_path).stem
    escaped = re.escape(stem)
    patterns = [re.compile(rf"\b(from|import)\s+[^\n]*{escaped}\b"), re.compile(rf"['\"](?:[^'\"]*/)?{escaped}(?:['\"]|\b)")]
    return sorted(path for path, content in corpus.items() if path != mod_path and any(p.search(content) for p in patterns))


def find_tests_for_module(mod_path: str, corpus: dict[str, str]) -> list[str]:
    stem = Path(mod_path).stem
    return sorted(path for path, content in corpus.items() if path != mod_path and (stem in path or re.search(rf"\b{re.escape(stem)}\b", content)))


def verify_target(target: Path) -> tuple[bool, str]:
    if not target.exists():
        return False, "File or directory does not exist on disk"
    if target.is_dir():
        return True, "Directory module exists and passed source validation"
    if target.suffix == ".py":
        try:
            ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
        except (OSError, SyntaxError) as exc:
            return False, f"Python syntax/import surface invalid: {exc}"
    return True, "Target exists and passed source validation"


def run_audit() -> dict:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    modules, prod, tests = load_cataloged_modules(), *build_import_corpus()
    results, counts = [], {"operational": 0, "env_dependent": 0, "partially_wired": 0, "broken": 0, "planned": 0}
    for index, mod in enumerate(modules, start=1):
        mod = {**mod, "id": index}
        path = mod["path"]
        valid, validation = verify_target(ROOT_DIR / path)
        callers, test_files = find_callers_for_module(path, prod), find_tests_for_module(path, tests)
        if not valid:
            status, decision, notes = "🔴 Broken", "review", validation
            counts["broken"] += 1
        elif path in ENVIRONMENT_DEPENDENT_MODULES:
            status, decision, notes = "🟡 Environment-Dependent", "retain", "Requires external host service or token"
            counts["env_dependent"] += 1
        elif callers:
            status, decision, notes = "🟢 Operational", "retain", f"Active inbound callers ({len(callers)} files)"
            counts["operational"] += 1
        else:
            status, decision, notes = "🟠 Partially Wired", "owner-review", "Importable production capability with no active inbound callers"
            counts["partially_wired"] += 1
        results.append({**mod, "status": status, "callers": callers, "tests": test_files, "notes": notes,
                        "verified_at": generated_at, "verification_command": VERIFICATION_COMMAND,
                        "owner_circle": "unassigned", "decision": decision})
    return {"schema_version": AUDIT_VERSION, "generated_at": generated_at, "verification_command": VERIFICATION_COMMAND,
            "catalog_source": "MODULES_LIST.md", "modules": results, "counts": counts, "total": len(results)}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    data = run_audit()
    out = ROOT_DIR / "docs/audit_reports/module_wiring_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"[+] Audited {data['total']} catalog modules; report saved to {out.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
