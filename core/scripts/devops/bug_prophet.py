# --- Merged from bug_prophet.py ---

#!/usr/bin/env python3
"""
SupremeAI - BugProphet Agent 🔮
================================
Static analysis + AI-driven bug/anti-pattern prediction for PR review.

Purpose:
- AST-based static scanning for common Python bugs and security smells.
- AI-powered deep analysis to predict logical bugs, race conditions,
  and API misuse before code reaches production.
- Generates a structured Markdown report with severity levels.

Author: SupremeAI Core
Date: July 18, 2026
"""

import argparse
import ast
import concurrent.futures
import datetime
import hashlib
import json
import logging
import re
import sys
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

import litellm

# --- Path Setup (consistent with ai_scribe_historian.py) ---
# বাংলা মন্তব্য: ক্লিন ইমপোর্ট স্ট্রাকচার এবং পাথ রেজোলিউশন নিশ্চিত করা হচ্ছে।
try:
    from backend.core.config import settings
except ImportError:
    # বাংলা: এই ফলব্যাক পাথটি আগে ভুল ছিল — Path(__file__).parent মানে
    # scripts/devops/ ডিরেক্টরি, যেখানে backend/ সাবফোল্ডার আদৌ নেই। রিপো-রুট
    # খুঁজতে .parent.parent.parent দরকার (scripts/devops/ → scripts/ → repo root)।
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from core.config import settings

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

litellm.set_verbose = False
litellm.max_retries = 3
litellm.retry_strategy = {"wait_time": 16, "allowed_exceptions": [Exception]}

CACHE_FILE = Path(__file__).parent / ".bug_prophet_cache.sqlite"
TARGET_DIRECTORIES = ["backend/core", "backend/tools"]
FILE_PATTERN = "*.py"
EXCLUDE_FILES = {"__init__.py", "bug_prophet.py", "ai_scribe_historian.py"}

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"

# --- Data Structures ---


@dataclass
class Issue:
    rule_id: str
    category: str
    severity: str
    message: str
    line: int
    column: int
    detection: str  # "static" or "ai"
    snippet: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FileReport:
    file_path: str
    file_hash: str
    issues: list[Issue] = field(default_factory=list)
    ai_summary: str = ""
    risk_score: float = 0.0  # 0.0 - 10.0

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "issues": [i.to_dict() for i in self.issues],
            "ai_summary": self.ai_summary,
            "risk_score": self.risk_score,
        }


# --- LLM Infrastructure (same pattern as ai_scribe_historian) ---


class LLMCallError(Exception):
    """সব রিট্রাই শেষে LLM কল ব্যর্থ হলে এই এরর রেইজ হবে।"""


key_index = 0
api_key_lock = threading.Lock()


