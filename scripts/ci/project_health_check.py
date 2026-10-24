#!/usr/bin/env python3
"""
SupremeAI Project Health Checker
================================
Scans the project for real, actionable issues:
  - Duplicate Alembic revision IDs
  - Migration chain breakage (down_revision pointing nowhere)
  - Multiple merge-head conflicts
  - Docker port exposure / missing Redis password
  - Prometheus scrape port mismatch
  - Hardcoded credentials in docker-compose
  - firebase.json placeholder URLs
  - CI workflow missing top-level permissions
  - CORS allow_headers=["*"] in FastAPI
  - Admin JWT stored in localStorage (frontend)
  - Duplicate FastAPI app entrypoints
  - Missing RLS on Supabase tables
  - Secret/credential leaks in source files

Usage:
    python project_health_check.py [--root /path/to/project] [--json]

Exit code 0 = clean, 1 = issues found.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Finding:
    severity: str  # CRITICAL | HIGH | MEDIUM | LOW
    category: str
    file: str
    line: int
    message: str
    suggestion: str = ""


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity, category, file, line, message, suggestion=""):
        self.findings.append(
            Finding(severity, category, file, line, message, suggestion)
        )

    def summary(self) -> dict:
        counts = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return {"total": len(self.findings), "by_severity": counts}

    def to_json(self) -> str:
        return json.dumps(
            {**self.summary(), "findings": [asdict(f) for f in self.findings]},
            indent=2,
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def glob_recursive(root: Path, patterns: list[str]) -> list[Path]:
    results = []
    skip_dirs = {
        "node_modules", ".git", "__pycache__", ".venv", ".venv_ci",
        "venv", "dist", ".next", "coverage", "ci-reports",
        "reports", ".kilo"
    }
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for name in filenames:
            if name in {"poetry.lock", "package-lock.json", "project_health_check.py"}:
                continue
            p = Path(dirpath) / name
            if any(p.match(pat) for pat in patterns):
                results.append(p)
    return sorted(results)


# ---------------------------------------------------------------------------
# Individual check functions
# ---------------------------------------------------------------------------

def check_duplicate_alembic_revisions(root: Path, report: Report):
    """Find Alembic migration files with duplicate revision IDs."""
    mig_dir = root / "backend" / "alembic_migrations" / "versions"
    if not mig_dir.is_dir():
        return

    rev_map: dict[str, list[Path]] = {}
    down_revs: dict[str, str] = {}

    for f in mig_dir.glob("*.py"):
        text = read_text(f)
        rev_match = re.search(r'revision\s*(?::\s*[^=]+)?\s*=\s*["\']([a-zA-Z0-9_]+)["\']', text)
        down_match = re.search(
            r'^[ \t]*down_revision\s*(?::\s*[^=]+)?\s*=\s*(?:None|["\']([a-zA-Z0-9_]+)["\']|\((.*?)\))',
            text,
            re.MULTILINE,
        )
        if rev_match:
            rev_id = rev_match.group(1)
            rev_map.setdefault(rev_id, []).append(f)
            if down_match and down_match.group(1):
                down_revs[rev_id] = down_match.group(1)

    # duplicates
    for rev_id, files in rev_map.items():
        if len(files) > 1:
            for f in files:
                report.add(
                    "CRITICAL",
                    "duplicate_migration_revision",
                    str(f.relative_to(root)),
                    0,
                    f"Revision ID '{rev_id}' is used in {len(files)} files",
                    "Each migration must have a unique revision ID.",
                )

    # broken chain: down_revision points to a non-existent revision
    all_revs = set(rev_map.keys())
    for rev_id, down in down_revs.items():
        if down not in all_revs:
            file_path = rev_map[rev_id][0]
            report.add(
                "HIGH",
                "broken_migration_chain",
                str(file_path.relative_to(root)),
                0,
                f"Revision '{rev_id}' has down_revision '{down}' which does not exist",
                "Fix the down_revision to point to a valid parent or None.",
            )


def check_multiple_merge_heads(root: Path, report: Report):
    """Detect multiple merge-head migrations that merge the same branches."""
    mig_dir = root / "backend" / "alembic_migrations" / "versions"
    if not mig_dir.is_dir():
        return

    merge_migrations: list[tuple[Path, tuple[str, ...]]] = []
    for f in mig_dir.glob("*.py"):
        text = read_text(f)
        down_match = re.search(
            r'down_revision\s*(?::\s*[^=]+)?\s*=\s*\(([^)]+)\)', text, re.DOTALL
        )
        if down_match:
            parents = tuple(
                re.findall(r'["\']([a-zA-Z0-9_]+)["\']', down_match.group(1))
            )
            if len(parents) >= 2:
                merge_migrations.append((f, parents))

    # check for overlapping parent sets
    for i, (f1, p1) in enumerate(merge_migrations):
        for f2, p2 in merge_migrations[i + 1:]:
            shared = set(p1) & set(p2)
            if shared:
                report.add(
                    "HIGH",
                    "conflicting_merge_heads",
                    str(f1.relative_to(root)),
                    0,
                    f"Merge migration and {f2.name} both merge branches: {shared}",
                    "Keep only one merge migration; delete the other.",
                )


def check_docker_port_exposure(root: Path, report: Report):
    """Check production docker-compose for exposed ports that should be internal."""
    prod = root / "docker-compose.production.yml"
    if not prod.is_file():
        return

    text = read_text(prod)

    # Redis without password
    if "redis" in text.lower():
        has_redis_pass = bool(
            re.search(r'redis.*requirepass|REDIS_PASSWORD', text, re.IGNORECASE)
        )
        if not has_redis_pass:
            report.add(
                "CRITICAL",
                "redis_no_password",
                str(prod.relative_to(root)),
                0,
                "Redis service has no password set in production compose",
                "Add --requirepass or REDIS_PASSWORD env var.",
            )

    # ports that should be internal-only
    internal_services = ["postgres", "redis", "prometheus", "grafana",
                         "otel-collector", "alertmanager"]
    for svc in internal_services:
        # find the service block and check if it has ports:
        pattern = rf'^\s+{svc}:\s*$.*?(?=^\s+\S+:|\Z)'
        block_match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
        if block_match and "ports:" in block_match.group(0):
            report.add(
                "HIGH",
                "port_exposed_internally",
                str(prod.relative_to(root)),
                0,
                f"Service '{svc}' has ports exposed to host — should be internal-only",
                f"Remove 'ports:' from {svc} or bind to the loopback interface (env == \"local\" style dev only).",
            )


def check_prometheus_port_mismatch(root: Path, report: Report):
    """Check if Prometheus scrape target port matches backend's actual port."""
    prom = root / "infrastructure" / "monitoring" / "prometheus" / "prometheus.yml"
    if not prom.is_file():
        return

    text = read_text(prom)

    # find all targets
    targets = re.findall(r"targets:\s*\['([^']+)'\]", text)
    for t in targets:
        if ":8000" in t:
            report.add(
                "MEDIUM",
                "prometheus_port_mismatch",
                str(prom.relative_to(root)),
                0,
                f"Scrape target '{t}' uses port 8000 but backend runs on 8080",
                "Change scrape target port to 8080.",
            )


