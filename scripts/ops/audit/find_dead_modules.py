#!/usr/bin/env python3
"""Canonical dead-module auditor (MAINTAINABILITY_PLAN.md §2 / §13).

Builds an AST import graph over the repository and classifies every Python
module under ``backend/`` (excluding ``backend/_archive/``) as:

  imported          at least one importer anywhere (including tests)
  test-only         only importers live under backend/tests/**
  runtime-invoked   never imported, but invoked from workflows / Docker /
                    Procfile / shell / pyproject / Makefile
  manual-ops        never imported; referenced from docs / runbooks
  entrypoint        has a ``__main__`` guard or is a known entry file
  dead              zero importers, zero runtime refs, zero doc refs

Evidence is written to ``ci-reports/dead_modules.json`` so the maintainability
phases (plan §2) stay machine-verifiable instead of opinion-based.

Usage:
    python3 scripts/audit/find_dead_modules.py                 # summary
    python3 scripts/audit/find_dead_modules.py --json-only     # quiet
    python3 scripts/audit/find_dead_modules.py --min-lines 100 --top 40

Limitations (documented, conservative):
  * ``from pkg import name`` is resolved to ``pkg/name.py`` when that file
    exists; attribute-only usage (``pkg.name.attr`` after ``import pkg``)
    is not tracked — the plan's per-candidate ``rg`` verification step
    remains mandatory before archiving anything.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

EXCLUDED_DIRS = {
    ".git", ".github", ".venv", "venv", "env", "node_modules", "__pycache__",
    "build", "dist", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "backend/_archive", "frontend/node_modules", "htmlcov", "site-packages",
}

# Files that are entrypoints by convention (always alive).
ENTRY_FILE_NAMES = {"main.py", "wsgi.py", "asgi.py", "manage.py", "conftest.py"}
# Everything under these prefixes is operational-by-nature (never reported dead):
# migrations are discovery-loaded by alembic; tests are discovery-loaded by pytest.
ENTRY_PREFIXES = (
    "backend/migrations/",
    "backend/alembic_migrations/",
    "backend/tests/",
)

RUNTIME_REF_GLOBS = [
    ".github/**/*.yml", ".github/**/*.yaml", ".github/**/*.sh",
    "**/Dockerfile*", "**/Procfile*", "**/Makefile", "**/*.mk",
    "pyproject.toml", "**/pyproject.toml", "**/*.cfg", "**/*.ini",
    "**/render.yaml", "**/vercel.json", "**/*.service",
    "**/*.sh", "**/package.json", "**/docker-compose*.yml",
]

DOC_REF_GLOBS = ["docs/**/*.md", "*.md", "docs/**/*.rst"]

RUNTIME_SCAN_CAP_BYTES = 2_000_000  # ignore giant generated blobs


@dataclass
class ModuleInfo:
    path: Path                  # repo-relative POSIX path
    module: str                 # dotted module name ("backend.worker_service")
    lines: int
    has_main_guard: bool = False
    importers: list[str] = field(default_factory=list)     # repo-rel paths
    test_importers: list[str] = field(default_factory=list)
    runtime_refs: list[str] = field(default_factory=list)  # ref source files
    doc_refs: list[str] = field(default_factory=list)

    @property
    def is_entry(self) -> bool:
        name = self.path.name
        rel = self.path.as_posix()
        if rel.startswith(ENTRY_PREFIXES):
            return True
        return name in ENTRY_FILE_NAMES and self.path.parent in (
            REPO_ROOT, REPO_ROOT / "backend",
        )


def iter_python_files() -> list[Path]:
    excluded = {REPO_ROOT / d for d in EXCLUDED_DIRS}
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*.py"):
        if any(p == e or e in p.parents for e in excluded):
            continue
        files.append(p)
    return sorted(files)


def dotted_name(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT)
    parts = list(rel.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def packages_present(modules: dict[str, ModuleInfo]) -> set[str]:
    pkgs: set[str] = set()
    for mod in modules:
        parts = mod.split(".")
        for i in range(1, len(parts)):
            pkgs.add(".".join(parts[:i]))
    return pkgs


def resolve_relative(module_file: Path, level: int, base: str | None) -> str:
    """Resolve a relative import against the importing file's package.

    ``from .x import y`` inside ``pkg/mod.py`` must resolve against
    ``pkg`` — i.e. the importing FILE's own name is always stripped first
    (``__init__.py`` already IS the package, so it also drops one part).
    """
    rel = module_file.relative_to(REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if not parts:
        return ""
    if parts[-1] == "__init__":
        parts = parts[:-1]          # __init__ -> package
        extra_up = level - 1
    else:
        parts = parts[:-1]          # module -> containing package
        extra_up = level - 1
    for _ in range(max(extra_up, 0)):
        if parts:
            parts = parts[:-1]
    if base:
        parts += base.split(".")
    return ".".join(parts)


def collect_imports(
    path: Path,
) -> tuple[set[str], list[tuple[str, list[str]]], bool]:
    """Return (absolute_modules, [(resolved_base, names)], has_main_guard)."""
    try:
        tree = ast.parse(path.read_text(errors="replace"))
    except SyntaxError:
        return set(), [], False
    abs_mods: set[str] = set()
    froms: list[tuple[str, list[str]]] = []
    main_guard = False

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                abs_mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names if a.name != "*"]
            if node.level == 0:
                base = node.module or ""
                if base:
                    abs_mods.add(base)
                froms.append((base, names))
            else:
                pkg = resolve_relative(path, node.level, node.module)
                if pkg:
                    abs_mods.add(pkg)
                froms.append((pkg, names))
        elif isinstance(node, ast.Call):
            fn = node.func
            dynamic = None
            if isinstance(fn, ast.Attribute) and fn.attr == "import_module":
                dynamic = "import_module"
            elif isinstance(fn, ast.Name) and fn.id == "__import__":
                dynamic = "__import__"
            if dynamic and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    abs_mods.add(arg.value)
        elif isinstance(node, ast.If):
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
                and any(
                    isinstance(c, ast.Constant) and c.value == "__main__"
                    for c in test.comparators
                )
            ):
                main_guard = True
    return abs_mods, froms, main_guard


def build_graph() -> dict[str, ModuleInfo]:
    files = iter_python_files()
    modules: dict[str, ModuleInfo] = {}
    for f in files:
        rel_path = f.relative_to(REPO_ROOT)
        modules[dotted_name(f)] = ModuleInfo(
            path=rel_path,
            module=dotted_name(f),
            lines=len(f.read_text(errors="replace").splitlines()),
        )
    pkgs = packages_present(modules)

    # The backend app runs with cwd=backend/, so production code imports
    # BOTH as ``backend.core.x`` and as ``core.x`` (backend-dir-relative).
    # Resolve both conventions or live modules get misclassified as dead.
    backend_first_parts = {
        p.name for p in (REPO_ROOT / "backend").iterdir() if p.is_dir()
    }

    for f in files:
        abs_mods, froms, guard = collect_imports(f)
        if guard:
            modules[dotted_name(f)].has_main_guard = True
        importer = f.relative_to(REPO_ROOT).as_posix()
        is_test = importer.startswith("backend/tests/")
        targets: set[str] = set(abs_mods)
        for base, names in froms:
            for name in names:
                cand = f"{base}.{name}" if base else name
                targets.add(cand)
        # alias convention targets: ``core.x`` -> ``backend.core.x``
        expanded: set[str] = set()
        for cand in targets:
            expanded.add(cand)
            first = cand.split(".", 1)[0]
            if first in backend_first_parts:
                expanded.add(f"backend.{cand}")
        for target in expanded:
            # walk up: backend.pkg.mod.sym -> backend.pkg.mod -> backend.pkg
            parts = target.split(".")
            for i in range(len(parts), 0, -1):
                mod = ".".join(parts[:i])
                if mod in modules:
                    info = modules[mod]
                    if is_test:
                        info.test_importers.append(importer)
                    else:
                        info.importers.append(importer)
                    break
                if mod in pkgs:
                    break  # imported a live package; stop walking up
    return modules


SKIP_PATH_PARTS = (
    "/node_modules/", "/.git/", "/.pnpm/", "/.venv/", "/venv/",
    "/ci-reports/", "/dist/", "/build/", "/coverage/",
)
# Historical plan/audit docs list dead candidates by name — those mentions are
# self-referential and must not classify anything as "manual-ops alive".
SKIP_DOC_PREFIXES = ("docs/plan-network/", "docs/plans/", "docs/archive/")


def _scannable(p: Path, doc: bool) -> bool:
    if not p.is_file() or p.stat().st_size > RUNTIME_SCAN_CAP_BYTES:
        return False
    try:
        rel = p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return False
    if any(part in f"/{rel}/" for part in SKIP_PATH_PARTS):
        return False
    if doc and rel.startswith(SKIP_DOC_PREFIXES):
        return False
    return True


def _scan_text_files(globs: list[str], doc: bool = False) -> list[Path]:
    seen: set[Path] = set()
    for g in globs:
        for p in REPO_ROOT.glob(g):
            if _scannable(p, doc):
                seen.add(p)
    return sorted(seen)


def add_runtime_and_doc_refs(
    modules: dict[str, ModuleInfo],
) -> tuple[set[str], set[str]]:
    """Fill runtime_refs / doc_refs; return (runtime_hit, doc_hit) keys."""
    runtime_hits: set[str] = set()
    doc_hits: set[str] = set()

    candidates = [m for m in modules.values() if not m.importers]
    if not candidates:
        return runtime_hits, doc_hits

    stems = {m.path.stem: m for m in candidates}
    rels = {m.path.as_posix(): m for m in candidates}
    dots = {m.module: m for m in candidates}

    def register(info: ModuleInfo, src: Path, bucket: list[str]) -> None:
        entry = src.relative_to(REPO_ROOT).as_posix()
        if entry not in bucket:
            bucket.append(entry)

    for src in _scan_text_files(RUNTIME_REF_GLOBS):
        try:
            text = src.read_text(errors="replace")
        except OSError:
            continue
        for stem, info in stems.items():
            if stem in text:
                runtime_hits.add(stem)
                register(info, src, info.runtime_refs)
        for rel, info in rels.items():
            if rel in text:
                runtime_hits.add(rel)
                register(info, src, info.runtime_refs)
        for dot, info in dots.items():
            if dot in text:
                runtime_hits.add(dot)
                register(info, src, info.runtime_refs)

    for src in _scan_text_files(DOC_REF_GLOBS, doc=True):
        try:
            text = src.read_text(errors="replace")
        except OSError:
            continue
        for stem, info in stems.items():
            if stem in text:
                doc_hits.add(stem)
                register(info, src, info.doc_refs)
        for rel, info in rels.items():
            if rel in text:
                doc_hits.add(rel)
                register(info, src, info.doc_refs)
    return runtime_hits, doc_hits


def text_ref_pass(modules: dict[str, ModuleInfo]) -> set[str]:
    """One textual pass over backend/*.py for dead-candidate stems.

    Catches dynamic/string-based loading (``importlib.import_module(f"...")``,
    plugin registries, getattr-by-name) that the AST graph cannot see.
    Returns the set of candidate stems referenced anywhere in backend code
    outside the candidate file itself.
    """
    candidates = [
        m for m in modules.values()
        if m.path.as_posix().startswith("backend/")
        and not m.importers and not m.test_importers
        and not m.is_entry and not m.runtime_refs
    ]
    if not candidates:
        return set()
    stems = {m.path.stem: m.path.as_posix() for m in candidates}
    hits: set[str] = set()
    for f in iter_python_files():
        rel = f.relative_to(REPO_ROOT).as_posix()
        try:
            text = f.read_text(errors="replace")
        except OSError:
            continue
        for stem, owner in stems.items():
            if stem == Path(owner).stem and rel == owner:
                continue  # a file mentioning its own name is not evidence
            if stem in text:
                hits.add(stem)
    return hits


def classify(modules: dict[str, ModuleInfo]) -> dict[str, list[ModuleInfo]]:
    _, doc_hits = add_runtime_and_doc_refs(modules)
    text_hits = text_ref_pass(modules)
    out: dict[str, list[ModuleInfo]] = {
        "dead": [], "test_only": [], "runtime_invoked": [],
        "manual_ops": [], "main_guard": [], "entrypoint": [],
        "text_ref": [], "imported": [],
    }
    for info in modules.values():
        # The maintainability plan targets backend/; other trees still
        # participate in the import graph but are not classified here.
        if not info.path.as_posix().startswith("backend/"):
            continue
        if info.importers:
            out["imported"].append(info)
        elif info.is_entry:
            out["entrypoint"].append(info)
        elif info.runtime_refs:
            out["runtime_invoked"].append(info)
        elif info.test_importers:
            # only tests import it — cannot archive without updating tests
            out["test_only"].append(info)
        elif info.path.stem in doc_hits or info.path.as_posix() in doc_hits:
            out["manual_ops"].append(info)
        elif info.path.stem in text_hits:
            # referenced by name in code text — dynamic-load risk, keep
            out["text_ref"].append(info)
        elif info.has_main_guard:
            out["main_guard"].append(info)
        else:
            out["dead"].append(info)
    for bucket in out.values():
        bucket.sort(key=lambda m: (-m.lines, m.path))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--min-lines", type=int, default=1)
    ap.add_argument("--top", type=int, default=0,
                    help="show only top N dead files by lines")
    ap.add_argument("--json-only", action="store_true")
    ap.add_argument("--output", default="ci-reports/dead_modules.json")
    args = ap.parse_args()

    modules = build_graph()
    buckets = classify(modules)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": "scripts/audit/find_dead_modules.py",
        "scanned_modules": len(modules),
        "stats": {k: len(v) for k, v in buckets.items()},
        "dead_lines_total": sum(m.lines for m in buckets["dead"]),
        "dead": [
            {
                "path": m.path.as_posix(),
                "module": m.module,
                "lines": m.lines,
                "importers": m.importers,
                "test_importers": m.test_importers,
                "runtime_refs": m.runtime_refs,
                "doc_refs": m.doc_refs,
            }
            for m in buckets["dead"]
        ],
        "test_only": [
            {"path": m.path.as_posix(), "lines": m.lines,
             "test_importers": m.test_importers[:5]}
            for m in buckets["test_only"]
        ],
        "runtime_invoked": [
            {"path": m.path.as_posix(), "lines": m.lines,
             "refs": m.runtime_refs[:5]}
            for m in buckets["runtime_invoked"]
        ],
        "manual_ops": [
            {"path": m.path.as_posix(), "lines": m.lines,
             "doc_refs": m.doc_refs[:5]}
            for m in buckets["manual_ops"]
        ],
        "main_guard": [
            {"path": m.path.as_posix(), "lines": m.lines,
             "has_main_guard": True}
            for m in buckets["main_guard"]
        ],
        "text_ref": [
            {"path": m.path.as_posix(), "lines": m.lines}
            for m in buckets["text_ref"]
        ],
    }

    out_path = REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n")

    if not args.json_only:
        print(f"scanned modules: {len(modules)}")
        for k, v in report["stats"].items():
            print(f"  {k:16} {v}")
        dead = [d for d in report["dead"] if d["lines"] >= args.min_lines]
        if args.top:
            dead = dead[: args.top]
        print(f"\ndead files >= {args.min_lines} lines: {len(dead)}")
        for d in dead:
            print(f"  {d['lines']:6}  {d['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
