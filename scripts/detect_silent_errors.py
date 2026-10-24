#!/usr/bin/env python3
"""SupremeAI Silent Error Detector (সাইলেন্ট এরর ডিটেক্টর) — static + runtime audit.

A zero-dependency (Python stdlib only) scanner that finds every category of
"silent error" in the SupremeAI codebase and reports each finding with a
severity. It is built for both local use and CI automation — see
`.github/workflows/silent-error-scan.yml`.

Why this exists
---------------
Silent errors are the most expensive bugs to find: the code path keeps running,
but failures are swallowed (`except Exception: pass`), or the error is dumped
into a default value that looks legitimate, or an `asyncio.create_task()` is
fired and forgotten so a whole background feature dies with zero trace.
This scanner makes them visible and gives CI a regression gate so the count
can only go down.

Detected Python patterns (AST-based):
  except-pass             bare/broad `except` whose body is only `pass`
  except-continue         bare/broad `except: continue` — silent loop skip
  except-break            `except: break` — silent loop exit
  except-return-default   `except` returning None/False/""/0/[]/{}/True with no log
  except-no-log           broad exception handled but never logged / re-raised
  bare-except             bare `except:` (also swallows KeyboardInterrupt/SystemExit)
  suppress-exception      contextlib.suppress(Exception)
  create-task-unref       asyncio.create_task(...) with the task reference discarded
  syntax-error            file that cannot be parsed (definitely broken)

Detected JS/TS patterns (regex + brace matching):
  empty-catch             catch { } with an empty body
  catch-return-silent     catch returning null/undefined/false/[]/{}/'' or continue/break
  promise-catch-silent    .catch(() => {}) — rejection discarded
  json-parse-unguarded    JSON.parse outside any try/catch
  floating-fetch          fetch(...) fired and forgotten (no await/return)
  onerror-empty           onerror = () => {}

Runtime log scan (--logs):
  python tracebacks, "Exception ignored in", "Silenced error",
  unhandled promise rejections, "Task was destroyed but it is pending!",
  coroutine never awaited, ERROR/CRITICAL bursts.

Usage
-----
    python scripts/detect_silent_errors.py                       # scan repo, human output
    python scripts/detect_silent_errors.py --json report.json --markdown report.md
    python scripts/detect_silent_errors.py --fail-on high        # CI gate (default)
    python scripts/detect_silent_errors.py --baseline scripts/silent_errors_baseline.json
    python scripts/detect_silent_errors.py --update-baseline     # refresh snapshot
    python scripts/detect_silent_errors.py --logs auto           # also scan *.{log} files
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent  # project root (parent of scripts/)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - not all consoles support reconfigure
    _ = None

SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "info": 0}

DEFAULT_EXCLUDE_DIRS = {
    "node_modules", ".venv", ".venv_ci", ".venv_probe", "venv", "site-packages",
    "dist", "dist-admin", "dist-user", "dist-electron", "__pycache__", ".git",
    "htmlcov", "coverage", "coverage-tmp", ".turbo", ".next", "out",
    ".pytest_cache", ".ruff_cache", ".mypy_cache", "playwright-report",
    "test-results", "_archive", ".secrets", ".firebase",
    ".playwright-mcp", ".agents", ".continue", ".kilo", ".lingma", ".vscode",
    ".devcontainer", ".github", "snapshots", "__snapshots__", "storybook-static",
    "build", "e2e-artifacts", "generated", ".terraform", "node_modules_cache",
    ".cache",
}

DEFAULT_SCAN_DIRS = [
    "backend", "frontend/src", "apps", "packages", "shared", "tools",
    "config", "configs", "scripts", "migrations",
]

MAX_FILE_BYTES = 600_000

LOG_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("python-traceback", re.compile(r"Traceback \(most recent call last\)")),
    ("exception-ignored", re.compile(r"Exception ignored[^\n]*")),
    ("silenced-error-log", re.compile(r"Silenced error[^\n]*", re.IGNORECASE)),
    ("unhandled-rejection", re.compile(r"Unhandled(?:PromiseRejection| Rejection| Error)[^\n]*", re.IGNORECASE)),
    ("task-destroyed-pending", re.compile(r"Task was destroyed but it is pending")),
    ("coroutine-never-awaited", re.compile(r"was never awaited|never fetched from this coroutine")),
    ("error-burst", re.compile(r"\b(ERROR|CRITICAL|FATAL)\b[^\n\u2588]*")),
]


def rel(path: str | Path) -> str:
    """Return a repo-relative, forward-slash path (stable across OS/CI)."""
    return os.path.relpath(str(path), str(ROOT)).replace("\\", "/")


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def iter_files(root_dir: str, exts: tuple[str, ...], exclude: set[str]):
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, root_dir)):
        dirnames[:] = [d for d in dirnames if d not in exclude]
        for fn in filenames:
            path = os.path.join(dirpath, fn)
            if os.path.splitext(fn)[1].lower() in exts and os.path.getsize(path) <= MAX_FILE_BYTES:
                yield path


def is_test_file(path: str) -> bool:
    """Heuristic: path lives under tests dirs or is a *_test / test_* / *.spec file."""
    p = rel(path)
    parts = p.split("/")
    if any(seg in ("tests", "__tests__", "test", "testing") for seg in parts):
        return True
    name = parts[-1].lower()
    return name.startswith("test_") or name.endswith("_test") or name.endswith("_test.py") or ".spec." in name or ".test." in name
# ---------------------------------------------------------------------------
# Python AST analysis
# ---------------------------------------------------------------------------

LOG_CALL_NAMES = {
    "debug", "info", "warning", "warn", "error", "exception", "critical", "log",
    "print", "trace", "traceback", "record", "capture", "report", "log_error",
    "log_exception", "add_note", "set_failed", "update_status", "save_state",
    "mark_failed", "emit", "notify", "raise_for_status", "publish",
}


def exc_type_repr(node: ast.ExceptHandler) -> tuple[str, bool, bool]:
    """Return (display, broad, feature_gate) for an except handler's type."""
    t = node.type
    if t is None:
        return "bare", True, False
    names: list[str] = []
    broad = False
    feature_gate = False
    targets = t.elts if isinstance(t, ast.Tuple) else [t]
    for elt in targets:
        if isinstance(elt, ast.Name):
            names.append(elt.id)
            if elt.id in ("Exception", "BaseException"):
                broad = True
            if elt.id in ("ImportError", "ModuleNotFoundError"):
                feature_gate = True
        elif isinstance(elt, ast.Attribute):
            seg = []
            n = elt
            while isinstance(n, ast.Attribute):
                seg.append(n.attr)
                n = n.value
            if isinstance(n, ast.Name):
                seg.append(n.id)
            names.append(".".join(reversed(seg)))
        else:
            names.append(ast.unparse(elt) if hasattr(ast, "unparse") else "?")
    text = ", ".join(names) or "bare"
    return text, broad, feature_gate


