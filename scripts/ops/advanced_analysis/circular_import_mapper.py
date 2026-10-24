#!/usr/bin/env python3
"""
SupremeAI — সার্কুলার ইম্পোর্ট ম্যাপার
====================================
backend/ এর সমস্ত .py ফাইল পার্স করে import গ্রাফ তৈরি করে,
Tarjan's algorithm দিয়ে strongly connected components (SCC) খুঁজে বের করে,
এবং সার্কুলার ডিপেন্ডেন্সি চেইন রিপোর্ট করে।

ব্যবহার:
    python scripts/circular_import_mapper.py
    python scripts/circular_import_mapper.py --json
    python scripts/circular_import_mapper.py --dot > cycles.dot
    python scripts/circular_import_mapper.py --module core.config
    python scripts/circular_import_mapper.py --module services.llm --json

এক্সিট কোড:
    0 = কোনো সাইকেল নেই (পরিষ্কার)
    1 = সাইকেল পাওয়া গেছে
    2 = ত্রুটি ঘটেছে
"""

from __future__ import annotations

import ast
import argparse
import datetime
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ────────────────────────────────────────────────────────────
# কনফিগারেশন — রিপো এবং ব্যাকএন্ড পাথ
# ────────────────────────────────────────────────────────────
# বাংলা (M11 ফিক্স): আগে parent.parent = scripts/ হতো — ফলে BACKEND_DIR
# অস্তিত্বহীন scripts/backend-এ যায় এবং mapper নীরবে 0-মডিউল রিপোর্ট দিত
# (fake measurement surface)। সঠিক মূল: parents[2] = repo root।
REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"

# ────────────────────────────────────────────────────────────
# গ্লোবাল ক্যাশে — পারফরম্যান্সের জন্য পার্সড AST সংরক্ষণ করা হয়
# ────────────────────────────────────────────────────────────
_ast_cache: Dict[str, Optional[ast.AST]] = {}
_source_cache: Dict[str, str] = {}

# ইম্পোর্ট তথ্যের ধরন: (টার্গেট_মডিউল, কাঁচা_লাইন, সিভিয়রিটি)
ImportInfo = Tuple[str, str, str]

# গ্রাফ ধরন: মডিউল → ইম্পোর্ট তালিকা
ImportGraph = Dict[str, List[ImportInfo]]

# সিভিয়রিটি আইকন ম্যাপিং
SEVERITY_ICONS = {"CRITICAL": "🔴", "LAZY": "🟡", "CONDITIONAL": "🔵"}


# ────────────────────────────────────────────────────────────
# হেল্পার: ফাইল → মডিউল নাম রূপান্তর
# ────────────────────────────────────────────────────────────
def _file_to_module(filepath: Path) -> str:
    """ফাইলের পাথ থেকে ডট-সেপারেটেড মডিউল নাম বের করে।
    
    যেমন: backend/api/routes.py → "api.routes"
    এবং: backend/services/__init__.py → "services"
    """
    try:
        rel = filepath.relative_to(BACKEND_DIR)
    except ValueError:
        # ব্যাকএন্ডের বাইরে হলে রিপো রুট থেকে রিলেটিভ নেবো
        try:
            rel = filepath.relative_to(REPO_ROOT)
        except ValueError:
            return filepath.stem
    parts = list(rel.parts)
    # .py এক্সটেনশন সরাই
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    # __init__ ফাইল হলে শেষ পার্ট বাদ দিই
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else ""


def _module_to_possible_files(module: str) -> List[Path]:
    """মডিউল নাম থেকে সম্ভাব্য .py ফাইলের পাথ তালিকা বের করে।
    
    দুটি সম্ভাবনা: pkg/__init__.py এবং pkg.py
    """
    parts = module.split(".")
    candidates: List[Path] = []
    # __init__.py এর জন্য
    if parts:
        candidates.append(BACKEND_DIR.joinpath(*parts, "__init__.py"))
    # .py ফাইলের জন্য
    if len(parts) >= 1:
        candidates.append(BACKEND_DIR.joinpath(*parts[:-1], f"{parts[-1]}.py"))
    return candidates


def _resolve_module_to_file(module: str, module_to_file: Dict[str, Path]) -> Optional[Path]:
    """মডিউল নাম থেকে আসল ফাইল পাথ দ্রুত রিজলভ করে।
    
    প্রথমে ম্যাপিং চেক, না পাওয়া গেলে ডিস্ক থেকে খুঁজে।
    """
    if module in module_to_file:
        return module_to_file[module]
    for candidate in _module_to_possible_files(module):
        if candidate.is_file():
            module_to_file[module] = candidate
            return candidate
    return None


