# backend/core/code_indexer.py
"""Aider-inspired Repository Map (stdlib-ast, zero-dependency).

Mirrors core/markdown_indexer.py singleton pattern. Read-only, bounded, honest
stats — PLAN-003 (Aider-style repo map) implementation.

বাংলা: Python stdlib ``ast`` দিয়ে সিম্বল (class/function) এক্সট্র্যাকশন,
intra-package import-edge গ্রাফ, pure-Python PageRank র‍্যাংকিং, এবং টোকেন-বাজেটে
(aider-style) রেন্ডার। tree_sitter-এর মতো ভারী dependency নেই (#3 Reuse Before
Creation)। সব ক্যাপ হার্ড — Render 512MB container-এ memory-pressure গার্ড
(64MB source cap, 2000-file cap, 200k-symbol cap); স্ট্যাটস সৎ (#13 No Silent
Failure); ব্যর্থ হলে কলার আজকের মতোই probe চালায় — কোনো ভুয়া map নয় (#8)।
"""

from __future__ import annotations

import ast
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from core.logging_config import logger

_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    "htmlcov",
    "dist",
    "build",
    "coverage",
}
# Hard bounds — the 512MB cap-guard: even a worst-case tree keeps the index
# structures (symbols + edges + one source string at a time) far below the
# container memory headroom.
_MAX_FILES = 2000
_MAX_FILE_BYTES = 100_000
_MAX_TOTAL_BYTES = 64 * 1024 * 1024  # 64MB of source text — parse is per-file streaming
_MAX_SYMBOLS = 200_000
_PR_ITERS = 20
_PR_DAMP = 0.85
_GOAL_BOOST_CAP = 1.5  # multiplicative boost ceiling (plan risk-table mitigation)


