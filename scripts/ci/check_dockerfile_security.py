#!/usr/bin/env python3
"""
check_dockerfile_security.py
============================
Audit tool to enforce non-root execution in all production Dockerfiles (Trap #97),
extended with the R47 base-image FROM-pin ratchet (issue #2084, radar lane R47).

Legacy check (Trap #97, unchanged semantics):
1. Dockerfile has a USER directive that is NOT 'root' or '0'.
2. USER directive is declared after package installations or setup.
3. Fails or warns if a container runs as root.

R47 FROM-pin plane (issue #2084, report-only by default):
    Every production base image in the tree is a mutable tag float
    (15 Dockerfiles / 20 FROM instructions / 0 digest pins at ccb6bb1,
    scout-verified live). A re-pushed upstream tag silently changes every
    deploy built from it, and no guard in the family read a FROM line before
    this check (check_dockerfile_security.py audited USER directives only).

    Classification per FROM image reference:
      digest   - name@sha256:<64hex>                      -> pinned (immutable)
      version  - tag starts with MAJOR.MINOR.PATCH         -> auditable pin (option C)
      float    - everything else (3.11-slim, 24-alpine,    -> unpinned
                 1.27-alpine, latest, no tag)

    Shrink-only ratchet (the #1796/#1829/#1913/#1969 doctrine):
      scripts/ci/dockerfile_from_baseline.json carries the KNOWN unpinned
      set, keyed by repo-relative path -> sorted image refs. Live unpinned
      references not present in the baseline are DRIFT. The baseline may
      only ever shrink; fixing a FROM shrinks its entry in the same change.

    Non-production surfaces are allowlisted and never audited (the #2084
    never-do note): docs/devcontainer/Dockerfile,
    core/ecosystem/Dockerfile.test.

    This check never edits a Dockerfile and never pre-computes digests
    (#2084 honesty note: implementers pin at build time; stale digests are
    worse than honest pointers).

Exit codes:
    0 = USER pass (or legacy usage) and, when --from-strict is given, no
        new unpinned FROM outside the baseline
    1 = USER violation (legacy path) or FROM ratchet drift (--from-strict)
    2 = usage error

Usage:
    python scripts/ci/check_dockerfile_security.py                 # legacy USER audit (unchanged)
    python scripts/ci/check_dockerfile_security.py --from-strict   # roster ratchet mode (R47)
    python scripts/ci/check_dockerfile_security.py --from-baseline # regenerate the floor
    python scripts/ci/check_dockerfile_security.py --json          # machine report (both planes)
    python scripts/ci/check_dockerfile_security.py --self-test     # hermetic proof, no repo writes
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_TAG = "[from-pin-guard]"
BASELINE_PATH = Path("scripts/ci/dockerfile_from_baseline.json")

FROM_ALLOWLIST_PREFIXES = (
    "docs/devcontainer/",          # non-prod dev image (#2084 never-do note)
    "core/ecosystem/Dockerfile.test",  # non-prod test image (#2084 never-do note)
)

FROM_RE = re.compile(r"^FROM\s+(.+)$", re.IGNORECASE)
DIGEST_RE = re.compile(r"@sha256:[0-9a-fA-F]{64}$")
VERSION_TAG_RE = re.compile(r":\s*(\d+\.\d+\.\d+)")  # option C: MAJOR.MINOR.PATCH leading tag

EXIT_OK = 0
EXIT_VIOLATION = 1
EXIT_USAGE = 2


def find_dockerfiles(root: Path) -> list[Path]:
    dockerfiles = []
    for p in root.rglob("*Dockerfile*"):
        # Ignore test-runners, temporary files, python scripts or virtual environments
        if any(part.startswith(".") or part in ("node_modules", ".venv", "venv") for part in p.parts):
            continue
        if p.suffix in (".py", ".sh", ".md", ".json", ".swp", ".bak", ".tmp"):
            continue
        if p.is_file() and ("dockerfile" in p.name.lower()):
            dockerfiles.append(p)
    return dockerfiles


def is_allowlisted(rel: str) -> bool:
    return any(rel == pref or rel.startswith(pref) for pref in FROM_ALLOWLIST_PREFIXES)


def parse_froms(content: str) -> list[tuple[int, str]]:
    """Return (line_no, image_ref) for every FROM instruction.

    Tolerates build flags (FROM --platform=...), multi-stage
    (FROM x AS y) and comment lines; image_ref is the first non-flag token.
    """
    out: list[tuple[int, str]] = []
    for idx, line in enumerate(content.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        m = FROM_RE.match(stripped)
        if not m:
            continue
        tokens = [t for t in m.group(1).split() if not t.startswith("--")]
        if not tokens:
            continue
        out.append((idx, tokens[0]))
    return out


def classify_image(image_ref: str) -> str:
    """digest | version | float (see module docstring)."""
    if DIGEST_RE.search(image_ref):
        return "digest"
    if VERSION_TAG_RE.search(image_ref):
        return "version"
    return "float"


def check_dockerfile(dockerfile: Path) -> list[str]:
    issues = []
    content = dockerfile.read_text(encoding="utf-8", errors="ignore")
    lines = content.splitlines()

    user_instructions = []
    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        # Match USER instruction
        match = re.match(r"^USER\s+([^\s]+)", stripped, re.IGNORECASE)
        if match:
            user_instructions.append((idx, match.group(1).strip()))

    if not user_instructions:
        issues.append(f"Missing USER directive in {dockerfile.relative_to(REPO_ROOT)}. Container runs as root by default!")
    else:
        last_line_num, last_user = user_instructions[-1]
        if last_user.lower() in ("root", "0"):
            issues.append(
                f"Dockerfile {dockerfile.relative_to(REPO_ROOT)} specifies USER '{last_user}' on line {last_line_num}. Containers must run as non-root!"
            )

    return issues


def collect_from_surface(dockerfiles: list[Path]) -> dict[str, dict]:
    """Live FROM surface, allowlist applied.

    Returns {rel_path: {"froms": [(line, ref, class)], "unpinned": sorted refs}}.
    """
    surface: dict[str, dict] = {}
    for df in sorted(dockerfiles):
        rel = str(df.relative_to(REPO_ROOT))
        if is_allowlisted(rel):
            continue
        content = df.read_text(encoding="utf-8", errors="ignore")
        froms = parse_froms(content)
        classified = [(ln, ref, classify_image(ref)) for ln, ref in froms]
        unpinned = sorted({ref for _, ref, cls in classified if cls == "float"})
        surface[rel] = {"froms": classified, "unpinned": unpinned}
    return surface


def load_baseline() -> dict[str, list[str]]:
    if not BASELINE_PATH.exists():
        return {}
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data.get("unpinned_froms", {})


def run_from_ratchet(dockerfiles: list[Path], *, json_out: bool) -> int:
    """R47 ratchet: drift = live unpinned refs outside the shrink-only baseline."""
    surface = collect_from_surface(dockerfiles)
    baseline = load_baseline()

    live = {rel: info["unpinned"] for rel, info in surface.items() if info["unpinned"]}

    drift: dict[str, list[str]] = {}
    for rel, refs in sorted(live.items()):
        known = set(baseline.get(rel, []))
        new = sorted(set(refs) - known)
        if new:
            drift[rel] = new

    shrunk: list[str] = []
    for rel, refs in sorted(baseline.items()):
        now = set(live.get(rel, []))
        fixed = sorted(set(refs) - now)
        if fixed:
            shrunk.append(f"{rel}: {fixed}")

    total_live = sum(len(v) for v in live.values())
    if json_out:
        print(json.dumps({
            "guard": "from-pin",
            "baseline_file": str(BASELINE_PATH),
            "live_unpinned_files": len(live),
            "live_unpinned_refs": total_live,
            "drift": drift,
            "shrinkable": shrunk,
            "verdict": "DRIFT" if drift else "COMPLIANT",
        }, indent=1))
    else:
        print(f"{GUARD_TAG} R47 FROM-pin ratchet over {len(surface)} production Dockerfile(s)")
        print(f"{GUARD_TAG} live unpinned refs: {total_live} across {len(live)} file(s); baseline: {sum(len(v) for v in baseline.values())} refs")
        for rel, info in surface.items():
            for ln, ref, cls in info["froms"]:
                mark = "PIN" if cls != "float" else "float"
                print(f"{GUARD_TAG}   [{mark:>5}] {rel}:{ln} {ref}")
        if shrunk:
            print(f"{GUARD_TAG} baseline shrink available (fix and regenerate in the same change):")
            for s in shrunk:
                print(f"{GUARD_TAG}   - {s}")
        if drift:
            print(f"{GUARD_TAG} DRIFT: {sum(len(v) for v in drift.values())} new unpinned FROM ref(s) not in the baseline:")
            for rel, refs in drift.items():
                print(f"{GUARD_TAG}   + {rel}: {refs}")
            print(f"{GUARD_TAG} fix by digest/full-version pinning the new FROM(s), or extend the baseline only for non-prod surfaces")
            return EXIT_VIOLATION
        print(f"{GUARD_TAG} COMPLIANT: no unpinned FROM outside the shrink-only baseline")
    return EXIT_OK


def regenerate_baseline(dockerfiles: list[Path]) -> int:
    surface = collect_from_surface(dockerfiles)
    live = {rel: info["unpinned"] for rel, info in surface.items() if info["unpinned"]}
    doc = {
        "_comment": (
            "R47 FROM-pin baseline (shrink-only ratchet, #2084). Known unpinned base-image "
            "refs per production Dockerfile. Never grows automatically: new unpinned refs "
            "fail --from-strict. Shrink entries in the same change that pins the FROM. "
            "Non-prod surfaces (docs/devcontainer/, core/ecosystem/Dockerfile.test) are "
            "allowlisted, never audited."
        ),
        "unpinned_froms": dict(sorted(live.items())),
    }
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"{GUARD_TAG} baseline written: {BASELINE_PATH} ({sum(len(v) for v in live.values())} refs / {len(live)} files)")
    return EXIT_OK


def self_test() -> int:
    """Hermetic proof: classification, parsing, ratchet polarity. No repo writes."""
    tmp = Path(tempfile.mkdtemp(prefix="frompin-selftest-"))
    checks: list[tuple[str, bool]] = []

    # 1. classification
    checks.append(("digest classified", classify_image("python:3.11-slim@sha256:" + "a" * 64) == "digest"))
    checks.append(("full version classified", classify_image("python:3.11.14-slim") == "version"))
    checks.append(("float classified", classify_image("python:3.11-slim") == "float"))
    checks.append(("latest classified", classify_image("node:latest") == "float"))
    checks.append(("bare name classified", classify_image("alpine") == "float"))

    # 2. parsing: flags, aliases, comments
    content = "\n".join([
        "# FROM python:3.9 (a comment, ignored)",
        "FROM --platform=linux/amd64 python:3.11-slim AS builder",
        "FROM python:3.11.14-slim",
        "FROM node:24-alpine AS runtime",
    ])
    froms = parse_froms(content)
    checks.append(("comment skipped", len(froms) == 3))
    checks.append(("flag stripped", froms[0][1] == "python:3.11-slim"))
    checks.append(("alias tolerated", froms[2][1] == "node:24-alpine"))

    # 3. allowlist routing
    checks.append(("devcontainer allowlisted", is_allowlisted("docs/devcontainer/Dockerfile")))
    checks.append(("test image allowlisted", is_allowlisted("core/ecosystem/Dockerfile.test")))
    checks.append(("prod NOT allowlisted", not is_allowlisted("gateway/Dockerfile")))

    # 4. ratchet polarity via the module's pure functions (no repo-root coupling)
    prod_content = "FROM python:3.11-slim\nUSER app\n"
    froms = parse_froms(prod_content)
    unpinned = sorted({ref for _, ref in froms if classify_image(ref) == "float"})
    checks.append(("prod float detected", unpinned == ["python:3.11-slim"]))

    baseline = {"svc/Dockerfile": ["python:3.11-slim"]}
    live = {"svc/Dockerfile": unpinned}
    drift = {rel: sorted(set(refs) - set(baseline.get(rel, []))) for rel, refs in live.items()}
    drift = {k: v for k, v in drift.items() if v}
    checks.append(("baselined ref -> no drift", not drift))

    new_content = "FROM python:3.12-slim\nUSER app\n"
    unpinned2 = sorted({ref for _, ref in parse_froms(new_content) if classify_image(ref) == "float"})
    live2 = {"svc/Dockerfile": unpinned2}
    drift2 = {rel: sorted(set(refs) - set(baseline.get(rel, []))) for rel, refs in live2.items()}
    drift2 = {k: v for k, v in drift2.items() if v}
    checks.append(("new ref -> DRIFT", drift2.get("svc/Dockerfile") == ["python:3.12-slim"]))

    ok = all(passed for _, passed in checks)
    for name, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {name}")
    print(f"self-test: {sum(p for _, p in checks)}/{len(checks)}")
    return EXIT_OK if ok else EXIT_VIOLATION


def main(argv: list[str] | None = None) -> int:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Dockerfile non-root audit (Trap #97) + R47 FROM-pin ratchet")
    parser.add_argument("--from-strict", action="store_true",
                        help="ratchet mode: exit 1 on unpinned FROM refs outside the baseline (roster)")
    parser.add_argument("--from-baseline", action="store_true",
                        help="regenerate the shrink-only baseline from the live surface")
    parser.add_argument("--json", action="store_true", help="machine-readable report (with --from-strict)")
    parser.add_argument("--self-test", action="store_true", help="hermetic detector proof, no repo writes")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    dockerfiles = find_dockerfiles(REPO_ROOT)
    if not dockerfiles:
        print("[INFO] No Dockerfiles found to inspect.")
        return 0

    if args.from_baseline:
        return regenerate_baseline(dockerfiles)

    if args.from_strict:
        return run_from_ratchet(dockerfiles, json_out=args.json)

    # Legacy path (unchanged): USER audit; FROM plane reported informationally only.
    print(f"Auditing {len(dockerfiles)} Dockerfile(s) for non-root USER compliance (Trap #97)...")
    all_issues = []
    for df in sorted(dockerfiles):
        issues = check_dockerfile(df)
        if issues:
            for issue in issues:
                print(f"[FAIL] {issue}")
                all_issues.append(issue)
        else:
            print(f"[PASS] {df.relative_to(REPO_ROOT)}")

    # R47 informational plane: never affects the legacy exit code.
    surface = collect_from_surface(dockerfiles)
    floats = {rel: info["unpinned"] for rel, info in surface.items() if info["unpinned"]}
    total = sum(len(v) for v in floats.values())
    if total:
        print(f"\n[INFO] R47 FROM-pin plane (report-only, run --from-strict for the ratchet): "
              f"{total} float-tag base image(s) across {len(floats)} Dockerfile(s); "
              f"0 digest pins fleet-wide as of the #2084 sweep.")

    if all_issues:
        print(f"\nTotal violations found: {len(all_issues)}")
        return 1

    print("\nAll Dockerfiles enforce non-root USER compliance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
