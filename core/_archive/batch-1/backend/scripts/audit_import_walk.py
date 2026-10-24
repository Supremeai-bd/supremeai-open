#!/usr/bin/env python3
"""Audit tool: import every module under a backend package in a fresh subprocess.

Usage (from backend/):
    TESTING=true ENV=test python scripts/audit_import_walk.py <package-name>

Writes one JSON line per module to stdout:
    {"module": "...", "status": "ok"|"FAIL", "error": "..."}
and a final {"_summary": {"package": ..., "total": ..., "failed": ...}} line.
Failure details (traceback tails) are dumped to /tmp/import_failures_<pkg>.json.

Rationale: one subprocess per TOP-LEVEL PACKAGE (~45 total) isolates global-state
corruption between packages while keeping runtime manageable.
"""

import importlib
import json
import os
import pathlib
import sys
import traceback

BACKEND = pathlib.Path(__file__).resolve().parent.parent  # backend/


def modules_for(pkg: str):
    root = BACKEND / pkg
    if root.is_file() or root.with_suffix(".py").is_file():
        yield pkg
        return
    for p in sorted(root.rglob("*.py")):
        if "__pycache__" in p.parts or ".venv" in p.parts:
            continue
        rel = p.relative_to(BACKEND).with_suffix("")
        parts = list(rel.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if not parts:
            continue
        yield ".".join(parts)


def main() -> int:
    pkg = sys.argv[1]
    os.chdir(BACKEND)
    sys.path.insert(0, str(BACKEND))
    failures = []
    count = 0
    for mod in modules_for(pkg):
        count += 1
        try:
            importlib.import_module(mod)
            status = "ok"
            err = ""
        except BaseException as exc:  # noqa: BLE001 - audit must catch everything
            status = "FAIL"
            err = f"{type(exc).__name__}: {exc}"
            tb = traceback.format_exc(limit=6)
            failures.append({"module": mod, "error": err, "tb": tb.splitlines()[-6:]})
        print(json.dumps({"module": mod, "status": status, "error": err}), flush=True)
    print(
        json.dumps({"_summary": {"package": pkg, "total": count, "failed": len(failures)}}),
        flush=True,
    )
    if failures:
        pathlib.Path(f"/tmp/import_failures_{pkg.replace('.', '_')}.json").write_text(
            json.dumps(failures, indent=1)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
