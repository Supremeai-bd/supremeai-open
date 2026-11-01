"""Sentinel-parity battery for the supremeai-browser satellite contract.

Post-#4934 role: the browser runtime (config, content_pruner, cookie_bridge,
infinite_scanner, semantic_extractor, session_manager, stealth_profile,
content_screen, injection_canaries) is OWNED by the sovereign satellite repo
``Supremeai-bd/supremeai-browser`` and is pruned from the open monorepo.
This file remains in the open repo ONLY as the registered open-side sentinel
mirror (scripts/ci/satellite_sentinels.json) — so its open-side duty is the
sentinel contract itself, not satellite runtime behavior:

  1. the open<->satellite mirror entry for this very file stays registered;
  2. the sync driver (federation_satellite_sync.py) carries the same entry
     (two SSOT copies must not drift);
  3. the root sentinel anchor (browser/main.py) survives the prune, keeping
     zero-drift parity verifiable;
  4. the pruned runtime stays pruned — if browser/runtime/ reappears in the
     open repo without a contract update, this suite FAILS CLOSED (radar:
     prune/class rule — a guard never rots silently back to life).

ZERO network, ZERO browser launches, stdlib-only.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SENTINELS_JSON = REPO_ROOT / "scripts" / "ci" / "satellite_sentinels.json"
SYNC_DRIVER = REPO_ROOT / "scripts" / "ci" / "federation_satellite_sync.py"
SELF_PATH = "tests/test_browser_foundation.py"
SATELLITE_REPO = "Supremeai-bd/supremeai-browser"


def _mirror_entries() -> list[dict]:
    raw = json.loads(SENTINELS_JSON.read_text(encoding="utf-8"))
    pairs = raw.get("pairs", raw if isinstance(raw, list) else [])
    assert pairs, "satellite_sentinels.json must define mirror pairs"
    return [p for p in pairs if p.get("open") == SELF_PATH]


def test_own_mirror_entry_registered():
    entries = _mirror_entries()
    assert entries, f"{SELF_PATH} lost its sentinel mirror entry"
    entry = entries[0]
    assert entry.get("path") == SELF_PATH, "mirror path must equal the open path"
    assert entry.get("satellite") == SATELLITE_REPO, (
        "mirror must point at the sovereign browser satellite"
    )


def test_sync_driver_registration_matches_json():
    src = SYNC_DRIVER.read_text(encoding="utf-8")
    assert SELF_PATH in src, "sync driver lost the mirror registration"
    assert SATELLITE_REPO in src, "sync driver lost the satellite target"
    assert SELF_PATH in SENTINELS_JSON.read_text(encoding="utf-8"), (
        "json/driver SSOT drift: registration present in driver, absent in json"
    )


def test_root_sentinel_anchor_survives():
    anchor = REPO_ROOT / "browser" / "main.py"
    assert anchor.is_file(), (
        "#4934 promised browser/main.py as the root sentinel contract anchor; "
        "it vanished — zero-drift parity is unverifiable"
    )


def test_runtime_stays_pruned_fail_closed():
    runtime_dir = REPO_ROOT / "browser" / "runtime"
    assert not runtime_dir.exists(), (
        "browser/runtime/ reappeared in the open repo after the #4934 prune; "
        "satellite sovereignty requires it to live only in "
        f"{SATELLITE_REPO} — restore the prune or update the sentinel contract "
        "explicitly (never let the boundary rot silently)"
    )
