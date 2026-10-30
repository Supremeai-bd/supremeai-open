#!/usr/bin/env python3
"""constitution_pointer_guard.py — dead-authority-pointer guard (#1642).

AGENT_RULES.md — the former constitution — was deleted by PR #1526 (Single
Door SSOT consolidated into AGENTS.md). 55+ tracked files kept citing the
deleted file: live code read it at runtime (agent_runner.step_rules,
skill_bundle.seed_from_canonical), docs linked to it, routing tables routed
it. A citation to a non-existent authority file is either a dead-end for an
agent resolving policy (broken autonomy) or an invitation to "helpfully"
re-create the deleted constitution — the exact revert-shape
docs/AUDIT_2026-10-28.md warns against (F2).

This guard fails closed on any NEW citation of a constitutionally-deleted
path outside the reviewed ALLOWLIST below. The allowlist is explicit and
reasoned: historical records (audits, ADRs, loop comments documenting the
deletion itself), admin-owned protected paths (.github/), mirror-parity
files, and an enumerated docs debt list to be swept by a fast-follow work
order (30-file bridge cap forces the two-slice split).

Doctrine (single paragraph form):
  1. AGENTS.md is the Single Door SSOT; citations must resolve to live
     tracked files (git ls-files), never to a deleted twin.
  2. Historical mentions (audits, ADRs, deletion-documentation) are legal
     ONLY inside this file's reviewed allowlist — the list is the ratchet.
  3. The allowlist must track reality: a stale allowlist entry (file no
     longer tracked) fails the guard — no ghost entries.

Regex precision (why stem-level matching): `\\bAGENT_RULES\\b` matches
"AGENT_RULES.md", "AGENT_RULES §6", "AGENT_RULES U4" but NOT
"AGENT_RULES_PATH" (underscore is a word char → no boundary) and NOT
"agent_rules.json" (case-sensitive). Those name a live config file
(config/agent_rules.json) — a different surface, deliberately out of class.

Exit codes: 0 = clean (allowlisted mentions allowed) · 1 = violations ·
2 = usage/scan error (fail-closed on scan failure, never fail-open).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Constitutionally-deleted paths. Each entry: (dead_path, citation_regex, why_dead)
DEAD_CONSTITUTION_PATHS: tuple[tuple[str, str, str], ...] = (
    (
        "AGENT_RULES.md",
        r"\bAGENT_RULES\b",
        "deleted by PR #1526 — Single Door SSOT consolidated into AGENTS.md",
    ),
)

# Reviewed allowlist — every entry needs a reason. Structured as
# {relative_path: (class, reason)}. Classes:
#   historical    — documents/logs the deletion era itself; rewriting history
#                   would falsify the record (U2 Truth & Evidence)
#   protected     — admin-owned .github/ paths (bridge contract: admin review)
#   mirror-parity — byte-parity mirrors of private-repo files; the private
#                   twin carries the same historical text
#   enforcement   — this guard and its test: their citations ARE the dead-path
#                   registry definitions (pattern source, not drift)
#   debt          — live stale pointer, enumerated for the fast-follow docs
#                   sweep WO (30-file cap split of #1642); enforced-against-
#                   growth ratchet: new files may never join this class
ALLOWLIST: dict[str, tuple[str, str]] = {
    # -- enforcement: the registry source itself ----------------------------
    "scripts/ci/constitution_pointer_guard.py": (
        "enforcement",
        "defines DEAD_CONSTITUTION_PATHS + ALLOWLIST; citations are pattern definitions",
    ),
    "tests/test_constitution_pointer_guard.py": (
        "enforcement",
        "pins the guard contract with fixture citations",
    ),
    # -- enforcement: R42 interop consumers (#2031) --------------------------
    # The docs-link-integrity lane does NOT cite the deleted file as authority;
    # it ROUTES those ghost citations to this guard: EXCLUDED_TARGET_SUBSTR
    # declares the exclusion pattern, the baseline JSON is the machine-readable
    # debt ledger (10 knownExcluded), and the tests pin that contract. Their
    # citations are pattern/contract definitions, not drift — same class as
    # this guard's own registry source.
    "scripts/ci/docs_link_integrity_guard.py": (
        "enforcement",
        "R42 gate (#2031): EXCLUDED_TARGET_SUBSTR routes AGENT_RULES.md ghost citations to THIS guard's debt class (#1642->#1708); the citation is the interop routing definition, not drift",
    ),
    ".githooks/pre-push": (
        "enforcement",
        "R42 gate wiring (#2031, section 15): comment documents that AGENT_RULES.md ghost citations are excluded debt owned by THIS guard (#1642->#1708)",
    ),
    "scripts/ci/docs_link_integrity_baseline.json": (
        "enforcement",
        "R42 baseline (#2031): knownExcluded is the machine-readable ledger of the 10 AGENT_RULES.md ghost entries this guard owns (#1642->#1708)",
    ),
    "tests/test_docs_link_integrity_guard.py": (
        "enforcement",
        "R42 gate tests (#2031): fixture + knownExcluded==10 assertion pin the ghost-debt routing contract",
    ),
    # -- historical: the deletion is documented here BY DESIGN --------------
    "scripts/agents/continuous_agent_loop.py": (
        "historical",
        "documents the #1526 deletion inside the freshness-gate skip logic",
    ),
    "core/runner/agent_runner.py": (
        "historical",
        "step_rules comment records the #1526 re-point (#1642)",
    ),
    "scripts/agents/skill_bundle.py": (
        "historical",
        "seed comment records the #1526 re-point (#1642)",
    ),
    "scripts/ci/boundary_sanitization_guard.py": (
        "historical",
        "anti-revert note explains why the root file is not approved (#1642)",
    ),
    "scripts/ci/hourly_satellite_batcher.py": (
        "historical",
        "quarantine pin asserts the deleted file stays unrouted (#1642)",
    ),
    "README.md": (
        "historical",
        "one line records 'the former AGENT_RULES.md was deleted by #1526'",
    ),
    "tests/test_constitution_freshness.py": (
        "historical",
        "pins the deleted-file freshness-gate behavior (#1526 contract)",
    ),
    "core/github/scripts/constitution/freshness_gate.py": (
        "mirror-parity",
        "private .github/scripts twin; 2026-10-01 incident record",
    ),
    "core/github/scripts/constitution/template_gate.py": (
        "mirror-parity",
        "private .github/scripts twin; historical template contract note",
    ),
    "scripts/agents/instruction_builder.py": (
        "historical",
        "documents the drift discovery that motivated the SSOT consolidation",
    ),
    "docs/AGENT_LOOP_SPEC.md": (
        "historical",
        "one line records 'the former AGENT_RULES.md was deleted by #1526'",
    ),
    # -- protected: admin-owned .github/ ------------------------------------
    ".github/ISSUE_TEMPLATE/auditor-rule-breaker-report.yml": (
        "protected",
        "admin-owned issue template (bridge contract: admin review)",
    ),
    ".github/ISSUE_TEMPLATE/feature-request.yml": (
        "protected",
        "admin-owned issue template (bridge contract: admin review)",
    ),
    ".github/workflows/pipeline.yml": (
        "protected",
        "admin-owned workflow (bridge contract: admin review)",
    ),
    # -- debt: live stale pointers, enumerated for the fast-follow sweep ----
    # বাংলা (#3524-অভিঘাত, 2026-10-31): #3524-এর archive-migration 473টি doc
    # supremeai-archive-এ সরিয়েছে; সেই ২৩টি এন্ট্রি এখানে ghost ছিল (untracked) —
    # guard-এর নিজের self-test অদ্রব্য ("shipped ALLOWLIST has no stale entries")
    # সেগুলোর অপসারণ বাধ্য করে। debt-র‍্যাচেট অক্ষত: নতুন ফাইল কখনো এই শ্রেণিতে
    # যুক্ত হবে না; docs/AUTONOMY_LOOP_CONTRACT.md থাকছে (98e5815-এ পুনঃট্র্যাক্টেড,
    # এখনও live debt)। ভবিষ্যৎ bulk-move-এর শিক্ষা: migration-এর সাথে cross-guard
    # registry sync আবশ্যক (de2c051 parity-guard collateral-এর একই শ্রেণি)।
    "docs/AUTONOMY_LOOP_CONTRACT.md": (
        "debt",
        "docs sweep WO-2: related-docs lists + §47 authority pointer",
    ),
}


def _compile_patterns() -> list[tuple[str, re.Pattern[str], str]]:
    return [
        (dead_path, re.compile(regex), why)
        for dead_path, regex, why in DEAD_CONSTITUTION_PATHS
    ]


def tracked_files(repo_root: Path) -> list[str]:
    """git ls-files — the tracked universe the guard scans (fail-closed)."""
    proc = subprocess.run(  # noqa: S603
        ["git", "ls-files", "-z"],
        cwd=str(repo_root),
        capture_output=True,
        timeout=30,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git ls-files failed (exit {proc.returncode}): "
            f"{proc.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return [p for p in proc.stdout.decode("utf-8", errors="replace").split("\0") if p]


def scan_tree(
    repo_root: Path,
    files: list[str],
    patterns: list[tuple[str, re.Pattern[str], str]] | None = None,
    allowlist: dict[str, tuple[str, str]] | None = None,
) -> tuple[list[dict], list[str]]:
    """Scan tracked files for dead-path citations outside the allowlist.

    Returns (violations, stale_allowlist_entries). Violations are dicts with
    file/line/dead_path/why/text. Binary files and unreadable entries are
    skipped silently only if the OS reports them absent from disk (tracked
    but deleted working-tree copies); read errors on present files fail the
    scan loudly (honesty over availability).
    """
    patterns = patterns if patterns is not None else _compile_patterns()
    allow = allowlist if allowlist is not None else ALLOWLIST
    violations: list[dict] = []
    stale: list[str] = []
    tracked_set = set(files)

    for path in allow:
        if path not in tracked_set:
            stale.append(path)

    for rel in files:
        if rel in allow:
            continue
        abs_path = repo_root / rel
        if not abs_path.is_file():
            continue  # tracked but absent in working tree (CI checkout edge)
        try:
            blob = abs_path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"unreadable tracked file {rel}: {exc}") from exc
        if b"\x00" in blob:
            continue  # binary — textual citation class only
        text = blob.decode("utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for dead_path, regex, why in patterns:
                if regex.search(line):
                    violations.append(
                        {
                            "file": rel,
                            "line": lineno,
                            "dead_path": dead_path,
                            "why": why,
                            "text": line.strip()[:160],
                        }
                    )
    return violations, stale


def run(repo_root: Path) -> tuple[list[dict], list[str], list[str]]:
    files = tracked_files(repo_root)
    violations, stale = scan_tree(repo_root, files)
    return violations, stale, files


def self_test() -> bool:
    """Hermetic contract check — no network, no git, no repo mutation."""
    import tempfile

    patterns = _compile_patterns()
    ok = True

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        print(f"  [{'PASS' if cond else 'FAIL'}] {label}")
        if not cond:
            ok = False

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "clean.md").write_text(
            "# Governance\nSee AGENTS.md — the Single Door SSOT.\n", encoding="utf-8"
        )
        (root / "doc.md").write_text(
            "policy lives in AGENT_RULES.md §3\n", encoding="utf-8"
        )
        (root / "code.py").write_text(
            '# legacy comment: AGENT_RULES U4 doctrine\nx = "AGENT_RULES_PATH ok"\n'
            'y = "agent_rules.json ok"\n',
            encoding="utf-8",
        )
        (root / "allowed.md").write_text(
            "historical: AGENT_RULES.md was deleted\n", encoding="utf-8"
        )
        (root / "bin.dat").write_bytes(b"\x00\x01AGENT_RULES.md inside binary")
        files = ["clean.md", "doc.md", "code.py", "allowed.md", "bin.dat"]

        allow = {"allowed.md": ("historical", "test entry")}
        violations, stale = scan_tree(root, files, patterns, allow)

        check("clean file not flagged", not any(v["file"] == "clean.md" for v in violations))
        check("md citation flagged", any(
            v["file"] == "doc.md" and v["line"] == 1 for v in violations))
        check("py comment flagged", any(
            v["file"] == "code.py" and v["line"] == 1 for v in violations))
        check("AGENT_RULES_PATH not flagged (word-boundary)", not any(
            v["file"] == "code.py" and v["line"] == 2 for v in violations))
        check("agent_rules.json not flagged (case-sensitive)", not any(
            v["file"] == "code.py" and v["line"] == 3 for v in violations))
        check("binary skipped", not any(v["file"] == "bin.dat" for v in violations))
        check("allowlisted file skipped", not any(
            v["file"] == "allowed.md" for v in violations))
        check("dead_path reason carried", all(
            v["why"].startswith("deleted by PR #1526") for v in violations))
        check("violation count exact", len(violations) == 2)

        # stale allowlist detection
        _, stale2 = scan_tree(root, ["clean.md"], patterns, {"ghost.md": ("debt", "x")})
        check("stale allowlist entry detected", stale2 == ["ghost.md"])

        # allowlist carries no dead entries in the shipped configuration
        real_files = tracked_files(REPO_ROOT)
        _, shipped_stale = scan_tree(REPO_ROOT, real_files)
        check("shipped ALLOWLIST has no stale entries", not shipped_stale)

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail closed on citations of constitutionally-deleted paths (#1642)"
    )
    parser.add_argument("--self-test", action="store_true", help="hermetic contract check")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    if args.self_test:
        print("constitution_pointer_guard self-test:")
        return 0 if self_test() else 1

    try:
        violations, stale, files = run(REPO_ROOT)
    except RuntimeError as exc:
        print(f"SCAN ERROR (fail-closed): {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "scanned": len(files),
                    "violations": violations,
                    "stale_allowlist": stale,
                    "allowlist_size": len(ALLOWLIST),
                },
                indent=2,
            )
        )
        return 1 if violations or stale else 0

    print(
        f"Dead-authority-pointer guard — {len(files)} tracked files scanned, "
        f"allowlist {len(ALLOWLIST)} entries (doctrine #1642)"
    )
    if stale:
        print(f"STALE ALLOWLIST ({len(stale)}): allowlist drift — entries no longer tracked:")
        for path in stale:
            print(f"  {path}")
    if violations:
        print(f"VIOLATIONS ({len(violations)}): citations of deleted constitution paths:")
        for v in violations:
            print(f"  {v['file']}:{v['line']}: [{v['dead_path']}] {v['text']}")
        print("Fix: re-point to AGENTS.md (Single Door SSOT) or extend ALLOWLIST with a reason.")
        return 1
    if stale:
        return 1
    debt = sorted(p for p, (cls, _) in ALLOWLIST.items() if cls == "debt")
    print(f"clean — {len(debt)} enumerated debt entries pending the docs fast-follow sweep")
    return 0


if __name__ == "__main__":
    sys.exit(main())
