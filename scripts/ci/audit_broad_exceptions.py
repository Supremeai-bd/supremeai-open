#!/usr/bin/env python3
"""Report broad exception handlers in production Python paths.

This is intentionally report-only for the first rollout: existing resilience
boundaries are numerous, and turning the inventory into a blocking gate without
review would create unsafe drive-by changes. The report gives each handler a
stable file/line reference for owner review.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


DEFAULT_ROOTS = ("backend", "tools", "scripts")
EXCLUDED_PARTS = {"tests", "examples", "__pycache__", ".venv", "venv"}


def iter_python_files(roots: tuple[str, ...]) -> list[Path]:
    files: list[Path] = []
    for root_name in roots:
        root = Path(root_name)
        if not root.exists():
            continue
        files.extend(
            path
            for path in root.rglob("*.py")
            if not EXCLUDED_PARTS.intersection(path.parts)
        )
    return sorted(set(files))


def audit_file(path: Path) -> list[dict[str, object]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [{"file": str(path), "line": 1, "kind": "parse_error", "detail": str(exc)}]

    findings: list[dict[str, object]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        is_broad = node.type is None or (
            isinstance(node.type, ast.Name) and node.type.id == "Exception"
        )
        if is_broad:
            findings.append(
                {
                    "file": str(path),
                    "line": node.lineno,
                    "kind": "bare_except" if node.type is None else "exception",
                    "bound_name": node.name,
                }
            )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="ci-reports/broad-exceptions.json")
    parser.add_argument("roots", nargs="*", default=list(DEFAULT_ROOTS))
    args = parser.parse_args()

    findings = [finding for path in iter_python_files(tuple(args.roots)) for finding in audit_file(path)]
    report = {
        "status": "report-only",
        "roots": args.roots,
        "finding_count": len(findings),
        "findings": findings,
        "next_action": "Review each production handler and replace broad catches with specific exceptions or an approved resilience boundary.",
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Broad exception audit: {len(findings)} findings (report-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
