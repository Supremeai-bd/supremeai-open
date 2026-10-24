#!/usr/bin/env python3
"""Script Index Generator (SIL-0d) — scripts/_INDEX.md is ALWAYS derived, never hand-maintained.

WHY THIS EXISTS (user problem): "there is many script but all of them aren't
intelligent enough... if we change something in codebase script don't track
them."  The old _INDEX.md was a hand-curated list that rotted: it referenced
deleted scripts (context_snapshot.py, check_env_health.py, migrate.py,
find_dead_code.py at root, ...) and missed ~230 real ones.  This generator
DISCOVERS the live inventory on every run, so a new/renamed/deleted script is
reflected the next time the index is regenerated (and `--check` fails CI when
somebody forgets).

What it does
    1. Discovers every script under scripts/ via the shared auto_discovery
       lib: *.py through discover_py_files (git-aware, respects .gitignore),
       plus *.sh / *.mjs / *.js / *.dart through discover_files.
    2. Extracts a one-line purpose per script WITHOUT importing anything:
       module docstring first line (AST) -> argparse description (AST) ->
       leading comment block (shell/js/dart).  Files with nothing get an
       explicit "(no docstring ...)" marker so the gap is visible, not silent.
    3. Groups by top-level subdirectory (scripts/ai, scripts/ci, ...) and
       emits one Markdown table per group.
    4. Preserves hand-curated knowledge: any section wrapped in
       ``<!-- hand:Name --> ... <!-- /hand:Name -->`` in the target file is
       carried over verbatim.  Hand sections that reference files which no
       longer exist produce a loud warning (stdout) but are never edited.
    5. Writes scripts/_INDEX.md (or --output).  --check regenerates in
       memory and exits 1 when the file on disk is stale -- wire it into CI.

Design rules
    - stdlib only; no subprocess, no git calls of its own (discovery may use
      `git ls-files` through the shared lib), no imports of scanned files.
    - never crashes on unparseable files; bad files are reported in-band.
    - zero-byte files (empty __init__.py and friends) are skipped and counted.

USAGE
    python3 scripts/generate_script_index.py            # regenerate _INDEX.md
    python3 scripts/generate_script_index.py --check    # CI gate, exit 1 if stale
    python3 scripts/generate_script_index.py --output /tmp/idx.md
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))  # so `lib.auto_discovery` resolves from any cwd

try:
    from lib.auto_discovery import (  # type: ignore
        discover_files,
        discover_py_files,
        get_layout,
        require,
    )
except ImportError as exc:  # pragma: no cover - only when repo layout is broken
    sys.stderr.write(
        f"generate_script_index: cannot import scripts/lib/auto_discovery.py ({exc}).\n"
        "Run this script from a full checkout (scripts/lib must exist).\n"
    )
    raise SystemExit(2)

REPO_ROOT = get_layout().root
DEFAULT_OUTPUT = SCRIPTS_DIR / "_INDEX.md"
NO_DOCSTRING_MARK = "(no docstring — run scripts/devops/devops_ai_scribe.py or add one)"
PURPOSE_MAX_LEN = 160
HAND_BLOCK_RE = re.compile(r"<!--\s*hand:(.+?)\s*-->\n(.*?)<!--\s*/hand:\1\s*-->", re.DOTALL)
BACKTICK_REF_RE = re.compile(r"`([\w][\w/\.\-]*\.(?:py|sh|mjs|js|dart|md|yml|yaml|json))`")
TIMESTAMP_RE = re.compile(r"^> Last generated: .*? UTC ·", re.MULTILINE)

PY_EXTS = {".py"}
NONPY_PATTERNS = ("*.sh", "*.mjs", "*.js", "*.dart")


# --------------------------------------------------------------------------- #
# Purpose extraction (AST / comment based — never imports the scanned file)
# --------------------------------------------------------------------------- #

_DECORATIVE_RE = re.compile(r"^[=\-_*~#╔═╦─══\s|+<>·.]+$")
_FILENAME_RE = re.compile(r"^[\w/\.\-]+\.(?:py|sh|mjs|js|dart)$", re.IGNORECASE)


def _is_noise(line: str) -> bool:
    """Banner rules, box-drawing filler or a bare filename — useless as a purpose."""
    s = line.strip()
    return (not s) or _DECORATIVE_RE.match(s) is not None or _FILENAME_RE.match(s) is not None


def _first_useful_line(text: str) -> str:
    """First line that actually says something (skips banners / bare filenames)."""
    for raw in str(text).splitlines():
        line = " ".join(raw.split())
        if _is_noise(line):
            continue
        return line
    return ""


def _clean(text: str) -> str:
    """One flat, table-safe line."""
    line = " ".join(str(text).split())
    if len(line) > PURPOSE_MAX_LEN:
        line = line[: PURPOSE_MAX_LEN - 1].rstrip() + "…"
    return line.replace("|", "/").strip()


def _argparse_description(tree: ast.AST) -> Optional[str]:
    """Trivially extractable argparse description: ArgumentParser(description='...')."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "ArgumentParser":
            continue
        for kw in node.keywords:
            if kw.arg == "description" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                return kw.value.value
    return None


