#!/usr/bin/env python3
"""tests/test_tower_tool_name_drift.py — dead tower-tool-name regression guard (#2493).

Failure class being locked out (rename-wave caller debt, #2493):

  The MCP tower renames its tool surface in waves — wave 1 (2026-10-29,
  #2454 r3 deploy) retired ``bridge_work_queue``/``bridge_work_order`` for
  the dotted ``bridge.work_queue``/``bridge.work_order``; wave 2 (2026-10-30,
  first observed by #2484/#2476, live-verified by #2493) retired the whole
  snake_case core ``github_*`` family for the dotted ``github.*`` forms.
  Tracked-tree callers that still sent the dead names did not fail loudly in
  CI — they failed silently in production: the satellite CI sentinel went
  blind, the landing watchdog's flight plane went dark, doc ingest broke,
  and onboarding docs taught agents the dead convention. Detection took a
  human-filed receipt days later. Root cause: no automated drift detection
  between the tree's tower-call names and the live roster.

  This guard pins the known-dead names and fails on any NEW quoted
  occurrence in tracked code, so the class cannot silently regress and
  wave-3 casualties are a one-line pin away.

বাংলা সারসংক্ষেপ:
------------------
টাওয়ার ঢেউয়ে (rename wave) টুলের নাম বদলায়, কিন্তু রিপোর কলাররা পুরনো নামেই
ডাকতে থাকে — CI ধরে না, প্রোডাকশনে নীরবে অন্ধ হয়ে যায় (sentinel/watchdog/ingest)।
এই guard মৃত নামগুলো পিন করে রাখে; ট্র্যাকড কোডে quoted রূপে নতুন করে কেউ সেই
নাম লিখলেই টেস্ট লাল হবে। ঢেউ ৩ এলে শুধু DEAD_TOWER_TOOL_NAMES-এ এক লাইন যোগ হবে।

Scope rules (honest surface, minimal false positives):
  - ONLY quoted occurrences count (``"name"``/``'name'``/backticked) — a bare
    word in a comment or docstring documenting the rename history is NOT a
    caller. String-literal matches cover real wire payloads: TS/JS object
    values, JSON registry entries, JSON-RPC params, Python call_tool args.
  - Allowlisted paths are OWN-REGISTRY surfaces or historical evidence where
    a dead name is either a different plane's live tool name or the recorded
    past — see ALLOWLISTED_PREFIXES for the per-entry justification.
  - DO NOT add the still-live snake_case families here by "helpfulness":
    ``github_repo_tree``/``github_search_repos``/``github_repo_info``/
    ``github_read_external_file``/``github_collect_highlights`` and the
    claim/feedback family (``work_claim``, ``bridge_read_feedback``,
    ``bridge_work_renew``, ``bridge_work_release``) are LIVE underscore
    forms (probe-verified 2026-10-30, #2493). Only pinned-dead names belong.

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):
  - pytest:  pytest tests/test_tower_tool_name_drift.py
  - stdlib:  python3 tests/test_tower_tool_name_drift.py   (plain runner)

Every test is offline and deterministic (pure text scan over ``git ls-files``).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Pinned dead names -> their live dotted successors, with the evidence that
# killed each. Extend this dict (one line) when the next rename wave lands;
# the main scan then enforces it tree-wide immediately.
DEAD_TOWER_TOOL_NAMES: dict[str, str] = {
    # wave 1 — 2026-10-29 (#2454 r3 deploy; migration receipts #2459/#2469)
    "bridge_work_queue": "bridge.work_queue",
    "bridge_work_order": "bridge.work_order",
    # wave 2 — 2026-10-30 (observed #2484/#2476; live-verified #2493; probed
    # -32602 "Tool not found" on the deployed tower 2026-10-30, GLM Agent 19)
    "github_actions_op": "github.actions_op",
    "github_code_search": "github.code_search",
    "github_create_issue": "github.create_issue",
    "github_get_failed_logs": "github.get_failed_logs",
    "github_list_prs": "github.list_prs",
    "github_list_secrets": "github.list_secrets",
    "github_read_file": "github.read_file",
    "github_search_code": "github.search_code",
    "github_workflow_runs": "github.workflow_runs",
}

# Files/prefixes where a quoted dead name is legitimate. Each entry carries
# its own justification — keep this list minimal and honest.
ALLOWLISTED_PREFIXES: tuple[tuple[str, str], ...] = (
    ("tests/test_tower_tool_name_drift.py",
     "this guard's own pin data quotes the dead names as data"),
    ("tests/test_tower_queue_tool_name_epochs.py",
     "oscillation-epoch tolerance test — quotes BOTH spellings of the "
     "oscillating queue tool as test data (wave-1 dotted / wave-3 underscore, "
     "live-verified 2026-10-31): the drift pin model is one-directional per "
     "wave, this test pins the bidirectional try-in-order cure; same "
     "name-as-data doctrine as this guard's own self-allowlist above"),
    ("tests/test_tower_name_tolerance.py",
     "contract tests for the shared rename-wave tolerance cure "
     "(scripts/ci/tower_name_tolerance.py) — assert the epoch ledger contains "
     "BOTH documented spellings per oscillating family (wave-1 dotted / "
     "wave-3 underscore, live-verified 2026-10-31) and that first-live-wins "
     "crosses a dead spelling; same name-as-data doctrine as this guard's "
     "own self-allowlist above"),
    ("scripts/ci/tower_name_tolerance.py",
     "shared rename-wave tolerance cure (caller-side try-in-order across "
     "documented name epochs) — its TOOL_NAME_EPOCHS map IS the name-as-data "
     "ledger: every spelling it quotes is one of the two live-in-some-wave "
     "forms of the same oscillating family, called only via first-live-wins, "
     "never hardcoded at a call site; the docstring's wave-3 narrative also "
     "names both forms as history"),
    ("scripts/tower/tool_consolidation_reference.py",
     "historical consolidation-mapping SSOT (MERGED records of old->new)"),
    ("scripts/ci/mcp_access_policy_guard.py",
     "guards the control-plane's OWN registry source (embedded strings)"),
    ("tests/test_mcp_access_policy_guard.py",
     "tests the control-plane registry guard, quotes its embedded pins"),
    ("core/tools/mcp/",
     "core satellite's OWN MCP tool surface — its own registry names, calls "
     "GitHub REST directly, never the tower (same doctrine as the "
     "control-plane pins, #2493 scope note)"),
    ("infrastructure/mcp-control-plane/",
     "control-plane's OWN registry/policy pins + tombstones that exist "
     "precisely to record retired names (#2493: self-consistent, out of scope)"),
    ("docs/",
     "historical receipts/specs — the evidence trail is allowed to name the "
     "past; the strict surface is code"),
)

# Tracked text extensions scanned. Code + config + docs that carry wire
# payloads; binaries and lockfiles are out of model.
SCANNED_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".sh", ".bash", ".md", ".json", ".yaml", ".yml", ".toml",
}

# One quoted segment per match: double/single quotes or backticks on a line.
# Line-based by design: deterministic, dependency-free, and every real tower
# call site quotes the tool name on a single line.
_QUOTED_RE = re.compile(r'"[^"\n]*"|\'[^\'\n]*\'|`[^`\n]*`')


def quoted_dead_names(line: str) -> list[str]:
    """Return the dead tower-tool names appearing as quoted strings in a line."""
    found: list[str] = []
    for segment in _QUOTED_RE.findall(line):
        for dead in DEAD_TOWER_TOOL_NAMES:
            if re.search(rf"\b{re.escape(dead)}\b", segment):
                found.append(dead)
    return found


def _is_allowlisted(rel_path: str) -> tuple[bool, str]:
    for entry, why in ALLOWLISTED_PREFIXES:
        if entry.endswith("/"):
            if rel_path.startswith(entry):
                return True, why
        elif rel_path == entry:
            return True, why
    return False, ""


def tracked_text_files() -> list[str]:
    """Tracked files from git, filtered to scanned text extensions.

    Includes untracked-but-not-ignored files (worktree semantics): a guard
    run before commit — the bridge-patch verification mode — must see the
    very files the patch adds, or the gate would be vacuously green at
    exactly the moment it matters.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    files = []
    for chunk in out.stdout.split("\0"):
        if not chunk:
            continue
        if Path(chunk).suffix.lower() in SCANNED_EXTENSIONS:
            files.append(chunk)
    return sorted(files)


