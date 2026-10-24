#!/usr/bin/env python3
"""
SupremeAI Duplicate Logic Detector — অনুরূপ কোড সনাক্তকরণ
==================================================
AST-ভিত্তিক স্ট্রাকচারাল তুলনা ব্যবহার করে ডুপ্লিকেট ফাংশন ও ক্লাস খুঁজে বের করে।
শুধুমাত্র স্ট্যান্ডার্ড লাইব্রেরি ব্যবহার করে।

বেরিয়া কোড: ০ = পরিষ্কার, ১ = ডুপ্লিকেট পাওয়া গেছে, ২ = ত্রুটি
"""

import ast
import argparse
import copy
import hashlib
import json
import os
import sys
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ── বাদ দেওয়ার পথ প্যাটার্ন ──────────────────────────────────────────────
EXCLUDED_DIRS = {
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

EXCLUDED_SUFFIXES = {"_test.py", "_tests.py", "test_.py", "tests.py"}

# ── কেন্দ্রীয় প্যাকেজের অগ্রাধিকার ক্রম (বেশি কেন্দ্রীয় = বেশি অগ্রাধিকার) ───
CENTRALITY_RANK = {
    "core": 10,
    "models": 9,
    "services": 8,
    "utils": 7,
    "common": 6,
    "shared": 5,
    "lib": 4,
    "helpers": 3,
    "api": 2,
    "routers": 1,
}


class FuncInfo:
    """একটি ফাংশন/মেথডের বিশ্লেষণাত্মক তথ্য ধারণ করে।"""

    __slots__ = (
        "file",
        "line",
        "end_line",
        "name",
        "param_count",
        "param_names",
        "body_line_count",
        "structural_hash",
        "normalized_source",
        "body_lines",
        "has_docstring",
        "docstring_length",
        "is_method",
        "class_name",
        "qname",
    )

    def __init__(
        self,
        file: str,
        line: int,
        end_line: int,
        name: str,
        param_count: int,
        param_names: List[str],
        body_line_count: int,
        structural_hash: str,
        normalized_source: str,
        body_lines: List[str],
        has_docstring: bool,
        docstring_length: int,
        is_method: bool = False,
        class_name: Optional[str] = None,
    ):
        self.file = file
        self.line = line
        self.end_line = end_line
        self.name = name
        self.param_count = param_count
        self.param_names = param_names
        self.body_line_count = body_line_count
        self.structural_hash = structural_hash
        self.normalized_source = normalized_source
        self.body_lines = body_lines
        self.has_docstring = has_docstring
        self.docstring_length = docstring_length
        self.is_method = is_method
        self.class_name = class_name
        self.qname = f"{class_name}.{name}" if class_name else name

    def centrality_score(self) -> float:
        """ফাইলের প্যাকেজ কেন্দ্রীয়তার স্কোর বের করে।"""
        parts = Path(self.file).parts
        score = 0.0
        for part in parts:
            if part in CENTRALITY_RANK:
                score += CENTRALITY_RANK[part]
        # গভীরে থাকা ফাইল কম কেন্দ্রীয়
        score -= len(parts) * 0.5
        return score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "name": self.name,
            "qname": self.qname,
            "param_count": self.param_count,
            "param_names": self.param_names,
            "body_line_count": self.body_line_count,
            "structural_hash": self.structural_hash,
            "has_docstring": self.has_docstring,
            "docstring_length": self.docstring_length,
            "is_method": self.is_method,
            "class_name": self.class_name,
            "centrality": self.centrality_score(),
        }


class ClassInfo:
    """একটি ক্লাসের কাঠামোগত তথ্য ধারণ করে।"""

    __slots__ = (
        "file",
        "line",
        "name",
        "method_names",
        "method_count",
        "base_classes",
    )

    def __init__(
        self,
        file: str,
        line: int,
        name: str,
        method_names: List[str],
        base_classes: List[str],
    ):
        self.file = file
        self.line = line
        self.name = name
        self.method_names = sorted(method_names)
        self.method_count = len(method_names)
        self.base_classes = base_classes

    def structure_signature(self) -> str:
        """ক্লাস কাঠামোর একটি হ্যাশযোগ্য স্বাক্ষর তৈরি করে।"""
        sig = "|".join(self.method_names) + "||" + ",".join(self.base_classes)
        return hashlib.sha256(sig.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "name": self.name,
            "method_names": self.method_names,
            "method_count": self.method_count,
            "base_classes": self.base_classes,
            "structure_sig": self.structure_signature(),
        }


