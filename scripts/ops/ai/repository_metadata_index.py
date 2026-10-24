#!/usr/bin/env python3
"""Generate a deterministic repository metadata index for intelligence tooling."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

EXCLUDED = {".git", "node_modules", "__pycache__", ".venv"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yml", ".yaml", ".toml", ".md"}


def file_entry(root: Path, path: Path) -> dict:
    data = path.read_bytes()
    return {"path": path.relative_to(root).as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "suffix": path.suffix}


def git_commit(root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_index(root: Path) -> dict:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and not EXCLUDED.intersection(path.parts) and (path.suffix in TEXT_SUFFIXES or path.name in {"Dockerfile", "Makefile"}):
            entries.append(file_entry(root, path))
    return {
        "schema_version": "1.1",
        "root": str(root),
        "commit": git_commit(root),
        "file_count": len(entries),
        "files": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("ci-reports/repository-metadata.json"))
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(build_index(root), indent=2) + "\n", encoding="utf-8")
    print(f"indexed {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
