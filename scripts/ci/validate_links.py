#!/usr/bin/env python3
"""
validate_links.py — repository markdown link-integrity validator (#404, Seq 0.4).

Mission (issue #404, 3-Tier Verification Contract, tier 2):
  "python scripts/ci/validate_links.py (or grep check for broken local
  relative paths)" — this CLI is the standard validator that the tier names;
  the grep alternative is the fallback it replaces. Repo-wide goal: 0 dead
  links (tier 3).

What it validates
=================
1. Inline links ``[text](target)``, images ``![alt](src)`` and reference-style
   definitions ``[id]: target`` (usages resolve through their definition).
2. Target classes:
   - ``#anchor`` / ``file.md#anchor`` — GitHub-style heading slugs
     (unicode-aware: Bengali headings keep their characters; duplicate
     headings get the GitHub ``-1``/``-2`` suffixes in document order).
   - ``./rel``, ``../rel``, bare relative paths, ``/repo-root-relative``.
   - ``http(s)://`` — SKIPPED by default (deterministic offline CI mode);
     ``--check-remote`` probes opt-in (HEAD with GET fallback; 404/410 =
     broken; 401/403/429/5xx/timeouts = "unverifiable" WARNING that never
     gates the exit code — remote liveness is diagnostic, not contractual).
   - ``mailto:`` — skipped.
3. Code immunity: fenced blocks (```` ``` ```` / ``~~~``) and inline code
   spans (``` `...` ```) are stripped before extraction, so copy-paste
   usage examples in docs never false-positive.

Design principles (house doctrine, mirrors boundary_sanitization_guard.py):
  - Fail-closed: an unreadable markdown file is an operational error
    (exit 2), never a silent pass. Broken links => exit 1, each reported
    with ``file:line`` and the exact target.
  - Stdlib-only, no network by default, no git writes, deterministic
    (sorted, stable) output.
  - Calibrated against origin/main ``b019b1d``: on the pristine tree it
    reports exactly the 5 known-broken links in ``examples/curl-tests/README.md``
    (relative depth ``../docs/...`` instead of ``../../docs/...``) — see the
    #404 handoff appendix for the byte-exact repair hunks.

Exit codes: 0 = clean · 1 = broken links found · 2 = operational error.

Usage
=====
    python scripts/ci/validate_links.py                  # whole repo (deterministic)
    python scripts/ci/validate_links.py --json           # machine-readable report
    python scripts/ci/validate_links.py --files A.md B.md
    python scripts/ci/validate_links.py --root /some/repo
    python scripts/ci/validate_links.py --check-remote   # opt-in remote probing
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Tuple

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}

# --- extraction ---------------------------------------------------------------

FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)

# [text](<target with spaces>) or [text](target "title")
ANGLE_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(\s*<([^<>\n]+)>\s*(?:\"[^\"]*\"\s*)?\)")
# [text](target) — first whitespace-delimited token is the target
PLAIN_LINK_RE = re.compile(r"!?\[[^\]\n]*\]\(\s*([^\s)<][^)\s]*)\s*(?:\"[^\"]*\"\s*)?\)")
# reference-style definition: [id]: target
REFDEF_RE = re.compile(r"^ {0,3}\[([^\]\n]+)\]:\s*([^\s]+)\s*$", re.M)

ATX_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
SETEXT_RE = re.compile(r"^ {0,3}(=+|-+)\s*$")

EXTERNAL_SCHEMES = ("http://", "https://")
SKIPPED_SCHEMES = ("mailto:",)


def strip_code_regions(text: str) -> str:
    """Blank out fenced blocks line-wise (line numbers preserved) + inline spans/HTML comments."""
    out_lines: List[str] = []
    fence: Optional[str] = None
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        m = FENCE_RE.match(stripped)
        if fence is None:
            if m:
                fence = m.group(1)[:3]
                out_lines.append("\n")
                continue
            out_lines.append(line)
        else:
            # inside a fence: only the matching closing fence exits
            if m and m.group(1).startswith(fence):
                fence = None
            out_lines.append("\n")
    text = "".join(out_lines)
    text = HTML_COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    text = INLINE_CODE_RE.sub("", text)
    return text


def github_slug(text: str) -> str:
    """GitHub heading slug: lowercase, keep unicode letters/numbers/MARKS +
    hyphen/underscore, spaces -> '-'. Categories L/N/M matter: Bengali vowel
    signs (া ি ো) and the anusvara (ং) are combining marks (Mn/Mc) —
    str.isalnum() is False for them, but GitHub keeps them in anchors.
    Dropping them would false-positive every Bengali-heading anchor."""
    lowered = text.strip().lower()
    out: List[str] = []
    for ch in lowered:
        cat = unicodedata.category(ch)
        if cat[0] in ("L", "N", "M") or ch in "_-":
            out.append(ch)
        elif ch == " ":
            out.append("-")
    return "".join(out)


def heading_slugs(text: str) -> Dict[str, int]:
    """Map slug -> occurrence index (document order) for a markdown document."""
    stripped = strip_code_regions(text)
    lines = stripped.splitlines()
    slugs: Dict[str, int] = {}
    order: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = ATX_HEADING_RE.match(line)
        if m:
            order.append(github_slug(m.group(2)))
            i += 1
            continue
        # setext: heading text on the previous line
        if i > 0 and SETEXT_RE.match(line):
            prev = lines[i - 1].strip()
            if prev and not ATX_HEADING_RE.match(lines[i - 1]):
                order.append(github_slug(prev))
        i += 1
    seen: Dict[str, int] = {}
    for s in order:
        if not s:
            continue
        n = seen.get(s, 0)
        seen[s] = n + 1
        slugs[s if n == 0 else f"{s}-{n}"] = slugs.get(s if n == 0 else f"{s}-{n}", 0)
    return slugs


def extract_links(text: str) -> List[Tuple[int, str]]:
    """Return (line_number, target) pairs for every markdown link/image/refdef."""
    stripped = strip_code_regions(text)
    found: List[Tuple[int, str]] = []
    for m in ANGLE_LINK_RE.finditer(stripped):
        line = stripped.count("\n", 0, m.start(1)) + 1
        found.append((line, m.group(1).strip()))
    for m in PLAIN_LINK_RE.finditer(stripped):
        line = stripped.count("\n", 0, m.start(1)) + 1
        found.append((line, m.group(1).strip()))
    for m in REFDEF_RE.finditer(stripped):
        line = stripped.count("\n", 0, m.start(2)) + 1
        found.append((line, m.group(2).strip()))
    return found


# --- validation ---------------------------------------------------------------


class LinkValidator:
    def __init__(self, root: str, check_remote: bool = False, remote_timeout: int = 15):
        self.root = os.path.abspath(root)
        self.check_remote = check_remote
        self.remote_timeout = remote_timeout
        self.broken: List[dict] = []
        self.warnings: List[dict] = []
        self.op_errors: List[dict] = []
        self.md_files: List[str] = []
        self._slug_cache: Dict[str, Dict[str, int]] = {}
        self.local_links = 0
        self.external_links = 0
        self.anchor_links = 0

    # -- file collection -------------------------------------------------------
    def collect(self) -> None:
        for dirpath, dirs, files in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for fn in sorted(files):
                if fn.lower().endswith(".md"):
                    self.md_files.append(os.path.join(dirpath, fn))

    # -- helpers -----------------------------------------------------------------
    def _slugs_for(self, path: str) -> Dict[str, int]:
        if path not in self._slug_cache:
            try:
                with open(path, encoding="utf-8") as fh:
                    self._slug_cache[path] = heading_slugs(fh.read())
            except OSError:
                self._slug_cache[path] = {}
        return self._slug_cache[path]

    def _check_anchor(self, target_path: Optional[str], frag: str, where: str) -> None:
        self.anchor_links += 1
        # where is root-relative; anchor checks need the TRUE path (CWD-independence)
        path = target_path if target_path else os.path.join(self.root, where)
        if not os.path.exists(path):
            return  # missing file is (or will be) reported by the path check
        slugs = self._slugs_for(path)
        if frag not in slugs:
            self.broken.append({
                "file": where, "target": f"#{frag}" if target_path is None else os.path.relpath(path, self.root) + "#" + frag,
                "reason": "anchor not found (GitHub slug of any heading)",
            })

    def _check_local(self, target: str, where: str, line: int) -> None:
        self.local_links += 1
        path_part, _, frag = target.partition("#")
        # where is root-relative — resolve against the file's TRUE directory,
        # never the process CWD (a CWD-relative resolve silently breaks when
        # the tool is invoked from anywhere other than the repo root).
        true_dir = os.path.dirname(os.path.join(self.root, where))
        if target.startswith("/"):
            resolved = os.path.normpath(os.path.join(self.root, path_part.lstrip("/")))
        else:
            resolved = os.path.normpath(os.path.join(true_dir, path_part))
        if not os.path.exists(resolved):
            self.broken.append({
                "file": where, "line": line, "target": target,
                "reason": "local path does not exist",
            })
            return
        if frag:
            self._check_anchor(resolved, frag, where)

    def _check_remote_url(self, url: str, where: str, line: int) -> None:
        self.external_links += 1
        if not self.check_remote:
            return
        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(url, method=method,
                                             headers={"User-Agent": "supremeai-link-validator/1.0"})
                with urllib.request.urlopen(req, timeout=self.remote_timeout) as resp:
                    status = resp.status
                if status < 400:
                    return
                if status in (404, 410):
                    self.broken.append({"file": where, "line": line, "target": url,
                                        "reason": f"remote returned HTTP {status}"})
                    return
                # other 4xx/5xx after both methods -> unverifiable
            except urllib.error.HTTPError as exc:
                if exc.code in (404, 410):
                    self.broken.append({"file": where, "line": line, "target": url,
                                        "reason": f"remote returned HTTP {exc.code}"})
                    return
                if method == "GET":
                    break
            except Exception:  # noqa: BLE001 — network diagnostics, not contract
                if method == "GET":
                    break
        self.warnings.append({"file": where, "line": line, "target": url,
                              "reason": "unverifiable (timeout/4xx/5xx/rate-limit) — remote checks are diagnostic only"})

    # -- main pass -----------------------------------------------------------------
    def run(self) -> None:
        if not self.md_files:  # idempotent: never double-collect (each double-collected
            self.collect()     # file would report every link twice — the exact bug class
        if not self.md_files:
            self.broken.append({"file": "-", "target": "-",
                                "reason": f"no markdown files found under {self.root} (operational sanity)"})
            return
        for path in self.md_files:
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError) as exc:
                # Fail-closed doctrine: an unreadable markdown file is NOT a
                # "broken link" (exit 1) — it is an UNVERIFIABLE input, i.e. an
                # operational error (exit 2), mirroring boundary_sanitization_guard.
                self.op_errors.append({"file": path,
                                       "reason": f"unreadable markdown: {type(exc).__name__}"})
                continue
            rel = os.path.relpath(path, self.root)
            for line, target in extract_links(text):
                low = target.lower()
                if low.startswith(EXTERNAL_SCHEMES):
                    self._check_remote_url(target, rel, line)
                elif low.startswith(SKIPPED_SCHEMES):
                    continue
                elif target.startswith("#"):
                    self._check_anchor(None, target[1:], rel)
                else:
                    self._check_local(target, rel, line)


def main(argv: Optional[List[str]] = None) -> int:
    default_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap = argparse.ArgumentParser(description="Markdown link-integrity validator (issue #404 Seq 0.4 tier-2).")
    ap.add_argument("--root", default=default_root, help="repository root (default: the repo this script lives in)")
    ap.add_argument("--files", nargs="*", default=None, help="scan only these markdown files (relative to --root)")
    ap.add_argument("--json", action="store_true", help="machine-readable report on stdout")
    ap.add_argument("--check-remote", action="store_true",
                    help="opt-in: probe http(s) links (404/410 = broken; other failures = warnings)")
    ap.add_argument("--remote-timeout", type=int, default=15, help="per-request timeout for --check-remote")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"OPERATIONAL ERROR: --root is not a directory: {root}", file=sys.stderr)
        return 2

    v = LinkValidator(root, check_remote=args.check_remote, remote_timeout=args.remote_timeout)
    if args.files:
        v.md_files = [os.path.normpath(os.path.join(root, f)) for f in args.files]
        for f in v.md_files:
            if not os.path.isfile(f):
                print(f"OPERATIONAL ERROR: --files entry not found: {f}", file=sys.stderr)
                return 2

    if args.files:
        for path in list(v.md_files):
            try:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError) as exc:
                v.op_errors.append({"file": path,
                                    "reason": f"unreadable markdown: {type(exc).__name__}"})
                continue
            rel = os.path.relpath(path, root)
            for line, target in extract_links(text):
                low = target.lower()
                if low.startswith(EXTERNAL_SCHEMES):
                    v._check_remote_url(target, rel, line)
                elif low.startswith(SKIPPED_SCHEMES):
                    continue
                elif target.startswith("#"):
                    v._check_anchor(None, target[1:], rel)
                else:
                    v._check_local(target, rel, line)
    else:
        v.run()  # collects once (idempotent) then scans

    v.broken.sort(key=lambda r: (r.get("file", ""), r.get("line", 0), r.get("target", "")))
    v.warnings.sort(key=lambda r: (r.get("file", ""), r.get("line", 0), r.get("target", "")))

    if args.json:
        print(json.dumps({
            "root": root,
            "files_scanned": len(v.md_files),
            "local_links": v.local_links,
            "anchor_links": v.anchor_links,
            "external_links": v.external_links,
            "broken": v.broken,
            "warnings": v.warnings,
            "op_errors": v.op_errors,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"validate_links: scanned {len(v.md_files)} markdown file(s) under {root}")
        print(f"  local links: {v.local_links} · anchors: {v.anchor_links} · external: {v.external_links}"
              f"{' (skipped; use --check-remote)' if not args.check_remote else ''}")
        for w in v.warnings:
            print(f"  WARN {w['file']}:{w.get('line', '?')} -> {w['target']} ({w['reason']})")
        for b in v.broken:
            print(f"  BROKEN {b['file']}:{b.get('line', '?')} -> {b['target']} ({b['reason']})")
        for o in v.op_errors:
            print(f"  OP-ERROR {o['file']} ({o['reason']})", file=sys.stderr)
        if not v.broken:
            print("  RESULT: 0 dead links — clean")
        else:
            print(f"  RESULT: {len(v.broken)} broken link(s)")
    if v.op_errors:
        return 2
    return 1 if v.broken else 0


if __name__ == "__main__":
    sys.exit(main())
