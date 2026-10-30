#!/usr/bin/env python3
"""
boundary_sanitization_guard.py — Public/Private Boundary & Proprietary Logic
Isolation Guard (#107, P0-critical, Layer 2 / infra-ops).

গার্ডের মিশন (বাংলা):
  supremeai-open হলো পাবলিক সারফেস। প্রোপ্রাইটারি ইন্টেলিজেন্স (supremeai-core
  decision moat, private vault keys, internal system prompts, production
  credentials) কখনোই এই repo-তে commit/leak হতে পারবে না। এই গার্ড fail-closed
  ভাবে সেই বাউন্ডারি enforce করে — শুধুমাত্র approved public contracts, client
  SDKs, schemas এবং generic agent loop runner এখানে থাকবে।

DESIGN PRINCIPLES
  - Fail-closed: unknown / unreadable / unparseable input => violation or
    operational error (exit 2). The guard NEVER silently passes on doubt.
  - Stdlib-only: runs anywhere python3 runs (no PyYAML, no network, no git
    writes). Boot-smoke-safe for the 3-tier verification contract.
  - Complements gitleaks (.gitleaks.toml covers generic secret shapes); this
    guard covers the PROPRIETARY-LOGIC and APPROVED-SURFACE layers that
    generic secret scanners structurally cannot express.
  - Detection rules are CALIBRATED against the live tree: every rule below was
    empirically dry-scanned against origin/main before landing so that
    legitimate code (masking regexes, env-var NAME plumbing, registry metadata,
    prose mentions of the private repo in docs) is NOT flagged.

MODES
  --check                 Full audit of every git-tracked file in the current
                          checkout (boot smoke test / final barrier).
  --files F [F...]        Scan exactly these paths (PR changed-files mode,
                          used by pipeline.yml on every pull request).
  --base SHA --head SHA   Scan files changed between two revisions
                          (git diff --name-only base..head).
  --self-test             Offline guard-the-guard fixtures: violations must be
                          caught, calibrated-legitimate content must pass.

EXIT CODES
  0  clean
  1  boundary violations found
  2  operational error / guard misused (fail-closed: never a pass)

APPROVING A NEW PUBLIC SURFACE
  The approved-surface registry lives in THIS file (single SSOT, no extra
  config file in scope). Expanding it is a conscious, reviewable act: edit
  APPROVED_* below via a PR that references the governing issue.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ---------------------------------------------------------------------------
# Approved public surface registry (SSOT — see module docstring)
# ---------------------------------------------------------------------------

APPROVED_TOP_LEVEL_DIRS = {
    ".github",
    ".githooks",  # issue #161: local ingress pre-push guard (poka-yoke, no runtime surface)
    ".agents",  # Agent workspace customizations (rules, skills, minimal-elegance)
    "api-schemas",
    "docs",
    "evals",  # Golden eval suite — 100-case AI quality benchmark + offline runner (issue #1362)
    "examples",
    "infrastructure",
    "scripts",
    # tests/ — approved for issue #45 (validate_schemas CLI test suite);
    # expansion per the process documented in this module's docstring:
    # registry changes ride a PR that references the governing issue.
    # Content-layer checks (PROPRIETARY-LOGIC scan) still apply to every
    # file under this surface — path approval never bypasses content rules.
    "tests",
    "patches",  # Federation bridge unified diff patches for target repositories
    "gateway",  # Federation bridge surface for Supremeai-bd/supremeai-api (issue #469)
    "command",  # Federation bridge surface for Supremeai-bd/supremeai-command (issue #505)
    "browser",  # Federation bridge surface for Supremeai-bd/supremeai-browser (issue #502)
    "sdk",  # Federation bridge surface for Supremeai-bd/supremeai-sdk (issue #510)
    "studio",  # Federation bridge surface for Supremeai-bd/supremeai-studio (issue #508)
    "skills",  # Federation bridge surface for Supremeai-bd/supremeai-skills (issue #503)
    "vscode",  # Federation bridge surface for Supremeai-bd/supremeai-vscode (issue #504)
    "core",  # Federation bridge surface for Supremeai-bd/supremeai-core (issue #507)
    "infra",  # Federation bridge surface for Supremeai-bd/supremeai-infrastructure (issue #509)
}

APPROVED_ROOT_FILES = {
    ".gitattributes",
    ".gitignore",
    ".gitleaks.toml",
    ".gitleaksignore",
    ".importlinter",  # import-contract gate config (issue 1791): repo-root TOML consumed by lint-imports; dev-only, no runtime surface
    ".pre-commit-config.yaml",
    "AGENTS.md",
    # "AGENT_RULES.md" deliberately NOT approved — deleted by #1526 (#1642);
    # keeping it here would invite re-creating the dead constitution at root.
    "AUTONOMOUS_TRANSIT_PIPELINE.md",
    "CONTRIBUTING.md",
    "ECOSYSTEM_MAP.md",
    "LICENSE",
    "README.md",
    "mcp.json",
    "requirements-dev.txt",  # dev/CI-only tooling pins (issue 1791): import-linter==2.15 for the .importlinter gate; nothing at runtime imports it
    "requirements-dev.lock",  # compiled lockfile for dev tooling pins (issue #1745 uv adoption)
    "ruff.toml",
}

# depth-2 granularity for dirs that host executable/config material;
# depth>=3 inherits approval from the depth-2 subtree.
APPROVED_SUBTREES = {
    # scripts/: agents/, ops/, ci/ are directory subtrees (ci/ added by #107).
    # "validate_schemas.py" is a FILE entry — the issue-#45 schema-validation
    # CLI lives at the issue's declared Touching-Files path (top level of
    # scripts/). Registry entries are second-level path segments; a file is
    # as valid a segment as a directory. Expansion per the process documented
    # in this module's docstring (PR references the governing issue #45).
    "scripts": {
        "agents",
        "ops",
        "ci",
        "tower",
        "bridge",
        "knowledge",
        "eval",  # feedback-to-eval + cost-per-task scripts (issue #1363, AIQ-090/AIQ-107)
        "validate_schemas.py",
    },
    ".github": {
        "ISSUE_TEMPLATE",
        "workflows",
        "actions",
        "PULL_REQUEST_TEMPLATE.md",
    },  # actions/ (reusable composite actions, #155 Federation Workflow Diet)
    "infrastructure": {
        "mcp-control-plane",
        "cloudflare-studio-proxy",
        # FILE entry (issue #1640): proprietary LICENSE notice at the mirror
        # surface root. Legal notices are boundary-neutral — license_ssot_guard
        # owns placement SSOT; PR #2510 adds these notices and its gate red
        # (run 40840030278, Boundary Sanitization Guard exit 1) is this
        # registry's omission, not a leak. Same FILE-entry precedent as
        # scripts/"validate_schemas.py" above.
        "LICENSE",
    },
}

# ---------------------------------------------------------------------------
# Layer 1 — PROPRIETARY PATH GUARD (a file must not LIVE in proprietary space)
# ---------------------------------------------------------------------------

PATH_RULES: list[tuple[str, str]] = [
    # (regex over the posix relpath, reason)
    (
        r"(^|/)\.env($|\.[^/]*$)",
        "dot-env file (only *.example/*.sample/*.template allowed)",
    ),
    (r"\.(pem|p12|pfx|jks|keystore|keytab)$", "private key / certificate store file"),
    (r"(^|/)id_(rsa|ed25519|ecdsa)(\..*)?$", "SSH private key file"),
    (r"(^|/)\.ssh/", "SSH material directory"),
    (r"(^|/)service-account[^/]*\.json$", "service-account credential file"),
    (
        r"(^|/)(vault|secrets?|credentials?|private-keys?)/",
        "credential/proprietary directory",
    ),
    (
        r"(^|/)(supremeai-core|packages/core|apps/core)(/|$)",
        "proprietary core module tree",
    ),
    (r"\.(sqlite3?|db)$", "database file"),
]

_ENV_ALLOWLIST_SUFFIX = re.compile(r"\.(example|sample|template)$", re.IGNORECASE)
_ENV_PATH = re.compile(r"(^|/)\.env($|\.[^/]*$)")

# ---------------------------------------------------------------------------
# Layer 2 — PROPRIETARY CONTENT GUARD (line-level, calibrated; see dry-scan)
# ---------------------------------------------------------------------------

# Assignment/value markers: flagged only with a CONCRETE value on the same
# line. Placeholder / reference values pass (secrets are allowed to be
# *referenced*; they are not allowed to be *embedded*).
_PLACEHOLDER_VALUE = re.compile(
    r"^(\s*|\$\{[^}]*\}|\$\{\{[^}]*\}\}|\$[A-Z_][A-Z0-9_]*|"
    r"<[^>]*>|x{3,}|\*{3,}|changeme|change-me|your[-_][-a-z0-9_]*|"
    r"example[-_][-a-z0-9_]*|placeholder|redacted|none|null|true|false|yes|no)\s*$",
    re.IGNORECASE,
)

_ASSIGNMENT_NAMES = (
    r"VAULT_TOKEN|VAULT_SECRET|VAULT_UNSEAL_KEY|VAULT_APPROLE_ID|"
    r"SUPABASE_SERVICE_ROLE_KEY|SUPREMEAI_CORE_TOKEN|BRIDGE_INTAKE_TOKEN|"
    r"PRIVATE_VAULT_KEY|MCP_TOWER_ADMIN_TOKEN"
)
_ASSIGNMENT = re.compile(rf"\b({_ASSIGNMENT_NAMES})\s*[:=]\s*(\S.*?)\s*$")

_CONTENT_MARKERS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"<system[_-]prompt>", re.IGNORECASE), "internal system prompt fence"),
    (
        re.compile(
            r"SYSTEM\s+PROMPT\s*[\u2014\u2013-]+\s*(INTERNAL|CONFIDENTIAL|PROPRIETARY|DO\s+NOT)",
            re.IGNORECASE,
        ),
        "internal system prompt banner",
    ),
    (
        re.compile(r"SUPREMEAI\s+CONFIDENTIAL", re.IGNORECASE),
        "proprietary confidentiality banner",
    ),
    (
        re.compile(
            r"INTERNAL\s*[\u2014\u2013-]+\s*DO\s+NOT\s+DISTRIBUTE", re.IGNORECASE
        ),
        "proprietary distribution banner",
    ),
    (
        re.compile(r"sb_secret_[A-Za-z0-9_\-]{10,}"),
        "Supabase service-role secret literal",
    ),
    (
        re.compile(
            r"(from\s+supremeai[_-]core[\s.]|import\s+supremeai[_-]core|['\"]supremeai-core/)"
        ),
        "proprietary supremeai-core module import",
    ),
]

# PEM private keys need a base64 BODY after the header — a bare header inside
# a masking regex (masking.ts) or prose is NOT key material.
_PEM_HEADER = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_PEM_BODY = re.compile(r"[A-Za-z0-9+/=]{60,}")

# Real credential shape in connection URLs: scheme://user:password@host
_DB_URL = re.compile(
    r"\b(?:postgres|postgresql|mysql|mongodb(?:\+srv)?)://[^\s:/@]+:[^\s@]+@",
    re.IGNORECASE,
)
_DB_URL_PLACEHOLDER = re.compile(
    r":\$\{[^}]*\}@|:\$\{\{[^}]*\}\}@|:(your|example|changeit|password|pass|user|xxx+)[^\s@]*@",
    re.IGNORECASE,
)


def _value_is_concrete(value: str) -> bool:
    """A value counts as leaked if it is non-empty and not a placeholder/ref."""
    stripped = value.strip().strip("\"'")
    if not stripped:
        return False
    return not _PLACEHOLDER_VALUE.match(stripped)


def _check_pem(lines: Sequence[str], header_idx: int) -> bool:
    """True if the PEM header is followed by base64 key body within 3 lines."""
    window = lines[header_idx + 1 : header_idx + 4]
    return any(_PEM_BODY.search(line) for line in window)


# ---------------------------------------------------------------------------
# Layer 3 — APPROVED SURFACE GUARD (only approved public surfaces reside here)
# ---------------------------------------------------------------------------


def surface_violation(rel_posix: str) -> str | None:
    top = rel_posix.split("/", 1)[0]
    if "/" not in rel_posix:
        if top in APPROVED_ROOT_FILES:
            return None
        return f"root file '{top}' is not in APPROVED_ROOT_FILES"
    if top not in APPROVED_TOP_LEVEL_DIRS:
        return f"top-level directory '{top}/' is not an approved public surface"
    second = rel_posix.split("/", 2)[1]
    allowed_subtrees = APPROVED_SUBTREES.get(top)
    if allowed_subtrees is not None and second not in allowed_subtrees:
        return f"'{top}/{second}/' is not an approved subtree under '{top}/'"
    return None


# ---------------------------------------------------------------------------
# Scanner core
# ---------------------------------------------------------------------------


def scan_file(repo_root: Path, rel: str) -> list[str]:
    """Return violation messages for one file (empty list = clean)."""
    findings: list[str] = []
    rel_posix = rel.replace("\\", "/")
    path = repo_root / rel_posix

    # -- Layer 1: path guard ------------------------------------------------
    for pattern, reason in PATH_RULES:
        if re.search(pattern, rel_posix, re.IGNORECASE):
            if _ENV_PATH.search(rel_posix) and _ENV_ALLOWLIST_SUFFIX.search(rel_posix):
                continue
            findings.append(f"PATH: {reason} (pattern: {pattern})")
            break  # one path verdict is enough

    # -- Layer 3: surface guard ---------------------------------------------
    surface = surface_violation(rel_posix)
    if surface:
        findings.append(f"SURFACE: {surface}")

    # -- Layer 2: content guard (text files only) ---------------------------
    if not path.is_file():
        findings.append("FAIL-CLOSED: path listed for scan does not exist on disk")
        return findings
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except (UnicodeDecodeError, ValueError):
        findings.append(
            "FAIL-CLOSED: binary/undecodable file cannot be content-audited "
            "(fail-closed — manual review or approved-surface entry required)"
        )
        return findings

    lines = text.splitlines()
    for idx, line in enumerate(lines):
        for marker_re, reason in _CONTENT_MARKERS:
            if marker_re.search(line):
                findings.append(f"CONTENT[{idx + 1}]: {reason}")
        assignment = _ASSIGNMENT.search(line)
        if assignment and _value_is_concrete(assignment.group(2)):
            findings.append(
                f"CONTENT[{idx + 1}]: credential assignment with concrete value "
                f"({assignment.group(1)})"
            )
        if _PEM_HEADER.search(line) and _check_pem(lines, idx):
            findings.append(f"CONTENT[{idx + 1}]: PEM private key with base64 body")
        if _DB_URL.search(line) and not _DB_URL_PLACEHOLDER.search(line):
            findings.append(
                f"CONTENT[{idx + 1}]: connection URL with embedded credentials"
            )

    return findings


def _git_tracked_files(repo_root: Path) -> list[str]:
    """Tracked file list via git; any git failure is an operational error."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(repo_root),
            capture_output=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"git ls-files failed: {exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(
            "git ls-files returned nonzero: "
            + proc.stderr.decode(errors="replace")[:400]
        )
    entries = [e for e in proc.stdout.decode(errors="replace").split("\0") if e]
    if not entries:
        raise RuntimeError(
            "git ls-files produced no output — refusing to pass (fail-closed)"
        )
    return entries