def purpose_for_py(path: Path) -> Tuple[str, str]:
    """(purpose_line, source_tag) for a python file; never raises."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return f"(unparseable — syntax error: {exc.msg})", "error"
    except OSError as exc:
        return f"(unreadable: {exc})", "error"

    doc = ast.get_docstring(tree)
    if doc:
        first = _clean(_first_useful_line(doc))
        if first:
            return first, "docstring"

    desc = _argparse_description(tree)
    if desc:
        first = _clean(desc)
        if first:
            return first, "argparse"

    return NO_DOCSTRING_MARK, "missing"


def purpose_for_comment_file(path: Path) -> Tuple[str, str]:
    """Purpose from the leading comment block of .sh/.mjs/.js/.dart files."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[:40]
    except OSError as exc:
        return f"(unreadable: {exc})", "error"

    ext = path.suffix
    collected: List[str] = []
    in_block = False
    for raw in lines:
        s = raw.strip()
        if ext == ".sh":
            if s.startswith("#!"):
                continue
            if s.startswith("#"):
                collected.append(s.lstrip("#").strip())
                continue
            if s:
                break  # comment run ended
        elif ext == ".dart":
            if s.startswith("///") or s.startswith("//"):
                collected.append(s.lstrip("/").strip())
                continue
            if s.startswith("/*"):
                in_block = True
                continue
            if in_block:
                if s.endswith("*/"):
                    in_block = False
                continue
            if s:
                break
        else:  # .js / .mjs
            if s.startswith("//"):
                collected.append(s.lstrip("/").strip())
                continue
            if s.startswith("/*"):
                in_block = True
                continue
            if in_block:
                if s.endswith("*/"):
                    in_block = False
                    continue
                collected.append(s.strip("*/").strip())
                continue
            if s:
                break

    for cand in collected:
        if _is_noise(cand):
            continue
        cleaned = _clean(cand)
        if cleaned:
            return cleaned, "comment"
    return NO_DOCSTRING_MARK, "missing"


# --------------------------------------------------------------------------- #
# Discovery + grouping
# --------------------------------------------------------------------------- #

def discover_scripts() -> Tuple[List[Tuple[Path, str]], int]:
    """[(absolute_path, scripts_relative_posix_path)], plus empty-file count."""
    py_files = discover_py_files(base=SCRIPTS_DIR, env="")  # git-aware, untracked included
    other_files = discover_files(SCRIPTS_DIR, NONPY_PATTERNS)

    entries: List[Tuple[Path, str]] = []
    skipped_empty = 0
    seen: set = set()
    for p in sorted(set(py_files) | set(other_files)):
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        try:
            if p.stat().st_size == 0:
                skipped_empty += 1
                continue
        except OSError:
            continue
        rel = p.relative_to(SCRIPTS_DIR).as_posix()
        entries.append((p, rel))
    return entries, skipped_empty


def group_of(rel_path: str) -> str:
    return rel_path.split("/", 1)[0] if "/" in rel_path else "(root)"


# --------------------------------------------------------------------------- #
# Markdown composition
# --------------------------------------------------------------------------- #