def get_ai_response(
    prompt: str,
    temperature: float = 0.2,
    max_retries_per_key: int = 3,
    retry_backoff_seconds: float = 2.0,
) -> str:
    """
    প্রম্পট পাঠায় এবং LLM-এর উত্তর রিটার্ন করে। ব্যর্থ হলে LLMCallError রেইজ করে।
    """
    global key_index
    api_keys_str = settings.gemini_api_key
    if not api_keys_str:
        raise LLMCallError("settings.gemini_api_key কনফিগার করা নেই।")

    keys = [k.strip() for k in api_keys_str.split(",") if k.strip()]
    if not keys:
        raise LLMCallError("কোনো বৈধ Gemini API key পাওয়া যায়নি।")

    max_retries = max_retries_per_key * len(keys)
    last_error: Exception | None = None

    for attempt in range(max_retries):
        current_key = keys[key_index % len(keys)]
        try:
            response = litellm.completion(
                model=settings.gemini_model_name,
                messages=[{"content": prompt, "role": "user"}],
                temperature=temperature,
                api_key=current_key,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            last_error = e
            error_msg = str(e)
            recoverable = any(
                code in error_msg
                for code in (
                    "429",
                    "RESOURCE_EXHAUSTED",
                    "RateLimit",
                    "403",
                    "PERMISSION_DENIED",
                    "API_KEY_SERVICE_BLOCKED",
                )
            )
            if not recoverable:
                raise

            logging.warning(
                f"Key ending in ...{current_key[-4:]} failed (attempt {attempt + 1}/{max_retries}), rotating key..."
            )
            with api_key_lock:
                key_index += 1
            import time

            time.sleep(retry_backoff_seconds * (2 ** (attempt // len(keys))))

    raise LLMCallError(f"সব API key দিয়ে চেষ্টার পরও ব্যর্থ: {last_error}")


# --- Static Analysis Engine ---


class StaticBugVisitor(ast.NodeVisitor):
    """
    বাংলা মন্তব্য: AST ভিজিটর যা কমন পাইথন বাগ, সিকিউরিটি স্মেল এবং অ্যান্টি-প্যাটার্ন ধরে।
    """

    DANGEROUS_BUILTINS = {"eval", "exec", "compile", "__import__", "input"}
    SQL_METHODS = {"execute", "executemany", "executescript", "cursor", "raw"}
    SECRET_PATTERNS = [
        re.compile(r'password\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
        re.compile(r'secret\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
        re.compile(r'api_key\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
        re.compile(r'token\s*=\s*["\'][^"\']+["\']', re.IGNORECASE),
    ]

    def __init__(self, source_lines: list[str], file_path: str):
        self.source_lines = source_lines
        self.file_path = file_path
        self.issues: list[Issue] = []
        self.function_nesting = 0
        self.loop_nesting = 0
        self.current_function: str | None = None

    def _add(self, rule_id: str, category: str, severity: str, message: str, node: ast.AST):
        snippet = ""
        try:
            if hasattr(node, "lineno") and node.lineno:
                idx = node.lineno - 1
                if 0 <= idx < len(self.source_lines):
                    snippet = self.source_lines[idx].strip()
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")

        self.issues.append(
            Issue(
                rule_id=rule_id,
                category=category,
                severity=severity,
                message=message,
                line=getattr(node, "lineno", 0),
                column=getattr(node, "col_offset", 0),
                detection="static",
                snippet=snippet,
            )
        )

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        self.function_nesting += 1
        prev_func = self.current_function
        self.current_function = node.name

        # BP007: Function too long
        body_lines = node.end_lineno - node.lineno if node.end_lineno else 0
        if body_lines > 50:
            self._add(
                "BP007",
                "Maintainability",
                SEVERITY_MEDIUM,
                f"Function '{node.name}' is {body_lines} lines long. Consider breaking it down.",
                node,
            )

        # BP006: Too many arguments
        arg_count = len(node.args.args) + len(node.args.kwonlyargs)
        if node.args.vararg:
            arg_count += 1
        if node.args.kwarg:
            arg_count += 1
        if arg_count > 7:
            self._add(
                "BP006",
                "Complexity",
                SEVERITY_MEDIUM,
                f"Function '{node.name}' has {arg_count} parameters. Consider using a data class or config object.",
                node,
            )

        # BP008: Deep nesting
        if self.function_nesting + self.loop_nesting > 4:
            self._add(
                "BP008",
                "Complexity",
                SEVERITY_MEDIUM,
                f"Deep nesting detected inside '{node.name}'. Refactor to reduce cognitive load.",
                node,
            )

        self.generic_visit(node)
        self.current_function = prev_func
        self.function_nesting -= 1

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        # BP001: Bare except
        if node.type is None:
            self._add(
                "BP001",
                "Reliability",
                SEVERITY_HIGH,
                "Bare 'except:' clause catches KeyboardInterrupt and SystemExit. Use 'except Exception:' instead.",
                node,
            )
        self.generic_visit(node)

    def visit_For(self, node: ast.For | ast.While | ast.If | ast.With):
        self.loop_nesting += 1
        if self.loop_nesting > 3:
            self._add(
                "BP008",
                "Complexity",
                SEVERITY_LOW,
                "Deep loop/conditional nesting detected. Consider extracting helper functions.",
                node,
            )
        self.generic_visit(node)
        self.loop_nesting -= 1

    visit_While = visit_For
    visit_If = visit_For
    visit_With = visit_For

    def visit_Call(self, node: ast.Call):
        # BP003: Dangerous builtins
        if isinstance(node.func, ast.Name) and node.func.id in self.DANGEROUS_BUILTINS:
            self._add(
                "BP003",
                "Security",
                SEVERITY_CRITICAL,
                f"Dangerous builtin '{node.func.id}()' used. This is a major security risk.",
                node,
            )

        # BP005: SQL injection risk (heuristic)
        if isinstance(node.func, ast.Attribute) and node.func.attr in self.SQL_METHODS:
            for arg in node.args:
                if isinstance(arg, (ast.JoinedStr, ast.Call)):
                    if (
                        isinstance(arg, ast.Call)
                        and isinstance(arg.func, ast.Attribute)
                        and arg.func.attr in {"format", "replace"}
                    ):
                        self._add(
                            "BP005",
                            "Security",
                            SEVERITY_CRITICAL,
                            f"Possible SQL injection via string formatting in '{node.func.attr}()'. Use parameterized queries.",
                            node,
                        )
                    elif isinstance(arg, ast.JoinedStr):
                        self._add(
                            "BP005",
                            "Security",
                            SEVERITY_CRITICAL,
                            f"Possible SQL injection via f-string in '{node.func.attr}()'. Use parameterized queries.",
                            node,
                        )

        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert):
        # BP009: Assert in production code
        self._add(
            "BP009",
            "Reliability",
            SEVERITY_MEDIUM,
            "'assert' statements are removed when Python runs with -O. Do not use them for production logic.",
            node,
        )
        self.generic_visit(node)

    def scan_source_text(self, source: str):
        """বাংলা মন্তব্য: সোর্স টেক্সট স্ক্যান করে হার্ডকোডেড সিক্রেট এবং কমেন্টেড কোড খোঁজে।"""
        for line_no, line in enumerate(self.source_lines, 1):
            stripped = line.strip()
            # BP010: Hardcoded secrets
            for pattern in self.SECRET_PATTERNS:
                if pattern.search(line) and not stripped.startswith("#"):
                    # Avoid matching env var lookups
                    if (
                        "os.getenv" not in line
                        and "environ" not in line
                        and "settings." not in line
                    ):
                        self._add(
                            "BP010",
                            "Security",
                            SEVERITY_HIGH,
                            "Possible hardcoded secret detected. Move to environment variables or secrets manager.",
                            type(
                                "obj",
                                (object,),
                                {
                                    "lineno": line_no,
                                    "col_offset": line.index("=") if "=" in line else 0,
                                },
                            )(),
                        )

            # BP011: TODO/FIXME with high severity keywords
            if "#" in stripped and any(
                k in stripped.lower() for k in ["hack", "temporary", "temp fix", "xxx"]
            ):
                self._add(
                    "BP011",
                    "Maintainability",
                    SEVERITY_LOW,
                    "Temporary/hacky code comment found. Address before merging.",
                    type("obj", (object,), {"lineno": line_no, "col_offset": 0})(),
                )


def run_static_analysis(file_path: Path) -> list[Issue]:
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return [
            Issue(
                "BP-SYNTAX",
                "ParseError",
                SEVERITY_CRITICAL,
                f"Syntax error: {e}",
                e.lineno or 1,
                e.offset or 0,
                "static",
            )
        ]

    visitor = StaticBugVisitor(lines, str(file_path))
    visitor.visit(tree)
    visitor.scan_source_text(content)
    return visitor.issues


# --- AI Analysis Engine ---

AI_BUG_PROMPT_TEMPLATE = """
You are **BugProphet**, an expert Python code reviewer and security analyst for the SupremeAI project.
Analyze the following Python file and predict bugs, race conditions, logic errors, API misuse, and performance anti-patterns.

**File Path:** `{file_path}`

**Instructions:**
1. Focus on issues that static analysis CANNOT catch (logical errors, concurrency, API misuse, type safety, resource leaks).
2. Return ONLY a valid JSON array. No markdown, no explanation outside JSON.
3. Each object must have: `rule_id` (string, prefix with AI-), `category` (string), `severity` ("CRITICAL"|"HIGH"|"MEDIUM"|"LOW"), `message` (string), `line` (int, best guess), `column` (int, 0 if unknown).
4. If no issues found, return an empty array `[]`.

**Code:**
```python
{code}
```
JSON Output:
"""


def run_ai_analysis(file_path: Path) -> list[Issue]:
    # বাংলা মন্তব্য: এআই বিশ্লেষণ যা রানটাইম/লজিক বাগ এবং এপিআই মিসইউজ ধরতে পারে।
    content = file_path.read_text(encoding="utf-8")
    prompt = AI_BUG_PROMPT_TEMPLATE.format(file_path=file_path, code=content)
    try:
        raw = get_ai_response(prompt, temperature=0.2)
        # Extract JSON from possible markdown fences
        raw = raw.strip()
        raw = raw.removeprefix("```json")
        raw = raw.removeprefix("```")
        raw = raw.removesuffix("```")
        raw = raw.strip()

        data = json.loads(raw)
        if not isinstance(data, list):
            logging.warning(f"AI analysis for {file_path} did not return a list.")
            return []

        issues = []
        for item in data:
            issues.append(
                Issue(
                    rule_id=item.get("rule_id", "AI-UNKNOWN"),
                    category=item.get("category", "AI"),
                    severity=item.get("severity", SEVERITY_MEDIUM),
                    message=item.get("message", "AI-detected issue"),
                    line=item.get("line", 1),
                    column=item.get("column", 0),
                    detection="ai",
                    snippet="",
                )
            )
        return issues
    except json.JSONDecodeError as e:
        logging.warning(f"AI analysis JSON parse failed for {file_path}: {e}")
        return []
    except LLMCallError:
        raise
    except Exception as e:
        logging.error(f"Unexpected error during AI analysis of {file_path}: {e}")
        return []


# --- Cache & Hash ---
import sqlite3


def _get_db_connection():
    conn = sqlite3.connect(CACHE_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT)")
    return conn


def load_cache() -> dict:
    cache = {}
    try:
        with _get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM cache")
            for row in cursor.fetchall():
                cache[row[0]] = json.loads(row[1])
    except Exception as e:
        logging.warning(f"Failed to load cache: {e}")
    return cache


def save_cache(cache: dict):
    try:
        with _get_db_connection() as conn:
            cursor = conn.cursor()
            for key, value in cache.items():
                cursor.execute(
                    "INSERT OR REPLACE INTO cache (key, value) VALUES (?, ?)",
                    (key, json.dumps(value)),
                )
            conn.commit()
    except Exception as e:
        logging.warning(f"Failed to save cache: {e}")


def get_file_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# --- Report Generation ---
def calculate_risk_score(issues: list[Issue]) -> float:
    score = 0.0
    weights = {SEVERITY_CRITICAL: 3.0, SEVERITY_HIGH: 1.5, SEVERITY_MEDIUM: 0.7, SEVERITY_LOW: 0.2}
    for issue in issues:
        score += weights.get(issue.severity, 0.5)
    # Cap at 10.0, normalize roughly
    return min(round(score, 1), 10.0)


def generate_markdown_report(reports: list[FileReport], output_path: Path):
    # বাংলা মন্তব্য: প্রাপ্ত ফলাফলের উপর ভিত্তি করে একটি সুন্দর এবং ডেকোরেটিভ রিপোর্ট ফাইল তৈরি করা।
    lines = [
        "# 🔮 BugProphet Analysis Report",
        f"Generated: {datetime.datetime.now().isoformat()}",
        f"Files Scanned: {len(reports)}",
        "",
        "## Summary",
        "| File | Risk Score | Critical | High | Medium | Low |",
        "|------|-----------|----------|------|--------|-----|",
    ]

    total_crit = total_high = total_med = total_low = 0
    for r in reports:
        c = sum(1 for i in r.issues if i.severity == SEVERITY_CRITICAL)
        h = sum(1 for i in r.issues if i.severity == SEVERITY_HIGH)
        m = sum(1 for i in r.issues if i.severity == SEVERITY_MEDIUM)
        l = sum(1 for i in r.issues if i.severity == SEVERITY_LOW)
        total_crit += c
        total_high += h
        total_med += m
        total_low += l
        lines.append(f"| `{r.file_path}` | {r.risk_score}/10 | {c} | {h} | {m} | {l} |")

    lines.extend(
        [
            "",
            f"**Totals:** {total_crit} Critical, {total_high} High, {total_med} Medium, {total_low} Low",
            "",
            "---",
            "",
            "## Detailed Findings",
        ]
    )

    for r in reports:
        if not r.issues:
            continue
        lines.append(f"### `{r.file_path}` (Risk: {r.risk_score}/10)")
        if r.ai_summary:
            lines.append(f"**AI Summary:** {r.ai_summary}")
        lines.append("")
        lines.append("| Rule | Severity | Category | Line | Message |")
        lines.append("|------|----------|----------|------|---------|")
        for issue in sorted(r.issues, key=lambda x: (x.line, x.severity)):
            lines.append(
                f"| `{issue.rule_id}` | {issue.severity} | {issue.category} | {issue.line} | {issue.message} |"
            )
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logging.info(f"✅ Markdown report saved to {output_path}")


# --- Main Orchestrator ---
def process_file(file_path: Path, cache: dict, force: bool, use_ai: bool) -> FileReport | None:
    # বাংলা মন্তব্য: প্রতিটি ফাইলকে স্ক্যান করে এবং ক্যাশে আপডেট করে।
    logging.info(f"Scanning: {file_path}")
    content = file_path.read_text(encoding="utf-8")
    content_hash = get_file_hash(content)

    cache_key = str(file_path)
    # বাংলা মন্তব্য: ক্যাশ কি চেক করা হচ্ছে 'file_hash' এর মাধ্যমে যাতে রিবিল্ড ফাস্ট হয়।
    if not force and cache_key in cache and cache[cache_key].get("file_hash") == content_hash:
        logging.info(f"Skipping {file_path} (cached).")
        cached = cache[cache_key]
        report = FileReport(
            file_path=str(file_path),
            file_hash=content_hash,
            issues=[Issue(**i) for i in cached.get("issues", [])],
            ai_summary=cached.get("ai_summary", ""),
            risk_score=cached.get("risk_score", 0.0),
        )
        return report

    # Static analysis
    static_issues = run_static_analysis(file_path)

    # AI analysis
    ai_issues: list[Issue] = []
    ai_summary = ""
    if use_ai:
        try:
            ai_issues = run_ai_analysis(file_path)
            if ai_issues:
                ai_summary = f"AI identified {len(ai_issues)} potential runtime/logic issue(s)."
        except LLMCallError as e:
            logging.error(f"AI analysis failed for {file_path}: {e}")
            ai_summary = "AI analysis unavailable due to LLM error."

    all_issues = static_issues + ai_issues
    risk = calculate_risk_score(all_issues)

    report = FileReport(
        file_path=str(file_path),
        file_hash=content_hash,
        issues=all_issues,
        ai_summary=ai_summary,
        risk_score=risk,
    )

    cache[cache_key] = report.to_dict()
    return report


def main(
    dry_run: bool = False,
    force: bool = False,
    workers: int = 4,
    use_ai: bool = True,
    files: list[str] | None = None,
    output: str = "bug_prophet_report.md",
):
    if not settings.gemini_api_key:
        logging.error("FATAL: GEMINI_API_KEY is not set in backend settings.")
        return

    if dry_run:
        logging.warning("Running in DRY-RUN mode. No files will be modified.")
    if force:
        logging.warning("Running in FORCE mode. Cache ignored.")

    cache = load_cache()
    reports: list[FileReport] = []

    if files:
        file_paths = [
            Path(f) for f in files if Path(f).exists() and Path(f).name not in EXCLUDE_FILES
        ]
    else:
        file_paths = []
        for target_dir in TARGET_DIRECTORIES:
            base = Path(target_dir)
            if not base.exists():
                logging.warning(f"Directory not found: {base}")
                continue
            for py_file in base.rglob(FILE_PATTERN):
                if py_file.name not in EXCLUDE_FILES:
                    file_paths.append(py_file)

    if not file_paths:
        logging.info("No files to scan.")
        return

    logging.info(f"BugProphet scanning {len(file_paths)} file(s) with {workers} workers...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_file = {
            executor.submit(process_file, fp, cache, force, use_ai): fp for fp in file_paths
        }
        for future in concurrent.futures.as_completed(future_to_file):
            try:
                report = future.result()
                if report:
                    reports.append(report)
            except Exception as e:
                logging.error(f"Error processing file: {e}")

    if not dry_run:
        save_cache(cache)

    # Sort by risk score descending
    reports.sort(key=lambda r: r.risk_score, reverse=True)

    generate_markdown_report(reports, Path(output))
    logging.info("BugProphet analysis complete. 🔮")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BugProphet: AI-powered bug prediction agent")
    parser.add_argument(
        "--dry-run", action="store_true", help="Run without writing cache or reports."
    )
    parser.add_argument("--force", action="store_true", help="Ignore cache and rescan everything.")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Concurrent workers.")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI analysis (static only).")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="bug_prophet_report.md",
        help="Output Markdown report path.",
    )
    parser.add_argument("--files", nargs="*", help="Specific files to scan (git hook mode).")
    args = parser.parse_args()

    main(
        dry_run=args.dry_run,
        force=args.force,
        workers=args.workers,
        use_ai=not args.no_ai,
        files=args.files,
        output=args.output,
    )

# --- Streaming Anomaly Detector ---
import asyncio
import math

# বাংলা: এই ইমপোর্টে আগে try/except fallback ছিল না — ফলে যখন এই মডিউলটি লাইভ
# backend অ্যাপ থেকে `run_anomaly_detector_loop` হিসেবে ইমপোর্ট করা হতো (core.lifespan
# app_lifespan-এর ভেতর থেকে, যেখানে sys.path-এ শুধু backend/-এর ভেতরের প্যাকেজ
# (core.*) দৃশ্যমান, `backend` নিজে একটা top-level প্যাকেজ হিসেবে দৃশ্যমান নয়),
# এটি সবসময় `ModuleNotFoundError: No module named 'backend'` দিত এবং BugProphet
# Anomaly Detector agent-টি চালুই হতো না (render_admin_.txt লগে এই এররই বারবার
# দেখা যাচ্ছিল)। উপরের config import-এর মতোই একই try/except fallback প্যাটার্ন এখানে
# প্রয়োগ করা হলো।
try:
    from backend.core.messaging.event_bus import (
        ErrorContext,
        ErrorEvent,
        error_event_bus,
    )
except ImportError:
    from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus


class AnomalyDetector:
    def __init__(self):
        # Tracking error frequencies per module. (timestamp, error_type)
        self.history = {}
        self.window_size_seconds = 60
        self.baseline_avg = {}
        self.baseline_std = {}

    def _update_baselines(self):
        # A lightweight Z-score model update
        now = datetime.datetime.now(datetime.UTC).timestamp()
        for module, events in self.history.items():
            # Keep only events in the window
            valid_events = [e for e in events if now - e[0] <= self.window_size_seconds]
            self.history[module] = valid_events

            count = len(valid_events)

            if module not in self.baseline_avg:
                self.baseline_avg[module] = count
                self.baseline_std[module] = 1.0  # Default std
            else:
                # Exponential moving average
                alpha = 0.1
                old_avg = self.baseline_avg[module]
                self.baseline_avg[module] = (alpha * count) + ((1 - alpha) * old_avg)

                # variance update
                var = (count - self.baseline_avg[module]) ** 2
                self.baseline_std[module] = math.sqrt(
                    (alpha * var) + ((1 - alpha) * (self.baseline_std[module] ** 2))
                )

    def process_event(self, event: ErrorEvent):
        module = event.module
        if module not in self.history:
            self.history[module] = []

        now = datetime.datetime.now(datetime.UTC).timestamp()
        self.history[module].append((now, event.error_type))

        self._update_baselines()

        # Check Z-score
        current_count = len(self.history[module])
        avg = self.baseline_avg.get(module, 0)
        std = self.baseline_std.get(module, 1.0)
        if std == 0:
            std = 1.0

        z_score = (current_count - avg) / std

        # If 10x more warnings than baseline (or very high Z-score)
        if current_count > 10 and current_count > (avg * 10) and z_score > 3.0:
            logging.critical(
                f"[BugProphet] PREDICTED OUTAGE in {module}! Z-score: {z_score:.2f}, Count: {current_count}, Avg: {avg:.2f}"
            )

            outage_event = ErrorEvent(
                module=module,
                error_type="PREDICTED_OUTAGE",
                message=f"Anomaly detected! Module '{module}' error rate is {current_count} (baseline {avg:.2f}).",
                severity="CRITICAL",
                structured_context=ErrorContext(module=module, env="production"),
            )
            # Emit directly to bus (ensure we don't infinitely loop by checking error type)
            if event.error_type != "PREDICTED_OUTAGE":
                asyncio.create_task(error_event_bus.async_emit(outage_event))


async def run_anomaly_detector_loop():
    """
    বাংলা মন্তব্য: Background loop that integrates bug_prophet directly with the ErrorEventBus.
    It predicts outages before they crash the process.
    """
    logging.info("🔮 BugProphet Anomaly Detector started.")
    detector = AnomalyDetector()

    # We register a listener to the error_event_bus
    def listener(event: ErrorEvent):
        if event.error_type not in ["PREDICTED_OUTAGE", "SILENT_PATTERN_ESCALATED"]:
            detector.process_event(event)

    error_event_bus.register_listener("*", listener)

    try:
        while True:
            # The loop just keeps the task alive, the listener does the work synchronously
            # Or we could poll the dead letter queue if we wanted, but listener is real-time.
            await asyncio.sleep(60)
            detector._update_baselines()
    except asyncio.CancelledError:
        error_event_bus.unregister_listener("*", listener)
        logging.info("🔮 BugProphet Anomaly Detector shutting down.")
