#!/usr/bin/env python3
"""বাংলা মন্তব্য: SupremeAI Learned-Regression Scanner (regression_scanner.py)

উদ্দেশ্য: এই স্ক্রিপ্ট generic bug pattern খোঁজে না (সেটা scripts/quality/self_audit_scan.py
আগে থেকেই করে) — এটা খুঁজে বের করে সেই নির্দিষ্ট bug-class গুলো যেগুলো এই প্রজেক্টে
*বাস্তবে বারবার ফিরে এসেছে*, একাধিক audit সেশন জুড়ে। প্রতিটা চেক একটা রিয়েল, আগে-পাওয়া
production bug থেকে শেখা — অনুমান না, ইতিহাস। যতবার নতুন কোড যোগ হবে, একই ভুল প্যাটার্ন
আবার ঘটার সম্ভাবনা থাকে (অন্য session/bot commit করলেও) — এই স্ক্যানার সেটা ধরে।

Zero-Cost নীতি মেনে: শুধু stdlib (ast, re, pathlib) ব্যবহার করে, কোনো external dependency
বা network call ছাড়াই চলে। CI-তে এবং pre-push hook উভয় জায়গায় ব্যবহারযোগ্য।

চেক করা bug classes (প্রতিটার পাশে যে audit-এ প্রথম পাওয়া গিয়েছিল তার নোট):
  1. auth-fallback-bypass  — is_test_environment()-guarded ব্লকের বাইরে unconditional
                              admin/privileged credential return (rbac.py, 2026-08-26)
  2. unguarded-localhost   — redis://localhost বা 127.0.0.1 fallback settings.env=="local"
                              guard ছাড়া (একাধিক ফাইলে বারবার, 2026-08-07 থেকে চলমান)
  3. yield-bare-return     — pytest fixture-এ yield-এর ঠিক পরে bare `return`, যা teardown
                              কোড unreachable করে দেয় (8+ ফাইলে পাওয়া গিয়েছিল, 2026-07 saga)
  4. dual-module-identity  — same basename বিভিন্ন directory-তে (config.py, llm_gateway.py,
                              evolution/) — secret_vault/honeypot_middleware bug-এর মূল কারণ
  5. hardcoded-render-id   — CI YAML-এ literal srv-xxxxxxxx Render service ID (আগে বারবার
                              hardcode হয়ে গিয়েছিল, principle অনুযায়ী নিষিদ্ধ)
  6. ssl-verify-bypass     — ssl.CERT_NONE বা verify=False (23834c8 regression)
  7. hardcoded-secret      — literal API key/secret/password/token pattern কোডে
  8. cors-wildcard         — allow_origins=["*"] with allow_credentials=True (silent security hole)
  9. bare-except-pass      — সম্পূর্ণ silent exception swallow (observability audit gap)

ব্যবহার:
    python3 scripts/quality/regression_scanner.py [--path .] [--json report.json] [--fail-on critical,high]

Exit code: 1 যদি --fail-on এ উল্লেখিত severity-র কোনো finding থাকে, নাহলে 0।
"""

import argparse
import ast
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Fix Windows cp1252 charmap encode issues for UTF-8 / Bengali strings
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    except Exception as e:
        _ = e

SKIP_DIRS = {
    "node_modules",
    ".git",
    "venv",
    "__pycache__",
    ".venv",
    "archive",
    "_archive",
    "dist",
    "build",
    ".turbo",
    ".pytest_cache",
    "coverage",
    ".mypy_cache",
    ".ruff_cache",
    ".venv_ci",
    ".kilo",
    "scratch",
}

SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1, "low": 0}


@dataclass
class Finding:
    check: str
    severity: str
    file: str
    line: int
    message: str


@dataclass
class Report:
    findings: list = field(default_factory=list)

    def add(self, check: str, severity: str, file: str, line: int, message: str) -> None:
        self.findings.append(Finding(check, severity, str(file), line, message))

    def by_severity(self, sev: str) -> list:
        return [f for f in self.findings if f.severity == sev]


def iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts) or p.name == "regression_scanner.py":
            continue
        yield p


def iter_all_source_files(root: Path):
    exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".yml", ".yaml"}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts and not any(part in SKIP_DIRS for part in p.parts):
            if p.name == "regression_scanner.py":
                continue
            yield p


# ── Check 1: auth-fallback-bypass ──────────────────────────────────────────
# প্যাটার্ন: try/if is_test_environment() ব্লকের ভেতরে early-return আছে, কিন্তু তার
# ঠিক নিচে (একই ফাংশনের শেষে, except/if ব্লকের বাইরে) আরেকটা unconditional return আছে
# যেটাও admin/privileged role ফেরত দেয় — মানে non-test path-এও একই জিনিস ফেরত যাচ্ছে।
AUTH_KEYWORDS = re.compile(
    r'"role"\s*:\s*"admin"|role\s*=\s*"admin"|is_admin\s*=\s*True', re.IGNORECASE
)


def check_auth_fallback_bypass(root: Path, report: Report) -> None:
    for path in iter_py_files(root):
        try:
            src = path.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(src)
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            func_src = ast.get_source_segment(src, node) or ""
            if "is_test_environment" not in func_src:
                continue
            if not AUTH_KEYWORDS.search(func_src):
                continue

            # খুঁজি: is_test_environment() চেকের বাইরে (guard clause ছাড়া) admin-sদৃশ
            # return আছে কিনা — অর্থাৎ ফাংশনের শেষ statement যদি unconditional return
            # হয় এবং তাতে admin keyword থাকে, আর তার আগে কোনো guaranteed raise/return
            # না থাকে সব branch-এ (crude but effective heuristic)।
            last_stmt = node.body[-1] if node.body else None
            guarded_return_found = False
            unconditional_admin_return = False

            for stmt in ast.walk(node):
                if isinstance(stmt, ast.If):
                    test_src = ast.get_source_segment(src, stmt.test) or ""
                    if "is_test_environment" in test_src:
                        guarded_return_found = True

            if isinstance(last_stmt, ast.Return):
                ret_src = ast.get_source_segment(src, last_stmt) or ""
                if AUTH_KEYWORDS.search(ret_src):
                    unconditional_admin_return = True

            # যদি guarded early-return থাকে (is_test_environment ভেতরে) কিন্তু ফাংশনের
            # শেষেও raise/HTTPException ছাড়াই আরেকটা admin-sদৃশ return থাকে -> সন্দেহজনক
            has_raise_or_401 = (
                "raise" in func_src or "401" in func_src or "HTTPException" in func_src
            )
            if (
                guarded_return_found
                and unconditional_admin_return
                and not (
                    has_raise_or_401
                    and func_src.rfind("raise") > func_src.find("is_test_environment")
                )
            ):
                report.add(
                    "auth-fallback-bypass",
                    "critical",
                    path,
                    last_stmt.lineno,
                    f"ফাংশন '{node.name}': is_test_environment() guard-এর বাইরেও admin/privileged "
                    f"return পাওয়া গেছে, কোনো raise/401 ছাড়াই — production-এ auth bypass হতে পারে। "
                    f"(rbac.py 2026-08-26 regression-এর একই প্যাটার্ন)",
                )


