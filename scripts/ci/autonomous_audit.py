#!/usr/bin/env python3
"""Repository-wide autonomous quality and security audit for SupremeAI.

Adapted from autonomous-audit for SupremeAI's federation topology and single pipeline architecture.
Lightweight, deterministic checks, dependency audits, SARIF generation, and Markdown reporting.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "audit-results"
EXCLUDES = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    "build",
    "coverage",
    "audit-results",
    ".freebuff",
    ".turbo",
    ".cache",
    "target",
    "web",
    "tmp",
    ".artifacts",
    "logs",
}
MAX_FILE_BYTES = 1_500_000

# Patterns for tests or test fixtures that can have benign dummy mock tokens
TEST_FILE_PATTERN = re.compile(r"(test_.*\.py|.*\.test\.(ts|tsx|js|jsx)|fixture|mock|test_fixtures)", re.IGNORECASE)


@dataclass
class Finding:
    rule_id: str
    severity: str
    title: str
    message: str
    path: str = ""
    line: int = 1
    evidence: str = ""


FINDINGS: list[Finding] = []
COMMANDS: list[dict] = []


def add(rule_id: str, severity: str, title: str, message: str, path: str = "", line: int = 1, evidence: str = "") -> None:
    FINDINGS.append(Finding(rule_id, severity, title, message, path, line, evidence[:240]))


def files() -> Iterable[Path]:
    for root, dirs, filenames in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDES and not d.startswith(".")]
        for fn in filenames:
            p = Path(root) / fn
            try:
                if p.stat().st_size <= MAX_FILE_BYTES:
                    yield p
            except OSError:
                continue


def text_files() -> Iterable[tuple[Path, str]]:
    for p in files():
        try:
            data = p.read_bytes()
            if b"\x00" in data:
                continue
            yield p, data.decode("utf-8", errors="replace")
        except OSError:
            continue


def run(name: str, command: list[str], timeout: int = 300, required: bool = False) -> None:
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            timeout=timeout,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        output = (stdout + "\n" + stderr).strip()
        COMMANDS.append({"name": name, "command": shlex.join(command), "exit_code": proc.returncode, "output": output[-4000:]})
        if proc.returncode != 0 and required:
            add("CI-COMMAND-FAILED", "high", f"{name} failed", output[-1000:])
    except FileNotFoundError:
        COMMANDS.append({"name": name, "command": shlex.join(command), "exit_code": None, "output": "tool not installed"})
        if required:
            add("CI-TOOL-MISSING", "medium", f"Required tool missing: {name}", "Install the tool or update the workflow.")
    except subprocess.TimeoutExpired:
        COMMANDS.append({"name": name, "command": shlex.join(command), "exit_code": 124, "output": "timeout"})
        add("CI-TIMEOUT", "high", f"{name} timed out", f"Command exceeded {timeout}s.")


def deterministic_checks() -> None:
    secret_patterns = [
        ("SECRET-HARDCODED", r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{16,}['\"]"),
        ("SECRET-AWS", r"AKIA[0-9A-Z]{16}"),
        ("SECRET-PRIVATE-KEY", r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        ("SECRET-GITHUB", r"gh[pousr]_[A-Za-z0-9_]{30,}"),
    ]
    dangerous = [
        ("SEC-RAW-EVAL", r"\b(eval|exec)\s*\(", "dynamic code execution"),
        ("SEC-SHELL-TRUE", r"subprocess\.[A-Za-z_]+\([^\n]*shell\s*=\s*True", "shell execution with shell=True"),
        ("SEC-VERIFY-FALSE", r"verify\s*=\s*False", "TLS certificate verification disabled"),
        ("SEC-DEBUG-TRUE", r"(?i)(debug|development)\s*[:=]\s*True", "debug/development mode enabled"),
        ("SEC-CORS-WILDCARD", r"(?i)(allow_origins|access-control-allow-origin)[^\n]*\*", "wildcard CORS policy"),
    ]
    for path, text in text_files():
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        is_test_file = bool(TEST_FILE_PATTERN.search(rel))

        # Check for secrets (ignore obvious placeholders or test mocks)
        for rule, pattern in secret_patterns:
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                matched_str = match.group(0).lower()
                if any(x in matched_str for x in ("example", "dummy", "placeholder", "mock", "test", "fake", "your-", "xxx")):
                    continue
                if is_test_file:
                    continue
                add(rule, "critical", "Possible secret in source", "Move credentials to Infisical or environment variables.", rel, line, match.group(0))

        # Dangerous patterns
        for rule, pattern, title in dangerous:
            for match in re.finditer(pattern, text):
                line = text.count("\n", 0, match.start()) + 1
                if is_test_file:
                    continue
                severity = "high" if rule in {"SEC-VERIFY-FALSE", "SEC-SHELL-TRUE"} else "medium"
                add(rule, severity, title, "Review occurrence and ensure explicit boundary or verification.", rel, line, match.group(0))

    for p in files():
        if p.name in {".env", ".env.local", ".env.production"}:
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            if not rel.endswith(".example"):
                add("SECRET-ENV-FILE", "high", "Environment file present in repository", "Verify it contains no real secrets.", rel)


def dependency_checks() -> None:
    if (ROOT / "package-lock.json").exists():
        run("npm-audit", ["npm", "audit", "--audit-level=high"], required=False)
    elif (ROOT / "pnpm-lock.yaml").exists():
        run("pnpm-audit", ["pnpm", "audit", "--audit-level=high"], required=False)
    if (ROOT / "requirements.txt").exists() or (ROOT / "pyproject.toml").exists():
        run("pip-audit", ["pip-audit", "-f", "json"], required=False)
    if (ROOT / "Cargo.lock").exists():
        run("cargo-audit", ["cargo", "audit"], required=False)
    run("gitleaks", ["gitleaks", "detect", "--source", ".", "--no-banner", "--redact"], required=False)


def specialized_checks() -> None:
    if any(p.suffix == ".py" for p in files()):
        run("ruff", ["ruff", "check", "scripts/"], required=False)
        run("bandit", ["bandit", "-r", "scripts/", "-ll", "-q"], required=False)


def write_outputs() -> None:
    OUT.mkdir(exist_ok=True)
    findings = [asdict(f) for f in FINDINGS]
    (OUT / "audit.json").write_text(json.dumps({"findings": findings, "commands": COMMANDS}, indent=2), encoding="utf-8")
    
    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [{
            "tool": {
                "driver": {
                    "name": "autonomous-repo-audit",
                    "informationUri": "https://github.com/SupremeAI-Open/supremeai-open"
                }
            },
            "results": []
        }]
    }
    for f in FINDINGS:
        level = "error" if f.severity in {"critical", "high"} else "warning" if f.severity == "medium" else "note"
        result = {
            "ruleId": f.rule_id,
            "level": level,
            "message": {"text": f.message},
            "locations": [{
                "physicalLocation": {
                    "artifactLocation": {"uri": f.path or "."},
                    "region": {"startLine": f.line}
                }
            }]
        }
        sarif["runs"][0]["results"].append(result)
    
    (OUT / "audit.sarif").write_text(json.dumps(sarif, indent=2), encoding="utf-8")
    
    counts = {s: sum(f.severity == s for f in FINDINGS) for s in ("critical", "high", "medium", "low")}
    lines = [
        "# Autonomous Repository Audit Report",
        "",
        f"Findings: **{len(FINDINGS)}** | Critical: **{counts['critical']}** | High: **{counts['high']}** | Medium: **{counts['medium']}**",
        "",
    ]
    for f in sorted(FINDINGS, key=lambda x: ({"critical": 0, "high": 1, "medium": 2, "low": 3}[x.severity], x.path, x.line)):
        loc = f"`{f.path}:{f.line}`" if f.path else "repository"
        lines.append(f"- **{f.severity.upper()} [{f.rule_id}]** {f.title} — {loc}: {f.message}")
    lines += ["", "## Commands Executed", ""]
    for c in COMMANDS:
        lines.append(f"- `{c['name']}` exit={c['exit_code']} — `{c['command']}`")
    (OUT / "audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Autonomous Repository Audit")
    parser.add_argument("--strict", action="store_true", help="fail on critical/high findings")
    args = parser.parse_args()
    
    print("[autonomous-audit] Starting audit...")
    deterministic_checks()
    dependency_checks()
    specialized_checks()
    write_outputs()
    
    counts = {s: sum(f.severity == s for f in FINDINGS) for s in ("critical", "high", "medium", "low")}
    print(f"[autonomous-audit] Complete: {len(FINDINGS)} findings (Critical: {counts['critical']}, High: {counts['high']}, Medium: {counts['medium']}).")
    print(f"[autonomous-audit] Artifacts written to {OUT}/audit.md and {OUT}/audit.sarif")
    
    if args.strict and any(f.severity in {"critical", "high"} for f in FINDINGS):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