def returns_silent_value(node: ast.ExceptHandler) -> tuple[bool, str]:
    """Detect `except: return <default>` where the default masks the failure."""
    for n in ast.walk(node):
        if isinstance(n, ast.Return):
            v = n.value
            if v is None:
                return True, "None"
            if isinstance(v, ast.Constant):
                if v.value is True:
                    return True, "True"
                if v.value in (False, None, "", 0, 0.0, b"", [], {}):
                    return True, repr(v.value)
            if isinstance(v, (ast.List, ast.Dict, ast.Tuple, ast.Set)):
                try:
                    if not ast.literal_eval(v):
                        return True, "empty-collection"
                except Exception:
                    return False, ""
    return False, ""


def has_log_or_surface(node: ast.ExceptHandler) -> bool:
    """Does the handler body log, re-raise, or otherwise surface the error?"""
    for n in ast.walk(node):
        if isinstance(n, ast.Raise):
            return True
        if isinstance(n, ast.Call):
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
            if name in LOG_CALL_NAMES:
                return True
    return False
def scan_python_file(path: str, include_tests: bool) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    is_test = is_test_file(path)
    if is_test and not include_tests:
        return findings

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        tree = ast.parse(src)
    except SyntaxError as e:
        findings.append({
            "file": rel(path), "line": getattr(e, "lineno", 1), "type": "syntax-error",
            "severity": "high", "code": f"SyntaxError: {e}",
            "function": "", "test": is_test, "feature_gate": False,
        })
        return findings
    except Exception as e:
        findings.append({
            "file": rel(path), "line": 1, "type": "unreadable",
            "severity": "info", "code": f"{type(e).__name__}: {e}",
            "function": "", "test": is_test, "feature_gate": False,
        })
        return findings

    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child._parent = parent  # type: ignore[attr-defined]

    lines = src.splitlines()

    def _snippet(node: ast.AST, limit: int = 200) -> str:
        start = node.lineno - 1  # type: ignore[attr-defined]
        end = getattr(node, "end_lineno", node.lineno)  # type: ignore[attr-defined]
        return "\n".join(l.strip()[:140] for l in lines[start:end])[:limit]

    def _function_of(node: ast.AST) -> str:
        n = node
        while n is not None:
            p = getattr(n, "_parent", None)
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return p.name
            n = p
        return ""

    def _emit(feat: dict[str, Any], type_: str, severity: str) -> None:
        eff = "low" if (is_test and not include_tests) else severity
        f = dict(feat)
        f["type"] = type_
        f["severity"] = eff
        findings.append(f)

    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler):
            continue
        type_text, is_broad, is_gate = exc_type_repr(node)
        body = node.body
        body_pass = len(body) == 1 and isinstance(body[0], ast.Pass)
        body_cont = len(body) == 1 and isinstance(body[0], ast.Continue)
        body_break = len(body) == 1 and isinstance(body[0], ast.Break)
        has_log = has_log_or_surface(node)
        silent_ret, ret_val = returns_silent_value(node)

        feat: dict[str, Any] = {
            "file": rel(path), "line": node.lineno, "type": "",
            "severity": "low", "code": _snippet(node),
            "function": _function_of(node), "test": is_test,
            "feature_gate": is_gate, "exception": type_text,
        }

        if body_pass:
            _emit(feat, "except-pass", "high" if (type_text == "bare" or is_broad) else "medium")
        elif body_cont:
            _emit(feat, "except-continue", "high" if type_text == "bare" else "medium")
        elif body_break:
            _emit(feat, "except-break", "low")
        elif not has_log and silent_ret:
            _emit(feat, "except-return-true" if ret_val == "True" else "except-return-default", "medium")
        elif not has_log and not is_gate:
            _emit(feat, "except-no-log", "low")
        elif type_text == "bare" and has_log:
            _emit(feat, "bare-except", "medium")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn_ = node.func
        fname = fn_.attr if isinstance(fn_, ast.Attribute) else (fn_.id if isinstance(fn_, ast.Name) else "")
        if fname == "create_task":
            parent = getattr(node, "_parent", None)
            if not isinstance(parent, (ast.Assign, ast.AnnAssign, ast.Await)):
                findings.append({
                    "file": rel(path), "line": node.lineno, "type": "create-task-unref",
                    "severity": "medium" if not is_test else "low",
                    "code": _snippet(node), "function": _function_of(node),
                    "test": is_test, "feature_gate": False, "exception": "",
                })
        elif fname == "suppress":
            is_suppress_exc = any(
                isinstance(a, ast.Name) and a.id in ("Exception", "BaseException")
                for a in node.args
            )
            if is_suppress_exc:
                findings.append({
                    "file": rel(path), "line": node.lineno, "type": "suppress-exception",
                    "severity": "medium" if not is_test else "low",
                    "code": _snippet(node), "function": _function_of(node),
                    "test": is_test, "feature_gate": False, "exception": "",
                })
    return findings