class ASTNormalizer(ast.NodeTransformer):
    """
    AST নোডকে স্ট্রাকচারালি নরমালাইজ করে — ভেরিয়েবলের নাম, স্ট্রিং লিটারেল,
    ডকস্ট্রিং ইত্যাদি প্লেসহোল্ডার দিয়ে প্রতিস্থাপন করে যাতে শুধু যুক্তিগত কাঠামো থাকে।
    """

    # ভেরিয়েবল নামের জন্য কাউন্টার
    _name_counter: Dict[str, int] = {}

    def _reset(self) -> None:
        ASTNormalizer._name_counter = {}

    def _anon_name(self, kind: str = "var") -> str:
        """একটি বেনামী প্লেসহোল্ডার নাম তৈরি করে (প্রতি ধরনে ইউনিক)।"""
        count = ASTNormalizer._name_counter.get(kind, 0)
        ASTNormalizer._name_counter[kind] = count + 1
        return f"_{kind}_{count}"

    def visit_Name(self, node: ast.Name) -> ast.Name:
        """সকল ভেরিয়েবল/ফাংশন নাম প্লেসহোল্ডারে পরিবর্তন করে।"""
        node.id = self._anon_name("v")
        self.generic_visit(node)
        return node

    def visit_arg(self, node: ast.arg) -> ast.arg:
        """প্যারামিটারের নাম প্লেসহোল্ডারে পরিবর্তন করে।"""
        node.arg = self._anon_name("p")
        self.generic_visit(node)
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        """স্ট্রিং, সংখ্যা ইত্যাদি লিটারেল নরমালাইজ করে।"""
        if isinstance(node.value, str):
            node.value = "__STR__"
        elif isinstance(node.value, (int, float)):
            node.value = 0
        elif isinstance(node.value, bytes):
            node.value = b"__BYTES__"
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """ফাংশন নাম প্লেসহোল্ডারে পরিবর্তন, ডকস্ট্রিং সরিয়ে দেয়।"""
        node.name = self._anon_name("func")
        # ডকস্ট্রিং অপসারণ
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body = node.body[1:]
        # ডেকোরেটর সরিয়ে দেয়
        node.decorator_list = []
        self.generic_visit(node)
        return node

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.ClassDef:
        """ক্লাস নাম ও বেস ক্লাস নরমালাইজ করে।"""
        node.name = self._anon_name("cls")
        node.decorator_list = []
        self.generic_visit(node)
        return node

    def visit_Attribute(self, node: ast.Attribute) -> ast.Attribute:
        """অ্যাট্রিবিউট নাম প্লেসহোল্ডারে পরিবর্তন করে।"""
        node.attr = self._anon_name("attr")
        self.generic_visit(node)
        return node

    def visit_Import(self, node: ast.Import) -> ast.Import:
        """ইম্পোর্ট স্টেটমেন্ট উপেক্ষা করে (খালি বডিতে রূপান্তর)।"""
        return ast.Pass()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:
        """ইম্পোর্ট-ফ্রম স্টেটমেন্ট উপেক্ষা করে।"""
        return ast.Pass()

    def visit_keyword(self, node: ast.keyword) -> ast.keyword:
        """কীওয়ার্ড আর্গুমেন্টের নাম প্লেসহোল্ডারে পরিবর্তন।"""
        node.arg = self._anon_name("kw")
        self.generic_visit(node)
        return node


def normalize_ast(node: ast.AST) -> str:
    """
    AST নোড নরমালাইজ করে এবং একটি স্ট্রাকচারাল হ্যাশ রিটার্ন করে।
    একই যুক্তিগত কাঠামোর ভিন্ন ভেরিয়েবল-নামের কোড একই হ্যাশ পাবে।
    """
    normalizer = ASTNormalizer()
    normalizer._reset()
    normalized = normalizer.visit(node)
    # ast.unparse ব্যবহার করে স্ট্রিং আউটপুট
    try:
        source = ast.unparse(normalized)
    except Exception:
        source = ast.dump(normalized)
    # সাদা জায়গা নরমালাইজ
    source = " ".join(source.split())
    return source


def compute_structural_hash(source: str) -> str:
    """নরমালাইজড উৎস থেকে SHA-২৫৬ হ্যাশের প্রথম ১৬ অক্ষর রিটার্ন করে।"""
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]


def is_test_file(filepath: str) -> bool:
    """ফাইলটি কি টেস্ট ফাইল কিনা তা যাচাই করে।"""
    basename = os.path.basename(filepath)
    for suffix in EXCLUDED_SUFFIXES:
        if basename.endswith(suffix) or basename.startswith("test_"):
            return True
    # পথে "test" বা "tests" ডিরেক্টরি থাকলে
    parts = Path(filepath).parts
    for part in parts:
        if part in ("tests", "test"):
            return True
    return False


def should_skip_dir(dirpath: str) -> bool:
    """ডিরেক্টরিটি এড়িয়ে যাওয়া উচিত কিনা যাচাই।"""
    dirname = os.path.basename(dirpath)
    return dirname in EXCLUDED_DIRS


def extract_source_lines(source: str, start_line: int, end_line: int) -> List[str]:
    """নির্দিষ্ট লাইন পরিসরের উৎস কোড বের করে।"""
    lines = source.splitlines()
    # AST লাইন নম্বর ১-ভিত্তিক
    return lines[start_line - 1 : end_line]


def get_param_info(func_node: ast.FunctionDef) -> Tuple[int, List[str]]:
    """ফাংশনের প্যারামিটার সংখ্যা ও নাম বের করে (self/cls বাদ দিয়ে)।"""
    params = []
    for arg in func_node.args.args:
        if arg.arg not in ("self", "cls"):
            params.append(arg.arg)
    # *args, **kwargs যোগ
    if func_node.args.vararg:
        params.append(f"*{func_node.args.vararg.arg}")
    if func_node.args.kwarg:
        params.append(f"**{func_node.args.kwarg.arg}")
    return len(params), params


def has_docstring(func_node: ast.FunctionDef) -> Tuple[bool, int]:
    """ফাংশনে ডকস্ট্রিং আছে কিনা ও তার দৈর্ঘ্য যাচাই।"""
    if (
        func_node.body
        and isinstance(func_node.body[0], ast.Expr)
        and isinstance(func_node.body[0].value, ast.Constant)
        and isinstance(func_node.body[0].value.value, str)
    ):
        return True, len(func_node.body[0].value.value)
    return False, 0


def get_end_line(node: ast.AST, source_lines: List[str]) -> int:
    """একটি AST নোডের শেষ লাইন নম্বর বের করে।"""
    if hasattr(node, "end_lineno") and node.end_lineno is not None:
        return node.end_lineno
    # ফলব্যাক: চিলড্রেন থেকে সর্বোচ্চ লাইন খোঁজা
    max_line = node.lineno if hasattr(node, "lineno") else 0
    for child in ast.walk(node):
        if hasattr(child, "lineno") and child.lineno:
            max_line = max(max_line, child.lineno)
        if hasattr(child, "end_lineno") and child.end_lineno:
            max_line = max(max_line, child.end_lineno)
    return max_line


