#!/usr/bin/env python3
"""architecture_check.py — M11 Phase-1: স্থাপত্য-সচেতনতা রিপোর্ট + baseline-N র্যাচেট।

বাংলা: এক স্ক্রিপ্টে তিনটি সত্য —

1. **স্ট্যাটিক import-গ্রাফ** — backend/-এর সব .py AST-parse করে অভ্যন্তরীণ
   এজ-তালিকা (ecosystem-first: ``scripts/advanced_analysis/circular_import_mapper``
   -এর প্রমাণিত AST/Tarjan ইঞ্জিন পুনর্ব্যবহৃত — নতুন ডিপেন্ডেন্সি নেই);
2. **চক্র** — Tarjan SCC (>1) — ডেটা হিসেবে পরিমাপিত, নীরবভাবে লুকানো নয়
   (আগে ``generate_domain_dependency_graph.py`` তে "cycles": [] হার্ডকোড ছিল);
3. **boundary লঙ্ঘন** — ``architecture-rules.yml`` (ডেটা-ফাইল) থেকে লোড।

**baseline-N র্যাচেট** (``scripts/architecture_baseline.json``): লঙ্ঘন-গণনা
(cycles + boundary) ≤ baseline হলে PASS, > baseline হলে exit 2 — নিচে-যাওয়া
র্যাচেট (check_gateway_bypass.py-র স্বীকৃত আকৃতি)। দুই-রান ডেল্টা = 0
(প্রতিটি আউটপুট sorted) — Gate-4 পুনরুৎপাদনযোগ্যতা চুক্তি।

CI স্পর্শ নেই (Phase-1 চুক্তি: visibility-only, founder-gated workflow পরে)।
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.advanced_analysis.circular_import_mapper import (  # noqa: E402
    _build_import_graph,
    _discover_py_files,
    _extract_imports,
    _file_to_module,
    _tarjan_scc,
)
from scripts.ci.circle_architecture_gate import violations as boundary_violations  # noqa: E402

BASELINE_PATH = ROOT / "scripts" / "architecture_baseline.json"
OUTPUT_PATH = ROOT / "docs" / "generated" / "backend_import_graph.json"
SCHEMA_VERSION = 1


def build_report() -> dict:
    """Deterministic architecture report (two-run delta = 0 চুক্তি)।"""
    started = time.time()

    py_files = sorted(_discover_py_files(), key=str)
    module_to_file = {_file_to_module(fp): fp for fp in py_files}
    module_to_file.pop("", None)
    all_modules = set(module_to_file)
    graph = _build_import_graph(list(py_files), module_to_file, all_modules)
    sccs = _tarjan_scc(graph, all_modules)

    edges: list[dict[str, str]] = []
    for src in sorted(graph):
        for tgt, _raw, _sev in graph[src]:
            edges.append({"from": src, "to": tgt})
    edges.sort(key=lambda e: (e["from"], e["to"]))

    cycles = sorted(sorted(scc) for scc in sccs)
    boundary = sorted(boundary_violations(ROOT))

    report = {
        "schema_version": SCHEMA_VERSION,
        "module_count": len(all_modules),
        "edge_count": len(edges),
        "modules": sorted(all_modules),
        "edges": edges,
        "cycles": cycles,
        "boundary_violations": boundary,
        "violation_count": len(cycles) + len(boundary),
    }
    return report


def load_baseline() -> int:
    if not BASELINE_PATH.exists():
        raise RuntimeError(
            f"{BASELINE_PATH} not found — architecture baseline is load-bearing data "
            "(fail-closed); run with --record to establish it from the current tree"
        )
    data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    baseline = data.get("baseline_violations")
    if not isinstance(baseline, int) or baseline < 0:
        raise RuntimeError("architecture_baseline.json: 'baseline_violations' must be a non-negative int")
    return baseline


def main() -> int:
    record = "--record" in sys.argv
    started = time.time()
    report = build_report()

    if record:
        BASELINE_PATH.write_text(
            json.dumps(
                {
                    "baseline_violations": report["violation_count"],
                    "scope": "cycles + boundary (architecture-rules.yml)",
                    "schema_version": SCHEMA_VERSION,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"architecture baseline recorded: {report['violation_count']} "
            f"(cycles={len(report['cycles'])}, boundary={len(report['boundary_violations'])})"
        )

    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    baseline = load_baseline()
    count = report["violation_count"]
    elapsed = round(time.time() - started, 3)
    print(
        f"architecture check: violations={count} baseline={baseline} "
        f"(cycles={len(report['cycles'])}, boundary={len(report['boundary_violations'])}, "
        f"modules={report['module_count']}, edges={report['edge_count']}, "
        f"measured={elapsed}s)"
    )
    if count > baseline:
        print(
            f"::error::architecture ratchet FAILED: {count} > baseline {baseline} — "
            "নতুন চক্র/বাউন্ডারি-লঙ্ঘন নিষিদ্ধ (baseline নামাতে হলে প্রমাণসহ করুন)"
        )
        return 2
    print("architecture ratchet passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
