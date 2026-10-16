#!/usr/bin/env python3
"""transit_prune_cli.py — thin I/O wrapper over the transit_prune pure core.

This is the executable entry point the landing.yml auto-prune job calls. It
owns ALL I/O (directory listing, evidence JSON read, plan JSON write) and the
pure core owns ALL decisions (fail-closed verified-dispatch contract).

Exit codes:
  0 — plan computed and written (dry-run reporting included).
  2 — internal/usage error (fail-loud; the workflow step must surface it).

Dry-run is the DEFAULT posture of the workflow (env PRUNE_DRY_RUN); the CLI
itself never deletes anything — execution (git rm + commit) stays in the
workflow step, driven by the plan JSON this tool emits.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import transit_prune  # noqa: E402  (colocated pure core)


def _load_evidence(path: Optional[str]) -> dict:
    if not path:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _list_patches(patches_dir: str) -> list:
    if not os.path.isdir(patches_dir):
        return []
    out = []
    for name in sorted(os.listdir(patches_dir)):
        if name.endswith(".patch"):
            out.append(os.path.join(patches_dir, name))
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Ephemeral transit auto-prune selector (#416)")
    parser.add_argument("--patches-dir", default="patches", help="transit inbox directory")
    parser.add_argument("--evidence", default=None,
                        help="dispatch-evidence JSON path (task_id -> evidence); "
                             "absent file = empty evidence (everything held, fail-closed)")
    parser.add_argument("--out", default="prune-plan.json", help="plan JSON output path")
    args = parser.parse_args(argv)

    try:
        patches = _list_patches(args.patches_dir)
        evidence = _load_evidence(args.evidence)
        result = transit_prune.select_prunable_patches(patches, evidence)
    except Exception as exc:  # fail-loud wrapper
        print(f"transit_prune_cli internal error: {exc}", file=sys.stderr)
        return 2

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, sort_keys=True)

    print(f"transit inbox: {len(patches)} patch(es) scanned")
    for h in result["held"]:
        task = h.get("task_id") or "-"
        print(f"  HOLD {h['patch']} ({task}): {'; '.join(h['reasons'])}")
    for p in result["prunable"]:
        print(f"  PRUNE {p['patch']} -> {p['commit_message']}")
    print(f"plan written: {args.out} (prunable={len(result['prunable'])}, held={len(result['held'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