# ────────────────────────────────────────────────────────────
# AST পার্সিং — ক্যাশে সহ
# ────────────────────────────────────────────────────────────
def _parse_file(filepath: Path) -> Optional[ast.AST]:
    """ফাইল পার্স করে AST রিটার্ন করে। ক্যাশে ব্যবহার করে পুনরায় পার্স এড়ায়।
    
    ১২৬১+ ফাইলের কোডবেসে এই ক্যাশিং উল্লেখযোগ্য সময় সাশ্রয় করে।
    """
    key = str(filepath)
    if key in _ast_cache:
        return _ast_cache[key]
    try:
        if key not in _source_cache:
            _source_cache[key] = filepath.read_text(encoding="utf-8", errors="ignore")
        source = _source_cache[key]
        if not source.strip():
            _ast_cache[key] = None
            return None
        tree = ast.parse(source, filename=str(filepath))
        _ast_cache[key] = tree
        return tree
    except (SyntaxError, ValueError, OSError):
        _ast_cache[key] = None
        return None


# ────────────────────────────────────────────────────────────
# সিভিয়রিটি ক্লাসিফিকেশন — ইম্পোর্ট কনটেক্সট বিশ্লেষণ
# ────────────────────────────────────────────────────────────
def _find_enclosing_function_depth(tree: ast.AST, target_lineno: int) -> int:
    """একটি লাইন নম্বর কতগুলো ফাংশন/অ্যাসিঙ্ক ফাংশনের ভিতরে আছে তা রিটার্ন করে।
    
    গভীরতা 0 = মডিউল টপ-লেভেল (CRITICAL)।
    গভীরতা > 0 = ফাংশনের ভিতরে (LAZY)।
    """
    depth = [0]

    class _FnVisitor(ast.NodeVisitor):
        """শুধুমাত্র ফাংশন ডেফিনিশন ভিজিট করে গভীরতা ট্র্যাক করে।"""

        def _visit_func(self, node: ast.AST) -> None:
            start = getattr(node, "lineno", 0)
            end = getattr(node, "end_lineno", start)
            if start <= target_lineno <= end:
                depth[0] += 1
                self.generic_visit(node)
                depth[0] -= 1
            # ফাংশনের বাইরে থাকলেও সব চাইল্ড চেক করতে হবে না

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._visit_func(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._visit_func(node)

    try:
        _FnVisitor().visit(tree)
    except Exception as e:
        print(f"warning: nesting-depth AST walk failed: {e}", file=sys.stderr)
    return depth[0]


def _is_in_type_checking_block(source_lines: List[str], line_no: int) -> bool:
    """ইম্পোর্ট লাইনটি কি `if TYPE_CHECKING:` ব্লকের ভিতরে আছে তা চেক করে।
    
    ইনডেন্টেশন বিশ্লেষণ দিয়ে নির্ধারণ করা হয়।
    """
    import_line = source_lines[line_no - 1] if line_no - 1 < len(source_lines) else ""
    import_indent = len(import_line) - len(import_line.lstrip())

    # উপরের দিকে খুঁজে বের করি TYPE_CHECKING ব্লক
    for i in range(max(0, line_no - 2), max(0, line_no - 30), -1):
        line = source_lines[i]
        stripped = line.strip()
        if stripped.startswith("if TYPE_CHECKING") or stripped.startswith("if typing.TYPE_CHECKING"):
            tc_indent = len(line) - len(line.lstrip())
            # ইম্পোর্ট লাইনটি TYPE_CHECKING এর চেয়ে বেশি ইনডেন্টেড হতে হবে
            if import_indent > tc_indent:
                return True
            # একই ইনডেন্টেশনে অন্য কিছু থাকলে ব্লক শেষ
            elif import_indent <= tc_indent:
                break
        # অ-খালি লাইন যা if নয় এবং কম ইনডেন্টেড — ব্লক শেষ
        elif stripped and not stripped.startswith("#"):
            line_indent = len(line) - len(line.lstrip())
            if line_indent < import_indent:
                break
    return False


def _is_in_try_except_importerror(source_lines: List[str], line_no: int) -> bool:
    """ইম্পোর্ট লাইনটি কি try/except ImportError বা except ModuleNotFoundError এর ভিতরে আছে।"""
    import_line = source_lines[line_no - 1] if line_no - 1 < len(source_lines) else ""
    import_indent = len(import_line) - len(import_line.lstrip())

    for i in range(max(0, line_no - 2), max(0, line_no - 15), -1):
        line = source_lines[i]
        stripped = line.strip()
        if stripped.startswith("try:"):
            try_indent = len(line) - len(line.lstrip())
            if import_indent > try_indent:
                # এখন except চেক করি
                for j in range(i + 1, min(len(source_lines), i + 20)):
                    exc_line = source_lines[j].strip()
                    if "except ImportError" in exc_line or "except ModuleNotFoundError" in exc_line:
                        return True
                    if exc_line and not exc_line.startswith(("#", "except")):
                        exc_indent = len(source_lines[j]) - len(source_lines[j].lstrip())
                        if exc_indent <= try_indent:
                            break
    return False


def _classify_import(
    import_node: ast.AST,
    tree: ast.AST,
    source_lines: List[str],
) -> str:
    """একটি ইম্পোর্ট নোডের সিভিয়রিটি নির্ধারণ করে।
    
    CRITICAL  = টপ-লেভেল ইম্পোর্ট (মডিউল লোডে সমস্যা)
    LAZY      = TYPE_CHECKING গার্ড বা ফাংশন বডিতে
    CONDITIONAL = try/except ImportError গার্ডে
    """
    line_no = getattr(import_node, "lineno", 0)
    if line_no < 1 or line_no > len(source_lines):
        return "CRITICAL"

    # ফাংশন ডেপথ চেক — ফাংশনের ভিতরে হলে LAZY
    if _find_enclosing_function_depth(tree, line_no) > 0:
        return "LAZY"

    # TYPE_CHECKING ব্লক চেক
    if _is_in_type_checking_block(source_lines, line_no):
        return "LAZY"

    # try/except ImportError চেক
    if _is_in_try_except_importerror(source_lines, line_no):
        return "CONDITIONAL"

    return "CRITICAL"


# ────────────────────────────────────────────────────────────
# ইম্পোর্ট এক্সট্র্যাকশন — ফাইল থেকে সব ইম্পোর্ট স্টেটমেন্ট বের করা
# ────────────────────────────────────────────────────────────
def _extract_imports(filepath: Path) -> List[ImportInfo]:
    """একটি .py ফাইল থেকে সব ইম্পোর্ট স্টেটমেন্ট বের করে।
    
    রিটার্ন: [(target_module, raw_import_line, severity), ...]
    রিলেটিভ ইম্পোর্ট (.module, ..module) অ্যাবসোলিউটে রূপান্তরিত হয়।
    """
    tree = _parse_file(filepath)
    if tree is None:
        return []

    key = str(filepath)
    source_lines = _source_cache.get(key, "").splitlines()
    file_module = _file_to_module(filepath)
    file_parts = file_module.split(".") if file_module else []
    imports: List[ImportInfo] = []

    for node in ast.iter_child_nodes(tree):
        # শুধুমাত্র টপ-লেভেল ইম্পোর্ট স্টেটমেন্ট দেখি (পারফরম্যান্সের জন্য)
        # তবে ফাংশনের ভিতরের ইম্পোর্টও চাই সিভিয়রিটি ডিটেকশনের জন্য
        target_module = None
        raw_line = ""

        if isinstance(node, ast.Import):
            for alias in node.names:
                target_module = alias.name
                raw_line = f"import {alias.name}"
                severity = _classify_import(node, tree, source_lines)
                imports.append((target_module, raw_line, severity))

        elif isinstance(node, ast.ImportFrom):
            raw_module = node.module or ""
            level = node.level or 0

            # রিলেটিভ ইম্পোর্টকে অ্যাবসোলিউটে রূপান্তর
            if level > 0:
                # level-1 সংখ্যক পার্ট উপরে যাই
                base_parts = file_parts[:-level] if level <= len(file_parts) else []
                if raw_module:
                    target_module = ".".join(base_parts + [raw_module]) if base_parts else raw_module
                else:
                    target_module = ".".join(base_parts) if base_parts else ""
            else:
                target_module = raw_module

            if target_module:
                names = [alias.name for alias in node.names]
                if len(names) <= 3:
                    names_str = ", ".join(names)
                else:
                    names_str = f"({', '.join(names[:2])}, ...{len(names) - 2} more)"
                raw_line = f"from {node.module or ('.' * level)} import {names_str}"
                severity = _classify_import(node, tree, source_lines)
                imports.append((target_module, raw_line, severity))

    return imports


# ────────────────────────────────────────────────────────────
# ইম্পোর্ট গ্রাফ নির্মাণ — সব .py ফাইল পার্স করে
# ────────────────────────────────────────────────────────────
def _discover_py_files() -> List[Path]:
    """backend/ এর সব .py ফাইল আবিষ্কার করে।
    
    os.walk ব্যবহার করে যা pathlib.rglob() থেকে দ্রুত।
    __pycache__ এবং .venv ডিরেক্টরি এড়ানো হয়।
    """
    skip_dirs = {"__pycache__", ".venv", "venv", "node_modules", ".git", "migrations"}
    py_files: List[Path] = []

    for root, dirs, files in os.walk(BACKEND_DIR):
        # অবাঞ্ছিত ডিরেক্টরি স্কিপ — in-place মডিফাই করে recurse এড়াই
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if f.endswith(".py"):
                py_files.append(Path(root) / f)

    return py_files


def _build_import_graph(
    py_files: List[Path],
    module_to_file: Dict[str, Path],
    all_modules: Set[str],
    target_module: Optional[str] = None,
) -> ImportGraph:
    """সব .py ফাইল থেকে ইম্পোর্ট গ্রাফ তৈরি করে।
    
    শুধুমাত্র অভ্যন্তরীণ (backend-এ থাকা) মডিউলের ইম্পোর্ট রাখা হয়।
    বাহ্যিক প্যাকেজ (যেমন fastapi, pydantic) বাদ দেওয়া হয়।
    """
    graph: ImportGraph = defaultdict(list)

    for fp in py_files:
        mod = _file_to_module(fp)
        if not mod:
            continue
        # নির্দিষ্ট মডিউল ফিল্টার করা হলে শুধু সেই মডিউল এবং তার সাব-মডিউল পার্স করি
        if target_module and not (mod == target_module or mod.startswith(target_module + ".")):
            # তবে অন্য মডিউলও পার্স করতে হবে যারা টার্গেটকে ইম্পোর্ট করে
            # তাই আমরা সব ফাইল পার্স করবো কিন্তু শুধু টার্গেট-সম্পর্কিত এজ রাখবো
            pass

        imp_list = _extract_imports(fp)
        for target, raw, sev in imp_list:
            if target in all_modules:
                graph[mod].append((target, raw, sev))

    # টার্গেট মডিউল ফিল্টার
    if target_module:
        # টার্গেট এবং তার সাব-মডিউলের সাথে সম্পর্কিত এজ রাখি
        relevant_prefixes = {target_module}
        # যে মডিউলগুলো টার্গেটকে ইম্পোর্ট করে বা টার্গেট যাদেরকে ইম্পোর্ট করে
        keep_srcs: Set[str] = set()
        for src, edges in graph.items():
            if src == target_module or src.startswith(target_module + "."):
                keep_srcs.add(src)
            for tgt, _, _ in edges:
                if tgt == target_module or tgt.startswith(target_module + "."):
                    keep_srcs.add(src)
        filtered: ImportGraph = defaultdict(list)
        for src in keep_srcs:
            for tgt, raw, sev in graph[src]:
                if tgt in keep_srcs and (tgt == target_module or tgt.startswith(target_module + ".")
                                         or src == target_module or src.startswith(target_module + ".")):
                    filtered[src].append((tgt, raw, sev))
        graph = filtered

    return graph


# ────────────────────────────────────────────────────────────
# Tarjan's SCC Algorithm — O(V + E) কমপ্লেক্সিটিতে সব চক্র খুঁজে বের করে
# ────────────────────────────────────────────────────────────
def _tarjan_scc(graph: ImportGraph, all_modules: Set[str]) -> List[List[str]]:
    """Tarjan's algorithm ব্যবহার করে সব strongly connected component খুঁজে বের করে।
    
    শুধুমাত্র আকার > 1 এর SCC রিটার্ন করে (অর্থাৎ প্রকৃত সার্কুলার ডিপেন্ডেন্সি)।
    রিকার্সন লিমিট স্বয়ংক্রিয়ভাবে বাড়ানো হয় বড় গ্রাফের জন্য।
    """
    index_counter = [0]
    stack: List[str] = []
    on_stack: Set[str] = set()
    index_map: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    sccs: List[List[str]] = []

    # গ্রাফের সব নোড সংগ্রহ
    nodes: Set[str] = set(all_modules)
    for src in graph:
        nodes.add(src)
        for tgt, _, _ in graph[src]:
            nodes.add(tgt)

    # ইটারেটিভ ভার্সন — রিকার্সন লিমিট সমস্যা এড়াতে
    # স্ট্যাক-ভিত্তিক DFS
    call_stack: List[Tuple[str, int, List[str]]] = []  # (node, edge_index, scc_buffer)
    node_iter_order = sorted(nodes)

    def push_start(v: str) -> None:
        """নতুন নোডের DFS শুরু করে।"""
        index_map[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)
        call_stack.append((v, 0, []))

    for v in node_iter_order:
        if v in index_map:
            continue
        push_start(v)

        while call_stack:
            current, ei, scc_buf = call_stack[-1]
            edges = graph.get(current, [])

            # পরবর্তী এজ খুঁজি
            found_next = False
            while ei < len(edges):
                w = edges[ei][0]  # target module
                ei += 1
                call_stack[-1] = (current, ei, scc_buf)

                if w not in index_map:
                    # আনভিজিটেড — রিকার্স করার মতো পুশ করি
                    call_stack[-1] = (current, ei, scc_buf)
                    push_start(w)
                    found_next = True
                    break
                elif w in on_stack:
                    lowlink[current] = min(lowlink[current], index_map[w])

            if found_next:
                continue

            # সব এজ প্রসেস হয়েছে — পপ করি
            call_stack.pop()

            if lowlink[current] == index_map[current]:
                # রুট নোড — SCC তৈরি
                scc: List[str] = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    scc.append(w)
                    if w == current:
                        break
                if len(scc) > 1:
                    sccs.append(scc)

            # প্যারেন্টের lowlink আপডেট
            if call_stack:
                parent = call_stack[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[current])

    return sccs


# ────────────────────────────────────────────────────────────
# চক্র পাথ পুনরুদ্ধার — SCC থেকে প্রকৃত পাথ বের করা
# ────────────────────────────────────────────────────────────
def _find_cycles_in_scc(scc: List[str], graph: ImportGraph) -> List[List[str]]:
    """একটি SCC থেকে সম্ভাব্য চক্র পাথ বের করে।
    
    বড় SCC-তে অসীম পারমিউটেশন এড়াতে সর্বোচ্চ ৩টি পাথ রিটার্ন করি।
    """
    scc_set = set(scc)
    cycles: List[List[str]] = []
    max_cycles = 3

    for start_node in scc:
        if len(cycles) >= max_cycles:
            break
        # BFS-স্টাইল DFS
        stack: List[Tuple[str, List[str], Set[str]]] = [(start_node, [start_node], {start_node})]
        while stack and len(cycles) < max_cycles:
            current, path, visited = stack.pop()
            for neighbor, _, _ in graph.get(current, []):
                if len(cycles) >= max_cycles:
                    break
                if neighbor == start_node and len(path) > 1:
                    cycles.append(path + [start_node])
                elif neighbor in scc_set and neighbor not in visited:
                    stack.append((neighbor, path + [neighbor], visited | {neighbor}))

    return cycles


# ────────────────────────────────────────────────────────────
# SCC সিভিয়রিটি ক্লাসিফিকেশন
# ────────────────────────────────────────────────────────────
def _classify_scc_severity(scc: List[str], graph: ImportGraph) -> str:
    """একটি SCC-র সামগ্রিক সিভিয়রিটি নির্ধারণ করে।
    
    যেকোনো একটি CRITICAL এজ থাকলে পুরো SCC CRITICAL হিসেবে চিহ্নিত হয়,
    কারণ একটি টপ-লেভেল ইম্পোর্টই মডিউল লোডে ব্যর্থ করতে পারে।
    """
    scc_set = set(scc)
    has_critical = False
    has_lazy = False

    for mod in scc:
        for target, _, sev in graph.get(mod, []):
            if target in scc_set:
                if sev == "CRITICAL":
                    has_critical = True
                elif sev == "LAZY":
                    has_lazy = True

    if has_critical:
        return "CRITICAL"
    if has_lazy:
        return "LAZY"
    return "CONDITIONAL"


# ────────────────────────────────────────────────────────────
# ফিক্স সাজেশন জেনারেটর
# ────────────────────────────────────────────────────────────
def _suggest_fixes(cycle: List[str], graph: ImportGraph) -> List[str]:
    """প্রতিটি চক্রের জন্য সম্ভাব্য সমাধান সাজেস্ট করে।
    
    প্রতিটি CRITICAL এজের জন্য নির্দিষ্ট কোড পরিবর্তনের সাজেশন দেয়।
    """
    suggestions: List[str] = []
    cycle_set = set(cycle)

    for i in range(len(cycle) - 1):
        src = cycle[i]
        tgt = cycle[i + 1]
        for target, raw, sev in graph.get(src, []):
            if target == tgt and target in cycle_set:
                if sev == "CRITICAL":
                    suggestions.append(
                        f"  💡 `{src}` → `{tgt}`: এই ইম্পোর্টটি ফাংশনের ভিতরে সরান অথবা "
                        f"`if TYPE_CHECKING:` গার্ড ব্যবহার করুন:\n"
                        f"     from typing import TYPE_CHECKING\n"
                        f"     if TYPE_CHECKING:\n"
                        f"         {raw}"
                    )
                elif sev == "LAZY":
                    suggestions.append(
                        f"  ✅ `{src}` → `{tgt}`: লেজি লোড — ঝুঁকি কম"
                    )
                else:
                    suggestions.append(
                        f"  🔒 `{src}` → `{tgt}`: গার্ডেড ইম্পোর্ট — নিরাপদ"
                    )
                break

    if not suggestions:
        suggestions.append(
            "  💡 এই চক্রের সমাধানে একটি শেয়ার্ড ইন্টারফেস মডিউল তৈরি করুন (interface segregation pattern)"
        )

    return suggestions


# ────────────────────────────────────────────────────────────
# টেক্সট ভিজুয়ালাইজেশন
# ────────────────────────────────────────────────────────────
def _visualize_cycle(cycle: List[str], severity: str) -> str:
    """চক্রের টেক্সট-ভিত্তিক ভিজুয়ালাইজেশন তৈরি করে।"""
    icon = SEVERITY_ICONS.get(severity, "⚪")
    return f"  {icon} {' → '.join(cycle)}"


def _timestamp() -> str:
    """বর্তমান সময়ের পঠনযোগ্য টাইমস্ট্যাম্প রিটার্ন করে।"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ────────────────────────────────────────────────────────────
# মার্কডাউন রিপোর্ট জেনারেটর
# ────────────────────────────────────────────────────────────
def _generate_markdown_report(
    sccs: List[List[str]],
    graph: ImportGraph,
    all_modules: Set[str],
    module_to_file: Dict[str, Path],
    elapsed: float,
    target_module: Optional[str] = None,
) -> str:
    """সম্পূর্ণ মার্কডাউন রিপোর্ট তৈরি করে।
    
    পরিসংখ্যান, SCC বিস্তারিত, চক্র ভিজুয়ালাইজেশন, এবং ফিক্স সাজেশন অন্তর্ভুক্ত।
    """
    lines: List[str] = []

    # হেডার
    lines.append("# 🔗 SupremeAI সার্কুলার ইম্পোর্ট রিপোর্ট")
    lines.append("")
    lines.append(f"**তারিখ**: {_timestamp()}  ")
    lines.append(f"**স্ক্যান সময়**: {elapsed:.2f}s")
    if target_module:
        lines.append(f"**টার্গেট মডিউল**: `{target_module}`")
    lines.append("")

    # ── পরিসংখ্যান ──
    total_edges = sum(len(edges) for edges in graph.values())
    total_imports_per_mod = (
        sum(len(edges) for edges in graph.values()) / len(all_modules)
        if all_modules
        else 0.0
    )
    largest_scc = max((len(s) for s in sccs), default=0)
    critical_count = sum(1 for s in sccs if _classify_scc_severity(s, graph) == "CRITICAL")
    lazy_count = sum(1 for s in sccs if _classify_scc_severity(s, graph) == "LAZY")
    conditional_count = sum(
        1 for s in sccs if _classify_scc_severity(s, graph) == "CONDITIONAL"
    )

    lines.append("## 📊 পরিসংখ্যান")
    lines.append("")
    lines.append("| মেট্রিক | মান |")
    lines.append("|---|---|")
    lines.append(f"| মোট মডিউল | {len(all_modules)} |")
    lines.append(f"| মোট ইন্টারনাল ইম্পোর্ট এজ | {total_edges} |")
    lines.append(f"| প্রতি মডিউলে গড় ইম্পোর্ট | {total_imports_per_mod:.1f} |")
    lines.append(f"| সার্কুলার ডিপেন্ডেন্সি গ্রুপ (SCC) | {len(sccs)} |")
    lines.append(f"| সবচেয়ে বড় SCC | {largest_scc} মডিউল |")
    lines.append(f"| 🔴 CRITICAL | {critical_count} |")
    lines.append(f"| 🟡 LAZY | {lazy_count} |")
    lines.append(f"| 🔵 CONDITIONAL | {conditional_count} |")
    lines.append("")

    if not sccs:
        lines.append("## ✅ কোনো সার্কুলার ইম্পোর্ট পাওয়া যায়নি!")
        lines.append("")
        lines.append("কোডবেস পরিষ্কার — কোনো চক্রীয় ডিপেন্ডেন্সি নেই।")
        return "\n".join(lines)

    # সিভিয়রিটি অনুসারে সাজানো
    sev_order = {"CRITICAL": 0, "LAZY": 1, "CONDITIONAL": 2}
    sorted_sccs = sorted(
        sccs, key=lambda s: (sev_order[_classify_scc_severity(s, graph)], -len(s))
    )

    lines.append("## 🔄 সার্কুলার ডিপেন্ডেন্সি গ্রুপ")
    lines.append("")

    for idx, scc in enumerate(sorted_sccs, 1):
        severity = _classify_scc_severity(scc, graph)
        icon = SEVERITY_ICONS.get(severity, "⚪")
        cycles = _find_cycles_in_scc(scc, graph)

        lines.append(f"### {icon} গ্রুপ {idx}: {severity} ({len(scc)} মডিউল)")
        lines.append("")

        # মডিউল তালিকা
        lines.append("**মডিউলগুলো:**")
        for mod in sorted(scc):
            fp = module_to_file.get(mod)
            if fp:
                try:
                    lines.append(f"- `{mod}` → `{fp.relative_to(REPO_ROOT)}`")
                except ValueError:
                    lines.append(f"- `{mod}` → `{fp}`")
            else:
                lines.append(f"- `{mod}`")
        lines.append("")

        # চক্রের ভিজুয়ালাইজেশন
        if cycles:
            lines.append("**চক্রের পাথ:**")
            for c in cycles:
                lines.append(_visualize_cycle(c, severity))
            lines.append("")

        # SCC-র ভিতরের এজ
        lines.append("**ইম্পোর্ট এজ:**")
        lines.append("")
        lines.append("```")
        scc_set = set(scc)
        for mod in sorted(scc):
            for target, raw, sev in graph.get(mod, []):
                if target in scc_set:
                    sev_icon = SEVERITY_ICONS.get(sev, "⚪")
                    lines.append(f"{sev_icon} {mod} → {target}")
                    lines.append(f"   {raw}")
        lines.append("```")
        lines.append("")

        # ফিক্স সাজেশন
        if cycles:
            lines.append("**সমাধান সাজেশন:**")
            lines.append("")
            for c in cycles:
                for suggestion in _suggest_fixes(c, graph):
                    lines.append(suggestion)
                    lines.append("")

        lines.append("---")
        lines.append("")

    # শীর্ষ ১০ সবচেয়ে বেশি ইম্পোর্টকারী
    lines.append("## 📈 শীর্ষ ১০ সবচেয়ে বেশি ইন্টারনাল ইম্পোর্টকারী মডিউল")
    lines.append("")
    import_counts = sorted(
        ((mod, len(edges)) for mod, edges in graph.items()), key=lambda x: -x[1]
    )
    lines.append("| মডিউল | ইন্টারনাল ইম্পোর্ট |")
    lines.append("|---|---|")
    for mod, count in import_counts[:10]:
        lines.append(f"| `{mod}` | {count} |")
    lines.append("")

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────
# JSON আউটপুট
# ────────────────────────────────────────────────────────────
def _generate_json_report(
    sccs: List[List[str]],
    graph: ImportGraph,
    all_modules: Set[str],
    module_to_file: Dict[str, Path],
    elapsed: float,
    target_module: Optional[str] = None,
) -> Dict[str, Any]:
    """স্ট্রাকচার্ড JSON রিপোর্ট তৈরি করে — CI/CD পাইপলাইনে ব্যবহারের জন্য।"""
    total_edges = sum(len(edges) for edges in graph.values())
    total_imports_per_mod = (
        sum(len(edges) for edges in graph.values()) / len(all_modules)
        if all_modules
        else 0.0
    )
    largest_scc = max((len(s) for s in sccs), default=0)

    sev_order = {"CRITICAL": 0, "LAZY": 1, "CONDITIONAL": 2}
    sorted_sccs = sorted(
        sccs, key=lambda s: (sev_order[_classify_scc_severity(s, graph)], -len(s))
    )

    scc_data = []
    for scc in sorted_sccs:
        severity = _classify_scc_severity(scc, graph)
        cycles = _find_cycles_in_scc(scc, graph)
        scc_set = set(scc)
        edges = []
        for mod in sorted(scc):
            for target, raw, sev in graph.get(mod, []):
                if target in scc_set:
                    edges.append({
                        "from": mod,
                        "to": target,
                        "raw": raw,
                        "severity": sev,
                    })
        scc_data.append({
            "severity": severity,
            "size": len(scc),
            "modules": sorted(scc),
            "files": {
                mod: str(module_to_file.get(mod, "")) for mod in sorted(scc)
            },
            "cycles": cycles,
            "edges": edges,
            "suggestions": _suggest_fixes(cycles[0], graph) if cycles else [],
        })

    return {
        "timestamp": _timestamp(),
        "scan_time_seconds": round(elapsed, 2),
        "target_module": target_module,
        "stats": {
            "total_modules": len(all_modules),
            "total_internal_edges": total_edges,
            "avg_imports_per_module": round(total_imports_per_mod, 1),
            "scc_count": len(sccs),
            "largest_scc_size": largest_scc,
        },
        "circular_dependencies": scc_data,
    }


# ────────────────────────────────────────────────────────────
# Graphviz DOT ফরম্যাট আউটপুট
# ────────────────────────────────────────────────────────────
def _generate_dot(
    sccs: List[List[str]],
    graph: ImportGraph,
    all_modules: Set[str],
) -> str:
    """Graphviz DOT ফরম্যাটে সার্কুলার ডিপেন্ডেন্সি গ্রাফ তৈরি করে।
    
    ব্যবহার: python circular_import_mapper.py --dot | dot -Tpng -o cycles.png
    """
    lines: List[str] = []
    lines.append("digraph circular_imports {")
    lines.append("  rankdir=LR;")
    lines.append('  fontname="Helvetica";')
    lines.append('  node [shape=box, style=filled, fontname="Helvetica"];')
    lines.append("")

    # রঙ ম্যাপিং
    color_map = {
        "CRITICAL": "#ff4444",
        "LAZY": "#ffaa00",
        "CONDITIONAL": "#4488ff",
    }

    # প্রতিটি SCC-র জন্য সাবগ্রাফ
    for idx, scc in enumerate(sccs):
        severity = _classify_scc_severity(scc, graph)
        color = color_map.get(severity, "#999999")
        lines.append(f"  subgraph cluster_{idx} {{")
        lines.append(f'    label="{severity} SCC #{idx + 1} ({len(scc)} modules)";')
        lines.append(f'    style=filled;')
        lines.append(f'    color="{color}";')
        lines.append(f'    fillcolor="{color}22";')
        lines.append(f'    fontcolor="{color}";')
        for mod in scc:
            safe = mod.replace(".", "_").replace("-", "_")
            lines.append(f'    {safe} [label="{mod}", fillcolor="{color}44"];')
        lines.append("  }")
        lines.append("")

    # এজ যোগ করি
    lines.append("  # ইম্পোর্ট এজ (শুধু সার্কুলার)")
    for scc in sccs:
        scc_set = set(scc)
        for mod in scc:
            for target, _, sev in graph.get(mod, []):
                if target in scc_set:
                    src_safe = mod.replace(".", "_").replace("-", "_")
                    tgt_safe = target.replace(".", "_").replace("-", "_")
                    color = color_map.get(sev, "#999999")
                    style = "bold" if sev == "CRITICAL" else ("dashed" if sev == "LAZY" else "dotted")
                    lines.append(f'  {src_safe} -> {tgt_safe} [color="{color}", style={style}];')

    lines.append("}")
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────
# CLI আর্গুমেন্ট পার্সিং
# ────────────────────────────────────────────────────────────
def _parse_args() -> argparse.Namespace:
    """কমান্ড-লাইন আর্গুমেন্ট পার্স করে।"""
    parser = argparse.ArgumentParser(
        description="SupremeAI সার্কুলার ইম্পোর্ট ম্যাপার — import চক্র শনাক্তকারী টুল",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
উদাহরণ:
  %(prog)s                          # মার্কডাউন রিপোর্ট আউটপুট
  %(prog)s --json                  # JSON ফরম্যাটে আউটপুট
  %(prog)s --dot                   # Graphviz DOT ফরম্যাট
  %(prog)s --module services.llm   # নির্দিষ্ট মডিউল চেক
  %(prog)s --module core.config --json

এক্সিট কোড:
  0 = কোনো চক্র নেই  |  1 = চক্র পাওয়া গেছে  |  2 = ত্রুটি
""",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="JSON ফরম্যাটে আউটপুট (CI/CD পাইপলাইনের জন্য)",
    )
    parser.add_argument(
        "--dot",
        action="store_true",
        default=False,
        help="Graphviz DOT ফরম্যাটে আউটপুট (ভিজুয়ালাইজেশনের জন্য)",
    )
    parser.add_argument(
        "--module",
        type=str,
        default=None,
        help="নির্দিষ্ট মডিউলের ডিপেন্ডেন্সি চেক করুন (যেমন: services.llm)",
    )
    return parser.parse_args()


