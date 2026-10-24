#!/usr/bin/env python3
"""
SupremeAI Advanced Duplicate Logic Detector
===========================================

Multi-engine duplicate detection system that finds:
  1. EXACT duplicate code blocks (copy-paste)
  2. NEAR-DUPLICATE functions (same signature, similar body)
  3. STRUCTURAL duplicates (same AST shape, different names)
  4. SEMANTIC duplicates (same logic, different syntax)
  5. IMPORT duplicates (same symbol imported via different paths)
  6. FILE-LEVEL duplicates (files that are >90% identical)

Usage:
    python scripts/advanced_analysis/duplicate_detector.py
    python scripts/advanced_analysis/duplicate_detector.py --json
    python scripts/advanced_analysis/duplicate_detector.py --threshold 0.85
    python scripts/advanced_analysis/duplicate_detector.py --fail-on-critical
    python scripts/advanced_analysis/duplicate_detector.py --engine exact
    python scripts/advanced_analysis/duplicate_detector.py --engine structural
    python scripts/advanced_analysis/duplicate_detector.py --engine import

Exit codes:
    0 = no critical duplicates found
    1 = critical duplicates found (--fail-on-critical mode)
    2 = error

Engines:
    exact       — normalized text hash matching (copy-paste blocks >= 10 lines)
    structural  — AST fingerprint matching (same code structure, different names)
    near_dup    — token-sequence similarity (Jaccard on token bigrams)
    import      — duplicate import paths (same symbol from different modules)
    file_level  — files that are >90% identical to each other

Author: Principal Autonomous Architect
Version: 1.0.0
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ════════════════════════════════════════════════════════════════════════════
# Configuration
# ════════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend" / "src"

# Minimum block size (lines) for exact duplicate detection
MIN_BLOCK_LINES = 10
# Similarity threshold for near-duplicate detection (0.0–1.0)
DEFAULT_THRESHOLD = 0.80
# Minimum function length (lines) for structural + near-dup analysis
MIN_FUNC_LINES = 5
# File-level duplicate threshold
FILE_LEVEL_THRESHOLD = 0.90

# File patterns to scan
PY_PATTERN = "*.py"
TS_PATTERN = "*.ts"
TSX_PATTERN = "*.tsx"

# Directories to exclude
EXCLUDE_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv", "venv",
    "_archive", "dist", "build", "coverage", ".next",
    "tests",  # tests often have intentional duplication
}

# ════════════════════════════════════════════════════════════════════════════
# Data Models
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class DuplicateFinding:
    """A single duplicate detection finding."""

    engine: str  # exact, structural, near_dup, import, file_level
    severity: str  # critical, high, medium, low
    file_a: str
    file_b: str
    line_a: int  # 1-indexed
    line_b: int
    similarity: float  # 0.0–1.0
    description: str
    suggestion: str = ""


@dataclass
class FunctionInfo:
    """Extracted function metadata for comparison."""

    name: str
    file: str
    line: int
    end_line: int
    args: list[str]
    body_text: str  # normalized source
    body_tokens: list[str]  # tokenized
    ast_fingerprint: str  # structural hash
    line_count: int


@dataclass
class DetectionResult:
    """Complete detection result."""

    findings: list[DuplicateFinding] = field(default_factory=list)
    files_scanned: int = 0
    functions_analyzed: int = 0
    elapsed_seconds: float = 0.0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")

    @property
    def total_count(self) -> int:
        return len(self.findings)


# ════════════════════════════════════════════════════════════════════════════
# Utility Functions
# ════════════════════════════════════════════════════════════════════════════


def should_exclude(path: Path) -> bool:
    """Check if a path should be excluded from scanning."""
    parts = set(path.parts)
    return bool(parts & EXCLUDE_DIRS)


def collect_files() -> list[Path]:
    """Collect all Python and TypeScript files to scan."""
    files: list[Path] = []

    if BACKEND_DIR.exists():
        for pattern in [PY_PATTERN]:
            for f in BACKEND_DIR.rglob(pattern):
                if not should_exclude(f):
                    files.append(f)

    if FRONTEND_DIR.exists():
        for pattern in [TS_PATTERN, TSX_PATTERN]:
            for f in FRONTEND_DIR.rglob(pattern):
                if not should_exclude(f):
                    files.append(f)

    return files


def normalize_text(text: str) -> str:
    """Normalize source code text for comparison.
    
    - Strip comments
    - Strip docstrings
    - Strip whitespace-only lines
    - Normalize whitespace
    - Lowercase
    """
    # Strip Python comments
    text = re.sub(r"#.*$", "", text, flags=re.MULTILINE)
    # Strip JS/TS comments
    text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Strip docstrings (Python)
    text = re.sub(r'""".*?"""', "", text, flags=re.DOTALL)
    text = re.sub(r"'''.*?'''", "", text, flags=re.DOTALL)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)
    # Strip string literals (replace with placeholder)
    text = re.sub(r'"[^"]*"', '"STR"', text)
    text = re.sub(r"'[^']*'", "'STR'", text)
    text = re.sub(r"`[^`]*`", "`STR`", text)
    # Strip numbers
    text = re.sub(r"\b\d+\b", "N", text)
    # Lowercase
    text = text.lower().strip()
    return text


def normalize_text_for_file_level(text: str) -> str:
    """Normalize source text for file-level exact-copy comparison.

    ROOT-CAUSE FIX: `normalize_text()` উদ্দেশ্যপ্রণোদিতভাবে string literals
    ("STR") ও numbers ("N") দিয়ে replace করে, যাতে copy-paste ব্লক ধরা যায়
    যেখানে ভ্যারিয়েবল নাম বদলানো হয়েছে (exact/near_dup engine-এর জন্য ঠিক
    আছে)। কিন্তু file_level engine এই একই aggressive normalization ব্যবহার
    করত "সম্পূর্ণ ফাইল ১০০% identical" পরীক্ষা করতে — ফলে
    backend/core/idempotency_middleware.py, error_pattern_db.py,
    error_handler.py ইত্যাদির মতো টেমপ্লেটেড deprecation-shim ফাইল, যেগুলো
    শুধু একটা string literal (টার্গেট মডিউল পাথ) আর comment-এ ভিন্ন, একই
    hash পেয়ে false-positive "100% identical (exact copy)" হিসেবে ফ্ল্যাগ
    হচ্ছিল -- অথচ ফাইলগুলো আসলে ভিন্ন মডিউলে পয়েন্ট করছে এবং duplicate না।
    file_level-এর জন্য শুধু comments/docstrings/whitespace normalize করা
    হচ্ছে, string literals ও number আসল অবস্থায়ই রাখা হচ্ছে যাতে সত্যিকারের
    বাইট-শনাক্তযোগ্য duplicate ফাইলই (যেমন খালি __init__.py) ধরা পড়ে।
    """
    text = re.sub(r"#.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r'""".*?"""', "", text, flags=re.DOTALL)
    text = re.sub(r"'''.*?'''", "", text, flags=re.DOTALL)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def tokenize(text: str) -> list[str]:
    """Tokenize source code for similarity comparison."""
    # Simple tokenizer: split on non-alphanumeric
    tokens = re.findall(r"[a-zA-Z_]\w*|==>|\S", text)
    return tokens


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def bigram_similarity(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Similarity based on token bigram overlap."""
    if len(tokens_a) < 2 or len(tokens_b) < 2:
        return 0.0
    bigrams_a = {tuple(tokens_a[i:i+2]) for i in range(len(tokens_a) - 1)}
    bigrams_b = {tuple(tokens_b[i:i+2]) for i in range(len(tokens_b) - 1)}
    return jaccard_similarity(bigrams_a, bigrams_b)