class CodeIndexer:
    """Read-only symbol graph over a Python workspace root (bounded walk)."""

    _instance: CodeIndexer | None = None
    _instance_root: Path | None = None

    @classmethod
    def get_instance(cls, root_dir: str | Path = ".") -> CodeIndexer:
        resolved = Path(root_dir).resolve()
        if cls._instance is None or cls._instance_root != resolved:
            cls._instance = cls(resolved)
            cls._instance_root = resolved
        return cls._instance

    def __init__(self, root_dir: str | Path = ".") -> None:
        self.root = Path(root_dir).resolve()
        self._stats: dict[str, Any] = {}
        self._symbols: dict[str, list[str]] = {}  # rel_path -> ["Cls:Foo", "Def:bar", ...]
        self._edges: dict[str, set[str]] = defaultdict(set)  # rel_path -> {rel_path, ...}
        self._rank: dict[str, float] = {}

    # -- bounded walk + ast extraction (read-only) --
    def _walk_py_files(self) -> list[Path]:
        """Bounded rglob: skip junk dirs, 100KB/file, 2000 files, 64MB total.

        বাংলা: ছোট ফাইল আগে (বাউন্ডেড walk) — তবে ক্যাপ ছাড়াই সাধারণত পুরো
        রিপো ঢুকে যায়; ক্যাপ কেবল worst-case গার্ড।
        """
        candidates: list[Path] = []
        total = 0
        for p in self.root.rglob("*.py"):
            if set(p.parts) & _SKIP_DIRS:
                continue
            try:
                size = p.stat().st_size
            except OSError:
                continue
            if size > _MAX_FILE_BYTES:
                continue
            candidates.append(p)
            total += size
        candidates.sort(key=lambda p: p.stat().st_size)
        files = candidates[:_MAX_FILES]
        if len(candidates) > _MAX_FILES:
            self._stats["files_skipped_cap"] = len(candidates) - _MAX_FILES
        if total > _MAX_TOTAL_BYTES:
            # Keep trimming largest-last until under the source-byte cap.
            kept: list[Path] = []
            kept_bytes = 0
            for p in files:
                s = p.stat().st_size
                if kept_bytes + s <= _MAX_TOTAL_BYTES:
                    kept.append(p)
                    kept_bytes += s
                else:
                    self._stats["files_skipped_cap"] = self._stats.get("files_skipped_cap", 0) + 1
            files = kept
        return files

    def _resolve_module(self, module: str, source_rel: str) -> str | None:
        """Resolve a dotted absolute module name to a repo-relative .py path.

        বাংলা: ``a.b.c`` → a/b/c.py অথবা a/b/__init__.py (যেটা root-এ exist
        করে)। relative import (node.level > 0) হলে source ফাইলের প্যাকেজ থেকে।
        """
        rel = module.replace(".", "/")
        for candidate in (f"{rel}.py", f"{rel}/__init__.py"):
            if (self.root / candidate).is_file():
                return candidate
        # Relative-import fallback: from .sibling import x
        if module and source_rel:
            base = self.root / source_rel
            sibling = (base.parent / (module.split(".")[0] + ".py")).resolve()
            if sibling.is_file() and sibling.is_relative_to(self.root):
                return str(sibling.relative_to(self.root))
        return None

    def build(self) -> dict[str, Any]:
        """Walk + parse the tree; returns honest stats (never raises)."""
        t0 = time.perf_counter()
        self._stats = {
            "files_indexed": 0,
            "parse_failures": 0,
            "files_skipped_cap": 0,
            "symbols": 0,
            "edges": 0,
            "bytes_indexed": 0,
        }
        self._symbols = {}
        self._edges = defaultdict(set)
        self._rank = {}
        symbol_budget = _MAX_SYMBOLS
        for p in self._walk_py_files():
            rel = str(p.relative_to(self.root))
            try:
                source = p.read_text(encoding="utf-8", errors="ignore")
                self._stats["bytes_indexed"] += len(source.encode("utf-8", errors="ignore"))
                tree = ast.parse(source)
            except (SyntaxError, OSError, ValueError):
                self._stats["parse_failures"] += 1
                continue
            syms: list[str] = []
            for node in tree.body:  # top-level only — cheap and sufficient (v1)
                if isinstance(node, ast.ClassDef):
                    syms.append(f"Cls:{node.name}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    syms.append(f"Def:{node.name}")
                elif isinstance(node, ast.ImportFrom):
                    targets: list[str] = []
                    if node.module:
                        targets.append(node.module)
                    elif node.level:  # from . import sibling
                        for alias in node.names:
                            resolved = self._resolve_module(alias.name, rel)
                            if resolved:
                                self._edges[rel].add(resolved)
                    for module_name in targets:
                        resolved = self._resolve_module(module_name, rel)
                        if resolved and resolved != rel:
                            self._edges[rel].add(resolved)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        resolved = self._resolve_module(alias.name, rel)
                        if resolved and resolved != rel:
                            self._edges[rel].add(resolved)
            symbol_budget -= len(syms)
            self._symbols[rel] = syms
            if symbol_budget <= 0:
                self._stats["files_skipped_cap"] = self._stats.get("files_skipped_cap", 0)
                break
        self._stats["files_indexed"] = len(self._symbols)
        self._stats["symbols"] = sum(len(s) for s in self._symbols.values())
        self._stats["edges"] = sum(len(e) for e in self._edges.values())
        self._stats["elapsed_s"] = round(time.perf_counter() - t0, 3)
        self._rank = self._pagerank()
        logger.info(f"[CodeIndexer] {self._stats}")  # honest stats — No Silent Failure
        return dict(self._stats)

    # -- pure-Python PageRank (networkx-free) --
    def _pagerank(self) -> dict[str, float]:
        nodes = list(self._symbols)
        if not nodes:
            return {}
        rank = {n: 1.0 / len(nodes) for n in nodes}
        for _ in range(_PR_ITERS):
            new = {n: (1 - _PR_DAMP) / len(nodes) for n in nodes}
            for src in nodes:
                out = self._edges.get(src)
                if out:
                    share = _PR_DAMP * rank[src] / len(out)
                    for dst in out:
                        if dst in new:
                            new[dst] += share
                else:
                    # Dangling node: keep its mass locally (standard treatment).
                    new[src] += _PR_DAMP * rank[src]
            rank = new
        return rank

    # -- aider-style budgeted render, optional goal-boost via existing local embeddings --
    def render_repo_map(self, budget_chars: int = 4000, goal: str | None = None) -> str:
        """Render a ranked, budget-bounded repo map. Honest header, no fake lines."""
        if not self._symbols and not self._stats:
            self.build()
        if not self._rank:
            self._rank = self._pagerank()
        lines: list[tuple[float, str]] = []
        for rel, syms in self._symbols.items():
            r = self._rank.get(rel, 0.0)
            head = ", ".join(syms[:8]) + (" …" if len(syms) > 8 else "")
            lines.append((r, f"{rel} — {head}" if head else rel))
        lines.sort(key=lambda item: item[0], reverse=True)
        if goal:
            lines = self._apply_goal_boost(lines, goal)
        out: list[str] = []
        used = 0
        for _, line in lines:
            if used + len(line) + 1 > budget_chars:
                break
            out.append(line)
            used += len(line) + 1
        header = (
            f"[REPO MAP] root={self.root.name} files={self._stats.get('files_indexed', 0)} "
            f"parse_failures={self._stats.get('parse_failures', 0)} budget={budget_chars}c"
        )
        return "\n".join([header, *out])

    def _apply_goal_boost(
        self, lines: list[tuple[float, str]], goal: str
    ) -> list[tuple[float, str]]:
        """Cosine-boost ranks toward the goal using the existing local embedding engine.

        বাংলা: ব্যর্থ হলে pure PageRank ক্রমেই থাকে (graceful — কোনো exception
        বের হয় না); boost সর্বোচ্চ ×{_GOAL_BOOST_CAP}।
        """
        try:
            import numpy as np  # local-only, best-effort; repo already vendors numpy

            from core.embeddings import get_local_encoder, hash_vectorize, local_embed

            goal_vec = local_embed(goal) or hash_vectorize(goal)
            g = np.asarray(goal_vec, dtype="float32")
            paths = [line.split(" — ")[0] for _, line in lines]
            encoder = get_local_encoder()
            if encoder is not None:
                matrix = np.asarray(encoder.encode(paths, show_progress_bar=False), dtype="float32")
            else:
                matrix = np.asarray([hash_vectorize(p) for p in paths], dtype="float32")
            g_norm = float(np.linalg.norm(g)) or 1.0
            m_norm = np.linalg.norm(matrix, axis=1)
            m_norm[m_norm == 0.0] = 1.0
            cos = (matrix @ g) / (m_norm * g_norm)
            boosted: list[tuple[float, str]] = []
            for (rank, line), sim in zip(lines, cos.tolist(), strict=False):
                boost = 1.0 + max(0.0, float(sim))
                boosted.append((rank * min(boost, _GOAL_BOOST_CAP), line))
            boosted.sort(key=lambda item: item[0], reverse=True)
            return boosted
        except Exception as exc:  # graceful: rank-order alone is sufficient
            logger.warning(f"[CodeIndexer] goal-boost skipped ({exc})")
            return lines


def get_repo_map(
    budget_chars: int = 4000, goal: str | None = None, root_dir: str | Path = "."
) -> str:
    """Convenience accessor — singleton, read-only, honest-degradation safe."""
    return CodeIndexer.get_instance(root_dir).render_repo_map(budget_chars=budget_chars, goal=goal)
