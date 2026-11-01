#!/usr/bin/env python3
"""tests/test_ci_supply_chain_guard.py — CI supply-chain lane guard (#2310).

Issue #2310 (security(bridge), verified 2026-10-29 by agent cycle-28):
CI executes branch-controlled code past the .github/ gate —

  V1  bridge-intake-instant checks out the PUSHED branch
      (refs/heads/bridge/**, content-controlled by the pushing agent) and
      runs scripts/ci/auto_bridge_pr_opener.py FROM that checkout with
      GH_TOKEN: MERGE_PAT in env. Branch-controlled python executes with
      a merge-capable token.
  V2  PR CI installs dependencies from branch-controlled manifests:
      composite setup-node-tower runs plain `npm ci` (lifecycle scripts
      of any dependency or of package.json itself execute), and
      studio-verification runs `pnpm install --frozen-lockfile` against
      the branch's own pnpm-lock.yaml. Any PR can therefore execute
      attacker-chosen code inside CI runners.
  V3  No .npmrc exists anywhere in the repo and no lifecycle hook is
      baselined — the lanes are OPEN by default (zero active hooks today,
      verified inventory: 18 package.json files, 0 lifecycle scripts,
      0 .npmrc, 5 lockfiles).

This file enforces what the bridge-able plane can enforce NOW and pins
the admin-handoff state for what only admins can fix:

  ACTIVE (green on pristine main, red on violation):
    A1  no lifecycle hooks (postinstall/preinstall/prepare/prepack) in
        any package.json outside the explicit in-file allowlist;
    A2  no .npmrc file anywhere in the working tree;
    A3  the five known lockfiles still exist (deletion = red);
    A4  studio install keeps --frozen-lockfile (SSOT-extracted from the
        live pipeline.yml).

  PENDING HANDOFF (SKIP with pointer until admins land the recipe, then
  permanently enforced — the test_ci_guards.py sequencing-honesty
  doctrine: a pending handoff is a pending state, not a regression):
    B1  bridge-intake-instant checkout pins a TRUSTED ref (the job must
        run MAIN's intake code; the pushed branch is data-only — verified:
        auto_bridge_pr_opener.py reads no working-tree content, it fetches
        bridge branches itself via git fetch driven by bridge:queued issue
        bodies);
    B2  npm ci carries lifecycle-script hardening (--ignore-scripts or
        equivalent marker).

ADMIN RECIPE (deployment-side reconciliation — NOT bridge-able; .github/
is an admin-owned protected path per the bridge contract, same lane as
constitution_pointer_guard.py documents):

  1. Pin the intake checkout to the default branch (pipeline.yml,
     bridge-intake-instant, first step):
         - name: Checkout repository
           uses: actions/checkout@v5
           with:
             ref: ${{ github.event.repository.default_branch }}
     This test B1 accepts `github.event.repository.default_branch` or a
     literal trusted branch name; it REJECTS branch-controlled contexts
     (`github.ref`, `github.event.ref`, `github.sha`, `github.ref_name`)
     so the pin cannot silently rot into a controlled value.
  2. Harden the tower install (composite setup-node-tower):
     `npm ci --ignore-scripts` plus `npm rebuild <allowlist>` for
     esbuild-class native deps, OR a committed infrastructure/
     mcp-control-plane/.npmrc with ignore-scripts=true plus documented
     exceptions. Landing either makes B2 activate.
  3. Keep lockfiles under review for PRs that touch them (pnpm plane is
     already frozen; npm plane is lockfile-driven by `npm ci`).

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):
  - pytest:  pytest tests/test_ci_supply_chain_guard.py
  - stdlib:  python3 tests/test_ci_supply_chain_guard.py

Boundary: tests/ only; .github/ is read (SSOT extraction), never written.
Offline and deterministic; no network, no subprocess.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PIPELINE = REPO_ROOT / ".github" / "workflows" / "pipeline.yml"
TOWER_COMPOSITE = REPO_ROOT / ".github" / "actions" / "setup-node-tower" / "action.yml"

LIFECYCLE_HOOKS = ("postinstall", "preinstall", "prepare", "prepack")

# A1 allowlist: (package.json path relative to repo root) -> {hook: reason}.
# Empty by default (verified 2026-10-29 inventory: zero hooks on main).
# Any entry added here MUST carry a written justification — this map is the
# audit trail for the supply-chain lane (#2310).
HOOK_ALLOWLIST: dict[str, dict[str, str]] = {}

# A3 presence pins: lockfiles that must never silently disappear.
# Post-#4934: browser/cloudflare-worker and vscode/extension moved to their
# sovereign satellite repos — their pins moved with them (never silently).
LOCKFILE_PINS = (
    ".agents/skills/devtools-audit/package-lock.json",
    "infrastructure/mcp-control-plane/package-lock.json",
    "studio/pnpm-lock.yaml",
)

_PRUNE_DIRS = {"node_modules", ".git", ".venv", "venv", "__pycache__"}


class _Skip(Exception):
    """Stdlib-mode skip signal (pytest path uses pytest.skip instead)."""


def _skip(reason: str) -> None:
    # Under pytest -> real pytest.skip; stdlib mode -> plain _Skip signal.
    if "PYTEST_CURRENT_TEST" in os.environ:
        import pytest

        pytest.skip(reason)
    raise _Skip(reason)


def _tracked_json_files() -> list[Path]:
    """All package.json under the repo root, pruning vendored/virtual dirs."""
    out: list[Path] = []
    for path in REPO_ROOT.rglob("package.json"):
        if _PRUNE_DIRS & set(path.relative_to(REPO_ROOT).parts):
            continue
        out.append(path)
    return sorted(out)


def _extract_job_block(text: str, job_name: str) -> str | None:
    """Return the raw text of a 2-space-indented job key block, or None.

    Same SSOT extraction contract as tests/test_ci_guards.py — the guard
    tests whatever the maintainers actually applied, never a duplicate.
    """
    lines = text.splitlines()
    key_re = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
    start = None
    for i, ln in enumerate(lines):
        m = key_re.match(ln)
        if m and m.group(1) == job_name:
            start = i
            break
    if start is None:
        return None
    out = [lines[start]]
    for ln in lines[start + 1 :]:
        if key_re.match(ln) or (ln.strip() and not ln[0].isspace()):
            break
        out.append(ln)
    return "\n".join(out)


def _load_pipeline_text() -> str:
    if not PIPELINE.is_file():
        raise AssertionError(
            f"pipeline.yml missing at {PIPELINE} — constitutional workflow file required"
        )
    return PIPELINE.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A1 — lifecycle-hook allowlist (zero hooks baselined on main, 2026-10-29)
# ---------------------------------------------------------------------------
def test_no_lifecycle_hooks_in_any_package_json() -> None:
    offenders: list[str] = []
    for path in _tracked_json_files():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise AssertionError(f"unreadable package.json {path}: {exc}")
        scripts = data.get("scripts", {}) or {}
        rel = path.relative_to(REPO_ROOT).as_posix()
        for hook in LIFECYCLE_HOOKS:
            if hook in scripts:
                allowed = HOOK_ALLOWLIST.get(rel, {}).get(hook)
                if not allowed:
                    offenders.append(f"{rel}::{hook}")
    assert not offenders, (
        "CI supply-chain lane violated: lifecycle hooks execute on every "
        f"`npm ci`/`pnpm install` inside CI (issue #2310 V2). Offenders: "
        f"{offenders}. If a hook is genuinely required, add it to "
        "HOOK_ALLOWLIST in this file WITH a written justification — that "
        "map is the audit trail."
    )


def test_hook_allowlist_entries_are_justified() -> None:
    bad = [
        rel
        for rel, hooks in HOOK_ALLOWLIST.items()
        if not hooks or any(not str(r).strip() for r in hooks.values())
    ]
    assert not bad, f"HOOK_ALLOWLIST entries without justification: {bad}"


# ---------------------------------------------------------------------------
# A2 — no .npmrc anywhere (registry/auth substitution vector)
# ---------------------------------------------------------------------------
def test_no_npmrc_files_anywhere() -> None:
    found = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in REPO_ROOT.rglob(".npmrc")
        if not (_PRUNE_DIRS & set(p.relative_to(REPO_ROOT).parts))
    ]
    assert not found, (
        "npm config surface appeared (issue #2310 V3): .npmrc can pin "
        "registries, inject auth tokens and toggle lifecycle scripts for "
        f"every npm install in CI. Found: {found}. Landing a hardened "
        "ignore-scripts .npmrc is the ADMIN RECIPE step 2 — update this "
        "test's baseline note in the same change if admins adopt it."
    )


# ---------------------------------------------------------------------------
# A3 — lockfile presence pins (deletion = resolution substitution vector)
# ---------------------------------------------------------------------------
def test_pinned_lockfiles_still_present() -> None:
    missing = [rel for rel in LOCKFILE_PINS if not (REPO_ROOT / rel).is_file()]
    assert not missing, (
        "pinned lockfile(s) disappeared: "
        f"{missing}. `npm ci`/`pnpm install --frozen-lockfile` fall back to "
        "unpinned resolution when their lockfile is gone, turning every CI "
        "install into arbitrary dependency selection (issue #2310). If a "
        "lockfile legitimately moved, update LOCKFILE_PINS in the same change."
    )


# ---------------------------------------------------------------------------
# A4 — studio install stays frozen (SSOT from live pipeline.yml)
# ---------------------------------------------------------------------------
def test_studio_install_stays_frozen() -> None:
    text = _load_pipeline_text()
    block = _extract_job_block(text, "studio-verification")
    if block is None:
        _skip("studio-verification job absent from pipeline.yml (restructured)")
    assert "--frozen-lockfile" in block, (
        "studio install lost --frozen-lockfile (issue #2310): unfrozen "
        "pnpm resolution lets a PR swap dependency versions via its own "
        "lockfile and execute attacker-chosen install scripts in CI."
    )


# ---------------------------------------------------------------------------
# B1 — PENDING HANDOFF: intake checkout pins a trusted ref
# ---------------------------------------------------------------------------
_TRUSTED_REF_RE = re.compile(
    r"ref:\s*['\"]?\$\{\{\s*github\.event\.repository\.default_branch\s*\}\}|"
    r"ref:\s*['\"]?main['\"]?\s*$",
    re.MULTILINE,
)
_BRANCH_CONTROLLED_REF_RE = re.compile(
    r"ref:\s*['\"]?\$\{\{\s*(github\.ref\b|github\.event\.ref|github\.sha|github\.ref_name)"
)


def test_bridge_intake_checkout_pins_trusted_ref() -> None:
    text = _load_pipeline_text()
    block = _extract_job_block(text, "bridge-intake-instant")
    if block is None:
        _skip("bridge-intake-instant job absent from pipeline.yml (restructured)")
    checkout_zone = block.split("Run Auto-Bridge PR Opener", 1)[0]
    if "ref:" not in checkout_zone:
        _skip(
            "PENDING HANDOFF (#2310 ADMIN RECIPE step 1): intake checkout does "
            "not yet pin a trusted ref — branch-controlled python runs with "
            "MERGE_PAT (V1). Admin-owned .github/ path; the moment the pin "
            "lands this test enforces it permanently."
        )
    m = _BRANCH_CONTROLLED_REF_RE.search(checkout_zone)
    assert not m, (
        f"intake checkout ref is branch-controlled ({m.group(1)}) — the pin "
        "rotated into an attacker-supplied value (issue #2310 V1). Pin "
        "github.event.repository.default_branch instead."
    )
    assert _TRUSTED_REF_RE.search(checkout_zone), (
        "intake checkout ref is not a recognized trusted value "
        "(accepted: github.event.repository.default_branch, literal 'main')"
    )


# ---------------------------------------------------------------------------
# B2 — PENDING HANDOFF: npm ci lifecycle-script hardening
# ---------------------------------------------------------------------------
def test_tower_npm_ci_scripts_hardening() -> None:
    if not TOWER_COMPOSITE.is_file():
        _skip(f"composite action missing at {TOWER_COMPOSITE}")
    text = TOWER_COMPOSITE.read_text(encoding="utf-8")
    hardened = (
        "--ignore-scripts" in text
        or "NPM_CONFIG_IGNORE_SCRIPTS" in text
        or "ignore-scripts" in text
    )
    if not hardened:
        _skip(
            "PENDING HANDOFF (#2310 ADMIN RECIPE step 2): setup-node-tower "
            "`npm ci` runs lifecycle scripts of branch-controlled manifests "
            "(V2). Admin-owned .github/ path; the moment hardening lands "
            "(--ignore-scripts + rebuild allowlist, or an ignore-scripts "
            ".npmrc) this test enforces it permanently."
        )


if __name__ == "__main__":
    fns = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = skipped = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS | {fn.__name__}")
        except _Skip as exc:
            skipped += 1
            print(f"  SKIP | {fn.__name__}: {exc}")
        except AssertionError as exc:
            failed += 1
            print(f"  FAIL | {fn.__name__}: {exc}")
        except (
            RuntimeError,
            ValueError,
            TypeError,
            OSError,
            KeyError,
        ) as exc:
            failed += 1
            print(f"  ERROR | {fn.__name__}: {type(exc).__name__}: {exc}")
    passed = len(fns) - failed - skipped
    if skipped:
        print(f"{passed}/{len(fns)} tests passed ({skipped} skipped, handoff pending)")
    else:
        print(f"{passed}/{len(fns)} tests passed")
    sys.exit(1 if failed else 0)
