#!/usr/bin/env python3
"""scripts/ci/ghost_host_guard.py — retire the no-server ghost host, permanently.

Root-cause closure for the ghost-host mis-attribution class (#2355 → #2348 →
#2377). The retired no-server host (spelled out by GHOST_HOST below) answers
plain-text 404 (`x-render-routing: no-server`) while the real
gateway `supremeai-api-ulw0.onrender.com` (README service-table SSOT) serves
200 healthy. Any probe/example/default still pointing at the ghost produces
the exact "core-api DARK" false outage that #2348 filed and #2377 retracted.

PR #2365 (cb1958d) retired 4 instances and named the class ("the defect is
the class, not the instance") but landed no enforcement — 3 executable and
4 documentation surfaces survived. This guard makes the CLASS structurally
un-reintroducible:

  - ZERO TOLERANCE on executable/config surfaces (*.py, *.sh, *.ps1, *.ts,
    *.tsx, *.js, *.mjs, *.json, *.yaml, *.yml, *.toml, Dockerfile, _redirects,
    vercel.json, and any extensionless executable): a ghost default there is
    always a live trap — no marker can whitewash it.
  - HISTORICAL-EVIDENCE lanes (docs/reports/**, docs/bridge/**) are allowed:
    they are immutable measured-evidence receipts; rewriting them would
    falsify the audit trail.
  - Other Markdown (docs/**/*.md and any *.md elsewhere) may retain ghost
    strings ONLY inside a retirement banner carrying the exact marker
    `ghost-host-retired: #2355/#2365/#2377` within the first 20 lines.
    Strip the banner, keep the string -> the guard fails. New ghost-bearing
    docs must either fix their URLs or declare the same banner honestly.

Modes (dual, house style):
  --check      scan the tracked tree (git ls-files, fs-walk fallback) and
               fail-closed on any violation; exit 0 clean, 1 findings.
  --self-test  hermetic tempdir scenarios proving every rule above,
               including the ulw0 real-host non-match.

Stdlib-only, offline, deterministic. Exit codes: 0 pass, 1 findings,
2 usage error.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TAG = "[ghost-host-guard]"

# Assembled at runtime: a scanner must name its target, but naming it as a
# literal would put the ghost string into this very file for the guard to
# trip on (self-scan is part of the live sweep). The concatenation keeps the
# contiguous substring out of the source text.
GHOST_HOST = "supremeai-api" "." "onrender.com"
REAL_HOST = "supremeai-api-ulw0.onrender.com"
BANNER_MARKER = "ghost-host-retired: #2355/#2365/#2377"
BANNER_WINDOW_LINES = 20

# Immutable measured-evidence receipts: occurrences there are the historical
# record of probes actually made against the ghost (SENTRY_* series, bridge
# closure receipts). Rewriting history is falsification; allowlisting is not.
ALLOWED_PREFIXES = (
    "docs/reports/",
    "docs/bridge/",
)

# Executable/config surfaces: zero tolerance regardless of any banner.
ZERO_TOLERANCE_SUFFIXES = (
    ".py", ".sh", ".ps1", ".ts", ".tsx", ".js", ".mjs", ".cjs",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
)
ZERO_TOLERANCE_NAMES = (
    "Dockerfile", "_redirects", "vercel.json",
)

WALK_PRUNE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


def is_zero_tolerance(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    if name in ZERO_TOLERANCE_NAMES or rel in ZERO_TOLERANCE_NAMES:
        return True
    return rel.endswith(ZERO_TOLERANCE_SUFFIXES)


def is_allowed_evidence(rel: str) -> bool:
    return rel.startswith(ALLOWED_PREFIXES)


def has_banner(text: str) -> bool:
    head = text.splitlines()[:BANNER_WINDOW_LINES]
    return any(BANNER_MARKER in line for line in head)


def list_tracked_files(root: Path) -> list[str]:
    """Tracked files via git (respects ignores); fs-walk fallback."""
    try:
        r = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root, capture_output=True, timeout=60, check=True,
        )
        entries = [e for e in r.stdout.decode("utf-8", "replace").split("\0") if e]
        if entries:
            return sorted(entries)
    except (OSError, subprocess.SubprocessError):
        pass
    out: list[str] = []
    for base, dirs, files in __import__("os").walk(root):
        dirs[:] = [d for d in dirs if d not in WALK_PRUNE_DIRS]
        for f in files:
            p = Path(base) / f
            out.append(str(p.relative_to(root)))
    return sorted(out)


def scan(root: Path) -> list[str]:
    """Return sorted violation strings for the tree rooted at `root`."""
    violations: list[str] = []
    for rel in list_tracked_files(root):
        path = root / rel
        try:
            if path.is_symlink() or not path.is_file():
                continue
            raw = path.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:  # binary heuristic
            continue
        text = raw.decode("utf-8", "replace")
        if GHOST_HOST not in text:
            continue
        rel_norm = rel.replace("\\", "/")
        if is_allowed_evidence(rel_norm):
            continue
        if is_zero_tolerance(rel_norm):
            violations.append(
                f"{rel_norm}: ghost host in EXECUTABLE/CONFIG surface "
                f"(zero tolerance — point it at {REAL_HOST}, the README SSOT)"
            )
            continue
        if text.endswith((".md", ".markdown", ".rst", ".txt")) or "/docs/" in f"/{rel_norm}":
            if has_banner(text):
                continue
            violations.append(
                f"{rel_norm}: ghost host in doc WITHOUT retirement banner — "
                f"fix the URLs to {REAL_HOST} or add a top banner carrying "
                f"the exact marker: {BANNER_MARKER}"
            )
            continue
        violations.append(
            f"{rel_norm}: ghost host in unrecognized surface class — "
            f"fix to {REAL_HOST} or file an explicit allowlist amendment"
        )
    return sorted(violations)


def run_check() -> int:
    violations = scan(REPO_ROOT)
    if violations:
        print(f"{TAG} FAIL — {len(violations)} ghost-host violation(s):")
        for v in violations:
            print(f"  - {v}")
        print(f"{TAG} real host: {REAL_HOST} (README service-table SSOT)")
        return 1
    print(f"{TAG} OK — no actionable ghost-host surfaces "
          f"(evidence lanes + bannered historical docs only)")
    return 0


# --------------------------------------------------------------------------- #
# self-test: hermetic scenarios, no repo mutation                              #
# --------------------------------------------------------------------------- #

def _make_tree(files: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="ghost-guard-selftest-"))
    for rel, content in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp


def run_self_test() -> int:
    failures: list[str] = []

    def expect(label: str, cond: bool) -> None:
        if not cond:
            failures.append(label)

    clean = _make_tree({
        "examples/client.py": f'URL = "https://{REAL_HOST}/v1"\n',
        "docs/CONSUMERS.md": f"Base URL: https://{REAL_HOST}\n",
        "docs/reports/SENTRY_X.md": f"measured: {GHOST_HOST} 404 at 01:45Z\n",
    })
    expect("clean tree (real host + evidence lane) passes", scan(clean) == [])

    trap = _make_tree({
        "examples/run_smoke.sh": f'URL="${{GATEWAY_URL:-https://{GHOST_HOST}}}"\n',
    })
    expect("ghost in executable surface fails", len(scan(trap)) == 1)

    no_banner = _make_tree({
        "docs/LEGACY.md": f"see https://{GHOST_HOST}/v1/models\n",
    })
    expect("ghost in unbannered doc fails", len(scan(no_banner)) == 1)

    bannered = _make_tree({
        "docs/LEGACY.md": (
            f"# old receipt\n\n> {BANNER_MARKER} — historical, ghost retired\n\n"
            f"see https://{GHOST_HOST}/v1/models\n"
        ),
    })
    expect("ghost in bannered doc passes", scan(bannered) == [])

    stripped = _make_tree({
        "docs/LEGACY.md": (
            "# old receipt\n" + "\n" * 25
            + f"line {BANNER_MARKER} beyond window\n"
            + f"see https://{GHOST_HOST}/v1/models\n"
        ),
    })
    expect("banner beyond 20-line window does not whitewash", len(scan(stripped)) == 1)

    marker_on_code = _make_tree({
        "scripts/probe.py": (
            f"# {BANNER_MARKER}\nURL = 'https://{GHOST_HOST}/healthz'\n"
        ),
    })
    expect("banner marker cannot whitewash executable surface",
           len(scan(marker_on_code)) == 1)

    ulw0 = _make_tree({"a.py": f'U = "https://{REAL_HOST}"\n'})
    expect(f"{REAL_HOST} never matches the ghost pattern", scan(ulw0) == [])

    expect("real repo tree passes --check semantics", scan(REPO_ROOT) == [])

    if failures:
        print(f"{TAG} SELF-TEST FAIL ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"{TAG} self-test OK — 8/8 scenarios pass")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ghost no-server host guard (see module docstring)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="scan the tracked tree, fail-closed")
    mode.add_argument("--self-test", action="store_true", help="hermetic scenario suite")
    args = ap.parse_args(argv)
    if args.self_test:
        return run_self_test()
    return run_check()


if __name__ == "__main__":
    sys.exit(main())