def _resolve_scan_files(repo_root: Path, requested: Sequence[str]) -> list[str]:
    """Validate and normalise --files input; fail-closed on bad input."""
    resolved: list[str] = []
    for item in requested:
        if not item.strip():
            raise RuntimeError("empty path in --files input")
        candidate = Path(item)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RuntimeError(f"refusing unsafe path in --files input: {item!r}")
        rel_posix = candidate.as_posix()
        if not (repo_root / rel_posix).exists():
            raise RuntimeError(f"--files path does not exist in checkout: {item!r}")
        resolved.append(rel_posix)
    if not resolved:
        raise RuntimeError("--files received no paths — refusing to pass (fail-closed)")
    return resolved


def _run_scan(repo_root: Path, files: Sequence[str], label: str) -> int:
    violations = 0
    for rel in files:
        for finding in scan_file(repo_root, rel):
            violations += 1
            print(f"::error::BOUNDARY VIOLATION [{label}] {rel} :: {finding}")
    print()
    print(
        f"Boundary scan summary [{label}]: files_scanned={len(files)} violations={violations}"
    )
    if violations:
        print(
            "Result: ❌ FAIL — proprietary boundary violations detected (fail-closed)."
        )
        print("Remediation: remove the material, or consciously expand the approved")
        print("surface registry in scripts/ci/boundary_sanitization_guard.py via a PR.")
        return 1
    print(
        "Result: ✅ PASS — public/private boundary intact (only approved public surfaces present)."
    )
    return 0