# ── Check 2: unguarded-localhost ────────────────────────────────────────────
LOCALHOST_URL_RE = re.compile(
    r"(redis://localhost|redis://127\.0\.0\.1|bolt://localhost|bolt://127\.0\.0\.1|"
    r"ws://localhost|ws://127\.0\.0\.1|http://localhost|http://127\.0\.0\.1)"
)
BARE_LOCALHOST_RE = re.compile(r"127\.0\.0\.1")
LOCAL_GUARD_RE = re.compile(
    r'env\s*==\s*["\']local["\']|environment\s*==\s*["\']local["\']|is_local\(\)'
)
# bare "127.0.0.1" used as a fallback DEFAULT for an ip/client-ip style parameter or
# variable (rate-limiting/logging bookkeeping) is not a connection-host fallback —
# e.g. `ip_address: str = "127.0.0.1"`, `client_ip: str = "127.0.0.1"`,
# `client_ip = request.client.host if request.client else "127.0.0.1"`.
# Only exclude when the surrounding name clearly refers to an IP/client address,
# never when it refers to a host/url/dsn/broker/endpoint.
IP_BOOKKEEPING_DEFAULT_RE = re.compile(
    r"\b\w*(?:client_ip|ip_address|remote_ip|\bip)\w*\s*:?\s*(?:str\s*)?="
    r'(?:[^=\n]*\belse\b)?[^=\n]*["\']127\.0\.0\.1["\']',
    re.IGNORECASE,
)
HOST_LIKE_NAME_RE = re.compile(
    r"\b\w*(?:host|url|dsn|broker|uri|endpoint|redis|bolt)\w*\s*[:=]",
    re.IGNORECASE,
)
# BIND targets (serve/listen) are the security-correct direction: binding a
# local server/DevTools port to loopback is how you AVOID exposing it — the
# unguarded-localhost rule targets CONNECT fallbacks that would silently hit
# the wrong host in production. Names like AUTOMATION_BIND_ADDRESS (Chrome
# --remote-debugging-address) are listen addresses, never connect hosts.
BIND_TARGET_NAME_RE = re.compile(r"\b\w*bind\w*\s*[:=]", re.IGNORECASE)


def check_unguarded_localhost(root: Path, report: Report) -> None:
    for path in iter_py_files(root):
        if "/tests/" in str(path) or path.name.startswith("test_"):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except UnicodeDecodeError:
            continue

        # Deny-list containers (e.g. the SSRF `_BLOCKED_HOSTS` set) *declare*
        # loopback hostnames in order to REJECT them — the opposite of an
        # unguarded fallback. Track the enclosing assignment name.
        container_stack: list[str] = []
        in_doc: bool = False
        triple_a, triple_b = '"""', "'''"

        for i, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Docstring/comment lines document behaviour — they are not
            # runtime host fallbacks (e.g. "bolt://localhost:7687" inside a
            # comment explaining the absence of one).
            triple_count = line.count(triple_a) + line.count(triple_b)
            if in_doc:
                if triple_count % 2 == 1:
                    in_doc = False
                continue
            if stripped.startswith((triple_a, triple_b)):
                # FIX: any line that IS docstring content — a complete
                # single-liner ("""...127.0.0.1...""", triple_count == 2)
                # or the opening line of a multi-line doc — documents
                # behaviour and is never a runtime host fallback. Previously
                # single-liner docstrings fell through to the code scan and
                # produced HIGH false positives (e.g. browser/session_manager
                # chrome_launch_args docstring mentioning the loopback bind).
                if triple_count % 2 == 1:
                    in_doc = True
                continue
            if stripped.startswith("#"):
                continue
            if triple_count % 2 == 1:
                in_doc = True
                line = line.split(triple_a)[0].split(triple_b)[0]
                stripped = line.strip()
                if not stripped:
                    continue

            # Track simple top-level assignments so set/dict members of a
            # *_BLOCKED* container are recognized (deny-list, not fallback).
            assign = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*[:=]", stripped)
            if assign and not stripped.endswith((",", ")", "]")):
                container_stack.append(assign.group(1))
            elif stripped in (")", "]", "}"):
                if container_stack:
                    container_stack.pop()

            is_url_form = LOCALHOST_URL_RE.search(line)
            is_bare = BARE_LOCALHOST_RE.search(line)
            if not is_url_form and not is_bare:
                continue

            if any("_BLOCKED" in name.upper() for name in container_stack):
                # Member of a deny-list container: loopback here IS the
                # enforcement, never an endpoint.
                continue

            if not is_url_form and is_bare:
                # bare 127.0.0.1: skip if it's clearly an IP-bookkeeping default
                # (not a host/url/dsn/broker fallback)
                if IP_BOOKKEEPING_DEFAULT_RE.search(line) and not HOST_LIKE_NAME_RE.search(line):
                    continue
                # bare 127.0.0.1 assigned to a BIND-target name is a listen
                # address (loopback-only by design) — not a connect fallback
                if BIND_TARGET_NAME_RE.search(line):
                    continue

            # আশেপাশের ৬ লাইনে local-env guard আছে কিনা দেখি
            window = "\n".join(lines[max(0, i - 6) : min(len(lines), i + 2)])
            if LOCAL_GUARD_RE.search(window):
                continue
            report.add(
                "unguarded-localhost",
                "high",
                path,
                i,
                "settings.env=='local' guard ছাড়া localhost/127.0.0.1 fallback — production-এ "
                "silently ভুল হোস্টে connect হবে বা crash করবে (established repo idiom: শুধু "
                "local env-এ fallback, নাহলে raise/log error)।",
            )