def scan_tree() -> dict[str, list[tuple[int, str]]]:
    """Scan the tracked tree; return {rel_path: [(lineno, dead_name), ...]}.

    Line numbers are 1-based and byte-exact against the worktree, so a
    failure message points straight at the offending call.
    """
    violations: dict[str, list[tuple[int, str]]] = {}
    for rel in tracked_text_files():
        allowlisted, _why = _is_allowlisted(rel)
        if allowlisted:
            continue
        path = REPO_ROOT / rel
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            for dead in quoted_dead_names(line):
                violations.setdefault(rel, []).append((lineno, dead))
    return violations


# --------------------------- the tests ---------------------------

def test_no_dead_tower_tool_names_in_tracked_code() -> None:
    violations = scan_tree()
    assert not violations, (
        "dead tower tool names found in quoted wire payloads — migrate to the "
        "dotted live forms (see DEAD_TOWER_TOOL_NAMES map) or justify an "
        "allowlist entry:\n"
        + "\n".join(
            f"  {path}:{lineno}: {dead} -> {DEAD_TOWER_TOOL_NAMES[dead]}"
            for path, hits in sorted(violations.items())
            for lineno, dead in hits
        )
    )


def test_pin_shape_and_successors() -> None:
    """Every pin must be a snake_case name with a dotted live successor."""
    for dead, successor in DEAD_TOWER_TOOL_NAMES.items():
        assert re.fullmatch(r"[a-z][a-z0-9_]*", dead), f"pin {dead!r} not snake_case"
        assert "." in successor, f"successor {successor!r} of {dead} must be dotted"
        assert not re.fullmatch(r"[a-z_]+", successor), (
            f"successor {successor!r} of {dead} must not be snake_case — that is "
            f"the exact naming split this guard exists to end"
        )
    # the two known waves are both represented
    assert any(d.startswith("bridge_") for d in DEAD_TOWER_TOOL_NAMES), "wave 1 pins lost"
    assert any(d.startswith("github_") for d in DEAD_TOWER_TOOL_NAMES), "wave 2 pins lost"


