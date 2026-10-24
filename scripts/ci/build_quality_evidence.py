#!/usr/bin/env python3
"""Build a bounded, report-only quality and cost optimization inventory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def count_matches(root: Path, suffixes: tuple[str, ...], needle: str) -> int:
    total = 0
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        try:
            total += path.read_text(encoding="utf-8", errors="ignore").count(needle)
        except OSError:
            continue
    return total


def build(root: Path) -> dict[str, object]:
    frontend = root / "frontend"
    return {
        "schema_version": "1.0",
        "mode": "report_only",
        "frontend": {
            "path_present": frontend.exists(),
            "source_files": sum(1 for p in frontend.rglob("*") if p.is_file() and p.suffix in {".ts", ".tsx"}),
            "explicit_any_count": count_matches(frontend, (".ts", ".tsx"), ": any"),
            "todo_fixme_count": count_matches(frontend, (".ts", ".tsx"), "TODO") + count_matches(frontend, (".ts", ".tsx"), "FIXME"),
        },
        "ci_efficiency": {
            "dependency_cache_expected": True,
            "changed_path_selection": True,
            "full_audits_scheduled": True,
            "destructive_cleanup_performed": False,
        },
        "next_actions": [
            "Reduce explicit any and unused-variable findings in bounded batches.",
            "Review dead-code/dependency reports before deleting anything.",
            "Raise coverage only after measuring the current baseline.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("ci-reports/quality-evidence.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build(root), indent=2) + "\n", encoding="utf-8")
    print(f"quality evidence written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