# ────────────────────────────────────────────────────────────
# মেইন এন্ট্রি পয়েন্ট
# ────────────────────────────────────────────────────────────
def main() -> int:
    """স্ক্রিপ্টের মূল ফাংশন — সব ধাপ পরিচালনা করে।
    
    ধাপ ১: সব .py ফাইল আবিষ্কার
    ধাপ ২: মডিউল ম্যাপিং তৈরি
    ধাপ ৩: ইম্পোর্ট গ্রাফ নির্মাণ
    ধাপ ৪: Tarjan's SCC অ্যালগরিদম চালানো
    ধাপ ৫: রিপোর্ট জেনারেশন এবং আউটপুট
    
    রিটার্ন: এক্সিট কোড (0=পরিষ্কার, 1=চক্র আছে, 2=ত্রুটি)
    """
    args = _parse_args()

    # ব্যাকএন্ড ডিরেক্টরি আছে কিনা চেক
    if not BACKEND_DIR.is_dir():
        print(f"ত্রুটি: ব্যাকএন্ড ডিরেক্টরি পাওয়া যায়নি: {BACKEND_DIR}", file=sys.stderr)
        return 2

    # ── ধাপ ১: সব .py ফাইল আবিষ্কার ──
    t0 = time.monotonic()
    py_files = _discover_py_files()
    if not py_files:
        print("ত্রুটি: backend/ এ কোনো .py ফাইল পাওয়া যায়নি", file=sys.stderr)
        return 2

    # ── ধাপ ২: মডিউল ↔ ফাইল ম্যাপিং ──
    module_to_file: Dict[str, Path] = {}
    all_modules: Set[str] = set()
    for fp in py_files:
        mod = _file_to_module(fp)
        if mod:
            module_to_file[mod] = fp
            all_modules.add(mod)

    # নির্দিষ্ট মডিউল চেক
    if args.module and args.module not in all_modules:
        # প্রিফিক্স ম্যাচ চেক
        prefix_matches = [m for m in all_modules if m.startswith(args.module)]
        if not prefix_matches:
            print(
                f"ত্রুটি: মডিউল '{args.module}' পাওয়া যায়নি",
                file=sys.stderr,
            )
            return 2

    # ── ধাপ ৩: ইম্পোর্ট গ্রাফ নির্মাণ ──
    graph = _build_import_graph(py_files, module_to_file, all_modules, args.module)
    t_parse = time.monotonic() - t0

    # ── ধাপ ৪: SCC অ্যালগরিদম ──
    t_scc_start = time.monotonic()
    sccs = _tarjan_scc(graph, all_modules)
    t_scc = time.monotonic() - t_scc_start
    elapsed = time.monotonic() - t0

    # ── ধাপ ৫: আউটপুট ──
    if args.json:
        report = _generate_json_report(sccs, graph, all_modules, module_to_file, elapsed, args.module)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.dot:
        print(_generate_dot(sccs, graph, all_modules))
    else:
        # মার্কডাউন রিপোর্ট + পারফরম্যান্স নোট
        md = _generate_markdown_report(sccs, graph, all_modules, module_to_file, elapsed, args.module)
        print(md)
        # stderr-এ পারফরম্যান্স তথ্য (CI লগের জন্য)
        print(
            f"\n[পারফরম্যান্স] পার্স: {t_parse:.2f}s | SCC: {t_scc:.2f}s | মোট: {elapsed:.2f}s | ফাইল: {len(py_files)}",
            file=sys.stderr,
        )

    # ── এক্সিট কোড ──
    if sccs:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
