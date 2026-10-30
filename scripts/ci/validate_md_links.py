#!/usr/bin/env python3
"""Markdown link validator — Seq 0.4 (#404) Link-Integrity tier.

Scans markdown files for dead links:
  - relative links (./x, ../x, plain paths) → resolved against the file's dir
  - repo-root-absolute links (/docs/...) → resolved against repo root
  - same-page anchors (#foo) → checked against GitHub-style heading slugs
  - cross-file anchors (page.md#foo) → file existence + slug match
  - external http(s) URLs → checked only with --external (HEAD probe,
    fail-honest: network errors are reported, never silently passed)

Code fences (``` … ``` and ~~~ … ~~~) and inline code spans are stripped
before extraction, so fenced YAML/Python snippets never yield false links.

Usage:
  python3 scripts/ci/validate_md_links_seq04.py                    # whole repo
  python3 scripts/ci/validate_md_links_seq04.py README.md docs/    # selected paths
  python3 scripts/ci/validate_md_links_seq04.py --external         # + HEAD probes

Exit codes: 0 = zero dead links; 1 = at least one dead link (fail-closed).
Stdlib-only, zero runtime deps (mirrors boundary_sanitization_guard style).
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
FENCE_RE = re.compile(r"^(?:```|~~~)")


def strip_fences(text: str) -> str:
    out, inside = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line.strip()):
            inside = not inside
            out.append("")
            continue
        out.append("" if inside else line)
    return "\n".join(out)


def strip_inline_code(text: str) -> str:
    return re.sub(r"`[^`]*`", "", text)


def github_slug(heading: str) -> str:
    text = unicodedata.normalize("NFKD", heading).strip().lower()
    kept = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in (" ", "-", "_"):
            kept.append(" " if ch == " " else ch)
        elif cat.startswith(("L", "N", "M")):  # unicode letters/numbers/marks
            kept.append(ch)
        # punctuation (P*), symbols (S*), control → dropped, like GitHub
    slug = "".join(kept).replace(" ", "-")
    return slug


def headings_of(md_text: str) -> set[str]:
    slugs = set()
    in_fence = False
    for line in md_text.splitlines():
        if FENCE_RE.match(line.strip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            slugs.add(github_slug(m.group(2)))
    return slugs


def classify(target: str) -> str:
    if target.startswith("mailto:"):
        return "skip"
    if re.match(r"^https?://", target):
        return "external"
    return "local"


def check_file(path: Path, repo_root: Path, external: bool, report: list[str]) -> int:
    raw = path.read_text(encoding="utf-8", errors="replace")
    body = strip_inline_code(strip_fences(raw))
    slugs = headings_of(raw)
    dead = 0
    base = path.parent

    for m in LINK_RE.finditer(body):
        target = m.group(1).strip()
        kind = classify(target)
        if kind == "skip":
            continue
        if kind == "external":
            if not external:
                continue
            ok = head_ok(target)
            if not ok:
                dead += 1
                report.append(f"DEAD external  {path}: {target}")
            continue

        fragment = None
        if "#" in target:
            target, frag = target.split("#", 1)
            fragment = frag or None

        if target:
            resolved = (repo_root / target.lstrip("/")) if target.startswith("/") else (base / target)
            if not resolved.exists():
                dead += 1
                report.append(f"DEAD file      {path}: {target}")
                continue
            if fragment and resolved.suffix.lower() in (".md", ".markdown"):
                tgt_slugs = headings_of(resolved.read_text(encoding="utf-8", errors="replace"))
                if fragment not in tgt_slugs:
                    dead += 1
                    report.append(f"DEAD anchor    {path}: {target}#{fragment}")
        else:
            if fragment and fragment not in slugs:
                dead += 1
                report.append(f"DEAD anchor    {path}: #{fragment}")
    return dead


def head_ok(url: str, timeout: int = 12) -> bool:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "link-validator/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 400
    except Exception:
        try:  # some hosts reject HEAD → retry GET
            req2 = urllib.request.Request(url, headers={"User-Agent": "link-validator/1.0"})
            with urllib.request.urlopen(req2, timeout=timeout) as resp:
                return resp.status < 400
        except Exception:
            return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*", default=None, help="files or dirs (default: repo root)")
    ap.add_argument("--external", action="store_true", help="HEAD-probe external http(s) URLs")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    targets = [Path(p) for p in args.paths] if args.paths else [repo_root]

    files: list[Path] = []
    for t in targets:
        t = t.resolve()
        if t.is_dir():
            files.extend(sorted(p for p in t.rglob("*.md") if not p.is_dir()))
        elif t.suffix.lower() in (".md", ".markdown"):
            files.append(t)
    files = [f for f in files if ".git" not in f.parts and "node_modules" not in f.parts]

    report: list[str] = []
    checked = 0
    dead_total = 0
    for f in files:
        checked += 1
        dead_total += check_file(f, repo_root, args.external, report)

    print(f"validate_md_links_seq04: files={checked} dead_links={dead_total} external_probes={'on' if args.external else 'off'}")
    for line in report:
        print(line)
    return 1 if dead_total else 0


if __name__ == "__main__":
    sys.exit(main())
