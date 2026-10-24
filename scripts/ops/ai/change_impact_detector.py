#!/usr/bin/env python3
"""Deterministic preflight for changed-file impact and protected paths."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

PROTECTED_PREFIXES = (".github/", ".clinerules/", ".specify/", "infrastructure/", "backend/alembic_migrations/")
PROTECTED_NAMES = {".env", ".env.local", ".env.production", "Dockerfile"}
IMPORT_PATTERNS = (
    re.compile(r"^\s*(?:from|import)\s+[\"']([^\"']+)[\"']"),
    re.compile(r"^\s*(?:from|import)\s+([.][A-Za-z0-9_./]+)"),
)

@dataclass(frozen=True)
class Finding:
    severity: str
    category: str
    path: str
    message: str


SEVERITY_POINTS = {"LOW": 1, "MEDIUM": 3, "HIGH": 6, "CRITICAL": 10}
CATEGORY_POINTS = {
    "broken_import": 4,
    "protected_path": 3,
    "lockfile_drift": 2,
}


def git_changed_files(root: Path, base: str = "") -> list[str]:
    command = ["git", "diff", "--name-only", "--diff-filter=ACMRT", base or "HEAD"]
    result = subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def is_protected(path: str) -> bool:
    return path in PROTECTED_NAMES or path.startswith(PROTECTED_PREFIXES) or path.endswith((".tf", ".tfvars"))


def is_safe_summary_change(path: str) -> bool:
    """Allow purely presentational or summary changes to have lower risk in preflight."""
    return path in {
        ".github/scripts/ci_summary_v2.py",
        ".github/scripts/surface_advanced_audit_summary.py",
        "scripts/generate_api_health_report.py",
    }


def resolve_local_import(source: Path, specifier: str, root: Path) -> Path | None:
    if not specifier.startswith((".", "/")):
        return None
    relative_specifier = specifier[1:] if specifier.startswith(".") and not specifier.startswith("./") else specifier
    candidate = (source.parent / relative_specifier).resolve() if specifier.startswith(".") else (root / specifier.lstrip("/")).resolve()
    candidates = [candidate, *[candidate.with_suffix(ext) for ext in (".py", ".ts", ".tsx", ".js", ".jsx")]]
    candidates.extend(candidate / name for name in ("__init__.py", "index.ts", "index.tsx", "index.js"))
    return next((item for item in candidates if item.is_file() and root in item.parents), None)


def scan_imports(root: Path, changed: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for relative in sorted(changed):
        source = root / relative
        if source.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"} or not source.is_file():
            continue
        for line_number, line in enumerate(source.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            specifiers = {specifier for pattern in IMPORT_PATTERNS for specifier in pattern.findall(line)}
            for specifier in specifiers:
                if specifier.startswith((".", "/")) and resolve_local_import(source, specifier, root) is None:
                    findings.append(Finding("HIGH", "broken_import", relative, f"Line {line_number}: local import '{specifier}' cannot be resolved"))
    return findings


def risk_details(findings: list[Finding]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    for finding in findings:
        points = max(SEVERITY_POINTS.get(finding.severity, 1), CATEGORY_POINTS.get(finding.category, 0))
        score += points
        reasons.append(f"{finding.category} in {finding.path} (+{points})")
    return score, reasons


def analyze(root: Path, changed: list[str]) -> dict:
    findings = scan_imports(root, set(changed))
    for path in changed:
        if is_protected(path):
            severity = "LOW" if is_safe_summary_change(path) else "HIGH"
            findings.append(Finding(severity, "protected_path", path, "Changed path requires review" if severity == "LOW" else "Changed path requires explicit human review"))
    manifests = {"package.json", "pnpm-lock.yaml", "yarn.lock", "package-lock.json"}
    if any(path.endswith("package.json") for path in changed) and not any(path in manifests - {"package.json"} for path in changed):
        findings.append(Finding("MEDIUM", "lockfile_drift", "package.json", "package.json changed without a lockfile change"))
    score, reasons = risk_details(findings)
    risk = "critical" if score >= 10 else "high" if score >= 6 else "medium" if score >= 2 else "low"
    status = "blocked" if risk in {"high", "critical"} else "review" if risk == "medium" else "pass"
    return {
        "status": status,
        "risk": risk,
        "risk_score": score,
        "risk_reasons": reasons,
        "changed_files": changed,
        "findings": [asdict(item) for item in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base", default="", help="Git revision to compare; defaults to working tree against HEAD")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    report = analyze(args.root.resolve(), git_changed_files(args.root.resolve(), args.base))
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.as_json else f"Risk: {report['risk']}\nStatus: {report['status']}\nFindings: {len(report['findings'])}")
    return 1 if report["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
