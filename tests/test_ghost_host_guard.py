#!/usr/bin/env python3
"""tests/test_ghost_host_guard.py — fail-closed behavioral suite for #2377.

Pins the ghost-host retirement contract delivered for #2377 (class closure of
#2355 → #2348 → #2377; instance lineage #2365):

  - zero tolerance: a ghost-host default in an executable/config surface
    (scripts, examples, CI configs, _redirects, vercel.json, …) fails the
    scan even when a banner marker is present — a marker documents history,
    it never whitewashes a live trap;
  - evidence lanes: docs/reports/** and docs/bridge/** are allowed (immutable
    measured-evidence receipts; rewriting them would falsify the audit trail);
  - banner contract: other Markdown may retain ghost strings only inside a
    retirement banner carrying the exact marker `ghost-host-retired:
    #2355/#2365/#2377` within the first 20 lines — stripped or late banners
    fail-closed;
  - real-host safety: `supremeai-api-ulw0.onrender.com` never matches the
    ghost pattern (no false positive on the README SSOT);
  - live sweep: the real tracked tree passes --check semantics (the #2377
    instance fixes — both curl-tests smoke defaults + both SEQ handoff
    banners — shipped in the same change);
  - wiring SSOT: the guard is present in the LIVE run_all_guards.py roster,
    never duplicated here.

Design (zero-dependency doctrine, dual mode — pytest + stdlib runners):

  - pytest:  pytest tests/test_ghost_host_guard.py
  - stdlib:  python3 tests/test_ghost_host_guard.py  (plain runner)

All tree scenarios are hermetic (tempdirs, offline, deterministic); the live
sweep is read-only.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD = REPO_ROOT / "scripts" / "ci" / "ghost_host_guard.py"
ROSTER = REPO_ROOT / "scripts" / "ci" / "run_all_guards.py"

sys.path.insert(0, str(REPO_ROOT / "scripts" / "ci"))
import ghost_host_guard as guard


def make_tree(files: dict[str, str]) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="ghost-guard-test-"))
    for rel, content in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp


GHOST = guard.GHOST_HOST
REAL = guard.REAL_HOST
MARKER = guard.BANNER_MARKER


# --------------------------------------------------------------------------- #
# wiring SSOT                                                                  #
# --------------------------------------------------------------------------- #

def test_guard_module_is_pinned_in_live_roster() -> None:
    roster = ROSTER.read_text(encoding="utf-8")
    assert f'"scripts/ci/{GUARD.name}", "--self-test"' in roster
    assert f'"scripts/ci/{GUARD.name}", "--check"' in roster


# --------------------------------------------------------------------------- #
# scan semantics                                                               #
# --------------------------------------------------------------------------- #

def test_clean_tree_passes() -> None:
    tree = make_tree({
        "examples/client.py": f'URL = "https://{REAL}/v1"\n',
        "docs/CONSUMERS.md": f"Base URL: https://{REAL}\n",
        "docs/reports/SENTRY_X.md": f"measured: {GHOST} 404 at 01:45Z\n",
        "docs/bridge/closure.md": f"receipt: retired ghost {GHOST}\n",
    })
    assert guard.scan(tree) == []


def test_ghost_in_executable_surface_fails() -> None:
    tree = make_tree({
        "examples/run_smoke.sh": f'URL="${{GATEWAY_URL:-https://{GHOST}}}"\n',
        "examples/run_smoke.ps1": f"$u = 'https://{GHOST}'\n",
        "studio/vercel.json": f'{{"url": "https://{GHOST}"}}\n',
    })
    violations = guard.scan(tree)
    assert len(violations) == 3
    assert all("zero tolerance" in v for v in violations)


def test_banner_marker_cannot_whitewash_executable() -> None:
    tree = make_tree({
        "scripts/probe.py": f"# {MARKER}\nURL = 'https://{GHOST}/healthz'\n",
    })
    violations = guard.scan(tree)
    assert len(violations) == 1
    assert "zero tolerance" in violations[0]


def test_unbannered_doc_fails() -> None:
    tree = make_tree({
        "docs/LEGACY.md": f"see https://{GHOST}/v1/models\n",
    })
    assert len(guard.scan(tree)) == 1


def test_bannered_doc_passes() -> None:
    tree = make_tree({
        "docs/LEGACY.md": (
            f"# old receipt\n\n> {MARKER} — historical, ghost retired\n\n"
            f"see https://{GHOST}/v1/models\n"
        ),
    })
    assert guard.scan(tree) == []


def test_late_banner_outside_window_does_not_whitewash() -> None:
    tree = make_tree({
        "docs/LEGACY.md": (
            "# old receipt\n" + "\n" * 25
            + f"line {MARKER} beyond window\n"
            + f"see https://{GHOST}/v1/models\n"
        ),
    })
    assert len(guard.scan(tree)) == 1


def test_real_host_never_matches_ghost_pattern() -> None:
    tree = make_tree({
        "README.md": f"| API Gateway | https://{REAL} |\n",
        "scripts/probe.py": f'URL = "https://{REAL}"\n',
        "studio/public/_redirects": f"/api/* https://{REAL}/api/:splat 200\n",
    })
    assert guard.scan(tree) == []


def test_binary_files_are_skipped() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="ghost-guard-test-"))
    (tmp / "blob.bin").write_bytes(b"\0" + GHOST.encode() + b"\0")
    assert guard.scan(tmp) == []


# --------------------------------------------------------------------------- #
# live sweep (read-only, real tracked tree)                                    #
# --------------------------------------------------------------------------- #

def test_live_tree_passes_check_semantics() -> None:
    assert guard.scan(REPO_ROOT) == []


# --------------------------------------------------------------------------- #
# stdlib dual-mode runner                                                      #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(
        (k, v) for k, v in globals().items() if k.startswith("test_") and callable(v)
    ):
        try:
            fn()
            print(f"PASS {name}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {name}: {exc}")
    total = len([k for k in globals() if k.startswith("test_")])
    print(f"{total - failed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
