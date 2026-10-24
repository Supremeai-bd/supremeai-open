# --- Merged from refactor_wiz.py ---

#!/usr/bin/env python3
"""
SupremeAI - RefactorWiz Agent 🧙
=================================
Technical debt identifier and safe refactoring planner.

Purpose:
- AST-based metrics collection (complexity, coupling, duplication, length).
- AI-generated safe refactoring plans with before/after suggestions.
- Produces Markdown reports with Mermaid diagrams showing module relationships.

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
import sys
import threading
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import litellm

# --- Path Setup ---
# বাংলা মন্তব্য: ক্লিন ইমপোর্ট স্ট্রাকচার এবং পাথ রেজোলিউশন নিশ্চিত করা হচ্ছে।
try:
    from backend.core.config import settings
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
    sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from core.config import settings

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

litellm.set_verbose = False
litellm.max_retries = 3
litellm.retry_strategy = {
    "wait_time": 16,
    "allowed_exceptions": [Exception]
}

CACHE_FILE = Path(__file__).parent / ".refactor_wiz_cache.sqlite"
TARGET_DIRECTORIES = ["backend/core", "backend/tools"]
FILE_PATTERN = "*.py"
EXCLUDE_FILES = {"__init__.py", "refactor_wiz.py", "ai_scribe_historian.py"}

# --- LLM Infrastructure ---

class LLMCallError(Exception):
    """সব রিট্রাই শেষে LLM কল ব্যর্থ হলে এই এরর রেইজ হবে।"""

key_index = 0
api_key_lock = threading.Lock()


def get_ai_response(prompt: str, temperature: float = 0.3, max_retries_per_key: int = 3, retry_backoff_seconds: float = 2.0) -> str:
    global key_index
    api_keys_str = settings.gemini_api_key
    if not api_keys_str:
        raise LLMCallError("settings.gemini_api_key কনফিগার করা নেই।")

    keys = [k.strip() for k in api_keys_str.split(',') if k.strip()]
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
                api_key=current_key
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            last_error = e
            error_msg = str(e)
            recoverable = any(code in error_msg for code in (
                "429", "RESOURCE_EXHAUSTED", "RateLimit", "403",
                "PERMISSION_DENIED", "API_KEY_SERVICE_BLOCKED"
            ))
            if not recoverable:
                raise

            logging.warning(f"Key ending in ...{current_key[-4:]} failed (attempt {attempt+1}/{max_retries}), rotating key...")
            with api_key_lock:
                key_index += 1
            import time
            time.sleep(retry_backoff_seconds * (2 ** (attempt // len(keys))))

    raise LLMCallError(f"সব API key দিয়ে চেষ্টার পরও ব্যর্থ: {last_error}")


# --- Data Structures ---

@dataclass
class DebtItem:
    rule_id: str
    category: str
    severity: str
    message: str
    line: int
    metric_value: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FunctionMetrics:
    name: str
    line_start: int
    line_end: int
    length: int
    arg_count: int
    return_count: int
    complexity: int  # Approximate cyclomatic complexity
    nested_depth: int


@dataclass
class FileDebtReport:
    file_path: str
    file_hash: str
    debts: list[DebtItem] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    ai_plan: str = ""
    refactoring_priority: float = 0.0  # 0.0 - 10.0

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "file_hash": self.file_hash,
            "debts": [d.to_dict() for d in self.debts],
            "metrics": self.metrics,
            "ai_plan": self.ai_plan,
            "refactoring_priority": self.refactoring_priority,
        }


# --- AST Metrics Collector ---

class MetricsVisitor(ast.NodeVisitor):
    """
    বাংলা মন্তব্য: ফাংশন-লেভেল মেট্রিক্স কালেক্ট করে — সাইক্লোম্যাটিক কমপ্লেক্সিটি, নেস্টিং ডেপ্থ, ইত্যাদি।
    """

    def __init__(self):
        self.functions: list[FunctionMetrics] = []
        self.imports: list[str] = []
        self.classes: list[str] = []
        self.current_func: FunctionMetrics | None = None
        self.nesting_stack = 0
        self.max_nesting_seen = 0

    def _complexity_increment(self, node: ast.AST):
        if self.current_func:
            self.current_func.complexity += 1
        self.nesting_stack += 1
        self.max_nesting_seen = max(self.max_nesting_seen, self.nesting_stack)
        self.generic_visit(node)
        self.nesting_stack -= 1

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            self.imports.append(f"{module}.{alias.name}")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        prev = self.current_func
        prev_nesting = self.nesting_stack
        self.nesting_stack = 0
        self.max_nesting_seen = 0

        func = FunctionMetrics(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            length=(node.end_lineno or node.lineno) - node.lineno,
            arg_count=len(node.args.args) + len(node.args.kwonlyargs) + (1 if node.args.vararg else 0) + (1 if node.args.kwarg else 0),
            return_count=0,
            complexity=1,  # Base complexity
            nested_depth=0,
        )
        self.current_func = func
        self.generic_visit(node)
        func.nested_depth = self.max_nesting_seen
        self.functions.append(func)

        self.current_func = prev
        self.nesting_stack = prev_nesting

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node: ast.If):
        self._complexity_increment(node)

    def visit_While(self, node: ast.While):
        self._complexity_increment(node)

    def visit_For(self, node: ast.For):
        self._complexity_increment(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        self._complexity_increment(node)

    def visit_With(self, node: ast.With):
        self._complexity_increment(node)

    def visit_Assert(self, node: ast.Assert):
        self._complexity_increment(node)

    def visit_Return(self, node: ast.Return):
        if self.current_func:
            self.current_func.return_count += 1
        self.generic_visit(node)


def collect_metrics(file_path: Path) -> tuple[MetricsVisitor, list[str]]:
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return MetricsVisitor(), lines

    visitor = MetricsVisitor()
    visitor.visit(tree)
    return visitor, lines


# --- Debt Detection Engine ---

def detect_debts(file_path: Path, visitor: MetricsVisitor, lines: list[str]) -> list[DebtItem]:
    debts: list[DebtItem] = []

    # RW001: High cyclomatic complexity
    for func in visitor.functions:
        if func.complexity > 10:
            debts.append(DebtItem(
                rule_id="RW001",
                category="Complexity",
                severity="HIGH",
                message=f"Function '{func.name}' has approximate cyclomatic complexity of {func.complexity}. Refactor into smaller helpers.",
                line=func.line_start,
                metric_value=str(func.complexity),
                suggestion="Extract nested conditionals into private helper methods."
            ))

    # RW002: Long function
    for func in visitor.functions:
        if func.length > 40:
            debts.append(DebtItem(
                rule_id="RW002",
                category="Size",
                severity="MEDIUM",
                message=f"Function '{func.name}' spans {func.length} lines.",
                line=func.line_start,
                metric_value=str(func.length),
                suggestion="Apply Extract Method to isolate logical sections."
            ))

    # RW006: Deep nesting
    for func in visitor.functions:
        if func.nested_depth > 3:
            debts.append(DebtItem(
                rule_id="RW006",
                category="Complexity",
                severity="MEDIUM",
                message=f"Function '{func.name}' has nesting depth of {func.nested_depth}.",
                line=func.line_start,
                metric_value=str(func.nested_depth),
                suggestion="Use early returns or extract nested blocks into functions."
            ))

    # RW007: Long parameter list
    for func in visitor.functions:
        if func.arg_count > 5:
            debts.append(DebtItem(
                rule_id="RW007",
                category="Interface",
                severity="LOW",
                message=f"Function '{func.name}' accepts {func.arg_count} parameters.",
                line=func.line_start,
                metric_value=str(func.arg_count),
                suggestion="Introduce a parameter object or builder pattern."
            ))

    # RW008: God class
    if len(visitor.classes) == 1 and len(visitor.functions) > 20:
        debts.append(DebtItem(
            rule_id="RW008",
            category="Architecture",
            severity="HIGH",
            message=f"Possible God Class detected with {len(visitor.functions)} methods.",
            line=1,
            metric_value=str(len(visitor.functions)),
            suggestion="Split responsibilities into multiple collaborator classes."
        ))

    # RW009: Duplicate code blocks (simple heuristic: identical line sequences of >= 4 lines)
    block_map: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for i in range(len(lines) - 3):
        block = tuple(line.strip() for line in lines[i:i+4])
        if len(block[0]) > 10:  # Ignore trivial short lines
            block_map[block].append(i + 1)

    for block, line_nums in block_map.items():
        if len(line_nums) > 1:
            debts.append(DebtItem(
                rule_id="RW009",
                category="Duplication",
                severity="MEDIUM",
                message=f"Duplicate 4-line block found at lines {line_nums}. Consider extracting a shared function.",
                line=line_nums[0],
                metric_value=str(len(line_nums)),
                suggestion="Apply Extract Function to eliminate duplication."
            ))
            # Limit duplicate warnings to avoid noise
            if len([d for d in debts if d.rule_id == "RW009"]) >= 3:
                break

    return debts


# --- AI Refactoring Planner ---

AI_REFACTOR_PROMPT_TEMPLATE = """
You are **RefactorWiz**, an expert Python architect for the SupremeAI project.
Given the following file's code and detected metrics, produce a safe, step-by-step refactoring plan.