# ---------------------------------------------------------------------------
# JS / TS analysis (regex + brace matching — stdlib only)
# ---------------------------------------------------------------------------

SILENT_RETURN_RE = re.compile(
    r"^\s*(?:return\s+(?:null|undefined|false|void\s*0|\[\]|\{\}|''|\"\"|0)\s*;?|"
    r"return\s*;?\s*|continue\s*;?|break\s*;?)\s*$"
)


def _catch_bodies(src: str):
    """Yield (line_no, stripped_body) for every catch block in src."""
    for m in re.finditer(r"catch\s*(?:\(\s*[A-Za-z_$][\w$]*\s*\))?\s*\{", src):
        start, i, depth = m.end(), m.end(), 1
        while i < len(src) and depth > 0:
            if src[i] == "{":
                depth += 1
            elif src[i] == "}":
                depth -= 1
            i += 1
        if depth != 0:
            continue  # unclosed — regex mismatch, skip
        body = re.sub(r"//[^\n]*", "", src[start:i - 1])
        body = re.sub(r"/\*.*?\*/", "", body, flags=re.S).strip()
        line_no = src.count("\n", 0, m.start()) + 1
        yield line_no, body


def scan_js_file(path: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    is_test = is_test_file(path)
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
    except Exception as e:
        return [{
            "file": rel(path), "line": 1, "type": "unreadable",
            "severity": "info", "code": f"{type(e).__name__}: {e}",
            "function": "", "test": is_test, "feature_gate": False,
        }]
    lines = src.splitlines()

    def _line(line_no: int) -> str:
        return (lines[line_no - 1] if 0 < line_no <= len(lines) else "").strip()[:200]

    def _emit(type_: str, severity: str, line_no: int, code: str) -> None:
        eff = "low" if is_test else severity
        findings.append({
            "file": rel(path), "line": line_no, "type": type_, "severity": eff,
            "code": code or _line(line_no), "function": "",
            "test": is_test, "feature_gate": False, "exception": "",
        })

    for line_no, body in _catch_bodies(src):
        code = _line(line_no)
        if body == "":
            _emit("empty-catch", "high", line_no, code)
        elif SILENT_RETURN_RE.match(body):
            _emit("catch-return-silent", "high", line_no, code)

    # .catch(() => {})  /  .catch((e) => {})  /  .catch(() => null)
    for m in re.finditer(
        r"\.catch\s*\(\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)?\s*=>\s*(?:\{\s*\}|\w+|null|undefined|void\s*0)\s*\)",
        src,
    ):
        line_no = src.count("\n", 0, m.start()) + 1
        _emit("promise-catch-silent", "medium", line_no, _line(line_no))

    # unguarded JSON.parse (outside any try/catch window)
    for i, line in enumerate(lines):
        if "JSON.parse(" in line or "JSON.parse (" in line:
            window = "\n".join(lines[max(0, i - 6): i + 3])
            if "try" not in window and "catch" not in window and "safeJson" not in line:
                _emit("json-parse-unguarded", "medium", i + 1, line)

    # floating fetch / axios call (neither awaited, returned, nor assigned)
    for i, line in enumerate(lines):
        s = line.strip()
        if re.match(r"^(fetch|axios[.\w]*|api\.\w+|http\.\w+)\s*\(", s):
            if not s.startswith(("await", "return")) and "=" not in _stmt_head(s):
                _emit("floating-fetch", "medium", i + 1, line)

    # onerror = () => {}  (silently swallowed errors)
    for i, line in enumerate(lines):
        if re.search(r"onerror\s*=\s*\(\s*\)\s*=>\s*\{\s*\}", line):
            _emit("onerror-empty", "high", i + 1, line)

    return findings


def _stmt_head(s: str) -> str:
    """Return the part of the statement before its first '('."""
    idx = s.find("(")
    return s if idx < 0 else s[:idx]
# ---------------------------------------------------------------------------
# Log file scan (optional) — surfaces runtime errors that were only written
# to a log file and would otherwise be invisible to static analysis.
# ---------------------------------------------------------------------------

def _default_log_sources() -> list[str]:
    candidates: list[str] = []
    if (ROOT / "logs").is_dir():
        candidates.append(str(ROOT / "logs"))
    if (ROOT / "scratch").is_dir():
        for sub in ("ci_logs",):
            if (ROOT / "scratch" / sub).is_dir():
                candidates.append(str(ROOT / "scratch" / sub))
    for f in ROOT.iterdir():
        if f.is_file() and f.suffix.lower() == ".log":
            candidates.append(str(f))
    return candidates


def _iter_log_files(sources: list[str]) -> list[str]:
    files: list[str] = []
    for src in sources:
        p = Path(src)
        if not p.exists():
            continue
        if p.is_file():
            if p.suffix.lower() == ".log" or "log" in p.name.lower():
                files.append(str(p))
        elif p.is_dir():
            for dp, _, names in os.walk(p):
                for n in names:
                    if n.endswith((".log", ".txt", ".out")):
                        full = os.path.join(dp, n)
                        if os.path.getsize(full) <= 20_000_000:  # cap huge logs
                            files.append(full)
    return files


def scan_log_file(path: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except Exception as e:
        return [{
            "file": rel(path), "line": 1, "type": "log-unreadable",
            "severity": "info", "code": f"{type(e).__name__}: {e}",
            "function": "", "test": False, "feature_gate": False,
        }]
    for idx, line in enumerate(lines, 1):
        for ptype, pat in LOG_PATTERNS:
            if pat.search(line):
                findings.append({
                    "file": rel(path), "line": idx, "type": ptype,
                    "severity": "info", "code": line.strip()[:200].rstrip("\r"),
                    "function": "", "test": False, "feature_gate": False,
                })
                break
    return findings
# ---------------------------------------------------------------------------
# Baseline / regression delta
# ---------------------------------------------------------------------------

def finding_key(f: dict[str, Any]) -> str:
    return f"{f['file']}:{f['line']}:{f['type']}"


def load_baseline(path: str | None) -> set[str]:
    if not path:
        return set()
    p = Path(path)
    if not p.exists():
        print(f"  ⚠️  Baseline not found ({path}); treating all findings as new.", file=sys.stderr)
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ⚠️  Could not read baseline {path}: {e}; treating all as new.", file=sys.stderr)
        return set()
    entries = data if isinstance(data, list) else data.get("findings", [])
    out: set[str] = set()
    for e in entries:
        out.add(f"{e['file']}:{e['line']}:{e['type']}")
    return out


def save_baseline(path: str, findings: list[dict[str, Any]]) -> None:
    """Persist a lean (file,line,type,severity) snapshot for known findings."""
    slim = [{"file": f["file"], "line": f["line"], "type": f["type"], "severity": f["severity"]}
            for f in findings if not str(f["type"]).startswith("log-")]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({"generated_at": _now(), "findings": slim}, indent=2), encoding="utf-8")
    print(f"  📌 Baseline written to {path} ({len(slim)} findings)")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def _severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(f["severity"] for f in findings))