def test_allowlist_paths_exist() -> None:
    """Allowlist entries must point at real tracked paths (no stale entries)."""
    tracked = set(tracked_text_files())
    for entry, _why in ALLOWLISTED_PREFIXES:
        if entry.endswith("/"):
            assert any(p.startswith(entry) for p in tracked), (
                f"allowlist prefix {entry!r} matches no tracked file — stale entry"
            )
        else:
            assert entry in tracked, f"allowlisted file {entry!r} not in the tree"


def test_scanner_detects_planted_violation_but_not_history_comments() -> None:
    """Tamper proof: real quoted calls are caught; bare history comments are not.

    Vacuously-green guard prevention (same doctrine as the tampered-case in
    scripts/ci/mcp_access_policy_guard.py): if the matcher ever stops matching
    quoted dead names, this test fails.
    """
    caller = [
        "const payload = { params: { name: \"github_read_file\" } };",
        "client.call_tool('github_workflow_runs', args)",
    ]
    history = [
        # bare words in comments/continuation-line docstrings are how the
        # tree legitimately documents rename history (loop:769, watchdog:13)
        "# 2026-10-29: the tower renamed bridge_work_queue -> bridge.work_queue",
        '"""Docstring header, wave 1."""\nrenamed bridge_work_order 2026-10-29'.splitlines()[1],
    ]
    hits_caller = [hit for line in caller for hit in quoted_dead_names(line)]
    hits_history = [hit for line in history for hit in quoted_dead_names(line)]
    assert set(hits_caller) == {"github_read_file", "github_workflow_runs"}, hits_caller
    assert hits_history == [], hits_history

    # end-to-end through the file scanner: a planted file under a fresh temp
    # tree root must be caught with the right line number
    with tempfile.TemporaryDirectory() as td:
        planted = Path(td) / "planted_caller.py"
        planted.write_text(
            "x = 1\nclient.call_tool(\"github_read_file\", {})\n", encoding="utf-8"
        )
        found = [
            (lineno, dead)
            for lineno, line in enumerate(
                planted.read_text(encoding="utf-8").splitlines(), start=1
            )
            for dead in quoted_dead_names(line)
        ]
        assert found == [(2, "github_read_file")], found


# --------------------------- stdlib runner ---------------------------

def _main() -> int:
    failed = False
    try:
        test_pin_shape_and_successors()
        print("[PASS] pin shape and successors")
    except AssertionError as exc:
        failed = True
        print(f"[FAIL] pin shape and successors: {exc}")
    try:
        test_allowlist_paths_exist()
        print("[PASS] allowlist paths exist")
    except AssertionError as exc:
        failed = True
        print(f"[FAIL] allowlist paths exist: {exc}")
    try:
        test_scanner_detects_planted_violation_but_not_history_comments()
        print("[PASS] scanner tamper self-check")
    except AssertionError as exc:
        failed = True
        print(f"[FAIL] scanner tamper self-check: {exc}")
    try:
        test_no_dead_tower_tool_names_in_tracked_code()
        print("[PASS] no dead tower tool names in tracked code")
    except AssertionError as exc:
        failed = True
        print(f"[FAIL] dead tower tool names in tracked code:\n{exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())