def cmd_check(repo_root: Path) -> int:
    files = _git_tracked_files(repo_root)
    print(
        f"Boundary Sanitization Guard — full-tree audit of {len(files)} tracked files"
    )
    return _run_scan(repo_root, files, "--check")


def cmd_files(repo_root: Path, requested: Sequence[str]) -> int:
    files = _resolve_scan_files(repo_root, requested)
    print(f"Boundary Sanitization Guard — changed-files scan ({len(files)} files)")
    return _run_scan(repo_root, files, "--files")


def cmd_base_head(repo_root: Path, base: str, head: str) -> int:
    for rev in (base, head):
        probe = subprocess.run(
            ["git", "rev-parse", "--verify", rev],
            cwd=str(repo_root),
            capture_output=True,
            timeout=30,
            check=False,
        )
        if probe.returncode != 0:
            raise RuntimeError(f"--base/--head revision not resolvable: {rev!r}")
    proc = subprocess.run(
        ["git", "diff", "--name-only", f"{base}..{head}"],
        cwd=str(repo_root),
        capture_output=True,
        timeout=60,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "git diff failed: " + proc.stderr.decode(errors="replace")[:400]
        )
    files = [f for f in proc.stdout.decode(errors="replace").splitlines() if f.strip()]
    if not files:
        print("No files changed between revisions — nothing to scan.")
        return 0
    print(
        f"Boundary Sanitization Guard — diff scan {base}..{head} ({len(files)} files)"
    )
    return _run_scan(repo_root, files, "--diff")


