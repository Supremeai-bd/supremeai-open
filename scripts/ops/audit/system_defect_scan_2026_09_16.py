#!/usr/bin/env python3
"""SupremeAI defect scanner (read-only, evidence generator) — 2026-09-16.

Complements ``scripts/audit/system_deep_scan_2026_09_15.py`` (route/contract
census) by scanning for *code-level* defects:

  * Python syntax errors (``ast.parse``) — deterministic, no bytecode writes
  * Silent failure handlers (``except: pass`` / ``except Exception: pass``)
  * Bare ``except:`` clauses
  * ``NotImplementedError`` / TODO-FIXME-HACK-XXX markers
  * Hardcoded secret *candidates* (regex, values masked in output)
  * TypeScript escape hatches (``@ts-ignore``, ``@ts-expect-error``, ``as any``)

Outputs (default ``docs/audits/evidence/<today>/``):
  defect_scan_summary.txt   human-readable digest
  defect_scan_report.json   machine-readable findings

Usage:
  python scripts/audit/system_defect_scan_2026_09_16.py
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SKIP_DIR_PARTS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".ruff_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".kilo",
    "htmlcov",
}
SKIP_FILE_SUFFIXES = (".min.js", ".map")
TEST_HINT = re.compile(
    r"(^|[\\/])(tests?|__tests__|e2e)[\\/]|(^|[\\/])test_[^\\/]*\.py$"
    r"|_test\.py$|\.test\.(ts|tsx)$|\.spec\.(ts|tsx)$|conftest\.py$",
    re.I,
)

SECRET_RX = re.compile(
    r"(?i)\b(api[_-]?key|secret|access[_-]?token|auth[_-]?token|password|passwd|"
    r"private[_-]?key)\b\s*[:=]\s*[\"']([^\"'\s{}()$]{16,})[\"']"
)
SECRET_ALLOW = re.compile(
    r"(?i)^(os\.getenv|process\.env|settings\.|config\.|env\.|placeholder|example|"
    r"dummy|fake|test|your[_-]?|xxx|change[_-]?me|<|\$\{|\$\()"
)
TODO_RX = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")
TS_ESCAPE_RX = re.compile(r"@ts-(ignore|expect-error)|:\s*any\b|as\s+any\b")


def find_root() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        if os.path.isdir(os.path.join(here, ".git")):
            return here
        parent = os.path.dirname(here)
        if parent == here:
            break
        here = parent
    return os.getcwd()


ROOT = find_root()
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
OUT = os.environ.get(
    "DEFECT_OUT", os.path.join(ROOT, "docs", "audits", "evidence", TODAY)
)
os.makedirs(OUT, exist_ok=True)


def tracked_files() -> list[str]:
    try:
        res = subprocess.run(
            ["git", "-C", ROOT, "ls-files"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        files = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
        if files:
            return files
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        print(f"[warn] git ls-files unavailable ({exc})", flush=True)
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_PARTS]
        for name in filenames:
            out.append(os.path.relpath(os.path.join(dirpath, name), ROOT))
    return out


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def is_skipped(rel: str) -> bool:
    if set(re.split(r"[\\/]", rel)) & SKIP_DIR_PARTS:
        return True
    return rel.endswith(SKIP_FILE_SUFFIXES)


def mask(text: str) -> str:
    return (text[:4] + "***") if len(text) > 4 else "***"


def scan_python(rel: str, findings: dict) -> None:
    src = read(os.path.join(ROOT, rel))
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        findings["syntax_errors"].append(
            {"file": rel, "line": exc.lineno, "msg": f"{type(exc).__name__}: {exc.msg}"}
        )
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            body = node.body
            handler_type = "bare" if node.type is None else ast.unparse(node.type)
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                findings["silent_failure"].append(
                    {
                        "file": rel,
                        "line": node.lineno,
                        "kind": "pass_only",
                        "handler": handler_type,
                    }
                )
            elif handler_type == "bare":
                findings["bare_except"].append({"file": rel, "line": node.lineno})
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Raise)
                    and isinstance(sub.exc, ast.Call)
                    and getattr(sub.exc.func, "id", "") == "NotImplementedError"
                ):
                    findings["not_implemented"].append(
                        {"file": rel, "line": sub.lineno, "symbol": node.name}
                    )
                    break
    for i, line in enumerate(src.splitlines(), 1):
        if TODO_RX.search(line):
            findings["todo_markers"].append(
                {"file": rel, "line": i, "text": line.strip()[:160]}
            )
        if not TEST_HINT.search(rel):
            m = SECRET_RX.search(line)
            if m and "os.environ" not in line and not SECRET_ALLOW.search(m.group(2)):
                findings["hardcoded_secret_candidates"].append(
                    {
                        "file": rel,
                        "line": i,
                        "kind": m.group(1),
                        "sample": mask(m.group(2)),
                    }
                )


def scan_ts(rel: str, findings: dict) -> None:
    if TEST_HINT.search(rel):
        return
    src = read(os.path.join(ROOT, rel))
    for i, line in enumerate(src.splitlines(), 1):
        if TS_ESCAPE_RX.search(line):
            findings["ts_escape_hatches"].append(
                {"file": rel, "line": i, "text": line.strip()[:160]}
            )


def main() -> int:
    files = [p.replace("/", os.sep) for p in tracked_files()]
    py_files = [p for p in files if p.endswith(".py") and not is_skipped(p)]
    ts_files = [p for p in files if p.endswith((".ts", ".tsx")) and not is_skipped(p)]

    findings: dict[str, list] = {
        "syntax_errors": [],
        "silent_failure": [],
        "bare_except": [],
        "not_implemented": [],
        "todo_markers": [],
        "hardcoded_secret_candidates": [],
        "ts_escape_hatches": [],
    }

    for rel in py_files:
        scan_python(rel, findings)
    for rel in ts_files:
        scan_ts(rel, findings)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": ROOT,
        "python_files_scanned": len(py_files),
        "ts_files_scanned": len(ts_files),
        "counts": {k: len(v) for k, v in findings.items()},
        "findings": findings,
    }

    with open(
        os.path.join(OUT, "defect_scan_report.json"), "w", encoding="utf-8"
    ) as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    lines: list[str] = [
        f"# SupremeAI defect scan — {TODAY}",
        f"# python files: {len(py_files)}  |  ts/tsx files: {len(ts_files)}",
        "",
    ]
    for key in (
        "syntax_errors",
        "silent_failure",
        "bare_except",
        "not_implemented",
        "hardcoded_secret_candidates",
    ):
        rows = findings[key]
        lines.append(f"== {key} ({len(rows)})")
        for row in rows[:400]:
            lines.append("   " + json.dumps(row, ensure_ascii=False))
        if len(rows) > 400:
            lines.append(f"   ... {len(rows) - 400} more (see JSON)")
        lines.append("")

    todo_by_file: dict[str, int] = {}
    for row in findings["todo_markers"]:
        todo_by_file[row["file"]] = todo_by_file.get(row["file"], 0) + 1
    lines.append(
        f"== todo_markers ({len(findings['todo_markers'])} hits, top 60 files)"
    )
    for rel, count in sorted(todo_by_file.items(), key=lambda kv: -kv[1])[:60]:
        lines.append(f"   {count:4}  {rel}")
    lines.append("")

    ts_by_file: dict[str, int] = {}
    for row in findings["ts_escape_hatches"]:
        ts_by_file[row["file"]] = ts_by_file.get(row["file"], 0) + 1
    lines.append(
        f"== ts_escape_hatches ({len(findings['ts_escape_hatches'])} hits,"
        " top 40 files)"
    )
    for rel, count in sorted(ts_by_file.items(), key=lambda kv: -kv[1])[:40]:
        lines.append(f"   {count:4}  {rel}")

    with open(
        os.path.join(OUT, "defect_scan_summary.txt"), "w", encoding="utf-8"
    ) as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"[done] evidence -> {os.path.relpath(OUT, ROOT)}")
    for key, rows in report["counts"].items():
        print(f"  {key:32} {rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