**File:** `{file_path}`

**Detected Metrics:**
{metrics_json}

**Detected Debts:**
{debts_json}

**Instructions:**
1. Provide a concise refactoring plan (max 400 words).
2. Prioritize by safety (do not change behavior).
3. Suggest specific design patterns if applicable (Strategy, Factory, Repository, etc.).
4. Include a "Quick Wins" section for immediate improvements.
5. If the code is clean, simply state: "No major refactoring needed."

**Code:**
```python
{code}
```
Refactoring Plan:
"""

def generate_ai_plan(file_path: Path, metrics: dict, debts: list[DebtItem]) -> str:
    # বাংলা মন্তব্য: এআই জেনারেটেড রিফ্যাক্টরিং প্ল্যান।
    content = file_path.read_text(encoding="utf-8")
    prompt = AI_REFACTOR_PROMPT_TEMPLATE.format(
        file_path=file_path,
        metrics_json=json.dumps(metrics, indent=2),
        debts_json=json.dumps([d.to_dict() for d in debts], indent=2),
        code=content,
    )
    try:
        return get_ai_response(prompt, temperature=0.3)
    except LLMCallError as e:
        logging.error(f"AI planning failed for {file_path}: {e}")
        return "AI refactoring plan unavailable due to LLM error."


# --- Cache & Hash ---
import sqlite3


def _get_db_connection():
    conn = sqlite3.connect(CACHE_FILE)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT)"
    )
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
                    (key, json.dumps(value))
                )
            conn.commit()
    except Exception as e:
        logging.warning(f"Failed to save cache: {e}")


def get_file_hash(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


# --- Report Generation ---
def calculate_priority(debts: list[DebtItem]) -> float:
    score = 0.0
    weights = {"HIGH": 2.0, "MEDIUM": 1.0, "LOW": 0.3}
    for d in debts:
        score += weights.get(d.severity, 0.5)
    return min(round(score, 1), 10.0)


def generate_markdown_report(reports: list[FileDebtReport], output_path: Path):
    # বাংলা মন্তব্য: রিফ্যাক্টরিং ডেব্ট রিপোর্ট তৈরি করা।
    lines = [
        "# 🧙 RefactorWiz Technical Debt Report",
        f"Generated: {datetime.datetime.now().isoformat()}",
        f"Files Analyzed: {len(reports)}",
        "",
        "## Summary",
        "| File | Priority | Debts | Complexity |",
        "|------|----------|-------|------------|",
    ]

    for r in reports:
        debt_count = len(r.debts)
        comp = r.metrics.get("avg_complexity", 0)
        lines.append(f"| `{r.file_path}` | {r.refactoring_priority}/10 | {debt_count} | {comp} |")

    lines.extend([
        "",
        "---",
        "",
        "## Refactoring Plans by File",
    ])

    for r in reports:
        if not r.debts and not r.ai_plan:
            continue

        lines.append(f"### `{r.file_path}` (Priority: {r.refactoring_priority}/10)")
        lines.append("")
        lines.append("**Metrics:**")
        lines.append(f"- Total Functions: {r.metrics.get('function_count', 0)}")
        lines.append(f"- Average Complexity: {r.metrics.get('avg_complexity', 0)}")
        lines.append(f"- Total Imports: {r.metrics.get('import_count', 0)}")
        lines.append(f"- Classes: {r.metrics.get('class_count', 0)}")
        lines.append("")

        if r.debts:
            lines.append("**Detected Debts:**")
            lines.append("")
            lines.append("| Rule | Severity | Category | Line | Message | Suggestion |")
            lines.append("|------|----------|----------|------|---------|------------|")
            for d in sorted(r.debts, key=lambda x: (x.line, x.severity)):
                lines.append(f"| `{d.rule_id}` | {d.severity} | {d.category} | {d.line} | {d.message} | {d.suggestion} |")
            lines.append("")

        if r.ai_plan:
            lines.append("**AI Refactoring Plan:**")
            lines.append("")
            lines.append(r.ai_plan)
            lines.append("")

        # Mermaid diagram for class/function structure (simplified)
        func_names = [f for f in r.metrics.get("functions", [])]
        if func_names:
            lines.append("**Structure Overview:**")
            lines.append("```mermaid")
            lines.append("graph TD;")
            for fn in func_names[:10]:  # Limit to 10 for readability
                safe_name = fn.replace('"', "'")
                lines.append(f'    {safe_name}["{safe_name}()"];')
            lines.append("```")
            lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logging.info(f"✅ RefactorWiz report saved to {output_path}")


# --- Main Orchestrator ---
def process_file(file_path: Path, cache: dict, force: bool, use_ai: bool) -> FileDebtReport | None:
    # বাংলা মন্তব্য: ফাইল অ্যানালাইসিস এবং মেট্রিক্স সংরক্ষণ প্রক্রিয়া।
    logging.info(f"Analyzing: {file_path}")
    content = file_path.read_text(encoding="utf-8")
    content_hash = get_file_hash(content)

    cache_key = str(file_path)
    # বাংলা মন্তব্য: ক্যাশ কি চেক করা হচ্ছে 'file_hash' এর মাধ্যমে।
    if not force and cache_key in cache and cache[cache_key].get("file_hash") == content_hash:
        logging.info(f"Skipping {file_path} (cached).")
        c = cache[cache_key]
        return FileDebtReport(
            file_path=str(file_path),
            file_hash=content_hash,
            debts=[DebtItem(**d) for d in c.get("debts", [])],
            metrics=c.get("metrics", {}),
            ai_plan=c.get("ai_plan", ""),
            refactoring_priority=c.get("refactoring_priority", 0.0),
        )

    visitor, lines = collect_metrics(file_path)
    debts = detect_debts(file_path, visitor, lines)

    metrics = {
        "function_count": len(visitor.functions),
        "class_count": len(visitor.classes),
        "import_count": len(visitor.imports),
        "avg_complexity": round(sum(f.complexity for f in visitor.functions) / max(len(visitor.functions), 1), 1),
        "functions": [f.name for f in visitor.functions],
    }

    ai_plan = ""
    if use_ai and debts:
        try:
            ai_plan = generate_ai_plan(file_path, metrics, debts)
        except LLMCallError as e:
            logging.error(f"AI planning failed: {e}")
            ai_plan = "Unavailable."

    priority = calculate_priority(debts)

    report = FileDebtReport(
        file_path=str(file_path),
        file_hash=content_hash,
        debts=debts,
        metrics=metrics,
        ai_plan=ai_plan,
        refactoring_priority=priority,
    )

    cache[cache_key] = report.to_dict()
    return report


def main(dry_run: bool = False, force: bool = False, workers: int = 4, use_ai: bool = True, files: list[str] | None = None, output: str = "refactor_wiz_report.md"):
    if not settings.gemini_api_key:
        logging.error("FATAL: GEMINI_API_KEY is not set in backend settings.")
        return

    if dry_run:
        logging.warning("Running in DRY-RUN mode.")
    if force:
        logging.warning("Running in FORCE mode. Cache ignored.")

    cache = load_cache()
    reports: list[FileDebtReport] = []

    if files:
        file_paths = [Path(f) for f in files if Path(f).exists() and Path(f).name not in EXCLUDE_FILES]
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
        logging.info("No files to analyze.")
        return

    logging.info(f"RefactorWiz analyzing {len(file_paths)} file(s) with {workers} workers...")

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
                logging.error(f"Error analyzing file: {e}")

    if not dry_run:
        save_cache(cache)

    reports.sort(key=lambda r: r.refactoring_priority, reverse=True)
    generate_markdown_report(reports, Path(output))
    logging.info("RefactorWiz analysis complete. 🧙")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RefactorWiz: Technical debt detection & refactoring planner")
    parser.add_argument("--dry-run", action="store_true", help="Run without writing cache or reports.")
    parser.add_argument("--force", action="store_true", help="Ignore cache.")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Concurrent workers.")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI planning (metrics only).")
    parser.add_argument("-o", "--output", type=str, default="refactor_wiz_report.md", help="Output report path.")
    parser.add_argument("--files", nargs="*", help="Specific files to analyze.")
    args = parser.parse_args()

    main(
        dry_run=args.dry_run,
        force=args.force,
        workers=args.workers,
        use_ai=not args.no_ai,
        files=args.files,
        output=args.output,
    )


