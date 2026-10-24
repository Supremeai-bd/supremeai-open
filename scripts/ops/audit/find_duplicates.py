#!/usr/bin/env python3
"""Find duplicate file groups under backend/ — canonical evidence tool.

Plan reference: docs/plan-network/MAINTAINABILITY_PLAN.md §3 + §13.

A same-basename file group is NOT automatically a duplicate. This auditor
separates real duplicates from mere name collisions and emits machine-readable
evidence (ci-reports/duplicate_files.json) so consolidation batches stay
evidence-driven, never guesswork.

Group classification (per group of >=2 live copies sharing a basename):
- ``shim``     : at least one copy is a deprecated re-export/bridge whose
                 delegation target is another copy in the group. Actionable:
                 redirect importers to the canonical copy, archive the shim.
- ``identical``: at least one pair of copies is byte-equal. Actionable: keep
                 one, redirect importers, archive the rest.
- ``twin``     : best pairwise similarity >= TWIN_THRESHOLD without being
                 identical or a shim pair. Actionable after manual diff review.
- ``distinct`` : same basename, different purpose (name collision only).
                 Reported for completeness — NOT actionable.

Usage:
    python3 scripts/audit/find_duplicates.py            # summary + JSON
    python3 scripts/audit/find_duplicates.py --json out.json
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "backend"
EXCLUDED_DIRS = {"__pycache__", "_archive", ".venv", "node_modules"}
TWIN_THRESHOLD = 0.85

# Docstring/comment markers that identify a deprecated re-export shim/bridge.
SHIM_MARKERS = (
    "compatibility bridge",
    "delegates to canonical",
    "deprecated:",
    "backward-compatibility while eliminating code duplication",
)

_IMPORT_RE = re.compile(
    r"^[ \t]*(?:from|import)[ \t]+([\w.]+)", re.MULTILINE
)


def iter_py_files() -> list[Path]:
    files: list[Path] = []
    for path in BACKEND.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(BACKEND).parts):
            continue
        files.append(path)
    return files


def module_variants(path: Path) -> list[str]:
    """Textual variants that may reference this module (dual import convention).

    Backend runs with cwd=backend/, so production code imports both
    ``backend.pkg.mod`` and ``pkg.mod``.
    """
    rel = path.relative_to(BACKEND).with_suffix("")
    parts = rel.parts
    dotted = ".".join(parts)
    return [f"backend.{dotted}", dotted]


def file_lines(path: Path) -> int:
    try:
        return path.read_text(encoding="utf-8", errors="replace").count("\n") + 1
    except OSError:
        return -1


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def similarity(a: Path, b: Path) -> float:
    ta = a.read_text(encoding="utf-8", errors="replace")
    tb = b.read_text(encoding="utf-8", errors="replace")
    return difflib.SequenceMatcher(None, ta, tb).quick_ratio()


def shim_target(text: str) -> str | None:
    """Extract the delegation target of a shim module, if any."""
    head = text[:800]
    m = re.search(r'_DEPRECATED_TARGET\s*=\s*["\']([\w.]+)["\']', text)
    if m:
        return m.group(1)
    # Compatibility-bridge style: docstring marker + a from-import of the target
    low = head.lower()
    if any(marker in low for marker in SHIM_MARKERS):
        for m in _IMPORT_RE.finditer(text[:2000]):
            mod = m.group(1)
            if mod.count(".") >= 1 and not mod.startswith(("__future__", "core.logging_config")):
                return mod
    return None


def is_shim(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if "__getattr__" in text and "importlib.import_module" in text:
        return True
    return any(marker in text[:600].lower() for marker in SHIM_MARKERS)


def build_import_index(files: list[Path]) -> list[tuple[Path, str]]:
    indexed = []
    for f in files:
        try:
            indexed.append((f, f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    return indexed


def count_importers(target: Path, index: list[tuple[Path, str]]) -> int:
    """Files that import target (any convention). Textual evidence only."""
    variants = module_variants(target)
    stem = target.stem
    n = 0
    for f, text in index:
        if f == target:
            continue
        for v in variants:
            if f"import {v}" in text or f"from {v} import" in text:
                n += 1
                break
        else:
            # intra-package relative import: from .<stem> import / from .<stem> as
            if f.parent == target.parent and re.search(
                rf"^from[ \t]+\.?{stem}[ \t]+import", text, re.MULTILINE
            ):
                n += 1
    return n


def classify_group(name: str, copies: list[Path], index) -> dict:
    hashes = {c: sha(c) for c in copies}
    lines = {c: file_lines(c) for c in copies}
    shims = [c for c in copies if is_shim(c)]
    entry: dict = {
        "group": name,
        "copies": [
            {"path": str(c.relative_to(REPO_ROOT)), "lines": lines[c], "sha": hashes[c]}
            for c in copies
        ],
    }

    # shim pair: shim's delegation target resolves to another copy in-group
    for s in shims:
        text = s.read_text(encoding="utf-8", errors="replace")
        target = shim_target(text)
        if not target:
            continue
        for other in copies:
            if other == s:
                continue
            other_variants = module_variants(other)
            # Exact delegation-target match only. A shim whose target lives
            # OUTSIDE this group (different basename) is NOT a duplicate pair —
            # it is a Phase-3 shim candidate; the group stays `distinct`.
            if target in other_variants:
                entry.update(
                    classification="shim",
                    canonical=str(other.relative_to(REPO_ROOT)),
                    stale=str(s.relative_to(REPO_ROOT)),
                    stale_importers=count_importers(s, index),
                )
                return entry

    # identical pair
    seen: dict[str, Path] = {}
    for c in copies:
        if hashes[c] in seen:
            entry.update(
                classification="identical",
                keep=str(seen[hashes[c]].relative_to(REPO_ROOT)),
                duplicate=str(c.relative_to(REPO_ROOT)),
            )
            return entry
        seen[hashes[c]] = c

    # twin pair (best pairwise quick_ratio; quick_ratio is an upper bound —
    # candidates near the threshold are re-checked with real_ratio)
    best, best_pair = 0.0, None
    for i in range(len(copies)):
        for j in range(i + 1, len(copies)):
            q = similarity(copies[i], copies[j])
            if q >= TWIN_THRESHOLD and q > best:
                best, best_pair = q, (copies[i], copies[j])
    if best_pair:
        entry.update(
            classification="twin",
            similarity=round(best, 3),
            copies_pair=[str(p.relative_to(REPO_ROOT)) for p in best_pair],
        )
        return entry

    entry["classification"] = "distinct"
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default=str(REPO_ROOT / "ci-reports" / "duplicate_files.json"))
    args = ap.parse_args()

    files = iter_py_files()
    index = build_import_index(files)

    groups: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        groups[f.name].append(f)

    results = []
    for name, copies in sorted(groups.items()):
        if len(copies) < 2:
            continue
        results.append(classify_group(name, list(copies), index))

    # __init__.py floods the report with meaningless package-init collisions;
    # keep them under distinct (reported, not actionable) but count separately.
    stats = defaultdict(int)
    for r in results:
        stats[r["classification"]] += 1

    actionable = [r for r in results if r["classification"] in ("shim", "identical", "twin")]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tool": "scripts/audit/find_duplicates.py",
        "twin_threshold": TWIN_THRESHOLD,
        "scanned_files": len(files),
        "stats": dict(stats),
        "actionable": actionable,
        "distinct": [
            {"group": r["group"], "copies": r["copies"]}
            for r in results
            if r["classification"] == "distinct"
        ],
    }

    out = Path(args.json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"scanned files: {len(files)}")
    print(f"same-basename groups >= 2 copies: {len(results)}")
    for k in ("shim", "identical", "twin", "distinct"):
        print(f"  {k:10s} {stats[k]}")
    print(f"actionable groups: {len(actionable)}")
    for r in actionable:
        if r["classification"] == "shim":
            print(
                f"  [shim] {r['stale']} -> {r['canonical']} "
                f"(importers: {r['stale_importers']})"
            )
        elif r["classification"] == "identical":
            print(f"  [identical] keep {r['keep']}, duplicate {r['duplicate']}")
        else:
            print(f"  [twin {r['similarity']}] {r['copies_pair']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