def _per_type(findings: list[dict[str, Any]]) -> dict[str, int]:
    d: dict[str, int] = {}
    for f in findings:
        d[f["type"]] = d.get(f["type"], 0) + 1
    return dict(sorted(d.items(), key=lambda kv: -kv[1]))


def _top_files(findings: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    counts: dict[str, int] = Counter()
    for f in findings:
        if SEVERITY_RANK.get(f["severity"], 0) >= 2:  # medium+
            counts[f["file"]] += 1
    return [{"file": k, "count": v} for k, v in counts.most_common(limit)]


def write_markdown(report: dict[str, Any], path: str) -> None:
    lines: list[str] = []
    lines.append("# 🔇 Silent Error Scan Report")
    lines.append("")
    lines.append(f"_Generated: {report['generated_at']} · Scanner: `scripts/detect_silent_errors.py`_")
    lines.append("")
    lines.append(f"- Python files scanned: **{report['files_scanned']['python']}**")
    lines.append(f"- JS/TS files scanned:  **{report['files_scanned']['js']}**")
    lines.append(f"- Log files scanned:    **{report['files_scanned']['logs']}**")
    lines.append("- Total findings: **%d**" % len(report["findings"]))
    for sev in ("high", "medium", "low", "info"):
        if report["severity_counts"].get(sev):
            lines.append(f"  - {sev}: **{report['severity_counts'][sev]}**")
    lines.append("")

    b = report.get("baseline")
    if b:
        lines.append("## Regression (vs baseline)")
        lines.append("")
        lines.append(f"- New findings (fail CI): **{b['new']}**")
        lines.append(f"- Known (baselined):      **{b['known']}**")
        lines.append(f"- Resolved since baseline: **{b['resolved']}**")
        lines.append("")

    lines.append("## Findings by type")
    lines.append("")
    lines.append("| Type | Count |")
    lines.append("|---|---|")
    for k, v in _per_type(report["findings"]).items():
        lines.append(f"| `{k}` | {v} |")
    lines.append("")

    if report["top_files"]:
        lines.append("## Files with most medium+ findings")
        lines.append("")
        lines.append("| File | Count |")
        lines.append("|---|---|")
        for tf in report["top_files"]:
            lines.append(f"| `{tf['file']}` | {tf['count']} |")
        lines.append("")

    lines.append("## Findings")
    lines.append("")
    lines.append("| Severity | File:Line | Type | Snippet |")
    lines.append("|---|---|---|---|")
    for f in sorted(report["findings"], key=lambda x: (-SEVERITY_RANK.get(x["severity"], 0), x["file"], x["line"])):
        snip = (f.get("code") or "").replace("|", "/").replace("\n", " ")[:80]
        lines.append(f"| {f['severity']} | `{f['file']}:{f['line']}` | `{f['type']}` | `{snip}` |")
    lines.append("")

    if report["log_findings"]:
        lines.append("## Log scan highlights")
        lines.append("")
        lines.append("| Type | File:Line | Snippet |")
        lines.append("|---|---|---|")
        for lg in report["log_findings"][:200]:
            snip = (lg.get("code") or "").replace("|", "/")[:90]
            lines.append(f"| `{lg['type']}` | `{lg['file']}:{lg['line']}` | `{snip}` |")
        lines.append("")

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    print(f"  📄 Markdown report written to {path}")
# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="detect_silent_errors.py",
        description="Detect all silent-error categories across the SupremeAI codebase.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--path", default=str(ROOT), help="project root (default: repo root)")
    p.add_argument("--scan-dirs", nargs="*", default=None,
                   help="repo-relative dirs to scan (default: DEFAULT_SCAN_DIRS)")
    p.add_argument("--exclude-dirs", nargs="*", default=[],
                   help="extra directory names to skip (merged with defaults)")
    p.add_argument("--json", default=None, help="write a machine-readable JSON report")
    p.add_argument("--markdown", default=None, help="write a Markdown summary report")
    p.add_argument("--fail-on", choices=["high", "medium", "low", "never"], default="high",
                   help="exit 1 if any NEW finding is at/above this severity (default: high)")
    p.add_argument("--baseline", default=None,
                   help="path to a baseline JSON; CI fails only on findings NOT in the baseline")
    p.add_argument("--update-baseline", action="store_true",
                   help="write the baseline snapshot of the current scan and exit 0")
    p.add_argument("--logs", nargs="*", default=None, metavar="PATH",
                   help="also scan log files; pass 'auto' for default log sources")
    p.add_argument("--include-tests", action="store_true",
                   help="treat test files as normal (their findings can reach high severity)")
    p.add_argument("--quiet", action="store_true",
                   help="suppress the per-finding console listing")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    scan_dirs = args.scan_dirs or DEFAULT_SCAN_DIRS
    exclude = DEFAULT_EXCLUDE_DIRS | set(args.exclude_dirs)
    py_exts = (".py",)
    js_exts = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

    all_findings: list[dict[str, Any]] = []
    n_py = n_js = 0

    print("🔍 Scanning for silent errors ...")
    for d in scan_dirs:
        if not os.path.isdir(os.path.join(ROOT, d)):
            continue
        for path in iter_files(d, py_exts, exclude):
            n_py += 1
            all_findings.extend(scan_python_file(path, args.include_tests))
        for path in iter_files(d, js_exts, exclude):
            n_js += 1
            all_findings.extend(scan_js_file(path))

    # de-duplicate identical (file,line,type)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for f in sorted(all_findings, key=lambda x: (-SEVERITY_RANK.get(x["severity"], 0), x["file"], x["line"])):
        k = finding_key(f)
        if k in seen:
            continue
        seen.add(k)
        if f["type"] in ("unreadable", "log-unreadable"):
            continue
        unique.append(f)
    all_findings = unique

    log_findings: list[dict[str, Any]] = []
    n_logs = 0
    if args.logs is not None:
        sources = _default_log_sources() if "auto" in args.logs else args.logs
        for lp in _iter_log_files(sources):
            n_logs += 1
            log_findings.extend(scan_log_file(lp))

    severity_counts = _severity_counts(all_findings)
    baseline_keys: set[str] | None = None
    baseline_block: dict[str, Any] | None = None

    if args.update_baseline:
        bl = args.baseline or os.path.join(ROOT, "scripts", "silent_errors_baseline.json")
        save_baseline(bl, all_findings)
        return 0
    if args.baseline:
        baseline_keys = load_baseline(args.baseline)
        new_k = [f for f in all_findings if finding_key(f) not in baseline_keys]
        known = [f for f in all_findings if finding_key(f) in baseline_keys]
        resolved = [k for k in baseline_keys if not any(finding_key(f) == k for f in all_findings)]
        baseline_block = {
            "path": os.path.relpath(args.baseline, ROOT),
            "new": len(new_k), "known": len(known), "resolved": len(resolved),
        }

    gate_rank = SEVERITY_RANK.get(args.fail_on, 3)
    if baseline_keys is not None:
        blockers = [f for f in all_findings
                    if finding_key(f) not in baseline_keys
                    and SEVERITY_RANK.get(f["severity"], 0) >= gate_rank]
    else:
        blockers = [f for f in all_findings if SEVERITY_RANK.get(f["severity"], 0) >= gate_rank]
    exit_code = 1 if (args.fail_on != "never" and blockers) else 0

    report = {
        "generated_at": _now(),
        "scanner": "scripts/detect_silent_errors.py",
        "files_scanned": {"python": n_py, "js": n_js, "logs": n_logs},
        "severity_counts": severity_counts,
        "per_type": _per_type(all_findings),
        "top_files": _top_files(all_findings),
        "findings": all_findings,
        "log_findings": log_findings,
        "baseline": baseline_block,
        "exit": {"code": exit_code, "reason": f"fail-on={args.fail_on}", "blockers": len(blockers)},
    }

    _print_summary(args, report, blockers)

    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  📄 JSON report written to {args.json}")
    if args.markdown:
        write_markdown(report, args.markdown)

    return exit_code