# ── Check 3: yield-bare-return ──────────────────────────────────────────────
def check_yield_bare_return(root: Path, report: Report) -> None:
    test_dirs_hint = ("test", "conftest")
    for path in iter_py_files(root):
        if not any(h in path.name for h in test_dirs_hint) and "/tests/" not in str(path):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except UnicodeDecodeError:
            continue

        for i, line in enumerate(lines):
            if line.strip() == "yield":
                # পরের non-empty লাইন bare return কিনা, এবং তারপরে আরও কোড আছে কিনা (unreachable)
                j = i + 1
                if j < len(lines) and lines[j].strip() == "return":
                    [l for l in lines[j + 1 :] if l.strip() and not l.strip().startswith("#")]
                    # পরের def/class শুরু হওয়া পর্যন্ত দেখি একই indent-block-এ আরও কোড আছে কিনা
                    has_unreachable_code = False
                    base_indent = len(lines[j]) - len(lines[j].lstrip())
                    for l in lines[j + 1 :]:
                        if not l.strip():
                            continue
                        cur_indent = len(l) - len(l.lstrip())
                        if cur_indent < base_indent:
                            break
                        if cur_indent == base_indent and l.strip() not in ("", "return"):
                            has_unreachable_code = True
                            break
                    if has_unreachable_code:
                        report.add(
                            "yield-bare-return",
                            "critical",
                            path,
                            j + 1,
                            "yield-এর ঠিক পরে bare `return`, তারপরও একই ইনডেন্টে আরও কোড আছে যা "
                            "কখনো এক্সিকিউট হবে না (unreachable teardown) — cross-test state leak "
                            "হওয়ার প্রধান কারণ ছিল (2026-07 CI saga)। try/yield/finally-তে পরিবর্তন করুন।",
                        )
                    else:
                        report.add(
                            "yield-bare-return",
                            "low",
                            path,
                            j + 1,
                            "yield-এর পরে bare `return` (harmless no-op, পরে কোনো কোড নেই) — শুধু flag, "
                            "real bug না। review-only.",
                        )


# ── Check 4: dual-module-identity ───────────────────────────────────────────
SENSITIVE_BASENAMES = {"config.py", "llm_gateway.py", "secret_vault.py", "honeypot_middleware.py"}
SENSITIVE_DIRNAMES = {"evolution"}


def check_dual_module_identity(root: Path, report: Report) -> None:
    seen_files = defaultdict(list)
    seen_dirs = defaultdict(list)
    for path in iter_py_files(root):
        if path.name in SENSITIVE_BASENAMES:
            seen_files[path.name].append(path)
    for d in root.rglob("*"):
        if (
            d.is_dir()
            and d.name in SENSITIVE_DIRNAMES
            and not any(part in SKIP_DIRS for part in d.parts)
        ):
            seen_dirs[d.name].append(d)

    for name, paths in seen_files.items():
        if len(paths) > 1:
            locs = ", ".join(str(p.relative_to(root)) for p in paths)
            report.add(
                "dual-module-identity",
                "medium",
                paths[0],
                0,
                f"'{name}' একাধিক জায়গায় আছে ({locs}) — একই basename ভিন্ন import path হলে "
                f"module-level singleton/cache দুইবার তৈরি হতে পারে (secret_vault/honeypot_middleware "
                f"bug-এর মূল কারণ ছিল এই প্যাটার্ন)। rename বা facade pattern প্রয়োগ করুন।",
            )
    for name, paths in seen_dirs.items():
        if len(paths) > 1:
            locs = ", ".join(str(p.relative_to(root)) for p in paths)
            report.add(
                "dual-module-identity",
                "low",
                paths[0],
                0,
                f"ডিরেক্টরি '{name}' একাধিক জায়গায় আছে ({locs}) — dead-code duplication বা import "
                f"বিভ্রান্তির ঝুঁকি, verify করে দেখুন কোনটা canonical।",
            )


