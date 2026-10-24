from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/generated/module_capability_matrix.json"


def classify(path: Path, source: str) -> str:
    text = path.as_posix()
    if "/tests/" in text or text.startswith("tests/"):
        return "test"
    if "adapter" in path.stem or "integration" in text or "mcp" in text:
        return "adapter"
    if "registry" in path.stem or "router" in path.stem or "service" in path.stem:
        return "canonical"
    if "worker" in text or "agent" in text:
        return "dormant_or_dynamic"
    return "human_review"


def python_entrypoints(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    names = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {"main", "create_app", "get_app", "health", "register"}:
            names.append(node.name)
    return sorted(set(names))


def build() -> dict:
    """Build a source-file capability inventory, not a functional module census.

    Functional modules are governed by the wiring audit and rendered to
    MODULES_LIST.md. This matrix intentionally describes implementation files
    so consumers cannot mistake a file count for the canonical module count.
    """
    modules = []
    excluded_parts = {
        ".git", "node_modules", ".vite", "dist", "dist-admin", "dist-user", "build", "coverage", "htmlcov",
        "__pycache__", ".next", "target", ".venv", ".venv_ci", "venv", "ci-reports",
        "site-packages", ".pytest_cache", ".ruff_cache", ".mypy_cache", "archive"
    }
    target_dirs = ["backend", "frontend", "infrastructure", "scripts"]

    # Try git ls-files first for absolute consistency across CI and local environments
    candidate_paths: list[Path] = []
    try:
        import subprocess
        cmd = ["git", "ls-files"] + target_dirs
        res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            line = line.strip()
            if line:
                candidate_paths.append(ROOT / line)
    except Exception:
        for base in (ROOT / d for d in target_dirs):
            if base.exists():
                candidate_paths.extend(base.rglob("*"))

    from pathlib import PurePosixPath

    for path in sorted(candidate_paths, key=lambda p: PurePosixPath(p.relative_to(ROOT).as_posix())):
        if any(part in excluded_parts or part.startswith(".venv") or "site-packages" in part for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8", errors="ignore")
        modules.append({
            "path": rel,
            "kind": path.suffix[1:],
            "classification": classify(path, source),
            "entrypoints": python_entrypoints(path) if path.suffix == ".py" else [],
            "capability_signals": sorted({word for word in ("capability", "register", "dispatch", "execute", "health", "memory", "browser", "mcp", "realtime") if word in source.lower()}),
        })
    audit_path = ROOT / "docs/audit_reports/module_wiring_audit.json"
    functional_module_count = None
    functional_status_counts = None
    if audit_path.exists():
        try:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            functional_module_count = audit.get("total")
            functional_status_counts = audit.get("counts")
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"[capability-matrix] audit summary unreadable at {audit_path}: {exc}",
                file=sys.stderr,
            )

    return {
        "schema_version": "2.0",
        "inventory_type": "source_file_capability",
        "source": "main",
        "source_file_count": len(modules),
        "functional_module_inventory": "MODULES_LIST.md",
        "functional_module_count": functional_module_count,
        "functional_status_counts": functional_status_counts,
        "modules": modules,
    }


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