def _print_summary(args: argparse.Namespace, report: dict[str, Any], blockers: list[dict[str, Any]]) -> None:
    c = report["severity_counts"]
    print("=" * 60)
    print(f"Python files scanned : {report['files_scanned']['python']}")
    print(f"JS/TS files scanned  : {report['files_scanned']['js']}")
    print(f"Log files scanned    : {report['files_scanned']['logs']}")
    print(f"Findings             : high={c.get('high', 0)} medium={c.get('medium', 0)} "
          f"low={c.get('low', 0)} info={c.get('info', 0)}")
    b = report.get("baseline")
    if b:
        print(f"Regression delta     : new={b['new']} known={b['known']} resolved={b['resolved']}")
    if not args.quiet:
        for f in sorted(blockers, key=lambda x: (-SEVERITY_RANK.get(x["severity"], 0), x["file"], x["line"])):
            snip = (f.get("code") or "").replace("\t", " ").replace("\n", " ")[:90]
            print(f"  [{f['severity']}] {f['file']}:{f['line']} ({f['type']}) — {snip}")
        for lg in report["log_findings"][:30]:
            print(f"  [log:{lg['type']}] {lg['file']}:{lg['line']} — {(lg.get('code') or '')[:80]}")
    print("=" * 60)
    if report["exit"]["code"] == 0:
        print("✅ PASS: no new silent errors above the fail threshold.")
    else:
        print(f"🚨 FAIL: {len(blockers)} silent error(s) at/above '{args.fail_on}' severity.")


if __name__ == "__main__":
    sys.exit(main())