def compose_markdown(entries: List[Tuple[Path, str]], skipped_empty: int,
                     hand_blocks: List[Tuple[str, str]]) -> Tuple[str, List[Dict[str, str]]]:
    rows_by_group: Dict[str, List[Tuple[str, str]]] = {}
    stats = {"py": 0, "sh": 0, "js": 0, "other": 0, "missing_docstring": 0}
    notes: List[Dict[str, str]] = []

    for path, rel in entries:
        if path.suffix == ".py":
            purpose, source = purpose_for_py(path)
            stats["py"] += 1
        elif path.suffix == ".sh":
            purpose, source = purpose_for_comment_file(path)
            stats["sh"] += 1
        elif path.suffix in (".js", ".mjs"):
            purpose, source = purpose_for_comment_file(path)
            stats["js"] += 1
        else:
            purpose, source = purpose_for_comment_file(path)
            stats["other"] += 1
        if source == "missing":
            stats["missing_docstring"] += 1
        rows_by_group.setdefault(group_of(rel), []).append((rel, purpose))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = len(entries)
    lines: List[str] = [
        "# scripts/ — Script Index (AUTO-GENERATED)",
        "",
        "> **AUTO-GENERATED by `scripts/generate_script_index.py` — DO NOT EDIT BY HAND.**",
        "> Regenerate: `python3 scripts/generate_script_index.py` · CI gate: `--check` (exit 1 when stale)",
        f"> Last generated: {now} · **{total} scripts** "
        f"({stats['py']} py · {stats['sh']} sh · {stats['js']} js/mjs · {stats['other']} other) "
        f"across {len(rows_by_group)} groups · {skipped_empty} empty files skipped · "
        f"{stats['missing_docstring']} missing docstrings.",
        "> AI: পুরো ফোল্ডার স্ক্যান না করে এই index পড়ুন। Paths are relative to `scripts/`.",
        "",
        "Hand-curated sections live inside `<!-- hand:Name -->` … `<!-- /hand:Name -->` blocks",
        "at the bottom — the generator preserves them verbatim on every regeneration.",
        "",
    ]

    for group in sorted(rows_by_group, key=lambda g: (g != "(root)", g)):
        rows = sorted(rows_by_group[group])
        label = "scripts/" if group == "(root)" else f"scripts/{group}/"
        lines.append(f"## {label}  ({len(rows)} scripts)")
        lines.append("")
        lines.append("| File | Purpose |")
        lines.append("|---|---|")
        for rel, purpose in rows:
            lines.append(f"| `{rel}` | {purpose} |")
        lines.append("")

    if hand_blocks:
        lines.append("---")
        lines.append("")
        lines.append("## Hand-curated sections (manual — preserved verbatim)")
        lines.append("")
        for name, body in hand_blocks:
            lines.append(f"<!-- hand:{name} -->")
            lines.append(body.rstrip())
            lines.append(f"<!-- /hand:{name} -->")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n", notes


def extract_hand_blocks(target: Path) -> List[Tuple[str, str]]:
    """Pull `<!-- hand:... -->` blocks out of the existing index (if any)."""
    if not target.exists():
        return []
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [(name.strip(), body) for name, body in HAND_BLOCK_RE.findall(text)]


def warn_stale_hand_refs(hand_blocks: List[Tuple[str, str]], target: Path) -> List[str]:
    """Hand sections are never edited by the generator — but rot in them must be loud."""
    warnings: List[str] = []
    for name, body in hand_blocks:
        refs = BACKTICK_REF_RE.findall(body)
        stale = []
        for ref in refs:
            if ref.startswith("scripts/") and (REPO_ROOT / ref).exists():
                continue
            if (SCRIPTS_DIR / ref).exists():
                continue
            stale.append(ref)
        if stale:
            warnings.append(
                f"hand section '{name}' references {len(stale)} path(s) that no longer "
                f"exist: {', '.join('`' + s + '`' for s in stale)} — fix the hand block in {target.name}"
            )
    return warnings


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Auto-generate scripts/_INDEX.md from the live scripts/ inventory "
                    "(docstring/argparse/comment purposes, grouped by subdirectory, "
                    "hand-curated sections preserved).",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help=f"output path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit 1 if the output file is out of date (CI gate)")
    args = parser.parse_args(argv)
    target = Path(args.output).resolve()

    entries, skipped_empty = discover_scripts()
    require(entries, "scripts under scripts/ -- the scan root is wrong or the tree is empty")

    hand_blocks = extract_hand_blocks(target)
    content, _ = compose_markdown(entries, skipped_empty, hand_blocks)

    for warning in warn_stale_hand_refs(hand_blocks, target):
        print(f"⚠️  STALE HAND SECTION: {warning}", file=sys.stderr)

    if args.check:
        try:
            current = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            print(f"STALE: {target} does not exist. Run: python3 scripts/generate_script_index.py")
            return 1
        # the generation timestamp obviously differs between runs — compare modulo it
        if TIMESTAMP_RE.sub("> Last generated: <TS> ·", current) == TIMESTAMP_RE.sub("> Last generated: <TS> ·", content):
            print(f"OK: {target} is up to date ({len(entries)} scripts, {len(hand_blocks)} hand sections).")
            return 0
        print(f"STALE: {target} differs from the regenerated index "
              f"({len(entries)} live scripts found). "
              f"Run: python3 scripts/generate_script_index.py")
        return 1

    target.write_text(content, encoding="utf-8")
    groups = len({group_of(rel) for _, rel in entries})
    print(f"Wrote {target} — {len(entries)} scripts across {groups} groups, "
          f"{skipped_empty} empty skipped, {len(hand_blocks)} hand section(s) preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
