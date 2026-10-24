#!/usr/bin/env python3
"""Rules Breaker Agent — Red Team / Pentest Scanner (#2574).

This agent proactively hunts for vulnerabilities and policy violations
in the SupremeAI codebase and opens GitHub issues for each finding.

Scope (audit-only, no code changes):
  1. Secret hardcoding / credential leaks
  2. Localhost / 127.0.0.1 / Windows-path binding in production code
  3. Unsafe privilege elevation / sudo / admin bypass patterns
  4. Silent exception swallowing (pass-only handlers)
  5. Missing backend authorization (client-side-only guards)
  6. Test manipulation (delete/skip/fake assertions)
  7. Direct main-branch push from bot
  8. Self-approval / self-merge patterns
  9. Missing 3-tier verification hooks
  10. Docs garbage (new .md outside allowlist)

Usage:
    python scripts/agents/rules_breaker.py --agent-name rules-breaker-1
    python scripts/agents/rules_breaker.py --agent-name rules-breaker-1 --limit 20
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

REPO = os.environ.get("GH_REPO", "SaifulHaqueNiloy/supremeai")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        **kwargs,
    )


def gh_issue_create(title: str, body: str, labels: list[str]) -> None:
    # বাংলা মন্যব্য (#3278): অনুপস্থিত লেবেলে gh issue create পুরোপুরি ব্যর্থ
    # করে (৩৩ security-finding silent-loss-এর কারণ)। তাই create-এর আগে
    # shared label-ensure — অনুপস্থিত লেবেল idempotently সৃষ্টি হয়।
    try:
        from agents.gh_label_ensure import ensure_labels
        labels = ensure_labels(labels)
    except Exception as exc:  # noqa: BLE001 — per-finding resilience: স্ক্যান থামবে না
        print(f"  ⚠️ label-ensure skipped: {exc}")
    cmd = [
        "gh", "issue", "create",
        "--repo", REPO,
        "--title", title,
        "--body", body,
    ]
    for label in labels:
        cmd.extend(["--label", label])
    res = run(cmd)
    if res.returncode == 0:
        print(f"  ✅ Created issue: {title}")
    else:
        print(f"  ❌ Failed to create issue: {res.stderr}")


# ============================================================================
# Scanner modules
# ============================================================================

def scan_secret_hardcoding(limit: int) -> list[dict]:
    """Detect hardcoded API keys, tokens, passwords, private keys."""
    findings = []
    patterns = [
        (r'(?i)(api_key|apikey|api_secret|secret_key|private_key|access_key)\s*[:=]\s*["\']([A-Za-z0-9_\-]{20,})["\']', "Hardcoded API key/secret"),
        (r'(?i)(password|passwd|pwd)\s*[:=]\s*["\'][^"\']{8,}["\']', "Hardcoded password"),
        (r'["\'](sk-[A-Za-z0-9]{20,})["\']', "Potential Stripe/OpenAI secret key"),
        (r'["\'](ghp_[A-Za-z0-9]{36})["\']', "Potential GitHub personal access token"),
        (r'["\'](AKIA[A-Z0-9]{16})["\']', "Potential AWS access key ID"),
        (r'["\']([0-9a-f]{32,})["\']', "Potential hardcoded hex token/secret"),
    ]
    exts = {".py", ".ts", ".js", ".json", ".yml", ".yaml", ".env", ".toml"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git", "backend/.venv",
                    "archives", "archive", "fixtures", "test_fixtures"}
    fixture_markers = ("fixture-", "test-token", "example-", "dummy-", "smoke@",
                       "placeholder", "test-pass", "fixture-pass", "fake-token")
    test_file_patterns = ("_test.py", "test_", "smoke_test", "production_smoke",
                          "conftest.py", "fixtures.py")

    files_scanned = 0
    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            if ".venv" in str(fpath) or "node_modules" in str(fpath):
                continue
            files_scanned += 1
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            scan_text = re.sub(r'""".*?"""', '""', text, flags=re.DOTALL)
            for pattern, desc in patterns:
                for m in re.finditer(pattern, scan_text):
                    matched_str = m.group(0).lower()
                    if any(marker in matched_str for marker in fixture_markers):
                        continue
                    line_start = scan_text.rfind("\n", 0, m.start()) + 1
                    line_end = scan_text.find("\n", m.end())
                    if line_end == -1: line_end = len(scan_text)
                    full_line = scan_text[line_start:line_end]
                    if "# noscan" in full_line:
                        continue
                    context_start = max(0, m.start() - 80)
                    context = scan_text[context_start:m.end() + 40]
                    if "getenv(" in context or "os.environ.get(" in context or "os.getenv(" in context:
                        continue
                    line_no = scan_text[:m.start()].count("\n") + 1
                    snippet = scan_text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
                    findings.append({
                        "file": str(fpath.relative_to(ROOT_DIR)),
                        "line": line_no,
                        "snippet": snippet,
                        "rule": "security.rule_002",
                        "severity": "BLOCK",
                        "description": f"[Secret Hardcoding] {desc} detected",
                    })
                    if len(findings) >= limit:
                        return findings
    return findings


# (P6, #3823) Line-level binding patterns (SSOT — scanner loop ও pure verdict
# helper একই tuple ব্যবহার করে, drift হয় না)।
_BINDING_PATTERNS = (
    (r'(?i)(localhost|127\.0\.0\.1|0\.0\.0\.0)', "Localhost/IP binding"),
    (r'(?i)(C:\\\\|D:\\\\|E:\\\\|/mnt/c/)', "Windows path binding"),
)

# (P6, #3823) Negation-context patterns: এই আকারের লাইনে localhost-token থাকে কিন্তু
# কোডটি আসলে localhost আপসাইন করে না — বরং localhost-কে EXCLUDE করে (যেমন CORS
# origin filter-এ `"localhost" not in o`)। সাবস্ট্রিং-ম্যাচিং এগুলোকে FP বানায় —
# #3727 (২০ FP) ও #3823-ফ্লাড (৬২ FP) এই একই ক্লাসের পুনরাবৃত্তি।
_NEGATION_CONTEXT_RE = re.compile(
    r"""(?ix)
    ['"](?:localhost|127\.0\.0\.1|0\.0\.0\.0)['"]\s*(?:not\s+in\b|is\s+not\b|!=)   # "localhost" not in x
    | (?:not\s+in\b|!=)\s*['"][^'"]*(?:localhost|127\.0\.0\.1|0\.0\.0\.0)['"]       # not in "...localhost..."
    | \bNO\s+(?:localhost|127\.0\.0\.1|0\.0\.0\.0)\b                                  # doc: "NO localhost/placeholder"
    """
)

# (P6, #3823) shell env-default idiom — `${DB_HOST:-localhost}` = env-driven host,
# hardcode নয় (apply_tier_patch.py docker-compose ENV ব্লক)।
_SHELL_DEFAULT_RE = re.compile(r"\$\{[^}]*:-(?:localhost|127\.0\.0\.1|0\.0\.0\.0)", re.I)

# (P6, #3823) scanner self-exclusion — detector নিজের সোর্স (pattern/docstring/usage
# text-এ localhost-স্ট্রিং থাকে) কখনো ফ্ল্যাগ করবে না।
_SELF_FILE = "rules_breaker.py"


def _line_is_localhost_binding(line: str) -> bool:
    """Line-level localhost/Windows-binding verdict (pure; regression-tested).

    True = real binding-shaped hit; False = comment/negation/self/tooling FP.
    """
    if line.strip().startswith("#"):
        return False
    if "is_local()" in line:  # fleet marker; `# is_local()` এবং `# test-only is_local()` দুটোই valid
        return False
    if any(kw in line for kw in ["getenv(", "os.environ.get(", "os.getenv(",
                                 "setdefault(", "help=", "default=",
                                 '"pattern"', "'pattern'", 'severity',
                                 're.compile', 'LOCALHOST_URL_RE']):
        return False
    if _NEGATION_CONTEXT_RE.search(line):
        return False
    if _SHELL_DEFAULT_RE.search(line):
        return False
    return any(re.search(pattern, line) for pattern, _ in _BINDING_PATTERNS)


def scan_localhost_binding(limit: int) -> list[dict]:
    """Detect actual localhost/127.0.0.1/Windows-path binding outside tests.

    #3823 (P6): negation-context + self-file + load-tooling exclusions added —
    the naive substring match was flagging localhost-EXCLUDING filters and the
    scanner's own source, spawning the 62-issue FP flood.
    """
    findings = []
    exts = {".py", ".ts", ".js", ".json"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git", "tests", "test",
                    "archives", "archive", "fixtures", "test_fixtures",
                    "k6", "loadtest", "benchmarks"}
    test_file_patterns = ("_test.py", "test_", "smoke_test", "production_smoke",
                          "conftest.py", "fixtures.py", "load_test", "benchmark")

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            fname_lower = fname.lower()
            if any(pat in fname_lower for pat in test_file_patterns):
                continue
            if fname_lower == _SELF_FILE:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                if not _line_is_localhost_binding(line):
                    continue
                desc = next(d for p, d in _BINDING_PATTERNS if re.search(p, line))
                findings.append({
                    "file": str(fpath.relative_to(ROOT_DIR)),
                    "line": i,
                    "snippet": line.strip()[:120],
                    "rule": "architecture.rule_001",
                    "severity": "BLOCK",
                    "description": f"[Localhost/Windows Binding] {desc} in production code",
                })
                if len(findings) >= limit:
                    return findings
    return findings


# (P6, #3774) Render service-ID regex (SSOT — scan + test একই আকৃতি ব্যবহার করে)।
# Render ID আকৃতি: srv- + 20 lowercase alphanumeric (যেমন srv-da666f8u01pc739bm3t0)।
_RENDER_SERVICE_ID_RE = re.compile(r"srv-[a-z0-9]{12,}")

# এই ফাইলগুলোতে ID-প্যাটার্ন থাকা বৈধ (scanner নিজের সোর্স + regression tests)।
_SERVICE_ID_ALLOWED_PREFIXES = ("scripts/agents/rules_breaker.py", "tests/")


def scan_render_service_ids(limit: int, root: Path | None = None) -> list[dict]:
    """Detect hardcoded Render service IDs in public deploy tooling (#3774).

    Service IDs are identifiers, not credentials (Render API still needs
    RENDER_API_KEY) — কিন্তু public repo-তে এরা production topology প্রকাশ করে
    (roadmap §8: private-plane material)। সব ID env থেকে আসবে:
    RENDER_SERVICE_ID / RENDER_IMAGE_SERVICE_ID — fallback hardcoded নিষিদ্ধ।
    Scope (#4091 — detector scope এখন পুরো ক্লাস-সারফেস): scripts/deploy/** +
    .github/scripts/** + infrastructure/** + root Dockerfile। #3774-পরবর্তী
    লাইভ-প্রমাণ: ৮টি hardcoded srv- ID গেট-স্কোপের বাইরে .github/scripts ও
    mcp-control-plane TS-এ টিকে ছিল — scope < surface ক্লাস-ত্রুটি।
    কমেন্ট-লাইনও ফ্ল্যাগ হয় — comment-এ লাইভ ID থাকলেও topology লিক হয়
    (Dockerfile কেস, #3774)।
    """
    findings = []
    scan_root = root if root is not None else ROOT_DIR
    targets: list[Path] = []
    scanned_suffixes = {
        ".py", ".ts", ".js", ".json", ".sh", ".yml", ".yaml", ".toml",
    }
    # (#4091) topology-bearing ডিরেক্ট্রি-সারফেস — প্রতিটি recursive:
    for rel_dir in ("scripts/deploy", ".github/scripts", "infrastructure"):
        base = scan_root / rel_dir
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in scanned_suffixes:
                continue
            # node_modules/ বাদ — vendored ট্রি এই গেটের সারফেস নয় (mcp-control-plane কেস)
            if "node_modules" in f.parts:
                continue
            targets.append(f)
    dockerfile = scan_root / "Dockerfile"
    if dockerfile.is_file():
        targets.append(dockerfile)

    for fpath in targets:
        rel = str(fpath.relative_to(scan_root)).replace(os.sep, "/")
        if any(rel == a or rel.startswith(a) for a in _SERVICE_ID_ALLOWED_PREFIXES):
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            if _RENDER_SERVICE_ID_RE.search(line):
                findings.append({
                    "file": rel,
                    "line": i,
                    "snippet": line.strip()[:120],
                    "rule": "security.rule_001",
                    "severity": "WARN",
                    "description": "[Topology Disclosure] Hardcoded Render service ID — move to env (RENDER_SERVICE_ID) per #3774",
                })
                if len(findings) >= limit:
                    return findings
    return findings


def scan_silent_failures(limit: int) -> list[dict]:
    """Detect pass-only exception handlers."""
    findings = []
    exts = {".py"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if re.match(r'^\s*except\b.*:\s*$', line):
                    # Check if next non-empty line is just 'pass'
                    j = i
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if next_line and not next_line.startswith("#"):
                            if next_line == "pass":
                                findings.append({
                                    "file": str(fpath.relative_to(ROOT_DIR)),
                                    "line": i,
                                    "snippet": line.strip()[:120],
                                    "rule": "reliability.rule_001",
                                    "severity": "BLOCK",
                                    "description": "Silent failure: bare except with pass-only handler",
                                })
                                if len(findings) >= limit:
                                    return findings
                            break
                        j += 1
    return findings


def scan_test_manipulation(limit: int) -> list[dict]:
    """Detect test delete/skip/fake assertion patterns."""
    findings = []
    patterns = [
        (r'@pytest\.mark\.skip', "pytest skip decorator"),
        (r'@pytest\.mark\.xfail', "pytest xfail decorator"),
        (r'def test_[^()]*\(.*\):\s*pass\s*$', "Empty test body (pass only)"),
        (r'assert\s+False\s*#', "Fake assertion"),
        (r'#\s*TODO.*test', "Skipped test TODO"),
    ]
    exts = {".py"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if "test" not in fpath.name.lower() and fpath.suffix.lower() != ".py":
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "gates.test_guard_gate",
                            "severity": "BLOCK",
                            "description": f"[Test Manipulation] {desc}",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


def scan_docs_garbage(limit: int) -> list[dict]:
    """Detect new .md docs outside allowlist."""
    findings = []
    allowed = {
        "docs/master_docs", "docs/agents", "docs/architecture", "docs/archive",
        "docs/governance", "docs/INDEX.md", "docs/ROADMAP.md",
    }
    for fpath in ROOT_DIR.rglob("*.md"):
        rel = str(fpath.relative_to(ROOT_DIR))
        if any(rel.startswith(a) for a in allowed):
            continue
        if ".venv" in rel or "node_modules" in rel or ".git" in rel:
            continue
        # Flag non-canonical docs
        findings.append({
            "file": rel,
            "line": 1,
            "snippet": rel,
            "rule": "gates.docs_garbage",
            "severity": "WARN",
            "description": "Docs garbage: .md file outside canonical allowlist",
        })
        if len(findings) >= limit:
            return findings
    return findings


def scan_privilege_elevation(limit: int) -> list[dict]:
    """Detect sudo/admin privilege elevation patterns."""
    findings = []
    patterns = [
        (r'(?i)(sudo\s+|runas\s+|elevat\w*\s*\(|ShellExecute.*runas|admin.*privilege|setuid|seteuid)', "Privilege elevation"),
    ]
    exts = {".py", ".ts", ".js", ".ps1", ".sh", ".bat", ".cmd"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                if line.strip().startswith("#"):
                    continue
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "security.rule_003",
                            "severity": "BLOCK",
                            "description": f"[Privilege Elevation] {desc} pattern detected",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


def scan_client_side_auth(limit: int) -> list[dict]:
    """Detect client-side-only authorization patterns."""
    findings = []
    patterns = [
        (r'(?i)(if\s*\(.*role\s*==|if\s*\(.*isAdmin|if\s*\(.*isLoggedIn|window\.location\.replace.*login)', "Client-side auth check"),
    ]
    exts = {".ts", ".tsx", ".js", ".jsx"}
    exclude_dirs = {"node_modules", "__pycache__", ".git", ".venv"}

    for root, dirs, files in os.walk(ROOT_DIR / "frontend"):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "security.rule_001",
                            "severity": "WARN",
                            "description": f"[Client-Side Auth] {desc} — backend enforcement missing?",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


# ============================================================================
# Attack simulation modules (safe, read-only probes)
# ============================================================================

def probe_sql_injection_patterns(limit: int) -> list[dict]:
    """Look for raw SQL string concatenation or f-string SQL."""
    findings = []
    patterns = [
        (r'(?i)(execute|executemany|cursor\.execute)\s*\(.*f["\']', "f-string SQL execution"),
        (r'(?i)(execute|executemany)\s*\(.*\+.*\+', "String-concatenated SQL"),
        (r'(?i)SELECT.*FROM.*WHERE.*\+', "Concatenated WHERE clause"),
    ]
    exts = {".py"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                if line.strip().startswith("#"):
                    continue
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "security.rule_001",
                            "severity": "BLOCK",
                            "description": f"[SQL Injection Risk] {desc} — parameterized queries required",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


def probe_path_traversal_patterns(limit: int) -> list[dict]:
    """Look for unsanitized file path joins with user input."""
    findings = []
    patterns = [
        (r'(?i)(os\.path\.join|Path\().*request\.(args|params|query|body|form)', "User input in path join"),
        (r'(?i)(open|Path)\(.*\+.*request', "User input in file open"),
    ]
    exts = {".py", ".ts", ".js"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "security.rule_001",
                            "severity": "BLOCK",
                            "description": f"[Path Traversal Risk] {desc} — sanitize paths before join/open",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


def probe_xss_patterns(limit: int) -> list[dict]:
    """Look for unsafe innerHTML / dangerouslySetInnerHTML without sanitization."""
    findings = []
    patterns = [
        (r'(?i)(innerHTML\s*=|dangerouslySetInnerHTML)', "Unsafe HTML injection"),
        (r'(?i)(\.html\(.*request\.|\.html\(.*user)', "User-controlled HTML rendering"),
    ]
    exts = {".ts", ".tsx", ".js", ".jsx"}
    exclude_dirs = {"node_modules", "__pycache__", ".git", ".venv"}

    for root, dirs, files in os.walk(ROOT_DIR / "frontend"):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "security.rule_001",
                            "severity": "WARN",
                            "description": f"[XSS Risk] {desc} — sanitize before rendering",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


def probe_auth_bypass(limit: int) -> list[dict]:
    """Look for missing auth decorators on sensitive routes."""
    findings = []
    patterns = [
        (r'@app\.(get|post|put|delete|patch)\s*\(.*\)\s*\n\s*def\s+\w+\(', "Missing auth decorator on route"),
    ]
    exts = {".py"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR / "backend"):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for pattern, desc in patterns:
                for m in re.finditer(pattern, text):
                    line_no = text[:m.start()].count("\n") + 1
                    route_line = text[m.start():m.end()].splitlines()[0]
                    findings.append({
                        "file": str(fpath.relative_to(ROOT_DIR)),
                        "line": line_no,
                        "snippet": route_line.strip()[:120],
                        "rule": "security.rule_001",
                        "severity": "BLOCK",
                        "description": f"[Auth Bypass Risk] {desc} — ensure backend auth enforced",
                    })
                    if len(findings) >= limit:
                        return findings
    return findings


def probe_insecure_deserialization(limit: int) -> list[dict]:
    """Look for pickle.loads / yaml.load / eval on untrusted input."""
    findings = []
    patterns = [
        (r'(?i)(pickle\.loads?|yaml\.load\(.*Loader=None|eval\(|exec\(|compile\(.*input)', "Insecure deserialization/eval"),
    ]
    exts = {".py", ".ts", ".js"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                if line.strip().startswith("#"):
                    continue
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "security.rule_003",
                            "severity": "BLOCK",
                            "description": f"[Insecure Deserialization] {desc} — use safe alternatives",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


def probe_cors_misconfiguration(limit: int) -> list[dict]:
    """Look for overly permissive CORS (allow_all origins)."""
    findings = []
    patterns = [
        (r'(?i)(allow_origins\s*=\s*\["\*"\]|allow_all|Access-Control-Allow-Origin.*\*)', "Permissive CORS"),
    ]
    exts = {".py", ".ts", ".js"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "security.rule_001",
                            "severity": "WARN",
                            "description": f"[CORS Misconfiguration] {desc} — restrict origins explicitly",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


def probe_log_injection(limit: int) -> list[dict]:
    """Look for unsanitized user input in log/print statements."""
    findings = []
    patterns = [
        (r'(?i)(print\(.*request\.|logger\.(info|debug|warn|error)\(.*request\.|logging\.\w+\(.*request\.)', "User input in log/print"),
    ]
    exts = {".py", ".ts", ".js"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "reliability.rule_002",
                            "severity": "WARN",
                            "description": f"[Log Injection] {desc} — sanitize before logging",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


def probe_self_merge_patterns(limit: int) -> list[dict]:
    """Look for self-approval or self-merge in automation scripts."""
    findings = []
    patterns = [
        (r'(?i)(self_merge|self-merge|self_approv|approve.*own|merge.*own)', "Self-merge/approve pattern"),
    ]
    exts = {".py", ".sh", ".yml", ".yaml"}
    exclude_dirs = {".venv", "node_modules", "__pycache__", ".git"}

    for root, dirs, files in os.walk(ROOT_DIR):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for fname in files:
            fpath = Path(root) / fname
            if fpath.suffix.lower() not in exts:
                continue
            try:
                text = fpath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                if line.strip().startswith("#"):
                    continue
                for pattern, desc in patterns:
                    if re.search(pattern, line):
                        findings.append({
                            "file": str(fpath.relative_to(ROOT_DIR)),
                            "line": i,
                            "snippet": line.strip()[:120],
                            "rule": "gates.self_merge_gate",
                            "severity": "BLOCK",
                            "description": f"[Self-Merge Risk] {desc} — prohibited by constitution",
                        })
                        if len(findings) >= limit:
                            return findings
    return findings


# ============================================================================
# Issue creation
# ============================================================================

# বাংলা মন্যব্য (#3278): scanner-severity → রিপোর canonical priority-label ম্যাপিং।
# আগে `severity:{sev}` লেবেল পোস্ট হতো — রিপোতে সেটা নেই (create-মৃত্যুর একটি
# কারণ), এবং priority-taxonomy-ও ভাঙে। এখন বিদ্যমান P-label-এ ম্যাপ।
_FINDING_SEVERITY_TO_PRIORITY = {
    "BLOCK": "P1-high",
    "WARN": "P2-medium",
    "INFO": "P3-low",
}

# বাংলা মন্যব্য (#3278): লেবেল-সেট canonical-taxonomy-তে — dispatcher-এর
# AREA_TO_ROLE/TYPE_TO_ROLE ম্যাপ এগুলো চেনে; সব লেবেল রিপোতে বিদ্যমান।
_FINDING_LABELS_BASE = ["type:security", "area:security", "handoff:coder", "status:unclaimed"]


def build_finding_issue(f: dict, scan_type: str, agent_name: str) -> tuple[str, str, list[str]]:
    """(#3278) Finding → (title, body, labels) — template-compliant ও canonical।

    আগে: টাইটেল `[scan] 🔴 SEV — ...` (title-convention ভাঙে), body-তে
    Mission/Priority/Touching Files/Verification সেকশন নেই (Template Guard
    `template:violating` দিত → unclaimable), লেবেল `vulnerability`/`severity:*`
    (রিপোতে নেই → create-ই মৃত)। এখন: `fix(security): ...` টাইটেল,
    চার-সেকশন চুক্তি-body, বিদ্যমান canonical লেবেল + severity→P-label।
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    priority = _FINDING_SEVERITY_TO_PRIORITY.get(f["severity"], "P2-medium")
    title = f"fix(security): {f['description']} ({f['file']}:{f['line']})"
    body = f"""### Mission & Problem Statement
Rules Breaker স্ক্যানে (`{scan_type}`) নিচের নিরাপত্তা-ফাইন্ডিং ধরা পড়েছে —
constitutional rule `{f['rule']}` লঙ্ঘিত। ফাইন্ডিং-ডিটেইল:

| Field | Value |
| :--- | :--- |
| **Scan Type** | `{scan_type}` |
| **Severity** | `{f['severity']}` (→ {priority}) |
| **Rule Violated** | `{f['rule']}` |
| **File** | `{f['file']}` |
| **Line** | `{f['line']}` |
| **Snippet** | `{f['snippet']}` |
| **Detected By** | `{agent_name}` (rules_breaker) |
| **Scan Time** | `{now}` |

**Description:** {f['description']}

### Priority Tier
{priority} — severity `{f['severity']}` থেকে ম্যাপড (BLOCK→P1, WARN→P2, INFO→P3)।

### Touching Files (Scope Gate Boundary)
- `{f['file']}`

### 3-Tier Verification Contract
1. **Reflection:** `git grep -n "{f['snippet'][:40]}" {f['file']}` — ফাইন্ডিং-স্নিপেট অপসারণ/সংশোধন নিশ্চিত।
2. **Syntax/Boot:** পরিবর্তিত ফাইল syntax-যাচাই (ভাষা-অনুযায়ী parse/lint)।
3. **Tests:** সংশ্লিষ্ট মডিউলের test-suite সবুজ + নতুন regression-test (ফাইন্ডিং-প্যাটার্টার্ন আর ধরা না পড়ে)।

---
_Auto-generated by `rules_breaker.py` — Red Team Pentest Agent (#3278 funnel-revival)_
"""
    labels = _FINDING_LABELS_BASE + [priority]
    return title, body, labels


def create_issue_for_finding(f: dict, scan_type: str, agent_name: str) -> None:
    """বাংলা (#3863): Team Leader pattern — scanner no longer creates issues directly.

    এই ফাংশন এখন একটা delegation report তৈরি করে — সরাসরি gh issue create
    call করে না। Scanner শুধু findings collect করে এবং একটা consolidated
    audit directive JSON-এ লেখে। Auditor agent সেই directive থেকে validated
    issues তৈরি করবে।
    """
    title, body, labels = build_finding_issue(f, scan_type, agent_name)
    # বাংলা (#3863): direct gh_issue_create disabled — Team Leader pattern.
    # Instead: collect into report, let auditor agent verify + create.
    _findings_report.append({
        "scan_type": scan_type,
        "agent_name": agent_name,
        "title": title,
        "body": body,
        "labels": labels,
        "file": f.get("file", ""),
        "line": f.get("line", 0),
        "snippet": f.get("snippet", ""),
    })


# বাংলা (#3863): global findings report — scanner collects here, doesn't create issues.
_findings_report: list[dict] = []


def get_findings_report() -> list[dict]:
    """Return collected findings (Team Leader pattern — no direct issue creation)."""
    return _findings_report


def clear_findings_report() -> None:
    """Clear the findings report (for next scan run)."""
    _findings_report.clear()


def write_findings_report(path: str = "/tmp/rules_breaker_findings.json") -> int:
    """Write findings to JSON file for auditor agent to consume.

    বাংলা (#3863): Scanner = Team Leader. সে নিজে issue create করে না।
    সে শুধু findings report লেখে → auditor agent সেটা read করে →
    validate করে → প্রয়োজনে issue create করে।
    """
    import json as _json
    import os
    if not _findings_report:
        return 0
    report = {
        "scan_time": _json.dumps({"ts": str(__import__("datetime").datetime.utcnow())}),
        "total_findings": len(_findings_report),
        "findings": _findings_report,
        "directive": (
            "Scanner completed audit. Auditor agent: please review each finding, "
            "filter false-positives (scanner's own regex patterns, test fixtures, "
            "offline configs), and create a single consolidated issue per real "
            "finding — not per raw regex match."
        ),
    }
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        _json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"📋 Findings report written: {path} ({len(_findings_report)} findings)")
    print(f"   Directive: auditor agent should review + create issues.")
    return len(_findings_report)


def run_scans(limit: int, agent_name: str) -> None:
    scanners = [
        ("secret-hardcoding", scan_secret_hardcoding),
        ("localhost-binding", scan_localhost_binding),
        ("render-service-id", scan_render_service_ids),
        ("silent-failures", scan_silent_failures),
        ("test-manipulation", scan_test_manipulation),
        ("docs-garbage", scan_docs_garbage),
        ("privilege-elevation", scan_privilege_elevation),
        ("client-side-auth", scan_client_side_auth),
        ("sql-injection", probe_sql_injection_patterns),
        ("path-traversal", probe_path_traversal_patterns),
        ("xss-risk", probe_xss_patterns),
        ("auth-bypass", probe_auth_bypass),
        ("insecure-deserialization", probe_insecure_deserialization),
        ("cors-misconfig", probe_cors_misconfiguration),
        ("log-injection", probe_log_injection),
        ("self-merge", probe_self_merge_patterns),
    ]

    total_findings = 0
    print(f"🔴 Starting Rules Breaker scan: agent={agent_name}, limit={limit}")
    print(f"   Scanners: {len(scanners)}")
    print()

    for scan_name, scanner in scanners:
        findings = scanner(limit)
        if not findings:
            print(f"  ✅ {scan_name}: clean")
            continue
        print(f"  ⚠️  {scan_name}: {len(findings)} finding(s)")
        for f in findings:
            create_issue_for_finding(f, scan_name, agent_name)
            total_findings += 1
            if total_findings >= limit:
                print(f"\n🛑 Reached limit of {limit} issues. Stopping.")
                return

    print(f"\n✅ Scan complete. Total findings collected: {total_findings}")
    # বাংলা (#3863): write findings report — auditor agent will review + create issues.
    write_findings_report()


def main() -> int:
    parser = argparse.ArgumentParser(description="Rules Breaker Agent — Red Team Pentest Scanner")
    parser.add_argument("--agent-name", required=True, help="Agent identifier (e.g. rules-breaker-1)")
    parser.add_argument("--limit", type=int, default=20, help="Max issues to create per run")
    args = parser.parse_args()

    run_scans(args.limit, args.agent_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