def extract_functions_from_file(filepath: str) -> Tuple[List[FuncInfo], List[ClassInfo]]:
    """
    একটি পাইথন ফাইল থেকে সকল ফাংশন ও ক্লাসের তথ্য বের করে।
    ফাংশন, অ্যাসিঙ্ক ফাংশন এবং ক্লাস মেথড সব অন্তর্ভুক্ত।
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (OSError, IOError) as e:
        print(f"  ⚠ ফাইল পড়তে সমস্যা: {filepath}: {e}", file=sys.stderr)
        return [], []

    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        # সিনট্যাক্স ত্রুটি থাকলে এড়িয়ে যাওয়া
        return [], []

    source_lines = source.splitlines()
    funcs: List[FuncInfo] = []
    classes: List[ClassInfo] = []

    def process_function(node: ast.FunctionDef, class_name: Optional[str] = None) -> None:
        """একটি ফাংশন/মেথড প্রক্রিয়া করে।"""
        # নরমালাইজের আগে মূল নাম সংরক্ষণ (নরমালাইজার AST মিউটেট করে)
        original_name = node.name
        param_count, param_names = get_param_info(node)
        doc, doc_len = has_docstring(node)
        end_ln = get_end_line(node, source_lines)
        body_lines = extract_source_lines(source, node.lineno, end_ln)
        body_line_count = end_ln - node.lineno + 1

        # নরমালাইজ কপি ব্যবহার করে যাতে মূল নোড নষ্ট না হয়
        node_copy = copy.deepcopy(node)
        normalized = normalize_ast(node_copy)
        struct_hash = compute_structural_hash(normalized)

        is_method = class_name is not None
        info = FuncInfo(
            file=filepath,
            line=node.lineno,
            end_line=end_ln,
            name=original_name,
            param_count=param_count,
            param_names=param_names,
            body_line_count=body_line_count,
            structural_hash=struct_hash,
            normalized_source=normalized,
            body_lines=body_lines,
            has_docstring=doc,
            docstring_length=doc_len,
            is_method=is_method,
            class_name=class_name,
        )
        funcs.append(info)

    def process_class(node: ast.ClassDef) -> None:
        """একটি ক্লাস ও তার মেথড প্রক্রিয়া করে।"""
        method_names = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # ডান্ডার মেথড বাদ (বেশিরভাগ ক্ষেত্রে বোকা তুলনা এড়াতে)
                if not item.name.startswith("__"):
                    method_names.append(item.name)
                process_function(item, class_name=node.name)

        base_names = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.append(base.attr)

        classes.append(
            ClassInfo(
                file=filepath,
                line=node.lineno,
                name=node.name,
                method_names=method_names,
                base_classes=base_names,
            )
        )

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            process_function(node)
        elif isinstance(node, ast.ClassDef):
            process_class(node)

    return funcs, classes


def collect_all_py_files(root: str) -> List[str]:
    """রুট ডিরেক্টরি থেকে সকল প্রাসঙ্গিক .py ফাইল সংগ্রহ করে।"""
    py_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # বাদ দেওয়ার ডিরেক্টরি ফিল্টার
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(dirpath, fname)
            if is_test_file(fpath):
                continue
            py_files.append(fpath)
    return py_files


# ══════════════════════════════════════════════════════════════════════════════
# ডুপ্লিকেট সনাক্তকরণের কৌশল
# ══════════════════════════════════════════════════════════════════════════════


def detect_exact_structural_hash(
    funcs: List[FuncInfo],
) -> List[List[FuncInfo]]:
    """
    কৌশল ১: সঠিক স্ট্রাকচারাল হ্যাশ ম্যাচ।
    একই AST কঙ্কাল (ভেরিয়েবলের নাম পরিবর্তিত হলেও একই যুক্তি)।
    """
    hash_groups: Dict[str, List[FuncInfo]] = defaultdict(list)
    for f in funcs:
        hash_groups[f.structural_hash].append(f)
    # শুধু একাধিক সদস্যের গ্রুপ রিটার্ন
    return [group for group in hash_groups.values() if len(group) > 1]


def detect_similar_signature(
    funcs: List[FuncInfo], min_lines: int
) -> List[List[FuncInfo]]:
    """
    কৌশল ২: সদৃশ ফাংশন স্বাক্ষর।
    একই প্যারামিটারের নাম/ধরন + অনুরূপ বডি আকার।
    """
    # প্যারামিটার নামের একটি স্বাক্ষর তৈরি (ক্রম সংরক্ষণ করে)
    sig_groups: Dict[str, List[FuncInfo]] = defaultdict(list)
    for f in funcs:
        if f.body_line_count < min_lines:
            continue
        # প্যারামিটারের স্বাক্ষর: ক্রমসজ্জিত নাম + গণনা
        param_key = f"{f.param_count}:{','.join(sorted(f.param_names))}"
        # বডির আকার গ্রুপিং (±৩০% টলারেন্স)
        size_bucket = max(1, f.body_line_count // 5)  # ৫ লাইনের বাকেট
        key = f"{param_key}|{size_bucket}"
        sig_groups[key].append(f)

    results = []
    for group in sig_groups.values():
        if len(group) < 2:
            continue
        # একই ফাইলের গ্রুপ বাদ দেওয়া
        files_seen = set()
        unique_group = []
        for f in group:
            if f.file not in files_seen:
                files_seen.add(f.file)
                unique_group.append(f)
        if len(unique_group) > 1:
            results.append(unique_group)
    return results


def detect_similar_class_structure(
    classes: List[ClassInfo],
) -> List[List[ClassInfo]]:
    """
    কৌশল ৩: সদৃশ ক্লাস কাঠামো।
    একই মেথড নাম ও অনুরূপ মেথড সংখ্যার ক্লাস।
    """
    sig_groups: Dict[str, List[ClassInfo]] = defaultdict(list)
    for c in classes:
        if c.method_count < 2:  # অতি ছোট ক্লাস এড়ানো
            continue
        sig = c.structure_signature()
        sig_groups[sig].append(c)

    results = []
    for group in sig_groups.values():
        if len(group) < 2:
            continue
        # একই ফাইলের ক্লাস বাদ
        files_seen = set()
        unique_group = []
        for c in group:
            if c.file not in files_seen:
                files_seen.add(c.file)
                unique_group.append(c)
        if len(unique_group) > 1:
            results.append(unique_group)
    return results


def line_overlap_ratio(lines_a: List[str], lines_b: List[str]) -> float:
    """
    দুটি লাইন তালিকার মধ্যে সাবস্ট্রিং ভিত্তিক ওভারল্যাপ অনুপাত বের করে।
    প্রতিটি লাইন নরমালাইজ করে (ট্রিম, ছোট হাতের) তুলনা করা হয়।
    """
    if not lines_a or not lines_b:
        return 0.0

    norm_a = [line.strip().lower() for line in lines_a if line.strip()]
    norm_b = [line.strip().lower() for line in lines_b if line.strip()]

    if not norm_a or not norm_b:
        return 0.0

    # ছোট তালিকাটি বড় তালিকার মধ্যে সাবস্ট্রিং কিনা যাচাই
    shorter, longer = (norm_a, norm_b) if len(norm_a) <= len(norm_b) else (norm_b, norm_a)

    # স্লাইডিং উইন্ডো দিয়ে সর্বোচ্চ ম্যাচ খোঁজা
    max_matches = 0
    window_size = len(shorter)

    for i in range(len(longer) - window_size + 1):
        window = longer[i : i + window_size]
        matches = sum(1 for a, b in zip(shorter, window) if a == b)
        max_matches = max(max_matches, matches)

    # ছোট ফাংশনের ক্ষেত্রে সরাসরি তুলনাও করা হয়
    if len(norm_a) == len(norm_b):
        direct_matches = sum(1 for a, b in zip(norm_a, norm_b) if a == b)
        max_matches = max(max_matches, direct_matches)

    # ছোট তালিকার দৈর্ঘ্যের সাপেক্ষে অনুপাত
    return max_matches / len(shorter) if shorter else 0.0


def detect_substring_body_similarity(
    funcs: List[FuncInfo], min_lines: int, threshold: float
) -> List[List[FuncInfo]]:
    """
    কৌশল ৪: সাবস্ট্রিং বডি সাদৃশ্য।
    একটি ফাংশনের বডি অন্যটির প্রায় সাবস্ট্রিং হলে (>৮০% ওভারল্যাপ)।
    লাইন-সংখ্যার বাকেট গ্রুপিং করে O(N^2) ওভারহেড এড়ানো হয়েছে।
    """
    # শুধু ন্যূনতম লাইনের ফাংশন
    candidates = [f for f in funcs if f.body_line_count >= min_lines]
    if not candidates:
        return []

    # লাইন সংখ্যার ভিত্তিতে সাজানো
    candidates.sort(key=lambda f: f.body_line_count)

    seen_pairs: Set[Tuple[str, str]] = set()
    results: List[List[FuncInfo]] = []

    # স্লাইডিং উইন্ডো: শুধুমাত্র কাছাকাছি দৈর্ঘ্যের ফাংশনগুলো তুলনা করা (দৈর্ঘ্যের অনুপাত threshold-এর নিচে হলে সম্ভব নয়)
    for i in range(len(candidates)):
        a = candidates[i]
        len_a = a.body_line_count
        max_len = int(len_a / threshold) if threshold > 0 else len_a

        for j in range(i + 1, len(candidates)):
            b = candidates[j]
            if b.body_line_count > max_len:
                # b অনেক বেশি দীর্ঘ — আর কোনো ম্যাচ সম্ভব নয়
                break

            if a.file == b.file:
                continue
            if a.structural_hash == b.structural_hash:
                continue

            pair_key = tuple(sorted((a.qname + a.file, b.qname + b.file)))
            if pair_key in seen_pairs:
                continue

            overlap = line_overlap_ratio(a.body_lines, b.body_lines)
            if overlap >= threshold:
                seen_pairs.add(pair_key)
                results.append([a, b])

    return results


# ══════════════════════════════════════════════════════════════════════════════
# ক্যানোনিকাল নির্বাচন ও তীব্রতা নির্ধারণ
# ══════════════════════════════════════════════════════════════════════════════


def choose_canonical(group: List[FuncInfo]) -> FuncInfo:
    """
    একটি গ্রুপ থেকে ক্যানোনিকাল (রাখার উপযুক্ত) সদস্য বেছে নেয়।
    অগ্রাধিকার: বেশি কেন্দ্রীয় প্যাকেজ > ভালো ডকস্ট্রিং > দীর্ঘ নাম > প্রথম।
    """
    best = group[0]
    best_score = _canonical_score(best)

    for f in group[1:]:
        score = _canonical_score(f)
        if score > best_score:
            best = f
            best_score = score

    return best


def _canonical_score(f: FuncInfo) -> float:
    """ক্যানোনিকাল স্কোর গণনা: যত বেশি, তত রাখার উপযুক্ত।"""
    score = 0.0
    # কেন্দ্রীয়তা
    score += f.centrality_score() * 2.0
    # ডকস্ট্রিং
    if f.has_docstring:
        score += 5.0
        score += min(f.docstring_length / 20.0, 5.0)  # দীর্ঘ ডকস্ট্রিং বোনাস
    # নামের দৈর্ঘ্য (বর্ণনামূলক নাম ভালো)
    score += min(len(f.name) * 0.3, 3.0)
    # ফাংশন নামে আন্ডারস্কোর কম থাকলে পাবলিক API
    if not f.name.startswith("_"):
        score += 2.0
    return score


def severity_for_group(
    group: List[FuncInfo], strategy: str
) -> Tuple[str, str]:
    """
    ডুপ্লিকেট গ্রুপের তীব্রতা নির্ধারণ করে।
    রিটার্ন: (ইমোজি, বাংলা বর্ণনা)
    """
    if strategy == "exact_hash":
        # ভিন্ন নাম থাকলে বেশি গুরুতর
        names = {f.name for f in group}
        if len(names) > 1:
            return (
                "🔴",
                "অভিন্ন যুক্তি, ভিন্ন নাম — সম্ভবত কপি-পেস্ট",
            )
        return (
            "🔴",
            "অভিন্ন স্ট্রাকচারাল হ্যাশ — একই যুক্তি পুনরায় লেখা",
        )
    elif strategy == "similar_signature":
        return (
            "🟡",
            "সদৃশ স্বাক্ষর ও আকার — সম্ভবত ইচ্ছাকৃত অনুকরণ",
        )
    elif strategy == "similar_class":
        return (
            "🟡",
            "সদৃশ ক্লাস কাঠামো — একই মেথড নাম ও সংখ্যা",
        )
    elif strategy == "substring":
        return (
            "🟢",
            "সামান্য বডি ওভারল্যাপ — সম্ভবত সাধারণ প্যাটার্ন",
        )
    return ("🟢", "অজানা সাদৃশ্য")


def choose_canonical_class(group: List[ClassInfo]) -> ClassInfo:
    """ক্লাস গ্রুপ থেকে ক্যানোনিকাল বেছে নেয়।"""
    best = group[0]
    best_score = 0.0
    for c in group:
        score = 0.0
        parts = Path(c.file).parts
        for part in parts:
            if part in CENTRALITY_RANK:
                score += CENTRALITY_RANK[part]
        score -= len(parts) * 0.5
        score += len(c.name) * 0.2  # দীর্ঘ নাম বর্ণনামূলক
        if score > best_score:
            best = c
            best_score = score
    return best


# ══════════════════════════════════════════════════════════════════════════════
# রিপোর্ট তৈরি
# ══════════════════════════════════════════════════════════════════════════════


def make_func_duplicate_report(
    group: List[FuncInfo], strategy: str
) -> Dict[str, Any]:
    """ফাংশন ডুপ্লিকেট গ্রুপের রিপোর্ট তৈরি করে।"""
    canonical = choose_canonical(group)
    emoji, description = severity_for_group(group, strategy)

    duplicates = []
    for f in group:
        if f is canonical:
            continue
        duplicates.append({
            "file": f.file,
            "line": f.line,
            "name": f.name,
            "qname": f.qname,
            "params": f.param_count,
            "body_lines": f.body_line_count,
            "has_docstring": f.has_docstring,
        })

    return {
        "severity": emoji,
        "severity_label": description,
        "strategy": strategy,
        "canonical": {
            "file": canonical.file,
            "line": canonical.line,
            "name": canonical.name,
            "qname": canonical.qname,
            "params": canonical.param_count,
            "body_lines": canonical.body_line_count,
            "has_docstring": canonical.has_docstring,
            "keep_reason": _keep_reason(canonical, group),
        },
        "duplicates": duplicates,
        "total_duplicates": len(duplicates),
    }


def _keep_reason(canonical: FuncInfo, group: List[FuncInfo]) -> str:
    """কেন এটি ক্যানোনিকাল তার কারণ বাংলায়।"""
    reasons = []
    if canonical.centrality_score() > 0:
        reasons.append("কেন্দ্রীয় প্যাকেজে অবস্থিত")
    if canonical.has_docstring:
        others_with_doc = sum(1 for f in group if f.has_docstring)
        if others_with_doc <= 1:
            reasons.append("একমাত্র ডকস্ট্রিংযুক্ত")
        else:
            reasons.append("ডকস্ট্রিং বেশি")
    if len(canonical.name) >= 15:
        reasons.append("বর্ণনামূলক নাম")
    if not canonical.name.startswith("_"):
        others_public = sum(1 for f in group if not f.name.startswith("_"))
        if others_public == 1:
            reasons.append("পাবলিক API")
    if not reasons:
        reasons.append("প্রথম আবিষ্কৃত")
    return ", ".join(reasons)


def make_class_duplicate_report(group: List[ClassInfo]) -> Dict[str, Any]:
    """ক্লাস ডুপ্লিকেট গ্রুপের রিপোর্ট তৈরি করে।"""
    canonical = choose_canonical_class(group)
    duplicates = []
    for c in group:
        if c is canonical:
            continue
        duplicates.append({
            "file": c.file,
            "line": c.line,
            "name": c.name,
            "method_count": c.method_count,
            "method_names": c.method_names,
            "bases": c.base_classes,
        })

    return {
        "severity": "🟡",
        "severity_label": "সদৃশ ক্লাস কাঠামো — একই মেথড নাম ও সংখ্যা",
        "strategy": "similar_class",
        "canonical": {
            "file": canonical.file,
            "line": canonical.line,
            "name": canonical.name,
            "method_count": canonical.method_count,
            "method_names": canonical.method_names,
            "bases": canonical.base_classes,
        },
        "duplicates": duplicates,
        "total_duplicates": len(duplicates),
    }


def _append_importer_line(
    lines: List[str],
    results: Dict[str, Any],
    filepath: str,
    indent: int = 8,
) -> None:
    """importer_counts থাকলে একটি লাইন যোগ করে (prod/test/soft)।"""
    counts = results.get("importer_counts") or {}
    if not counts:
        return
    # পথ normalize করে খুঁজি (results-এর key গুলো py_files থেকে, যা abs path)
    norm = os.path.normpath(os.path.abspath(filepath))
    entry = counts.get(norm) or counts.get(filepath)
    if not entry:
        return
    pad = " " * indent
    prod = entry.get("prod", 0)
    test = entry.get("test", 0)
    soft = entry.get("soft", 0)
    if prod == 0 and test == 0:
        marker = "🗑️  0 importer — মুছার উপযুক্ত (soft ref থাকলে যাচাই করুন)"
    elif prod == 0:
        marker = f"⚠️  0 prod / {test} test importer — test আপডেট দরকার"
    else:
        marker = f"📦 {prod} prod / {test} test importer"
    if soft:
        marker += f" (+{soft} soft ref)"
    lines.append(f"{pad}{marker}")


def format_text_report(results: Dict[str, Any]) -> str:
    """মানব-পাঠযোগ্য টেক্সট রিপোর্ট তৈরি করে।"""
    lines = []
    lines.append("")
    lines.append("═" * 70)
    lines.append("  SupremeAI ডুপ্লিকেট লজিক সনাক্তকরণ প্রতিবেদন")
    lines.append("  Duplicate Logic Detection Report")
    lines.append("═" * 70)
    lines.append("")

    total_groups = 0
    total_dupes = 0
    severity_counts = {"🔴": 0, "🟡": 0, "🟢": 0}

    # কৌশল অনুসারে গ্রুপ করা
    for strategy_label, strategy_key in [
        ("অভিন্ন স্ট্রাকচারাল হ্যাশ (Exact Structural Hash)", "exact_hash"),
        ("সদৃশ ফাংশন স্বাক্ষর (Similar Signature)", "similar_signature"),
        ("সদৃশ ক্লাস কাঠামো (Similar Class Structure)", "similar_class"),
        ("সাবস্ট্রিং বডি সাদৃশ্য (Substring Body Similarity)", "substring"),
    ]:
        groups = results.get(strategy_key, [])
        if not groups:
            continue

        lines.append(f"\n{'─' * 70}")
        lines.append(f"  {strategy_label}")
        lines.append(f"  গ্রুপ সংখ্যা: {len(groups)}")
        lines.append(f"{'─' * 70}")

        for idx, group_report in enumerate(groups, 1):
            emoji = group_report["severity"]
            desc = group_report["severity_label"]
            severity_counts[emoji] = severity_counts.get(emoji, 0) + 1

            total_groups += 1
            total_dupes += group_report["total_duplicates"]

            lines.append(f"\n  {emoji} গ্রুপ {idx}: {desc}")
            lines.append(f"     কৌশল: {strategy_key}")

            if "canonical" in group_report:
                can = group_report["canonical"]
                # রিলেটিভ পথ দেখানো
                rel_can = _relative_path(can["file"])
                # func-এ qname, class-এ name থাকে — উভয় সমর্থন
                can_name = can.get("qname") or can.get("name", "?")
                lines.append(f"     ✅ রাখার উপযুক্ত: {can_name} @ {rel_can}:{can['line']}")
                if "keep_reason" in can:
                    lines.append(f"        কারণ: {can['keep_reason']}")
                # func-এ params/body_lines/has_docstring আছে, class-এ নাও থাকতে পারে
                if "params" in can:
                    lines.append(
                        f"        প্যারামিটার: {can['params']}, "
                        f"লাইন: {can['body_lines']}, "
                        f"ডকস্ট্রিং: {'হ্যাঁ' if can['has_docstring'] else 'না'}"
                    )
                elif "method_count" in can:
                    lines.append(
                        f"        মেথড: {can['method_count']}, "
                        f"বেস: {', '.join(can.get('bases', [])) or 'none'}"
                    )
                _append_importer_line(lines, results, can["file"], indent=8)

            for dup in group_report.get("duplicates", []):
                rel_dup = _relative_path(dup["file"])
                dup_name = dup.get("qname") or dup.get("name", "?")
                lines.append(
                    f"     ⚠️  ডুপ্লিকেট: {dup_name} @ {rel_dup}:{dup['line']}"
                )
                if "params" in dup:
                    lines.append(
                        f"        প্যারামিটার: {dup['params']}, "
                        f"লাইন: {dup['body_lines']}, "
                        f"ডকস্ট্রিং: {'হ্যাঁ' if dup['has_docstring'] else 'না'}"
                    )
                elif "method_count" in dup:
                    lines.append(
                        f"        মেথড: {dup['method_count']}, "
                        f"বেস: {', '.join(dup.get('bases', [])) or 'none'}"
                    )
                _append_importer_line(lines, results, dup["file"], indent=8)

    # সারসংক্ষেপ
    lines.append(f"\n{'═' * 70}")
    lines.append("  সারসংক্ষেপ (Summary)")
    lines.append(f"{'═' * 70}")
    lines.append(f"  স্ক্যান করা ফাইল: {results.get('files_scanned', 0)}")
    lines.append(f"  বিশ্লেষিত ফাংশন: {results.get('functions_analyzed', 0)}")
    lines.append(f"  বিশ্লেষিত ক্লাস: {results.get('classes_analyzed', 0)}")
    lines.append(f"  মোট ডুপ্লিকেট গ্রুপ: {total_groups}")
    lines.append(f"  মোট ডুপ্লিকেট উদাহরণ: {total_dupes}")
    lines.append("")
    lines.append(f"  🔴 অভিন্ন যুক্তি (গুরুতর): {severity_counts.get('🔴', 0)}")
    lines.append(f"  🟡 সদৃশ কাঠামো (মাঝারি): {severity_counts.get('🟡', 0)}")
    lines.append(f"  🟢 সামান্য ওভারল্যাপ (হালকা): {severity_counts.get('🟢', 0)}")
    lines.append(f"{'═' * 70}")
    lines.append("")

    return "\n".join(lines)


def _relative_path(filepath: str) -> str:
    """রুট ডিরেক্টরি অনুযায়ী আপেক্ষিক পথ দেখায়।"""
    try:
        return str(Path(filepath).relative_to(REPO_ROOT))
    except ValueError:
        return filepath


# ══════════════════════════════════════════════════════════════════════════════
# মূল প্রবাহ
# ══════════════════════════════════════════════════════════════════════════════

def _detect_repo_root() -> str:
    """
    হার্ডকোডেড পথের বদলে স্বয়ংক্রিয়ভাবে repo root শনাক্ত করে।
    __file__ থেকে উপরে উঠে .git বা backend/ ডিরেক্টরি খোঁজে।
    """
    here = Path(__file__).resolve()
    cand = here
    for _ in range(6):
        cand = cand.parent
        if (cand / ".git").exists() or (cand / "backend").is_dir():
            return str(cand)
    return str(here.parent.parent.parent)


REPO_ROOT = _detect_repo_root()


# ── Importer Graph ইন্টিগ্রেশন ─────────────────────────────────────────────
# নির্ভুল AST-ভিত্তিক ইম্পোর্টার গণনা (আলাদা মডিউলে, একই ডিরেক্টরিতে)।
# ম্যানুয়াল grep-এর ৩০–৫০% ভুল গণনা এড়াতে এটি ব্যবহার করা হয়।
IMPORTER_GRAPH_AVAILABLE = False
_ig_mod = None  # type: ignore[assignment]
_ig_err_msg = ""
try:
    _ig_dir = str(Path(__file__).resolve().parent)
    if _ig_dir not in sys.path:
        sys.path.insert(0, _ig_dir)
    import importer_graph as _ig_mod  # type: ignore[no-redef]
    IMPORTER_GRAPH_AVAILABLE = True
except Exception as _ig_err:  # pragma: no cover
    _ig_err_msg = str(_ig_err)


def main() -> int:
    """
    মূল ফাংশন — সমস্ত বিশ্লেষণ ও রিপোর্টিং এখানে ঘটে।
    বেরিয়া কোড: ০=পরিষ্কার, ১=ডুপ্লিকেট পাওয়া, ২=ত্রুটি
    """
    parser = argparse.ArgumentParser(
        description="SupremeAI ডুপ্লিকেট লজিক সনাক্তকরণ (AST-ভিত্তিক)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        উদাহরণ:
          %(prog)s                              # ডিফল্ট: backend/ স্ক্যান
          %(prog)s --json                       # JSON আউটপুট
          %(prog)s --min-lines 10               # ১০+ লাইনের ফাংশন শুধু
          %(prog)s --threshold 0.9              # ৯০%% ওভারল্যাপ প্রয়োজন
          %(prog)s --path backend/brain/        # নির্দিষ্ট পথ স্ক্যান
        """),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="JSON ফরম্যাটে আউটপুট দেখাও",
    )
    parser.add_argument(
        "--min-lines",
        type=int,
        default=5,
        help="ন্যূনতম ফাংশন বডি লাইন (ডিফল্ট: ৫)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="সাদৃশ্য থ্রেশহোল্ড ০-১ (ডিফল্ট: ০.৮)",
    )
    parser.add_argument(
        "--path",
        type=str,
        default=os.path.join(REPO_ROOT, "backend"),
        help=f"স্ক্যান করার রুট পথ (ডিফল্ট: backend/)",
    )
    parser.add_argument(
        "--importer-audit",
        type=str,
        default=None,
        help="একটি ফাইলের নিখুঁত ইম্পোর্টার তালিকা দেখাও (AST-ভিত্তিক, নির্ভুল)",
    )
    parser.add_argument(
        "--orphans",
        action="store_true",
        help="0-production-importer ফাইল তালিকা (মুছার প্রার্থী, AST-ভিত্তিক)",
    )
    parser.add_argument(
        "--include-test-importers",
        action="store_true",
        default=False,
        help="orphans মোডে test ইম্পোর্টারও গণনা করো (ডিফল্ট: production শুধু)",
    )
    parser.add_argument(
        "--with-importers",
        action="store_true",
        default=False,
        help="ডুপ্লিকেট রিপোর্টে প্রতিটি সদস্যের importer count যোগ করো",
    )

    args = parser.parse_args()

    # ── Importer Graph মোড (--importer-audit / --orphans) ─────────────
    if args.importer_audit or args.orphans:
        if not IMPORTER_GRAPH_AVAILABLE:
            print(
                f"❌ Importer Graph ইঞ্জিন লোড করা যায়নি: {_ig_err_msg}",
                file=sys.stderr,
            )
            return 2
        roots = [args.path]
        graph = _ig_mod.build_graph(roots, include_tests=True)  # type: ignore[union-attr]
        _ig_mod.scan_patch_strings(graph)  # type: ignore[union-attr]
        _ig_mod.scan_module_string_constants(graph)  # type: ignore[union-attr]
        if args.importer_audit:
            print(_ig_mod.format_audit_report(graph, args.importer_audit))  # type: ignore[union-attr]
            return 0
        print(
            _ig_mod.format_orphans_report(  # type: ignore[union-attr]
                graph, prod_only=not args.include_test_importers
            )
        )
        return 0

    scan_root = args.path
    min_lines = args.min_lines
    threshold = max(0.0, min(1.0, args.threshold))

    # ── ধাপ ১: ফাইল সংগ্রহ ──────────────────────────────────────────
    if not os.path.isdir(scan_root):
        print(f"❌ ত্রুটি: পাথ বিদ্যমান নেই — {scan_root}", file=sys.stderr)
        return 2

    print(f"🔍 স্ক্যান চলছে: {scan_root}", file=sys.stderr)
    print(f"   ন্যূনতম লাইন: {min_lines}, থ্রেশহোল্ড: {threshold}", file=sys.stderr)

    py_files = collect_all_py_files(scan_root)
    print(f"   পাওয়া .py ফাইল: {len(py_files)}", file=sys.stderr)

    # ── ধাপ ২: ফাংশন ও ক্লাস বের করা ────────────────────────────────
    all_funcs: List[FuncInfo] = []
    all_classes: List[ClassInfo] = []
    parse_errors = 0

    for i, fpath in enumerate(py_files, 1):
        if i % 200 == 0:
            print(f"   প্রক্রিয়াকরণ: {i}/{len(py_files)}...", file=sys.stderr)
        try:
            funcs, classes = extract_functions_from_file(fpath)
            all_funcs.extend(funcs)
            all_classes.extend(classes)
        except Exception:
            parse_errors += 1

    # ন্যূনতম লাইন ফিল্টার (কিছু কৌশলে প্রযোজ্য)
    funcs_for_hash = all_funcs  # হ্যাশ ম্যাচে সব ফাংশন
    funcs_for_sig = [f for f in all_funcs if f.body_line_count >= min_lines]

    print(f"   বিশ্লেষিত ফাংশন: {len(all_funcs)}, ক্লাস: {len(all_classes)}", file=sys.stderr)
    if parse_errors:
        print(f"   ⚠ পার্স ত্রুটি: {parse_errors} ফাইল", file=sys.stderr)

    # ── ধাপ ৩: ডুপ্লিকেট সনাক্তকরণ (চারটি কৌশল) ───────────────────
    print("   কৌশল ১: স্ট্রাকচারাল হ্যাশ ম্যাচ...", file=sys.stderr)
    exact_hash_groups = detect_exact_structural_hash(funcs_for_hash)

    print("   কৌশল ২: সদৃশ স্বাক্ষর...", file=sys.stderr)
    similar_sig_groups = detect_similar_signature(funcs_for_sig, min_lines)

    print("   কৌশল ৩: সদৃশ ক্লাস কাঠামো...", file=sys.stderr)
    similar_class_groups = detect_similar_class_structure(all_classes)

    print("   কৌশল ৪: সাবস্ট্রিং বডি সাদৃশ্য...", file=sys.stderr)
    substring_groups = detect_substring_body_similarity(
        all_funcs, min_lines, threshold
    )

    # ── ধাপ ৪: রিপোর্ট তৈরি ────────────────────────────────────────
    # সব ডুপ্লিকেটের মোট সংখ্যা
    total_duplicate_count = (
        len(exact_hash_groups)
        + len(similar_sig_groups)
        + len(similar_class_groups)
        + len(substring_groups)
    )

    # ── ঐচ্ছিক: Importer Graph দিয়ে প্রতিটি ডুপ্লিকেট সদস্যের importer count ──
    importer_counts: Dict[str, Dict[str, int]] = {}
    if args.with_importers and IMPORTER_GRAPH_AVAILABLE:
        print("   কৌশল ৫: Importer Graph নির্মাণ (নির্ভুল গণনা)...", file=sys.stderr)
        ig_graph = _ig_mod.build_graph([scan_root], include_tests=True)  # type: ignore[union-attr]
        _ig_mod.scan_patch_strings(ig_graph)  # type: ignore[union-attr]
        _ig_mod.scan_module_string_constants(ig_graph)  # type: ignore[union-attr]
        for fpath in py_files:
            edges = ig_graph.reverse.get(fpath, [])
            prod = test = soft = 0
            seen_prod: Set[str] = set()
            seen_test: Set[str] = set()
            for e in edges:
                if e.importer == fpath:
                    continue
                if e.importer in ig_graph.test_files:
                    if e.importer not in seen_test:
                        seen_test.add(e.importer)
                        test += 1
                else:
                    if e.importer not in seen_prod:
                        seen_prod.add(e.importer)
                        prod += 1
            soft = len(ig_graph.soft_refs.get(fpath, []))
            importer_counts[fpath] = {"prod": prod, "test": test, "soft": soft}

    results = {
        "files_scanned": len(py_files),
        "functions_analyzed": len(all_funcs),
        "classes_analyzed": len(all_classes),
        "parse_errors": parse_errors,
        "importer_graph_available": IMPORTER_GRAPH_AVAILABLE,
        "importer_counts": importer_counts,
        "exact_hash": [
            make_func_duplicate_report(g, "exact_hash") for g in exact_hash_groups
        ],
        "similar_signature": [
            make_func_duplicate_report(g, "similar_signature")
            for g in similar_sig_groups
        ],
        "similar_class": [
            make_class_duplicate_report(g) for g in similar_class_groups
        ],
        "substring": [
            make_func_duplicate_report(g, "substring") for g in substring_groups
        ],
        "total_groups": total_duplicate_count,
    }

    # ── ধাপ ৫: আউটপুট ───────────────────────────────────────────────
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        report = format_text_report(results)
        print(report)

    print(
        f"✅ সম্পন্ন: {total_duplicate_count} ডুপ্লিকেট গ্রুপ পাওয়া",
        file=sys.stderr,
    )

    # বেরিয়া কোড
    if parse_errors > 0 and total_duplicate_count == 0:
        return 2
    if total_duplicate_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
