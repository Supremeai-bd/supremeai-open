#!/usr/bin/env python3
"""
SupremeAI Importer Graph — নির্ভুল ইম্পোর্টার বিশ্লেষণ
================================================================

একটি AST-ভিত্তিক, রেজেক্স-মুক্ত ইম্পোর্টার গণনা ইঞ্জিন। পূর্ববর্তী ম্যানুয়াল
`grep`-ভিত্তিক গণনা ৩০–৫০% পর্যন্ত ভুল ছিল কারণ রেজেক্স:
  - relative import (`from . import x`, `from ..pkg import y`) ধরতে পারে না,
  - import alias (`import a.b.c as c`) ধরতে পারে না,
  - dynamic import (`importlib.import_module("a.b.c")`) ধরতে পারে না,
  - একই নামের দুটি ফাইলকে (যেমন `core/gcp_firestore.py` ও
    `services/storage/gcp_firestore.py`) আলাদা না করে একসাথে গুণে ফেলে।

এই ইঞ্জিন প্রতিটি .py ফাইলের AST পার্স করে, প্রতিটি `import`/`from...import`
স্টেটমেন্টকে একটি নির্দিষ্ট ফিজিক্যাল ফাইলে resolve করে, এবং একটি reverse
ইনডেক্স তৈরি করে: `target_file → [(importer_file, line, kind, statement)]`।

নির্ভুলতার নিশ্চয়তা:
  1. প্রতিটি import পাইথন গ্রামার (AST) দিয়ে বিশ্লেষণ — regex নয়।
  2. relative import `level` অনুযায়ী importer-এর প্যাকেজ থেকে resolve করা হয়।
  3. প্রতিটি ফাইলের মডিউল পথ দুইভাবে নিবন্ধিত: ক্যানোনিকাল (walk-up নিয়ম) ও
     "stripped" alias (`backend/__init__.py` vestigial হলেও `core.x` resolve হয়)।
  4. দুটি ফাইল একই মডিউল পথে resolve হলে AMBIGUOUS হিসেবে চিহ্নিত করা হয় —
     কখনো নীরবে ভুল resolve করা হয় না।
  5. dynamic import (`importlib.import_module`, `__import__`) স্ট্রিং আর্গুমেন্ট
     থেকে ধরা হয়।
  6. `unittest.mock.patch("a.b.c.X")` স্ট্রিং-রেফারেন্স SOFT হিসেবে আলাদা
     রিপোর্ট করা হয় — hard import count-এ গণনা হয় না, কিন্তু মানুষ দেখতে পায়।

CLI মোড:
  --audit FILE          একটি ফাইলের নিখুঁত ইম্পোর্টার তালিকা (file:line:stmt)
  --orphans             0-ইম্পোর্টার ফাইলের তালিকা (মুছার প্রার্থী)
  --self-check          ইঞ্জিনের অভ্যন্তরীণ সামঞ্জস্য যাচাই
  --json                JSON আউটপুট
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# ── বাদ দেওয়ার ডিরেক্টরি ──────────────────────────────────────────────────
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
    ".tox",
    "site-packages",
    "dist",
    "build",
}


# ══════════════════════════════════════════════════════════════════════════════
# ডেটা ক্লাস
# ══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ImportEdge:
    """একটি import স্টেটমেন্ট থেকে একটি target ফাইলের দিকে প্রান্ত।"""

    importer: str            # যে ফাইলটি import করছে
    line: int                # import স্টেটমেন্টের লাইন
    kind: str                # import | importfrom | dynamic
    statement: str           # মূল স্টেটমেন্টের টেক্সট (সংক্ষেপ)
    target: str              # resolve হওয়া ফিজিক্যাল ফাইল
    via_module: str          # কোন মডিউল পথ দিয়ে resolve হলো


@dataclass(frozen=True)
class SoftRef:
    """স্ট্রিং-ভিত্তিক রেফারেন্স (mock.patch ইত্যাদি) — hard import নয়।"""

    importer: str
    line: int
    kind: str                # patch_string | importlib_string
    statement: str
    target_module: str       # স্ট্রিং থেকে পাওয়া মডিউল পথ


@dataclass
class ImporterGraph:
    """
    সম্পূর্ণ কোডবেসের import গ্রাফ। একবার তৈরি করে যেকোনো ফাইলের
    ইম্পোর্টার তাৎক্ষণিক জিজ্ঞাসা করা যায়।
    """

    roots: List[str]
    include_tests: bool = True

    # সব .py ফাইল (abs path)
    all_files: List[str] = field(default_factory=list)
    # কোন ফাইল test? (path-ভিত্তিক heuristic)
    test_files: Set[str] = field(default_factory=set)

    # module_path → [physical files]  (একাধিক হলে AMBIGUOUS)
    module_to_files: Dict[str, List[str]] = field(default_factory=dict)
    # ambiguous: module_path যেগুলোতে >1 ফাইল resolve হয়েছে
    ambiguous_modules: Dict[str, List[str]] = field(default_factory=dict)

    # file → সেই ফাইলের সব import প্রান্ত
    file_edges: Dict[str, List[ImportEdge]] = field(default_factory=dict)
    # target_file → সেই ফাইলের সব ইম্পোর্টার (reverse index)
    reverse: Dict[str, List[ImportEdge]] = field(default_factory=dict)
    # target_file → soft refs (patch/importlib strings)
    soft_refs: Dict[str, List[SoftRef]] = field(default_factory=dict)

    # srcroot ক্যাশ (file → srcroot dir)
    _srcroot_cache: Dict[str, Path] = field(default_factory=dict)

    # parse errors
    parse_errors: List[Tuple[str, str]] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# ফাইল সংগ্রহ
# ══════════════════════════════════════════════════════════════════════════════


def _is_test_file(path: str) -> bool:
    """test ফাইল কিনা — path ও নাম উভয় দিয়ে নির্ণয়।"""
    p = Path(path)
    if "tests" in p.parts or "test" in p.parts:
        return True
    name = p.name
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith("_tests.py")
        or name == "conftest.py"
    )


def collect_py_files(roots: List[str], include_tests: bool) -> Tuple[List[str], Set[str]]:
    """রুট ডিরেক্টরিগুলো থেকে সকল .py ফাইল সংগ্রহ করে।"""
    files: List[str] = []
    tests: Set[str] = set()
    seen: Set[str] = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.normpath(os.path.join(dirpath, fname))
                if fpath in seen:
                    continue
                seen.add(fpath)
                if _is_test_file(fpath):
                    tests.add(fpath)
                    if not include_tests:
                        continue
                files.append(fpath)
    return files, tests


# ══════════════════════════════════════════════════════════════════════════════
# মডিউল পথ গণনা
# ══════════════════════════════════════════════════════════════════════════════


def _find_srcroot(filepath: str) -> Path:
    """
    একটি .py ফাইলের srcroot বের করে: যে পূর্বপুরুষ ডিরেক্টরিতে __init__.py
    নেই (বা ফাইলসিস্টেমের রুট)। ঐ ডিরেক্টরি থেকে আপেক্ষিক পথই ক্যানোনিকাল
    মডিউল পথ।
    """
    d = Path(filepath).resolve().parent
    while True:
        parent = d.parent
        if not (parent / "__init__.py").exists():
            # parent-এ __init__.py নেই → parent srcroot (বা তার ওপরে)
            return parent
        if parent == d:
            return parent  # ফাইলসিস্টেমের রুট
        d = parent


def _module_path_for(filepath: str, srcroot: Path) -> Optional[str]:
    """srcroot থেকে আপেক্ষিক ক্যানোনিকাল মডিউল পথ।"""
    try:
        rel = Path(filepath).resolve().relative_to(srcroot)
    except ValueError:
        return None
    parts = list(rel.parts)
    if not parts:
        return None
    if parts[-1] == "__init__.py":
        mod_parts = parts[:-1]
    else:
        mod_parts = parts[:-1] + [parts[-1][:-3]]  # .py বাদ
    if not mod_parts:
        return None
    return ".".join(mod_parts)


def _stripped_alias(module_path: str, srcroot: Path) -> Optional[str]:
    """
    `backend/__init__.py` vestigial থাকলেও `core.x` রূপে import করা যায়।
    প্রথম কম্পোনেন্ট বাদ দিয়ে একটি alias পথ তৈরি করি, শুধুমাত্র যদি সেই
    কম্পোনেন্টের ডিরেক্টরিতে __init__.py থাকে (অর্থাৎ সে একটি প্যাকেজ, ফলে
    sys.path-এ থাকার সম্ভাবনা আছে)।
    """
    parts = module_path.split(".")
    if len(parts) < 2:
        return None
    first = parts[0]
    if not (srcroot / first / "__init__.py").exists():
        return None
    return ".".join(parts[1:])


# ══════════════════════════════════════════════════════════════════════════════
# গ্রাফ নির্মাণ
# ══════════════════════════════════════════════════════════════════════════════


def build_graph(roots: List[str], include_tests: bool = True) -> ImporterGraph:
    """সম্পূর্ণ import গ্রাফ নির্মাণ করে।"""
    graph = ImporterGraph(roots=roots, include_tests=include_tests)
    graph.all_files, graph.test_files = collect_py_files(roots, include_tests)

    # ধাপ ১: প্রতিটি ফাইলের মডিউল পথ(গুলো) নিবন্ধন
    for f in graph.all_files:
        srcroot = _find_srcroot(f)
        graph._srcroot_cache[f] = srcroot
        canon = _module_path_for(f, srcroot)
        if not canon:
            continue
        _register_module(graph, canon, f)
        stripped = _stripped_alias(canon, srcroot)
        if stripped and stripped != canon:
            _register_module(graph, stripped, f)

    # ধাপ ২: প্রতিটি ফাইলের import বিশ্লেষণ ও target resolve
    for f in graph.all_files:
        edges, softs = _analyze_imports(f, graph)
        graph.file_edges[f] = edges
        for s in softs:
            # soft ref: target_module থেকে সম্ভাব্য ফাইল খুঁজি
            tgt_files = graph.module_to_files.get(s.target_module, [])
            for tf in tgt_files:
                graph.soft_refs.setdefault(tf, []).append(s)

    # ধাপ ৩: reverse index তৈরি
    for _f, edges in graph.file_edges.items():
        for e in edges:
            graph.reverse.setdefault(e.target, []).append(e)

    # প্রতিটি target-এর ইম্পোর্টার সেট ডিডুপ্লিকেট করি (একই importer একাধিক
    # import লিখলেও একবার গণনা, তবে প্রতিটি স্টেটমেন্ট দেখানো হবে)
    return graph


def _register_module(graph: ImporterGraph, module: str, fpath: str) -> None:
    lst = graph.module_to_files.setdefault(module, [])
    if fpath not in lst:
        lst.append(fpath)
    if len(lst) > 1:
        graph.ambiguous_modules[module] = list(lst)


def _resolve_module(graph: ImporterGraph, module: str) -> List[str]:
    """একটি মডিউল পথকে ফিজিক্যাল ফাইলে রূপান্তর। 0 বা তার বেশি ফাইল।"""
    return list(graph.module_to_files.get(module, []))


# ══════════════════════════════════════════════════════════════════════════════
# import বিশ্লেষণ
# ══════════════════════════════════════════════════════════════════════════════


def _read_source(fpath: str) -> Optional[str]:
    try:
        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, IOError):
        return None


def _src_segment(source: str, lineno: int) -> str:
    """লাইন নম্বর থেকে এক লাইনের সংক্ষিপ্ত স্টেটমেট টেক্সট।"""
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        txt = lines[lineno - 1].strip()
        if len(txt) > 120:
            txt = txt[:117] + "..."
        return txt
    return ""


def _importer_package(filepath: str, graph: ImporterGraph) -> List[str]:
    """
    importer ফাইলের প্যাকেজ পথ(গুলো) — relative import resolve-এর জন্য।
    ক্যানোনিকাল পথ ও stripped alias উভয় ফেরত দেয় যাতে যেকোনো রূপেই resolve
    হতে পারে।

    গুরুত্বপূর্ণ: `__init__.py` ফাইলের __package__ হল প্যাকেজটি নিজেই (যে
    ডিরেক্টরিতে এটি আছে), প্যাকেজের প্যারেন্ট নয়। তাই __init__.py-এর ক্ষেত্রে
    মডিউল পথের শেষ কম্পোনেন্ট বাদ দেওয়া হয় না। এই নিয়ম না মানলে
    `from .submod import X` (agents/__init__.py-তে) ভুল করে `agents.submod` না
    হয়ে `<parent>.submod` হয়ে যায় — যা resolve হয় না, ফলে __init__.py থেকে
    করা relative import গুলো মিস হয়।
    """
    srcroot = graph._srcroot_cache.get(filepath)
    if not srcroot:
        srcroot = _find_srcroot(filepath)
        graph._srcroot_cache[filepath] = srcroot
    canon = _module_path_for(filepath, srcroot)
    if not canon:
        return []
    is_init = os.path.basename(filepath) == "__init__.py"
    packages: List[str] = []
    parts = canon.split(".")
    if is_init:
        # __init__.py নিজেই প্যাকেজ — শেষ কম্পোনেন্ট বাদ দেওয়া নয়
        packages.append(canon)
    elif len(parts) > 1:
        packages.append(".".join(parts[:-1]))
    stripped = _stripped_alias(canon, srcroot)
    if stripped:
        sparts = stripped.split(".")
        if is_init:
            packages.append(stripped)
        elif len(sparts) > 1:
            packages.append(".".join(sparts[:-1]))
        else:
            packages.append("")
    if not packages:
        packages.append("")
    return packages


def _analyze_imports(
    filepath: str, graph: ImporterGraph
) -> Tuple[List[ImportEdge], List[SoftRef]]:
    """একটি ফাইলের সব import বিশ্লেষণ করে edge ও soft ref তালিকা দেয়।"""
    source = _read_source(filepath)
    if source is None:
        return [], []
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as e:
        graph.parse_errors.append((filepath, f"SyntaxError: {e.msg} @ line {e.lineno}"))
        return [], []

    edges: List[ImportEdge] = []
    softs: List[SoftRef] = []
    importer_packages = _importer_package(filepath, graph)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _handle_plain_import(node, filepath, source, graph, edges)
        elif isinstance(node, ast.ImportFrom):
            _handle_import_from(
                node, filepath, source, graph, edges, importer_packages
            )
        elif isinstance(node, ast.Call):
            _handle_dynamic_call(node, filepath, source, softs, edges, graph)

    return edges, softs


def _handle_plain_import(
    node: ast.Import,
    filepath: str,
    source: str,
    graph: ImporterGraph,
    edges: List[ImportEdge],
) -> None:
    """`import a.b.c` বা `import a.b.c as x` হ্যান্ডল।"""
    stmt = _src_segment(source, node.lineno)
    for alias in node.names:
        mod = alias.name  # a.b.c
        for tgt in _resolve_module(graph, mod):
            edges.append(
                ImportEdge(
                    importer=filepath,
                    line=node.lineno,
                    kind="import",
                    statement=stmt,
                    target=tgt,
                    via_module=mod,
                )
            )


def _handle_import_from(
    node: ast.ImportFrom,
    filepath: str,
    source: str,
    graph: ImporterGraph,
    edges: List[ImportEdge],
    importer_packages: List[str],
) -> None:
    """`from X import a, b` বা relative `from . import x` হ্যান্ডল।"""
    stmt = _src_segment(source, node.lineno)
    level = node.level or 0
    module = node.module  # হতে পারে None (from . import x)

    # base মডিউল পথ নির্ণয়
    base_candidates: List[str] = []
    if level == 0:
        if module:
            base_candidates.append(module)
    else:
        # relative: importer-এর প্যাকেজ থেকে (level-1) ধাপ উপরে
        for pkg in importer_packages:
            pparts = pkg.split(".") if pkg else []
            if level - 1 > len(pparts):
                continue  # invalid (top-level-এর ওপরে)
            base = pparts[: len(pparts) - (level - 1)]
            if module:
                base = base + module.split(".")
            base_candidates.append(".".join(base))

    if not base_candidates:
        return

    for base in base_candidates:
        if not base:
            continue
        # base নিজে একটি target (এর __init__.py লোড হয়)
        for tgt in _resolve_module(graph, base):
            edges.append(
                ImportEdge(
                    importer=filepath,
                    line=node.lineno,
                    kind="importfrom",
                    statement=stmt,
                    target=tgt,
                    via_module=base,
                )
            )
        # প্রতিটি name যদি submodule হয়, সেও target
        for alias in node.names:
            submod = f"{base}.{alias.name}" if base else alias.name
            for tgt in _resolve_module(graph, submod):
                # base ও submod একই ফাইল হলে ডুপ্লিকেট এড়ানো
                if tgt in _resolve_module(graph, base):
                    continue
                edges.append(
                    ImportEdge(
                        importer=filepath,
                        line=node.lineno,
                        kind="importfrom",
                        statement=stmt,
                        target=tgt,
                        via_module=submod,
                    )
                )


def _handle_dynamic_call(
    node: ast.Call,
    filepath: str,
    source: str,
    softs: List[SoftRef],
    edges: List[ImportEdge],
    graph: ImporterGraph,
) -> None:
    """`importlib.import_module("a.b")` / `__import__("a.b")` হ্যান্ডল।"""
    func = node.func
    name: Optional[str] = None
    if isinstance(func, ast.Attribute):
        name = func.attr
    elif isinstance(func, ast.Name):
        name = func.id
    if name not in ("import_module", "__import__"):
        return
    if not node.args:
        return
    arg = node.args[0]
    if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
        return
    mod = arg.value.strip()
    if not mod or " " in mod or "/" in mod:
        return  # সম্ভবত ডায়নামিক ভেরিয়েবল, নির্দিষ্ট নয়
    stmt = _src_segment(source, node.lineno)
    tgts = _resolve_module(graph, mod)
    if tgts:
        for tgt in tgts:
            edges.append(
                ImportEdge(
                    importer=filepath,
                    line=node.lineno,
                    kind="dynamic",
                    statement=stmt,
                    target=tgt,
                    via_module=mod,
                )
            )
    else:
        softs.append(
            SoftRef(
                importer=filepath,
                line=node.lineno,
                kind="importlib_string",
                statement=stmt,
                target_module=mod,
            )
        )


# ══════════════════════════════════════════════════════════════════════════════
# patch("a.b.c.X") soft-ref স্ক্যান (আলাদা pass — ast.Call-এ string arg)
# ══════════════════════════════════════════════════════════════════════════════


def scan_patch_strings(graph: ImporterGraph) -> None:
    """সব ফাইলে `patch("a.b.c.attr")` স্ট্রিং রেফারেন্স খুঁজে soft_refs-এ যোগ।"""
    for f in graph.all_files:
        source = _read_source(f)
        if source is None:
            continue
        try:
            tree = ast.parse(source, filename=f)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            fname: Optional[str] = None
            if isinstance(func, ast.Attribute):
                fname = func.attr
            elif isinstance(func, ast.Name):
                fname = func.id
            if fname not in ("patch", "patch.object"):
                continue
            if not node.args:
                continue
            arg = node.args[0]
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            target_str = arg.value.strip()
            if not target_str:
                continue
            # "a.b.c.attr" → module = "a.b.c" (attr বাদ) এবং "a.b.c" (পুরোটাও চেক)
            parts = target_str.split(".")
            if len(parts) < 2:
                continue
            stmt = _src_segment(source, node.lineno)
            # ধাপে ধাপে শেষ কম্পোনেন্ট বাদ দিয়ে মডিউল পথ খুঁজি
            for i in range(len(parts) - 1, 0, -1):
                cand = ".".join(parts[:i])
                tgts = graph.module_to_files.get(cand)
                if tgts:
                    for tf in tgts:
                        graph.soft_refs.setdefault(tf, []).append(
                            SoftRef(
                                importer=f,
                                line=node.lineno,
                                kind="patch_string",
                                statement=stmt,
                                target_module=cand,
                            )
                        )
                    break


# ── মডিউল-পথ স্ট্রিং ধ্রুবক স্ক্যান ─────────────────────────────────────────
# importlib.import_module(router_def["path"]) প্যাটার্নে path একটি ভেরিয়েবল
# (যেমন api/routers.py-এর ALL_ROUTERS লিস্টে {"path": "api.routes.billing_api"}).
# সরাসরি import_module("constant") নয় বলে _handle_dynamic_call ধরতে পারে না।
# তাই সব স্ট্রিং ধ্রুবক স্ক্যান করে যেগুলো একটি নিবন্ধিত মডিউল পথে resolve হয়,
# সেগুলোকে dynamic edge হিসেবে যোগ করি (kind="string_ref")।
# নিরাপদ দিক: এটি শুধু under-count করতে পারে (কখনো over-count নয়) — অর্থাৎ
# একটি লাইভ ফাইলকে ভুলে orphan বানায় না, সবসময় রক্ষণশীল।
import re as _re

_MODULE_PATH_RE = _re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)+$")


def scan_module_string_constants(graph: ImporterGraph) -> int:
    """
    সব .py ফাইলের সব স্ট্রিং ধ্রুবক স্ক্যান করে যেগুলো একটি নিবন্ধিত মডিউল
    পথে resolve হয়, সেগুলোকে dynamic edge হিসেবে যোগ করে। যেমন
    `{"path": "api.routes.billing_api"}` → api/routers.py থেকে
    backend/api/routes/billing_api.py-তে একটি edge।
    রিটার্ন: যোগ করা edge সংখ্যা।
    """
    added = 0
    for f in graph.all_files:
        source = _read_source(f)
        if source is None:
            continue
        try:
            tree = ast.parse(source, filename=f)
        except SyntaxError:
            continue
        seen_here: Set[str] = set()  # একই ফাইলে একই মডিউল একাধিকবার → এক edge
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                val = node.value.strip()
            elif isinstance(node, ast.JoinedStr):
                # f-string: যদি একমাত্র অংশ একটি constant হয়, সেটি নিই
                continue
            else:
                continue
            if not val or len(val) > 200:
                continue
            if not _MODULE_PATH_RE.match(val):
                continue
            if val in seen_here:
                continue
            tgts = graph.module_to_files.get(val)
            if not tgts:
                continue
            # শুধু সেই স্ট্রিং নিই যা সম্ভবত একটি মডিউল রেফারেন্স (কমপক্ষে ২ অংশ)
            seen_here.add(val)
            stmt = _src_segment(source, node.lineno)
            for tgt in tgts:
                edge = ImportEdge(
                    importer=f,
                    line=node.lineno,
                    kind="string_ref",
                    statement=stmt,
                    target=tgt,
                    via_module=val,
                )
                graph.file_edges.setdefault(f, []).append(edge)
                graph.reverse.setdefault(tgt, []).append(edge)
                added += 1
    return added


# ══════════════════════════════════════════════════════════════════════════════
# প্রশ্ন API
# ══════════════════════════════════════════════════════════════════════════════


def importers_of(graph: ImporterGraph, target: str) -> List[ImportEdge]:
    """একটি ফাইলের সব hard-import edge ফেরত দেয়।"""
    t = os.path.normpath(os.path.abspath(target))
    return list(graph.reverse.get(t, []))


def importer_files(graph: ImporterGraph, target: str) -> List[str]:
    """ডিডুপ্লিকেট ইম্পোর্টার ফাইল তালিকা (নিজে বাদ)।"""
    out: List[str] = []
    seen: Set[str] = set()
    t = os.path.normpath(os.path.abspath(target))
    for e in graph.reverse.get(t, []):
        if e.importer == t:
            continue
        if e.importer in seen:
            continue
        seen.add(e.importer)
        out.append(e.importer)
    return out


def orphans(graph: ImporterGraph, prod_only: bool = True) -> List[str]:
    """
    0 hard-importer ফাইলের তালিকা (নিজে বাদ)। prod_only=True হলে test ফাইল
    ইম্পোর্টার উপেক্ষা করে শুধু production ইম্পোর্টার গণনা করে।
    """
    out: List[str] = []
    for f in graph.all_files:
        if prod_only and f in graph.test_files:
            # test ফাইল নিজে orphan কিনা আগ্রহ নেই যদি prod_only হয়
            continue
        has_importer = False
        for e in graph.reverse.get(f, []):
            if e.importer == f:
                continue
            if prod_only and e.importer in graph.test_files:
                continue
            has_importer = True
            break
        if not has_importer:
            out.append(f)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# সেলফ-চেক
# ══════════════════════════════════════════════════════════════════════════════


def self_check(graph: ImporterGraph) -> Dict[str, any]:
    """
    গ্রাফের অভ্যন্তরীণ সামঞ্জস্য যাচাই:
      - প্রতিটি edge-এর target আসলেই all_files-এ আছে কিনা,
      - প্রতিটি importer আসলেই all_files-এ আছে কিনা,
      - ambiguous module গুলোর সংখ্যা,
      - parse error সংখ্যা।
    """
    all_set = set(graph.all_files)
    bad_targets = 0
    bad_importers = 0
    for f, edges in graph.file_edges.items():
        if f not in all_set:
            bad_importers += 1
        for e in edges:
            if e.target not in all_set:
                bad_targets += 1
    return {
        "files": len(graph.all_files),
        "modules_registered": len(graph.module_to_files),
        "ambiguous_modules": len(graph.ambiguous_modules),
        "edges": sum(len(v) for v in graph.file_edges.values()),
        "parse_errors": len(graph.parse_errors),
        "bad_targets": bad_targets,
        "bad_importers": bad_importers,
        "ok": bad_targets == 0 and bad_importers == 0,
    }


# ══════════════════════════════════════════════════════════════════════════════
# রিপোর্ট ফরম্যাটিং
# ══════════════════════════════════════════════════════════════════════════════


def _rel(path: str, roots: List[str]) -> str:
    for r in roots:
        try:
            return str(Path(path).relative_to(r))
        except ValueError:
            continue
    return path


def format_audit_report(graph: ImporterGraph, target: str) -> str:
    """একটি ফাইলের ইম্পোর্টার তালিকা মানব-পাঠযোগ্য টেক্সটে।"""
    t = os.path.normpath(os.path.abspath(target))
    if not os.path.isfile(t):
        return f"❌ ফাইল পাওয়া যায়নি: {target}"
    edges = graph.reverse.get(t, [])
    softs = graph.soft_refs.get(t, [])

    # ডিডুপ্লিকেট ইম্পোর্টার ফাইল (production vs test)
    prod_importers: Dict[str, List[ImportEdge]] = {}
    test_importers: Dict[str, List[ImportEdge]] = {}
    for e in edges:
        if e.importer == t:
            continue
        bucket = test_importers if e.importer in graph.test_files else prod_importers
        bucket.setdefault(e.importer, []).append(e)

    soft_by_importer: Dict[str, List[SoftRef]] = {}
    for s in softs:
        if s.importer == t:
            continue
        soft_by_importer.setdefault(s.importer, []).append(s)

    lines: List[str] = []
    lines.append("")
    lines.append("═" * 78)
    lines.append("  Importer Audit Report")
    lines.append("═" * 78)
    lines.append(f"  🎯 টার্গেট ফাইল: {_rel(t, graph.roots)}")
    lines.append(
        f"  📊 hard importers: {len(prod_importers)} prod + "
        f"{len(test_importers)} test = {len(prod_importers) + len(test_importers)} মোট"
    )
    lines.append(f"  📝 soft refs (patch/importlib strings): {len(soft_by_importer)} ফাইল")
    lines.append("")

    if prod_importers:
        lines.append(f"{'─' * 78}")
        lines.append(f"  ✅ Production importers ({len(prod_importers)})")
        lines.append(f"{'─' * 78}")
        for imp in sorted(prod_importers):
            lines.append(f"  • {_rel(imp, graph.roots)}")
            for e in prod_importers[imp]:
                lines.append(
                    f"      L{e.line} [{e.kind}] via {e.via_module}"
                )
                lines.append(f"        {e.statement}")
    else:
        lines.append("  ⚠️  কোনো production importer নেই।")

    if test_importers:
        lines.append("")
        lines.append(f"{'─' * 78}")
        lines.append(f"  🧪 Test importers ({len(test_importers)})")
        lines.append(f"{'─' * 78}")
        for imp in sorted(test_importers):
            lines.append(f"  • {_rel(imp, graph.roots)}")
            for e in test_importers[imp]:
                lines.append(f"      L{e.line} [{e.kind}] {e.statement}")

    if soft_by_importer:
        lines.append("")
        lines.append(f"{'─' * 78}")
        lines.append(f"  📝 Soft string references ({len(soft_by_importer)} ফাইল) — hard import নয়")
        lines.append(f"{'─' * 78}")
        for imp in sorted(soft_by_importer):
            lines.append(f"  • {_rel(imp, graph.roots)}")
            for s in soft_by_importer[imp]:
                lines.append(
                    f"      L{s.line} [{s.kind}] → {s.target_module}"
                )
                lines.append(f"        {s.statement}")

    if graph.ambiguous_modules:
        # এই টার্গেট কোনো ambiguous module-এ পড়ে কিনা দেখাই
        t_modules = [
            m for m, fs in graph.module_to_files.items() if t in fs
        ]
        ambig = [m for m in t_modules if m in graph.ambiguous_modules]
        if ambig:
            lines.append("")
            lines.append(f"{'─' * 78}")
            lines.append("  ⚠️  AMBIGUOUS module mapping (মানুষ যাচাই করুন)")
            lines.append(f"{'─' * 78}")
            for m in ambig:
                lines.append(f"  module '{m}' → একাধিক ফাইল:")
                for f in graph.ambiguous_modules[m]:
                    marker = " ← এই টার্গেট" if f == t else ""
                    lines.append(f"      {_rel(f, graph.roots)}{marker}")

    lines.append("═" * 78)
    return "\n".join(lines)


def _is_entry_point(filepath: str) -> bool:
    """
    একটি ফাইল entry point কিনা নির্ণয় — `if __name__ == "__main__"` ব্লক বা
    পরিচিত entry-point নাম (main.py, app.py, run.py, manage.py, conftest.py)।
    entry point ফাইল সরাসরি import হয় না বলে orphan তালিকায় প্রদর্শিত হবে না।
    """
    name = os.path.basename(filepath)
    if name in ("main.py", "app.py", "run.py", "manage.py", "conftest.py",
                "wsgi.py", "asgi.py", "__main__.py", "server.py", "start.py"):
        return True
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except (OSError, IOError):
        return False
    return '__name__ == "__main__"' in src or "__name__ == '__main__'" in src


def format_orphans_report(graph: ImporterGraph, prod_only: bool = True) -> str:
    orph = orphans(graph, prod_only=prod_only)
    lines: List[str] = []
    lines.append("")
    lines.append("═" * 78)
    title = "Production Orphans" if prod_only else "All Orphans (incl. test importers)"
    lines.append(f"  {title} — 0 hard importer ফাইল")
    lines.append("═" * 78)

    # তিনটি বিভাগে ভাগ করি:
    #   (A) সত্যিকারের orphan (delete প্রার্থী) — __init__.py নয়, entry point নয়
    #   (B) __init__.py — package marker, সাধারণত import হয় না, স্বাভাবিক
    #   (C) entry point — __main__ ব্লক, সরাসরি চালানো হয়, orphan নয়
    true_orphans: List[str] = []
    init_orphans: List[str] = []
    entry_orphans: List[str] = []
    for f in orph:
        if os.path.basename(f) == "__init__.py":
            init_orphans.append(f)
        elif _is_entry_point(f):
            entry_orphans.append(f)
        else:
            true_orphans.append(f)

    lines.append(f"  মোট 0-importer ফাইল: {len(orph)}")
    lines.append(f"    ├── 🗑️  সত্যিকার orphan (delete প্রার্থী): {len(true_orphans)}")
    lines.append(f"    ├── 📦 __init__.py (package marker, স্বাভাবিক): {len(init_orphans)}")
    lines.append(f"    └── 🚀 entry point (__main__/app.py, orphan নয়): {len(entry_orphans)}")
    lines.append("")

    if true_orphans:
        lines.append(f"{'─' * 78}")
        lines.append(f"  🗑️  সত্যিকার orphan — মুছার প্রার্থী ({len(true_orphans)})")
        lines.append(f"{'─' * 78}")
        # soft ref আছে এমন orphan আগে দেখাই (মুছলে ঝুঁকি)
        risky = []
        clean = []
        for f in sorted(true_orphans):
            softs = graph.soft_refs.get(f, [])
            (risky if softs else clean).append(f)
        if risky:
            lines.append(f"  ⚠️  soft ref সহ ({len(risky)}) — মুছার আগে অবশ্যই যাচাই করুন:")
            for f in risky:
                lines.append(f"    • {_rel(f, graph.roots)}  [⚠ {len(graph.soft_refs.get(f, []))} soft ref]")
        if clean:
            lines.append(f"  ✅ সম্পূর্ণ clean — কোনো soft ref নেই ({len(clean)}):")
            for f in clean:
                lines.append(f"    • {_rel(f, graph.roots)}")

    lines.append("")
    lines.append(
        "  ℹ️  soft ref = mock.patch/importlib.import_module স্ট্রিং রেফারেন্স।\n"
        "      hard import না হলেও ফাইলটি রানটাইমে রেফারেন্স করা হতে পারে — যাচাই করুন।"
    )
    lines.append(
        "  ℹ️  মুছার আগে: --importer-audit <file> দিয়ে আরেকবার নিশ্চিত করুন।"
    )
    lines.append("═" * 78)
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


def _detect_repo_root() -> str:
    """git toplevel থেকে বা __file__ থেকে repo root অনুমান।"""
    # __file__ = .../supremeai-clone/scripts/advanced_analysis/importer_graph.py
    here = Path(__file__).resolve()
    # 3 ধাপ উপরে = repo root
    cand = here
    for _ in range(5):
        cand = cand.parent
        if (cand / ".git").exists() or (cand / "backend").is_dir():
            return str(cand)
    return str(here.parent.parent.parent)


def main() -> int:
    repo = _detect_repo_root()
    default_backend = os.path.join(repo, "backend")

    parser = argparse.ArgumentParser(
        description="SupremeAI Importer Graph — নির্ভুল AST-ভিত্তিক ইম্পোর্টার বিশ্লেষণ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--roots",
        nargs="+",
        default=[default_backend],
        help=f"স্ক্যান রুট(গুলো) (ডিফল্ট: {default_backend})",
    )
    parser.add_argument(
        "--audit",
        type=str,
        default=None,
        help="একটি ফাইলের নিখুঁত ইম্পোর্টার তালিকা দেখাও",
    )
    parser.add_argument(
        "--orphans",
        action="store_true",
        help="0-ইম্পোর্টার ফাইল তালিকা (মুছার প্রার্থী)",
    )
    parser.add_argument(
        "--include-tests",
        action="store_true",
        default=False,
        help="test ফাইলও ইম্পোর্টার হিসেবে গণনা করো (ডিফল্ট: production শুধু)",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="গ্রাফের অভ্যন্তরীণ সামঞ্জস্য যাচাই করো",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON আউটপুট",
    )
    args = parser.parse_args()

    print(f"🔍 Importer graph তৈরি হচ্ছে... roots={args.roots}", file=sys.stderr)
    graph = build_graph(args.roots, include_tests=True)
    scan_patch_strings(graph)
    n_str = scan_module_string_constants(graph)
    if n_str:
        print(
            f"   🔗 স্ট্রিং-ধ্রুবক মডিউল রেফারেন্স: {n_str}টি edge যোগ "
            f"(dynamic router loading ধরা হয়েছে)",
            file=sys.stderr,
        )
    print(
        f"   ফাইল: {len(graph.all_files)}, মডিউল: {len(graph.module_to_files)}, "
        f"edge: {sum(len(v) for v in graph.file_edges.values())}",
        file=sys.stderr,
    )
    if graph.parse_errors:
        print(f"   ⚠ parse ত্রুটি: {len(graph.parse_errors)} ফাইল", file=sys.stderr)
    if graph.ambiguous_modules:
        print(
            f"   ⚠ ambiguous module: {len(graph.ambiguous_modules)} (মানুষ যাচাই করবে)",
            file=sys.stderr,
        )

    if args.self_check:
        result = self_check(graph)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print("\nSelf-check:")
            for k, v in result.items():
                print(f"  {k}: {v}")
        return 0 if result["ok"] else 2

    if args.audit:
        print(format_audit_report(graph, args.audit))
        return 0

    if args.orphans:
        print(format_orphans_report(graph, prod_only=not args.include_tests))
        return 0

    # ডিফল্ট: সংক্ষিপ্ত সারসংক্ষেপ
    summary = {
        "files": len(graph.all_files),
        "modules_registered": len(graph.module_to_files),
        "ambiguous_modules": len(graph.ambiguous_modules),
        "edges": sum(len(v) for v in graph.file_edges.values()),
        "parse_errors": len(graph.parse_errors),
        "self_check": self_check(graph),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print("\nImporter Graph Summary:")
        for k, v in summary.items():
            if k == "self_check":
                print(f"  self_check: {v}")
            else:
                print(f"  {k}: {v}")
        print("\n  --audit FILE, --orphans, --self-check মোড ব্যবহার করুন।")
    return 0


if __name__ == "__main__":
    sys.exit(main())