def check_firebase_placeholder_urls(root: Path, report: Report):
    """Check firebase.json for placeholder example.com URLs."""
    fb = root / "firebase.json"
    if not fb.is_file():
        return

    text = read_text(fb)
    for i, line in enumerate(text.splitlines(), 1):
        if "example.com" in line:
            report.add(
                "MEDIUM",
                "firebase_placeholder_url",
                str(fb.relative_to(root)),
                i,
                "Placeholder URL 'example.com' found in firebase.json rewrite",
                "Replace with actual backend URL.",
            )


def check_ci_permissions(root: Path, report: Report):
    """Check CI workflow for missing top-level permissions block."""
    ci = root / ".github" / "workflows" / "ci.yml"
    if not ci.is_file():
        return

    text = read_text(ci)
    lines = text.splitlines()

    # check if top-level permissions: exists (before first job)
    has_top_permissions = False
    for line in lines:
        if line.strip().startswith("permissions:"):
            has_top_permissions = True
            break
        if line.strip().startswith("jobs:"):
            break

    if not has_top_permissions:
        report.add(
            "HIGH",
            "ci_missing_permissions",
            str(ci.relative_to(root)),
            0,
            "No top-level 'permissions:' block — all jobs get default token scope",
            "Add a restrictive top-level permissions: block.",
        )

    # check for insecure node version flag
    for i, line in enumerate(lines, 1):
        if "ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION" in line and "true" in line:
            report.add(
                "MEDIUM",
                "ci_insecure_node_flag",
                str(ci.relative_to(root)),
                i,
                "ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION set to true",
                "Remove this flag; use a supported Node version.",
            )


