#!/usr/bin/env python3
"""Create a tamper-evident, commit-linked CI evidence manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def git_value(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_bundle(root: Path, reports: list[Path]) -> dict:
    commit = git_value(root, "rev-parse", "HEAD")
    entries = []
    missing = []
    for report in sorted(reports, key=lambda item: str(item)):
        if report.exists() and report.is_file():
            entries.append({"path": str(report), "sha256": sha256(report), "bytes": report.stat().st_size})
        else:
            missing.append(str(report))
    return {
        "schema_version": "1.1",
        "commit": commit,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if not missing else "incomplete",
        "reports": entries,
        "missing_reports": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, default=Path("ci-reports/evidence-bundle.json"))
    parser.add_argument("reports", nargs="*", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    bundle = build_bundle(root, [path if path.is_absolute() else root / path for path in args.reports])
    output.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