# ---------------------------------------------------------------------------
# Guard-the-guard: offline self-test with deterministic fixtures
# ---------------------------------------------------------------------------


def _self_test_case(
    repo_root: Path, rel: str, content_lines: list[str], expect_violations: bool
) -> None:
    target = repo_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(content_lines), encoding="utf-8")
    findings = scan_file(repo_root, rel)
    if expect_violations and not findings:
        raise AssertionError(
            f"self-test MISS: {rel} should have been flagged (findings empty)"
        )
    if not expect_violations and findings:
        raise AssertionError(
            f"self-test FALSE-POSITIVE: {rel} should have passed, got: {findings}"
        )


def cmd_self_test() -> int:
    print("Boundary Sanitization Guard — self-test (guard-the-guard, offline)")
    # Leak fixtures are ASSEMBLED AT RUNTIME so that this guard's own source
    # never contains a contiguous, matchable leak shape — the guard must be
    # able to scan itself (--check includes this very file, fail-closed).
    vault_leak = "VAULT_" + 'TOKEN = "sample"\n'  # value kept short so this
    # source line cannot trip generic secret scanners (gitleaks); the guard's
    # own rule fires on NAME + any concrete non-placeholder value.
    pem_header = "-----BEGIN RSA " + "PRIVATE KEY-----\n"
    pem_body = "MIIEpAIBAAKCAQEA0123456789abcdefghijklmnopqrstuvwxyzABCDEF01QRST\n"
    service_role_leak = (
        "SUPABASE_SERVICE_ROLE_" + "KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\n"
    )
    sb_token_leak = 'const t = "sb_' + 'secret_AbCdEf1234567890";\n'
    core_import_py = "from supremeai_" + "core import decide\n"
    core_import_ts = "import client from 'supremeai-" + "core/client';\n"
    db_url_leak = "psql postgres://admin:" + "S3cretPw@db.internal:5432/prod\n"
    prompt_fence = (
        "<system_" + "prompt> internal reasoning moat </system_" + "prompt>\n"
    )
    secret_ref = "VAULT_" + "TOKEN: ${{ secrets.VAULT_" + "TOKEN }}\n"
    empty_ref = "VAULT_" + "TOKEN=\n"
    with tempfile.TemporaryDirectory(prefix="boundary-guard-selftest-") as tmp:
        root = Path(tmp)
        # (relpath, lines, expect_violation?)
        cases = [
            # --- must PASS (calibrated legitimate content) ---
            (
                "scripts/agents/runner.py",
                ["import os\n", "def main():\n    return 0\n"],
                False,
            ),
            (
                "docs/note.md",
                ["The private monorepo (supremeai-core) stays private.\n"],
                False,
            ),
            (
                "infrastructure/mcp-control-plane/src/lib/masking.ts",
                ["// PEM private keys\n", "/-----BEGIN [A-Z ]*PRIVATE KEY-----/,\n"],
                False,
            ),
            (
                "infrastructure/mcp-control-plane/render.yaml",
                ["      - key: SUPABASE_SERVICE_ROLE_KEY\n"],
                False,
            ),
            (
                "infrastructure/mcp-control-plane/src/lib/env.ts",
                ["export const KEY = process.env.SUPABASE_SERVICE_ROLE_KEY\n"],
                False,
            ),
            (".github/workflows/workflow_ref.yml", [secret_ref], False),
            ("docs/empty_ref.env.example", [empty_ref], False),
            (
                "infrastructure/LICENSE",
                ["Copyright (c) 2026 Supremeai-bd. Proprietary notice.\n"],
                False,
            ),
            # --- must FAIL (real leak classes; placed in APPROVED surfaces so
            # the CONTENT layer is what fires, not the surface layer) ---
            ("docs/leak_vault.py", [vault_leak], True),
            ("docs/leak_pem.txt", [pem_header, pem_body], True),
            ("scripts/agents/leak_env.py", [service_role_leak], True),
            ("scripts/agents/leak_token.ts", [sb_token_leak], True),
            ("scripts/agents/leak_import.py", [core_import_py], True),
            ("scripts/agents/leak_import.ts", [core_import_ts], True),
            ("scripts/agents/leak_dburl.sh", [db_url_leak], True),
            ("docs/leak_prompt.md", [prompt_fence], True),
            # --- path/surface layer ---
            (".env", ["DB_PASS=hunter2\n"], True),
            ("vault/keys.txt", ["hvs.abc\n"], True),
            ("unknown_surface/newfile.py", ["x = 1\n"], True),
            ("scripts/notapproved/tool.py", ["x = 1\n"], True),
            (
                "infrastructure/notapproved/tool.py",
                ["x = 1\n"],
                True,
            ),  # FILE entry must not over-allow the whole subtree
        ]
        for rel, lines, expect in cases:
            _self_test_case(root, rel, lines, expect)
        print(
            f"Self-test: {len(cases)}/{len(cases)} fixture assertions passed "
            f"(miss=0, false-positive=0)."
        )
    print("SELF-TEST PASS — guard detection + calibration verified.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="boundary_sanitization_guard.py",
        description=(
            "Public/Private boundary & proprietary-logic isolation guard (#107). "
            "Fail-closed: exit 0 clean / 1 violations / 2 operational error."
        ),
    )
    parser.add_argument(
        "--check", action="store_true", help="audit every git-tracked file"
    )
    parser.add_argument(
        "--files",
        nargs="+",
        metavar="PATH",
        help="scan exactly these paths (PR changed-files mode)",
    )
    parser.add_argument(
        "--base", metavar="SHA", help="diff-scan base revision (with --head)"
    )
    parser.add_argument(
        "--head", metavar="SHA", help="diff-scan head revision (with --base)"
    )
    parser.add_argument(
        "--self-test", action="store_true", help="offline guard-the-guard fixtures"
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[2]

    try:
        if args.self_test:
            return cmd_self_test()
        if args.check:
            return cmd_check(repo_root)
        if args.files:
            return cmd_files(repo_root, args.files)
        if args.base or args.head:
            if not (args.base and args.head):
                parser.print_usage(sys.stderr)
                print("error: --base and --head must be used together", file=sys.stderr)
                return 2
            return cmd_base_head(repo_root, args.base, args.head)
    except RuntimeError as exc:
        print(f"::error::boundary guard operational error: {exc}", file=sys.stderr)
        print("FAIL-CLOSED: operational error is never a pass.", file=sys.stderr)
        return 2

    parser.print_usage(sys.stderr)
    print(
        "error: choose a mode: --check | --files PATH... | --base SHA --head SHA | --self-test",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