# ── Check 5: hardcoded-render-id ────────────────────────────────────────────
RENDER_ID_RE = re.compile(r"srv-[a-z0-9]{20,}")


def check_hardcoded_render_id(root: Path, report: Report) -> None:
    for path in root.rglob("*.yml"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(lines, start=1):
            if RENDER_ID_RE.search(line) and "#" not in line.split("srv-")[0][-3:]:
                report.add(
                    "hardcoded-render-id",
                    "medium",
                    path,
                    i,
                    "Literal Render service ID (srv-...) হার্ডকোড করা — repo/org variable বা secret "
                    "হিসেবে রাখা উচিত (no-hardcode নীতি অনুযায়ী)।",
                )


# ── Check 6: ssl-verify-bypass ───────────────────────────────────────────────
SSL_BYPASS_RE = re.compile(r"CERT_NONE|verify\s*=\s*False|ssl\._create_unverified_context")


def check_ssl_bypass(root: Path, report: Report) -> None:
    for path in iter_py_files(root):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if SSL_BYPASS_RE.search(line):
                report.add(
                    "ssl-verify-bypass",
                    "critical",
                    path,
                    i,
                    "TLS certificate verification disabled (CERT_NONE/verify=False) — MITM ঝুঁকি। "
                    "প্রকৃত CA bundle ব্যবহার করে ঠিক করুন, verification off করবেন না।",
                )


# ── Check 7: hardcoded-secret (lightweight heuristic) ───────────────────────
SECRET_RE = re.compile(
    r'(api[_-]?key|secret|password|token|private[_-]?key)\s*=\s*[\'"]([A-Za-z0-9_\-/+=]{12,})[\'"]',
    re.IGNORECASE,
)
SECRET_ALLOW_PATTERNS = re.compile(
    r"os\.(environ|getenv)|test_|example|dummy|placeholder|xxx|your[_-]?", re.IGNORECASE
)


def check_hardcoded_secret(root: Path, report: Report) -> None:
    for path in iter_py_files(root):
        if (
            "/tests/" in str(path)
            or path.name.startswith("test_")
            or path.name == "secrets_rotation_manager.py"
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            continue
        for m in SECRET_RE.finditer(text):
            line_no = text[: m.start()].count("\n") + 1
            line_text = text.splitlines()[line_no - 1]
            if SECRET_ALLOW_PATTERNS.search(line_text):
                continue
            report.add(
                "hardcoded-secret",
                "critical",
                path,
                line_no,
                f"সম্ভাব্য hardcoded secret literal (key='{m.group(1)}') — manual review করুন, "
                f"সত্যিকারের হলে rotate + env var-এ সরান + git history scrub প্রয়োজন।",
            )


# ── Check 8: cors-wildcard ───────────────────────────────────────────────────
def check_cors_wildcard(root: Path, report: Report) -> None:
    for path in iter_py_files(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except UnicodeDecodeError:
            continue
        if "allow_origins" not in text:
            continue
        if (
            re.search(r'allow_origins\s*=\s*\[\s*["\']\*["\']\s*\]', text)
            and "allow_credentials=True" in text
        ):
            line_no = next(
                (i for i, l in enumerate(text.splitlines(), 1) if "allow_origins" in l), 1
            )
            report.add(
                "cors-wildcard",
                "high",
                path,
                line_no,
                "allow_origins=['*'] সাথে allow_credentials=True — ব্রাউজার এটা রিজেক্ট করবে বা, "
                "কিছু ক্ষেত্রে, credential leak-এর ঝুঁকি তৈরি করে। নির্দিষ্ট origin whitelist ব্যবহার করুন।",
            )


# ── Check 9: bare-except-pass ────────────────────────────────────────────────
def check_bare_except_pass(root: Path, report: Report) -> None:
    for path in iter_py_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                    report.add(
                        "bare-except-pass",
                        "medium",
                        path,
                        node.lineno,
                        "সম্পূর্ণ silent `except: pass` — error সম্পূর্ণ গায়েব হয়ে যায়, debugging "
                        "অসম্ভব হয়ে পড়ে। অন্তত logger.exception() যোগ করুন (with_error_bus decorator "
                        "বিবেচনা করুন)।",
                    )


CHECKS = [
    ("auth-fallback-bypass", check_auth_fallback_bypass),
    ("unguarded-localhost", check_unguarded_localhost),
    ("yield-bare-return", check_yield_bare_return),
    ("dual-module-identity", check_dual_module_identity),
    ("hardcoded-render-id", check_hardcoded_render_id),
    ("ssl-verify-bypass", check_ssl_bypass),
    ("hardcoded-secret", check_hardcoded_secret),
    ("cors-wildcard", check_cors_wildcard),
    ("bare-except-pass", check_bare_except_pass),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI learned-regression scanner")
    parser.add_argument("--path", default=".", help="Root directory to scan (default: cwd)")
    parser.add_argument("--json", default=None, help="Optional path to write JSON report")
    parser.add_argument(
        "--fail-on",
        default="critical,high",
        help="Comma-separated severities that cause a non-zero exit (default: critical,high)",
    )
    parser.add_argument(
        "--only",
        default=None,
        help="Comma-separated check names to run (default: all)",
    )
    args = parser.parse_args()

    root = Path(args.path).resolve()
    fail_severities = {s.strip() for s in args.fail_on.split(",") if s.strip()}
    only = {s.strip() for s in args.only.split(",")} if args.only else None

    report = Report()
    for name, fn in CHECKS:
        if only and name not in only:
            continue
        print(f"  scanning: {name} ...", file=sys.stderr)
        fn(root, report)

    # Console summary
    by_check = defaultdict(list)
    for f in report.findings:
        by_check[f.check].append(f)

    print("\n" + "=" * 78)
    print("SupremeAI Regression Scan — Summary")
    print("=" * 78)
    counts = defaultdict(int)
    for f in report.findings:
        counts[f.severity] += 1
    for sev in ("critical", "high", "medium", "low"):
        print(f"  {sev.upper():8s}: {counts.get(sev, 0)}")
    print("=" * 78)

    for check_name, items in sorted(
        by_check.items(), key=lambda kv: -SEVERITY_ORDER.get(kv[1][0].severity, 0)
    ):
        print(f"\n### {check_name} ({len(items)} finding(s))")
        for f in items[:50]:
            rel = f.file
            try:
                rel = str(Path(f.file).resolve().relative_to(root))
            except Exception as e:
                import logging

                logging.getLogger(__name__).exception(f"Silenced error: {e}")
            print(f"  [{f.severity.upper()}] {rel}:{f.line} — {f.message}")
        if len(items) > 50:
            print(f"  ... and {len(items) - 50} more (see --json output for full list)")

    if args.json:
        out = {
            "summary": dict(counts),
            "findings": [asdict(f) for f in report.findings],
        }
        Path(args.json).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nFull JSON report written to {args.json}")

    should_fail = any(f.severity in fail_severities for f in report.findings)
    if should_fail:
        print(
            f"\n❌ FAIL — findings at severity {sorted(fail_severities)} present.",
            file=sys.stderr,
        )
        return 1
    print("\n✅ PASS — no findings at the configured fail-on severity levels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
