#!/usr/bin/env python3
"""SupremeAI Gap Miner: dependency-free, read-only project intelligence scanner."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

EXCLUDED_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build", "coverage", ".next", ".turbo", "target", "__pycache__"}
TEXT_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".md", ".txt", ".sql", ".sh", ".ps1", ".html", ".css", ".scss"}
SECRET_NAME_RE = re.compile(r"(^|[_.-])(SECRET|TOKEN|PASSWORD|API[_-]?KEY|PRIVATE[_-]?KEY|ACCESS[_-]?KEY|AUTH[_-]?TOKEN)([_.-]|$)", re.IGNORECASE)
SECRET_VALUE_RE = re.compile(r"(?i)(api[_-]?key|secret|token|password|private[_-]?key)\\s*[=:]\\s*[\"']?[A-Za-z0-9_./+=:-]{16,}")
TODO_RE = re.compile(r"\\b(TODO|FIXME|HACK|XXX|BUG|TEMP)\\b", re.IGNORECASE)

@dataclass
class Finding:
    id: str
    category: str
    severity: str
    title: str
    path: str
    evidence: str
    impact: str
    recommendation: str
    score: int
    tags: list[str]

SEVERITY_SCORE = {"critical": 100, "high": 75, "medium": 45, "low": 20, "info": 5}

class Miner:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.files: list[Path] = []
        self.findings: list[Finding] = []
        self.stats: dict[str, Any] = {}
        self.text_cache: dict[Path, str] = {}
        self.scan_files()

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root)).replace('\\', '/')

    def scan_files(self) -> None:
        for base, dirs, names in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
            for name in names:
                p = Path(base) / name
                try:
                    if p.is_file(): self.files.append(p)
                except OSError: _ = None
        self.stats["file_count"] = len(self.files)

    def text(self, p: Path) -> str:
        if p in self.text_cache: return self.text_cache[p]
        if p.suffix.lower() not in TEXT_EXTS or p.stat().st_size > 2_000_000: return ""
        try:
            s = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            s = ""
        self.text_cache[p] = s
        return s

    def add(self, category, severity, title, path=".", evidence="", impact="", recommendation="", tags=()):
        self.findings.append(Finding(
            id=hashlib.sha1(f"{category}|{path}|{title}".encode()).hexdigest()[:12],
            category=category, severity=severity, title=title, path=path,
            evidence=evidence[:500], impact=impact, recommendation=recommendation,
            score=SEVERITY_SCORE[severity], tags=list(tags)))

    def security(self):
        env_files = []
        tracked_env = []
        for p in self.files:
            name = p.name.lower()
            if name == ".env" or name.startswith(".env."):
                env_files.append(p)
                try:
                    if subprocess.run(["git", "ls-files", "--error-unmatch", str(p.relative_to(self.root))], cwd=self.root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                        tracked_env.append(p)
                except OSError: _ = None
        for p in tracked_env:
            self.add("security", "critical", "Environment file appears tracked by Git", self.rel(p), "Git index contains an .env-like file", "Secrets can leak through repository history.", "Remove it from Git history where necessary, rotate exposed secrets, and keep only .env.example templates.", ["secrets", "git"])
        candidates = {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".npmrc", ".pypirc"}
        for p in self.files:
            if p.name in candidates:
                self.add("security", "high", "Potential credential-bearing file present", self.rel(p), p.name, "Credential files should not live in application repositories.", "Move credentials to a secret manager or environment configuration.", ["credentials"])
            text = self.text(p)
            for m in SECRET_VALUE_RE.finditer(text):
                if p.name.lower().startswith(".env") and p not in tracked_env: continue
                self.add("security", "high", "Possible hard-coded credential pattern", self.rel(p), m.group(0), "Hard-coded credentials can be committed, logged, or copied into artifacts.", "Replace with environment/secret references and rotate any exposed value.", ["secrets", "static-scan"])
                break
        gitignore = self.root / ".gitignore"
        if gitignore.exists():
            g = self.text(gitignore)
            for required in [".env", "*.pem", "*.key"]:
                if required not in g:
                    self.add("security", "medium", f"Git ignore does not obviously exclude {required}", ".gitignore", f"Missing pattern: {required}", "Accidental secret commits become more likely.", f"Add an explicit {required} ignore rule if appropriate.", ["gitignore"])
        else:
            self.add("security", "medium", "No .gitignore found", ".", "Missing repository ignore policy", "Build artifacts and secrets may be accidentally committed.", "Add a hardened .gitignore for all languages and deployment targets.", ["gitignore"])

    def ci(self):
        workflows = []
        gh = self.root / ".github/workflows"
        if gh.exists():
            workflows = [p for p in gh.rglob("*") if p.is_file() and p.suffix in {".yml", ".yaml"}]
        if not workflows:
            self.add("ci", "high", "No GitHub Actions workflows detected", ".github/workflows", "No workflow YAML files found", "Builds, tests, security and deployment may not be reproducible.", "Add separate concern-focused workflows or a consolidated pipeline with explicit quality gates.", ["github-actions"])
        content = "\n".join(self.text(p) for p in workflows)
        checks = {
            "test": r"(^|[\\s_-])(pytest|vitest|jest|npm run test|pnpm .*test|yarn .*test)",
            "lint": r"(^|[\\s_-])(eslint|ruff|flake8|mypy|lint)",
            "security": r"(trivy|semgrep|codeql|bandit|pip-audit|npm audit|pnpm audit|snyk)",
            "build": r"(npm run build|pnpm .*build|yarn .*build|docker build|poetry build)",
        }
        for label, pat in checks.items():
            if not re.search(pat, content, re.IGNORECASE):
                self.add("ci", "medium", f"CI does not visibly contain a {label} gate", ".github/workflows", f"No obvious {label} command/tool detected", "Regression or supply-chain risk can pass through CI.", f"Add or intentionally document a {label} stage.", ["ci", label])
        for p in workflows:
            t = self.text(p)
            if "pull_request" not in t and "push:" in t:
                self.add("ci", "low", "Workflow appears push-only", self.rel(p), "push trigger without pull_request trigger", "Problems can be discovered late rather than before merge.", "Consider PR validation for tests, lint and security.", ["ci", "pull-request"])

    def code(self):
        loc = []
        todo = Counter()
        py_functions = []
        for p in self.files:
            if p.suffix.lower() not in TEXT_EXTS: continue
            try: p.stat().st_size
            except OSError: continue
            text = self.text(p)
            lines = text.count("\\n") + (1 if text else 0)
            loc.append((lines, p))
            todo[self.rel(p)] = len(TODO_RE.findall(text))
            if lines > 1000:
                sev = "high" if lines > 2000 else "medium"
                self.add("code", sev, "Oversized source/config file", self.rel(p), f"{lines} lines", "Large files increase change risk, review cost and hidden coupling.", "Split by responsibility; extract pure modules/services and keep orchestration thin.", ["size", "maintainability"])
            elif lines > 600:
                self.add("code", "low", "Large source/config file", self.rel(p), f"{lines} lines", "Large modules tend to accumulate unrelated responsibilities.", "Review for cohesion and seams for extraction.", ["size"])
            if p.suffix == ".py":
                try:
                    tree = ast.parse(text)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            py_functions.append((len(text.splitlines()[node.lineno-1:node.end_lineno or node.lineno]), p, node.name))
                except SyntaxError: print('Silenced error in except block')
        for path, count in todo.items():
            if count >= 12:
                self.add("code", "medium", "High concentration of TODO/FIXME/HACK markers", path, f"{count} markers", "Known unfinished work can hide operational or correctness gaps.", "Convert high-value markers into tracked issues or remove stale comments.", ["technical-debt"])
        for lines, p, name in sorted(py_functions, reverse=True)[:20]:
            if lines > 150:
                sev = "high" if lines > 300 else "medium"
                self.add("code", sev, "Very large Python function", self.rel(p), f"{name} spans ~{lines} source lines", "Large functions are difficult to test and reason about.", "Split into small pure helpers and explicit orchestration stages.", ["complexity", "python"])
        self.stats["largest_files"] = [{"path": self.rel(p), "lines": l} for l,p in sorted(loc, reverse=True)[:20]]
        self.stats["todo_total"] = sum(todo.values())

    def providers(self):
        candidates = []
        for p in self.files:
            t = self.text(p)
            if any(k in t.lower() for k in ["provider", "llm", "model", "gemini", "groq", "openrouter", "huggingface", "moonshot", "deepseek", "ollama"]):
                candidates.append(p)
        provider_words = Counter()
        for p in candidates:
            t = self.text(p).lower()
            for k in ["gemini","groq","openrouter","huggingface","moonshot","deepseek","ollama","cloudflare","together","nvidia"]:
                if k in t: provider_words[k] += 1
        if provider_words:
            self.stats["provider_mentions"] = dict(provider_words)
        router_candidates = [p for p in candidates if "router" in p.name.lower() or "gateway" in p.name.lower()]
        for p in router_candidates:
            t = self.text(p)
            if "fallback" not in t.lower():
                self.add("providers", "medium", "LLM/router candidate has no visible fallback logic", self.rel(p), "No fallback keyword detected", "A single provider outage can become a user-visible outage.", "Add capability-aware fallback chains with circuit breakers and quota checks.", ["llm", "resilience"])
            if "cache" not in t.lower():
                self.add("providers", "medium", "LLM/router candidate has no visible caching hook", self.rel(p), "No cache keyword detected", "Repeated prompts can waste provider quota and latency.", "Use deterministic + semantic caching where correctness permits.", ["llm", "cache"])
        trackers = [p for p in candidates if "free_tier" in p.name.lower() or "quota" in p.name.lower()]
        if trackers and not any("redis" in self.text(p).lower() for p in trackers):
            self.add("providers", "low", "Provider quota tracker does not visibly use shared persistence", self.rel(trackers[0]), "No Redis keyword in tracker candidate", "Per-process counters can diverge across multiple workers.", "Persist counters/locks in shared Redis/DB when horizontal scaling is enabled.", ["quota", "redis"])

    def docs(self):
        dirs = [p.name.lower() for p in self.root.iterdir() if p.is_dir()]
        files = {p.name.lower() for p in self.root.iterdir() if p.is_file()}
        if "readme.md" not in files:
            self.add("docs", "medium", "README.md missing", ".", "No root README.md", "New developers and operators lack a canonical entry point.", "Add setup, architecture, local dev, deployment, troubleshooting and security notes.", ["documentation"])
        for required in [".env.example", "contributing.md", "security.md"]:
            if required not in files:
                sev = "low" if required != ".env.example" else "medium"
                self.add("docs", sev, f"{required} not found at repository root", ".", f"Missing {required}", "Operational knowledge may live only in individual developers' heads.", f"Add a concise {required} with project-specific guidance.", ["documentation"])
        if "docs" not in dirs and "documentation" not in dirs:
            self.add("docs", "low", "Dedicated documentation directory not detected", ".", "No docs/ or documentation/ directory", "Architecture decisions and operational runbooks become harder to discover.", "Create a small, indexed documentation area rather than duplicating README content.", ["documentation"])

    def dependency(self):
        markers = {"package.json": "node", "pyproject.toml": "python", "requirements.txt": "python", "poetry.lock": "python", "pnpm-lock.yaml": "node", "package-lock.json": "node", "yarn.lock": "node", "Cargo.toml": "rust", "go.mod": "go"}
        found = [m for m in markers if (self.root/m).exists()]
        self.stats["package_manifests"] = found
        if len([x for x in found if markers[x] == "node"]) > 1:
            self.add("dependencies", "medium", "Multiple Node package management manifests detected", ".", ", ".join(found), "Multiple lock/package managers can produce drift and inconsistent installs.", "Choose one authoritative package manager and document migration/compatibility files.", ["dependencies", "node"])
        if (self.root/"package.json").exists() and not (self.root/"pnpm-lock.yaml").exists() and "packageManager" in self.text(self.root/"package.json"):
            self.add("dependencies", "low", "Package manager is declared but lockfile is not detected", "package.json", "packageManager field exists without pnpm-lock.yaml", "Reproducibility and CI determinism can suffer.", "Commit the authoritative lockfile.", ["reproducibility"])

    def run(self, only: set[str] | None = None):
        jobs = {"security": self.security, "ci": self.ci, "code": self.code, "providers": self.providers, "docs": self.docs, "dependencies": self.dependency}
        for name, fn in jobs.items():
            if not only or name in only: fn()
        return self.findings

def md_report(root: Path, findings: list[Finding], stats: dict[str,Any]) -> str:
    sev = Counter(f.severity for f in findings)
    lines = ["# SupremeAI Gap Miner Report", "", f"Project: `{root}`", "", "## Executive scorecard", "", f"- Findings: **{len(findings)}**", f"- Critical: **{sev['critical']}**", f"- High: **{sev['high']}**", f"- Medium: **{sev['medium']}**", f"- Low: **{sev['low']}**", "", "## Priority findings", "", "| Severity | Category | Finding | Path | Score |", "|---|---|---|---|---:|"]
    for f in sorted(findings, key=lambda x: (-x.score, x.category, x.path))[:100]:
        lines.append(f"| {f.severity} | {f.category} | {f.title} | `{f.path}` | {f.score} |")
    lines += ["", "## Recommended order", "", "1. Critical security/secret exposure", "2. High-impact reliability and CI gaps", "3. Provider/quota/cache optimization", "4. Large-file and complexity reduction", "5. Documentation/operational gaps", "", "## Scanner telemetry", "", "```json", json.dumps(stats, indent=2, ensure_ascii=False), "```"]
    return "\n".join(lines)+"\n"

def main():
    ap = argparse.ArgumentParser(description="Read-only repository gap miner")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--format", choices=["json","md","both"], default="both")
    ap.add_argument("--out", default="reports/gap-miner")
    ap.add_argument("--only", help="comma-separated: security,ci,code,providers,docs,dependencies")
    ap.add_argument("--fail-on", choices=["critical","high","medium","low"], help="exit non-zero when findings at or above this severity exist")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    m = Miner(root)
    findings = m.run(set(args.only.split(',')) if args.only else None)
    payload = {"project": str(root), "summary": dict(Counter(f.severity for f in findings)), "findings": [asdict(f) for f in findings], "stats": m.stats}
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    if args.format in {"json","both"}: (out/"gap_report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.format in {"md","both"}: (out/"gap_report.md").write_text(md_report(root, findings, m.stats), encoding="utf-8")
    rank={"critical":4,"high":3,"medium":2,"low":1}
    if args.fail_on and any(rank[f.severity] >= rank[args.fail_on] for f in findings): return 2
    print(json.dumps(payload["summary"], indent=2))
    print(f"Report written to {out}")
    return 0

if __name__ == "__main__": raise SystemExit(main())
