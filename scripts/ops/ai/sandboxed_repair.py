#!/usr/bin/env python3
"""Apply a reviewed patch only inside a disposable temporary workspace."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import tempfile
from pathlib import Path

PROTECTED_PREFIXES = (".github/", ".clinerules/", ".specify/", "infrastructure/")


def changed_paths(patch: str) -> list[str]:
    return [line.split(" b/", 1)[1] for line in patch.splitlines() if line.startswith("+++ b/")]


def apply_safely(root: Path, patch_file: Path, output: Path) -> dict:
    patch = patch_file.read_text(encoding="utf-8")
    paths = changed_paths(patch)
    blocked = [path for path in paths if path.startswith(PROTECTED_PREFIXES) or path.endswith((".env", ".tfvars"))]
    if blocked:
        return {"status": "blocked", "reason": "protected paths require explicit human approval", "paths": blocked}
    with tempfile.TemporaryDirectory(prefix="supremeai-repair-") as directory:
        workspace = Path(directory) / "workspace"
        shutil.copytree(root, workspace, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"))
        check = subprocess.run(["git", "apply", "--check", str(patch_file)], cwd=workspace, capture_output=True, text=True)
        if check.returncode:
            return {"status": "blocked", "reason": "patch does not apply cleanly", "details": check.stderr.strip()}
        applied = subprocess.run(["git", "apply", str(patch_file)], cwd=workspace, capture_output=True, text=True)
        if applied.returncode:
            return {"status": "blocked", "reason": "patch application failed", "details": applied.stderr.strip()}
        diff = subprocess.run(["git", "diff", "--no-ext-diff"], cwd=workspace, check=True, capture_output=True, text=True).stdout
        output.write_text(diff, encoding="utf-8")
    return {"status": "pass", "paths": paths, "output": str(output)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("patch", type=Path)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("ci-reports/sandboxed-repair.diff"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = apply_safely(args.root.resolve(), args.patch.resolve(), args.output)
    print(report)
    return 1 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