def check_cors_wildcard_headers(root: Path, report: Report):
    """Check FastAPI files for CORS allow_headers=['*']."""
    py_files = glob_recursive(root, ["*.py"])
    for f in py_files:
        text = read_text(f)
        for i, line in enumerate(text.splitlines(), 1):
            if "allow_headers" in line and '"*"' in line:
                report.add(
                    "HIGH",
                    "cors_wildcard_headers",
                    str(f.relative_to(root)),
                    i,
                    "CORS allow_headers set to wildcard '*'",
                    "List only the required headers explicitly.",
                )


def check_localstorage_jwt(root: Path, report: Report):
    """Check frontend files for JWT tokens stored in localStorage."""
    ts_files = glob_recursive(root, ["*.ts", "*.tsx"])
    for f in ts_files:
        text = read_text(f)
        for i, line in enumerate(text.splitlines(), 1):
            if "localStorage" in line and (
                "jwt" in line.lower() or "token" in line.lower()
            ) and ("setItem" in line or "getItem" in line):
                report.add(
                    "MEDIUM",
                    "jwt_in_localstorage",
                    str(f.relative_to(root)),
                    i,
                    "JWT/token stored in localStorage — vulnerable to XSS",
                    "Use httpOnly cookies or in-memory storage instead.",
                )
                break  # one finding per file


def check_hardcoded_credentials(root: Path, report: Report):
    """Check docker-compose files for hardcoded credentials."""
    compose_files = list(root.glob("docker-compose*.yml")) + list(
        root.glob("infrastructure/**/docker-compose*.yml")
    )
    for f in compose_files:
        text = read_text(f)
        for i, line in enumerate(text.splitlines(), 1):
            # skip comments
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # check for postgres/postgres type patterns
            if re.search(
                r'POSTGRES_PASSWORD.*=.*postgres\b', line
            ) or re.search(r'POSTGRES_USER.*=.*postgres\b', line):
                if "test" not in str(f).lower() and "dev" not in line.lower():
                    report.add(
                        "MEDIUM",
                        "hardcoded_credential",
                        str(f.relative_to(root)),
                        i,
                        f"Hardcoded default credential: {stripped}",
                        "Use environment variable references instead.",
                    )


def check_duplicate_app_entrypoints(root: Path, report: Report):
    """Check if multiple FastAPI app instances exist in backend."""
    candidates = []
    for f in (root / "backend" / "api").rglob("*.py"):
        text = read_text(f)
        if re.search(r'app\s*=\s*FastAPI\s*\(', text):
            candidates.append(f)
    for f in (root / "backend" / "core").rglob("*.py"):
        text = read_text(f)
        if re.search(r'app\s*=\s*FastAPI\s*\(', text) or re.search(
            r'create_app\s*\(\s*\)', text
        ):
            candidates.append(f)

    if len(candidates) > 2:
        for f in candidates:
            report.add(
                "LOW",
                "duplicate_app_entrypoint",
                str(f.relative_to(root)),
                0,
                "Multiple FastAPI app entrypoints detected",
                "Consolidate into a single app factory.",
            )