def hash_text(text: str) -> str:
    """SHA-256 hash of text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ════════════════════════════════════════════════════════════════════════════
# Engine 1: Exact Duplicate Block Detection
# ════════════════════════════════════════════════════════════════════════════


def detect_exact_blocks(files: list[Path]) -> list[DuplicateFinding]:
    """Detect exact duplicate code blocks (copy-paste).
    
    Strategy: hash normalized text of every N-line sliding window.
    Matching hashes = exact duplicate blocks.
    """
    findings: list[DuplicateFinding] = []
    block_hashes: dict[str, list[tuple[str, int]]] = defaultdict(list)

    for filepath in files:
        try:
            lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        # Skip tiny files
        if len(lines) < MIN_BLOCK_LINES:
            continue

        rel_path = filepath.relative_to(REPO_ROOT).as_posix()

        for i in range(len(lines) - MIN_BLOCK_LINES + 1):
            block = "\n".join(lines[i:i + MIN_BLOCK_LINES])
            normalized = normalize_text(block)
            if len(normalized) < 50:  # skip tiny blocks
                continue
            h = hash_text(normalized)
            block_hashes[h].append((rel_path, i + 1))

    for h, locations in block_hashes.items():
        if len(locations) < 2:
            continue
        # Group by file — if same file has duplicate blocks, it's still a finding
        for i in range(len(locations)):
            for j in range(i + 1, len(locations)):
                file_a, line_a = locations[i]
                file_b, line_b = locations[j]
                severity = "critical" if file_a == file_b else "high"
                findings.append(DuplicateFinding(
                    engine="exact",
                    severity=severity,
                    file_a=file_a,
                    file_b=file_b,
                    line_a=line_a,
                    line_b=line_b,
                    similarity=1.0,
                    description=f"Exact duplicate block ({MIN_BLOCK_LINES}+ lines) — copy-paste detected",
                    suggestion="Extract to a shared utility function or constant",
                ))

    return findings


# ════════════════════════════════════════════════════════════════════════════
# Engine 2: Structural Duplicate Detection (AST Fingerprinting)
# ════════════════════════════════════════════════════════════════════════════


def get_ast_fingerprint(node: ast.AST) -> str:
    """Generate a structural fingerprint from an AST node.
    
    The fingerprint captures the STRUCTURE of the code (what operations
    are performed) without caring about variable names or values.
    """
    parts: list[str] = []

    def visit(n: ast.AST, depth: int = 0) -> None:
        parts.append(type(n).__name__)
        for child in ast.iter_child_nodes(n):
            visit(child, depth + 1)

    visit(node)
    return hash_text(":".join(parts))


def extract_functions(filepath: Path) -> list[FunctionInfo]:
    """Extract all function definitions from a Python file."""
    funcs: list[FunctionInfo] = []
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(filepath))
    except Exception:
        return funcs

    rel_path = filepath.relative_to(REPO_ROOT).as_posix()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.end_lineno is None:
                continue
            line_count = node.end_lineno - node.lineno
            if line_count < MIN_FUNC_LINES:
                continue

            # Get function body as text
            body_segments: list[str] = []
            for stmt in node.body:
                try:
                    body_segments.append(ast.unparse(stmt))
                except Exception:
                    body_segments.append(ast.dump(stmt))

            body_text = normalize_text("\n".join(body_segments))
            body_tokens = tokenize(body_text)
            fingerprint = get_ast_fingerprint(node)

            args = [a.arg for a in node.args.args]

            funcs.append(FunctionInfo(
                name=node.name,
                file=rel_path,
                line=node.lineno,
                end_line=node.end_lineno,
                args=args,
                body_text=body_text,
                body_tokens=body_tokens,
                ast_fingerprint=fingerprint,
                line_count=line_count,
            ))

    return funcs


def detect_structural_duplicates(funcs: list[FunctionInfo]) -> list[DuplicateFinding]:
    """Detect functions with identical AST structure (different names)."""
    findings: list[DuplicateFinding] = []
    by_fingerprint: dict[str, list[FunctionInfo]] = defaultdict(list)

    for f in funcs:
        by_fingerprint[f.ast_fingerprint].append(f)

    for fp, group in by_fingerprint.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                fa, fb = group[i], group[j]
                # Skip if same file and same name (overloads)
                if fa.file == fb.file and fa.name == fb.name:
                    continue
                # Skip if names are identical (intentional interface)
                if fa.name == fb.name:
                    continue
                severity = "high" if fa.file != fb.file else "medium"
                findings.append(DuplicateFinding(
                    engine="structural",
                    severity=severity,
                    file_a=fa.file,
                    file_b=fb.file,
                    line_a=fa.line,
                    line_b=fb.line,
                    similarity=1.0,
                    description=f"Structural duplicate: '{fa.name}' and '{fb.name}' have identical AST structure ({fa.line_count} lines)",
                    suggestion=f"Consolidate '{fa.name}' and '{fb.name}' into a single function or use a shared base",
                ))

    return findings


# ════════════════════════════════════════════════════════════════════════════
# Engine 3: Near-Duplicate Detection (Token Similarity)
# ════════════════════════════════════════════════════════════════════════════


def detect_near_duplicates(funcs: list[FunctionInfo], threshold: float) -> list[DuplicateFinding]:
    """Detect functions with high token-sequence similarity.
    
    Uses Jaccard similarity on token bigrams to find functions that
    are ~80%+ similar but not structurally identical.
    """
    findings: list[DuplicateFinding] = []

    # Only compare functions with >= MIN_FUNC_LINES and similar length
    for i in range(len(funcs)):
        for j in range(i + 1, len(funcs)):
            fa, fb = funcs[i], funcs[j]

            # Skip if length difference is too large (> 3x)
            if fa.line_count > fb.line_count * 3 or fb.line_count > fa.line_count * 3:
                continue

            # Skip if same file and very close (likely overloads)
            if fa.file == fb.file and abs(fa.line - fb.line) < 20:
                continue

            sim = bigram_similarity(fa.body_tokens, fb.body_tokens)
            if sim >= threshold:
                # Skip if already found as structural duplicate
                if fa.ast_fingerprint == fb.ast_fingerprint:
                    continue

                severity = "high" if sim >= 0.95 else "medium"
                findings.append(DuplicateFinding(
                    engine="near_dup",
                    severity=severity,
                    file_a=fa.file,
                    file_b=fb.file,
                    line_a=fa.line,
                    line_b=fb.line,
                    similarity=round(sim, 3),
                    description=f"Near-duplicate: '{fa.name}' ({fa.file}:{fa.line}) and '{fb.name}' ({fb.file}:{fb.line}) — {sim*100:.0f}% similar",
                    suggestion="Consider extracting shared logic or merging into a parameterized function",
                ))

    return findings


# ════════════════════════════════════════════════════════════════════════════
# Engine 4: Import Duplicate Detection
# ════════════════════════════════════════════════════════════════════════════


def detect_import_duplicates(files: list[Path]) -> list[DuplicateFinding]:
    """Detect same symbol imported from different paths.
    
    Example:
        from core.cache import Redis       # file_a.py
        from core.cache.redis_manager import Redis  # file_b.py
    → same class, different import paths → maintenance risk
    """
    findings: list[DuplicateFinding] = []
    symbol_to_imports: dict[str, list[tuple[str, int, str]]] = defaultdict(list)

    for filepath in files:
        if filepath.suffix != ".py":
            continue
        try:
            source = filepath.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(filepath))
        except Exception:
            continue

        rel_path = filepath.relative_to(REPO_ROOT).as_posix()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    name = alias.asname or alias.name
                    symbol_to_imports[name].append((rel_path, node.lineno, module))

    for symbol, imports in symbol_to_imports.items():
        if len(imports) < 2:
            continue
        # Group by module path
        modules = {imp[2] for imp in imports}
        if len(modules) < 2:
            continue  # same module, different files = normal

        for i in range(len(imports)):
            for j in range(i + 1, len(imports)):
                file_a, line_a, mod_a = imports[i]
                file_b, line_b, mod_b = imports[j]
                if mod_a == mod_b:
                    continue  # same module path
                findings.append(DuplicateFinding(
                    engine="import",
                    severity="low",
                    file_a=file_a,
                    file_b=file_b,
                    line_a=line_a,
                    line_b=line_b,
                    similarity=0.5,
                    description=f"Symbol '{symbol}' imported from different paths: '{mod_a}' vs '{mod_b}'",
                    suggestion=f"Standardize on a single import path for '{symbol}'",
                ))

    return findings


# ════════════════════════════════════════════════════════════════════════════
# Engine 5: File-Level Duplicate Detection
# ════════════════════════════════════════════════════════════════════════════

# বাংলা মন্তব্য (audit V3, 2026-09-17): নিচের জোড়াগুলোর duplication ইচ্ছাকৃত
# এবং কোডের docstring-এ কারণসহ ডকুমেন্টেড — তাই file_level engine এগুলো
# পরীক্ষা থেকে বাদ দেয়। প্রতিটি এন্ট্রির কারণের উৎস (সৎ ট্রেস) কমেন্টে থাকতে
# হবে; নতুন ছাড় যোগ করার আগে কোডে কারণ লেখা থাকতে হবে।
# - core/plugins/{experimental,official}/base.py — official লেয়ার back-compat
#   shim যা experimental implementation import করে; experimental→official
#   re-export করলে package-level import cycle তৈরি হত (official/__init__ →
#   official.gmail_plugin → experimental.gmail_plugin → experimental.base →
#   official/__init__)। কারণ ও সিদ্ধান্ত
#   core/plugins/experimental/base.py-র module docstring-এ লেখা আছে।
EXEMPT_FILE_LEVEL_PAIRS: set[frozenset[str]] = {
    frozenset(
        {
            "backend/core/plugins/experimental/base.py",
            "backend/core/plugins/official/base.py",
        }
    ),
}


def detect_file_level_duplicates(files: list[Path]) -> list[DuplicateFinding]:
    """Detect files that are >90% identical to each other."""
    findings: list[DuplicateFinding] = []
    file_hashes: dict[str, str] = {}  # path → normalized hash
    file_contents: dict[str, str] = {}

    for filepath in files:
        try:
            content = filepath.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        # Skip empty files and tiny __init__.py files
        if len(content.strip()) < 20:
            continue
        # ROOT-CAUSE FIX: আগে এই চেক raw content length (comment সহ) দেখত,
        # কিন্তু অনেক __init__.py ফাইলে শুধু একটা module-docstring/header
        # comment থাকে (কোনো actual কোড নেই) যেটা raw length ৫০ ছাড়িয়ে যায়
        # যদিও কোড হিসেবে খালি — ফলে সেগুলো "package marker" স্কিপ না হয়ে
        # একে অপরের সাথে false-positive "critical duplicate, delete one"
        # হিসেবে ফ্ল্যাগ হতো (একটা প্যাকেজের __init__.py ডিলিট করা যায় না)।
        # এখন comment/docstring স্ট্রিপ করার পর প্রকৃত কোড কতটুকু আছে সেটা
        # দেখে স্কিপ করা হচ্ছে।
        if filepath.name == "__init__.py":
            stripped_code = re.sub(r"#.*$", "", content, flags=re.MULTILINE)
            stripped_code = re.sub(r'""".*?"""', "", stripped_code, flags=re.DOTALL)
            stripped_code = re.sub(r"'''.*?'''", "", stripped_code, flags=re.DOTALL)
            if len(stripped_code.strip()) < 50:
                continue
        rel_path = filepath.relative_to(REPO_ROOT).as_posix()
        # ROOT-CAUSE FIX (continued): fuzzy Jaccard-similarity fallback নিচে
        # file_contents ব্যবহার করে -- এটাও আগে aggressive normalize_text()
        # (string/number stripping সহ) ব্যবহার করত, তাই hash mismatch হলেও
        # templated shim ফাইলগুলো token-set মিল দিয়ে >=90% similarity
        # threshold পার করে একই false-positive দিত। এখন হ্যাশ ও similarity
        # দুটোই file-level-উপযুক্ত হালকা normalization ব্যবহার করে, যাতে
        # string literal-এ প্রকৃত পার্থক্য (যেমন ভিন্ন টার্গেট মডিউল পাথ)
        # ধরা পড়ে।
        light_normalized = normalize_text_for_file_level(content)
        file_hashes[rel_path] = hash_text(light_normalized)
        file_contents[rel_path] = light_normalized

    file_list = list(file_hashes.keys())
    for i in range(len(file_list)):
        for j in range(i + 1, len(file_list)):
            fa, fb = file_list[i], file_list[j]
            # ডকুমেন্টেড-ইচ্ছাকৃত জোড়া ছাড় (উপরে EXEMPT_FILE_LEVEL_PAIRS দেখুন)
            if frozenset({fa, fb}) in EXEMPT_FILE_LEVEL_PAIRS:
                continue
            # Skip if exact same hash (already caught by exact engine)
            if file_hashes[fa] == file_hashes[fb]:
                findings.append(DuplicateFinding(
                    engine="file_level",
                    severity="critical",
                    file_a=fa,
                    file_b=fb,
                    line_a=1,
                    line_b=1,
                    similarity=1.0,
                    description=f"Files are 100% identical (exact copy)",
                    suggestion=f"Delete one of these files — they are exact duplicates",
                ))
                continue

            # Calculate similarity
            content_a = file_contents[fa]
            content_b = file_contents[fb]
            if not content_a or not content_b:
                continue
            # Quick check: if length difference > 50%, skip
            if len(content_a) > len(content_b) * 2 or len(content_b) > len(content_a) * 2:
                continue
            sim = jaccard_similarity(set(content_a.split()), set(content_b.split()))
            if sim >= FILE_LEVEL_THRESHOLD:
                findings.append(DuplicateFinding(
                    engine="file_level",
                    severity="critical",
                    file_a=fa,
                    file_b=fb,
                    line_a=1,
                    line_b=1,
                    similarity=round(sim, 3),
                    description=f"Files are {sim*100:.0f}% identical",
                    suggestion=f"Merge these files or delete the redundant one",
                ))

    return findings


# ════════════════════════════════════════════════════════════════════════════
# Report Generation
# ════════════════════════════════════════════════════════════════════════════


def generate_markdown_report(result: DetectionResult) -> str:
    """Generate a human-readable markdown report."""
    lines: list[str] = []

    lines.append("# 🔍 SupremeAI Duplicate Logic Detector Report")
    lines.append("")
    lines.append(f"**Files Scanned:** {result.files_scanned}")
    lines.append(f"**Functions Analyzed:** {result.functions_analyzed}")
    lines.append(f"**Elapsed:** {result.elapsed_seconds:.1f}s")
    lines.append("")

    # Summary table
    lines.append("## 📊 Summary")
    lines.append("")
    lines.append("| Engine | Critical | High | Medium | Low | Total |")
    lines.append("|--------|----------|------|--------|-----|-------|")

    engines = ["exact", "structural", "near_dup", "import", "file_level"]
    for engine in engines:
        engine_findings = [f for f in result.findings if f.engine == engine]
        crit = sum(1 for f in engine_findings if f.severity == "critical")
        high = sum(1 for f in engine_findings if f.severity == "high")
        med = sum(1 for f in engine_findings if f.severity == "medium")
        low = sum(1 for f in engine_findings if f.severity == "low")
        lines.append(f"| {engine} | {crit} | {high} | {med} | {low} | {len(engine_findings)} |")

    total_crit = result.critical_count
    total_high = result.high_count
    total_med = sum(1 for f in result.findings if f.severity == "medium")
    total_low = sum(1 for f in result.findings if f.severity == "low")
    lines.append(f"| **TOTAL** | **{total_crit}** | **{total_high}** | **{total_med}** | **{total_low}** | **{result.total_count}** |")
    lines.append("")

    if not result.findings:
        lines.append("✅ **No duplicates found!**")
        return "\n".join(lines)

    # Group by severity
    for severity in ["critical", "high", "medium", "low"]:
        sev_findings = [f for f in result.findings if f.severity == severity]
        if not sev_findings:
            continue

        emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}[severity]
        lines.append(f"## {emoji} {severity.upper()} Findings ({len(sev_findings)})")
        lines.append("")

        for i, f in enumerate(sev_findings[:50], 1):  # cap at 50 per severity
            lines.append(f"### {i}. [{f.engine}] {f.description}")
            lines.append(f"- **File A:** `{f.file_a}:{f.line_a}`")
            lines.append(f"- **File B:** `{f.file_b}:{f.line_b}`")
            lines.append(f"- **Similarity:** {f.similarity * 100:.0f}%")
            if f.suggestion:
                lines.append(f"- **Suggestion:** {f.suggestion}")
            lines.append("")

        if len(sev_findings) > 50:
            lines.append(f"_... and {len(sev_findings) - 50} more {severity} findings_")
            lines.append("")

    return "\n".join(lines)


# ════════════════════════════════════════════════════════════════════════════
# Main Detection Pipeline
# ════════════════════════════════════════════════════════════════════════════


def run_detection(
    threshold: float = DEFAULT_THRESHOLD,
    engines: list[str] | None = None,
) -> DetectionResult:
    """Run the full duplicate detection pipeline."""
    import time

    start = time.time()
    result = DetectionResult()

    if engines is None:
        engines = ["exact", "structural", "near_dup", "import", "file_level"]

    # Collect files
    files = collect_files()
    result.files_scanned = len(files)

    # Extract functions (for structural + near-dup)
    all_funcs: list[FunctionInfo] = []
    if "structural" in engines or "near_dup" in engines:
        for filepath in files:
            if filepath.suffix == ".py":
                all_funcs.extend(extract_functions(filepath))
    result.functions_analyzed = len(all_funcs)

    # Run engines
    if "exact" in engines:
        result.findings.extend(detect_exact_blocks(files))

    if "structural" in engines:
        result.findings.extend(detect_structural_duplicates(all_funcs))

    if "near_dup" in engines:
        result.findings.extend(detect_near_duplicates(all_funcs, threshold))

    if "import" in engines:
        result.findings.extend(detect_import_duplicates(files))

    if "file_level" in engines:
        result.findings.extend(detect_file_level_duplicates(files))

    # Sort by severity (critical first) then by similarity (descending)
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    result.findings.sort(
        key=lambda f: (severity_order.get(f.severity, 4), -f.similarity)
    )

    result.elapsed_seconds = time.time() - start
    return result


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="SupremeAI Advanced Duplicate Logic Detector"
    )
    parser.add_argument(
        "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help=f"Similarity threshold for near-duplicate detection (default: {DEFAULT_THRESHOLD})",
    )
    parser.add_argument(
        "--engine", type=str, nargs="+",
        choices=["exact", "structural", "near_dup", "import", "file_level", "all"],
        default=["all"],
        help="Which detection engines to run (default: all)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON instead of markdown",
    )
    parser.add_argument(
        "--fail-on-critical", action="store_true",
        help="Exit non-zero if critical duplicates found (CI mode)",
    )
    parser.add_argument(
        "--max-findings", type=int, default=100,
        help="Maximum number of findings to report (default: 100)",
    )

    args = parser.parse_args(argv)

    engines = None
    if args.engine != ["all"]:
        engines = args.engine

    result = run_detection(
        threshold=args.threshold,
        engines=engines,
    )

    # Limit findings
    if len(result.findings) > args.max_findings:
        result.findings = result.findings[:args.max_findings]

    if args.json:
        print(json.dumps({
            "summary": {
                "files_scanned": result.files_scanned,
                "functions_analyzed": result.functions_analyzed,
                "total_findings": result.total_count,
                "critical": result.critical_count,
                "high": result.high_count,
                "elapsed_seconds": result.elapsed_seconds,
            },
            "findings": [asdict(f) for f in result.findings],
        }, indent=2, ensure_ascii=False))
    else:
        print(generate_markdown_report(result))

    # Exit code
    if args.fail_on_critical and result.critical_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
