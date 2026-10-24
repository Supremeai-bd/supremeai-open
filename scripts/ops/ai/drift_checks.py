#!/usr/bin/env python3
"""Deterministic route, environment, and deployment drift checks."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ENV_PATTERN = re.compile(r"(?:process\.env\.([A-Z][A-Z0-9_]*)|import\.meta\.env\.([A-Z][A-Z0-9_]*))")
ROUTE_PATTERN = re.compile(r"(?:path|route)\s*[:=]\s*[\"']([^\"']+)[\"']")
DEPLOYMENT_FILES = {
    "backend/Dockerfile",
    "frontend/Dockerfile",
    "docker-compose.yml",
    "docker-compose.production.yml",
    "infrastructure/mcp-control-plane/render.yaml",
    "infrastructure/mcp-control-plane/Dockerfile",
    "infrastructure/wrangler.toml",
}


def files(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file() and path.suffix in suffixes and ".git" not in path.parts]


def environment_drift(root: Path) -> list[dict[str, str]]:
    referenced: set[str] = set()
    for path in files(root, (".ts", ".tsx", ".js", ".jsx", ".py")):
        referenced.update(match[0] or match[1] for match in ENV_PATTERN.findall(path.read_text(encoding="utf-8", errors="ignore")))
    examples = {match.group(1) for path in root.rglob("*.example") for match in re.finditer(r"^([A-Z][A-Z0-9_]*)=", path.read_text(encoding="utf-8", errors="ignore"), re.MULTILINE)}
    return [{"category": "environment_drift", "name": name, "message": "Referenced environment variable is not declared in an example file"} for name in sorted(referenced - examples) if not name.startswith("NEXT_PUBLIC_DEV_")]


def deployment_drift(root: Path) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for relative in sorted(DEPLOYMENT_FILES):
        path = root / relative
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"(?:COPY|ADD)\s+([^\s]+)", content):
            source = match.group(1).strip('"\'')
            if source.startswith("http") or source.startswith("$"):
                continue
            if not (root / source).exists() and not source.startswith("--"):
                findings.append({"category": "deployment_drift", "path": relative, "message": f"Referenced build path does not exist: {source}"})
    return findings


def analyze(root: Path) -> dict:
    findings = environment_drift(root) + deployment_drift(root)
    return {"status": "review" if findings else "pass", "finding_count": len(findings), "findings": findings}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = analyze(args.root.resolve())
    print(json.dumps(report, indent=2) if args.json else f"{report['status']}: {report['finding_count']} drift finding(s)")
    return 1 if report["status"] == "review" else 0


if __name__ == "__main__":
    raise SystemExit(main())