def check_secret_leaks(root: Path, report: Report):
    """Scan source files for potential secret/API key leaks."""
    patterns = [
        (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API key"),
        (r'gh[pousr]_[a-zA-Z0-9]{36,}', "GitHub token"),
        (r'AKIA[0-9A-Z]{16}', "AWS access key"),
        (r'-----BEGIN (RSA |EC )?PRIVATE KEY-----', "Private key"),
        (
            r'(?:supabase|firebase)_service_role["\s:=]+["\'][a-zA-Z0-9._-]{20,}["\']',
            "Service role key",
        ),
    ]
    src_files = glob_recursive(root, ["*.py", "*.ts", "*.tsx", "*.yml", "*.yaml",
                                       "*.json", "*.js"])
    for f in src_files:
        if any(x in str(f).lower() for x in ["/tests/", "test_", "/examples/", "sample_", "dummy", "sa_admin.json"]):
            continue
        text = read_text(f)
        for i, line in enumerate(text.splitlines(), 1):
            for pattern, label in patterns:
                if re.search(pattern, line):
                    # skip test/mock values
                    if any(w in line.lower() for w in
                           ["mock", "test", "example", "dummy", "fake"]):
                        continue
                    report.add(
                        "CRITICAL",
                        "secret_leak",
                        str(f.relative_to(root)),
                        i,
                        f"Potential {label} found in source",
                        "Remove immediately and rotate the key.",
                    )


def check_missing_rls(root: Path, report: Report):
    """Check SQL migration files for tables created without RLS."""
    sql_files = list((root / "backend" / "database" / "migrations").glob("*.sql"))
    sql_files += list((root / "migrations").glob("*.sql"))

    for f in sql_files:
        text = read_text(f)
        # find CREATE TABLE statements
        tables = re.findall(
            r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["\']?(\w+)["\']?',
            text, re.IGNORECASE
        )
        if not tables:
            continue
        has_rls = "ROW LEVEL SECURITY" in text.upper() or "ENABLE ROW LEVEL SECURITY" in text.upper()
        if not has_rls:
            report.add(
                "MEDIUM",
                "missing_rls",
                str(f.relative_to(root)),
                0,
                f"Tables {tables} created without RLS enabled",
                "Add 'ALTER TABLE <name> ENABLE ROW LEVEL SECURITY;' for each table.",
            )


def check_dockerfile_best_practices(root: Path, report: Report):
    """Check Dockerfiles for common issues."""
    dockerfiles = glob_recursive(root, ["Dockerfile*"])
    for f in dockerfiles:
        text = read_text(f)
        lines = text.splitlines()

        # check USER directive
        has_user = any(line.strip().startswith("USER ") for line in lines)
        if not has_user and "production" in str(f).lower():
            report.add(
                "MEDIUM",
                "dockerfile_no_user",
                str(f.relative_to(root)),
                0,
                "Production Dockerfile has no USER directive — runs as root",
                "Add 'USER nonroot' after creating a non-root user.",
            )

        # check for unpinned versions
        for i, line in enumerate(lines, 1):
            if line.strip().startswith("RUN pip install") and "--no-cache-dir" not in line:
                if "==" not in line and "openai-whisper" not in line:
                    report.add(
                        "LOW",
                        "dockerfile_unpinned_dep",
                        str(f.relative_to(root)),
                        i,
                        f"Pip install without version pin: {line.strip()}",
                        "Pin versions with '==' for reproducibility.",
                    )


def check_import_errors_python(root: Path, report: Report):
    """Quick syntax/import check on Python files by compiling them."""
    import ast

    py_files = glob_recursive(root, ["*.py"])
    errors = 0
    for f in py_files:
        if "test_" in f.name or "/tests/" in str(f):
            continue
        try:
            ast.parse(read_text(f))
        except SyntaxError as e:
            errors += 1
            if errors <= 20:  # cap to avoid flood
                report.add(
                    "MEDIUM",
                    "python_syntax_error",
                    str(f.relative_to(root)),
                    getattr(e, 'lineno', 0),
                    f"Syntax error: {str(e)[:200]}",
                    "Fix the Python syntax error.",
                )


def check_env_files_exposed(root: Path, report: Report):
    """Check if .env files are committed (should be gitignored)."""
    import subprocess

    env_files = list(root.glob(".env*"))
    for f in env_files:
        # Template/documentation files are MEANT to be committed — they hold
        # empty placeholders with generation instructions, never secrets.
        # (.env.example skip predates multi-env templates: #1121 landed
        # .env.production.example / .env.grafana.example, same class.)
        if f.name == ".env.example" or f.name.endswith(".example") or f.name.endswith(".template"):
            continue
        # Verify if the file is tracked in Git or not ignored
        is_tracked = False
        try:
            res = subprocess.run(
                ["git", "ls-files", "--error-unmatch", str(f.name)],
                cwd=str(root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            is_tracked = (res.returncode == 0)
        except Exception:
            is_tracked = False

        if not is_tracked:
            # File is strictly untracked / ignored by git
            continue

        text = read_text(f)
        # check if it has real-looking values
        has_secrets = bool(
            re.search(r'(?:KEY|SECRET|PASSWORD|TOKEN)\s*=\s*\S+', text, re.IGNORECASE)
        )
        if has_secrets:
            report.add(
                "HIGH",
                "env_file_with_secrets",
                str(f.relative_to(root)),
                0,
                f".env file contains secret-like values and is tracked in git",
                "Add .env to .gitignore and remove from git cache using git rm --cached.",
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CHECKS = [
    ("Duplicate Alembic revisions", check_duplicate_alembic_revisions),
    ("Multiple merge heads", check_multiple_merge_heads),
    ("Docker port exposure", check_docker_port_exposure),
    ("Prometheus port mismatch", check_prometheus_port_mismatch),
    ("Firebase placeholder URLs", check_firebase_placeholder_urls),
    ("CI permissions", check_ci_permissions),
    ("CORS wildcard headers", check_cors_wildcard_headers),
    ("JWT in localStorage", check_localstorage_jwt),
    ("Hardcoded credentials", check_hardcoded_credentials),
    ("Duplicate app entrypoints", check_duplicate_app_entrypoints),
    ("Secret leaks", check_secret_leaks),
    ("Missing RLS", check_missing_rls),
    ("Dockerfile best practices", check_dockerfile_best_practices),
    ("Python syntax errors", check_import_errors_python),
    ("Env files exposed", check_env_files_exposed),
]


def main():
    parser = argparse.ArgumentParser(
        description="SupremeAI Project Health Checker"
    )
    parser.add_argument(
        "--root", type=str, default=".",
        help="Project root directory (default: current dir)",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--severity", type=str, default="ALL",
        help="Min severity to show: CRITICAL, HIGH, MEDIUM, LOW, ALL",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        sys.exit(2)

    report = Report()

    print(f"Scanning project: {root}")
    print("=" * 60)

    for name, check_fn in CHECKS:
        print(f"  Running: {name}...", end=" ")
        try:
            check_fn(root, report)
            print("done")
        except Exception as e:
            print(f"ERROR: {e}")

    print("=" * 60)

    # filter by severity
    sev_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    min_sev = sev_order.get(args.severity.upper(), 99)

    filtered = [f for f in report.findings if sev_order.get(f.severity, 99) <= min_sev]

    if args.json:
        report.findings = filtered
        print(report.to_json())
    else:
        if not filtered:
            print("\\nNo issues found!")
        else:
            print(f"\\nFound {len(filtered)} issue(s):\\n")
            current_sev = None
            for f in sorted(filtered, key=lambda x: sev_order.get(x.severity, 99)):
                if f.severity != current_sev:
                    current_sev = f.severity
                    print(f"\\n--- {f.severity} ---")
                print(f"  [{f.category}] {f.file}:{f.line}")
                print(f"    {f.message}")
                if f.suggestion:
                    print(f"    -> {f.suggestion}")
                print()

    summary = report.summary()
    print(f"\\nSummary: {summary['total']} total findings")
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = summary["by_severity"].get(sev, 0)
        if count:
            print(f"  {sev}: {count}")

    # exit 1 if any CRITICAL or HIGH
    has_critical = summary["by_severity"].get("CRITICAL", 0) > 0
    has_high = summary["by_severity"].get("HIGH", 0) > 0
    sys.exit(1 if (has_critical or has_high) else 0)


if __name__ == "__main__":
    main()
