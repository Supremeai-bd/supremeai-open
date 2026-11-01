"""Sentinel-parity guard for the #1665 prompt-injection canary contract.

Post-#4934 role: the canary corpus (browser/runtime/injection_canaries.py)
and its screening seam (browser/runtime/content_screen.py) are OWNED by the
sovereign satellite repo ``Supremeai-bd/supremeai-browser`` and are pruned
from the open monorepo. This file remains in the open repo ONLY as the
registered open-side sentinel mirror (scripts/ci/satellite_sentinels.json) —
so its open-side duty is the sentinel contract itself, not corpus screening:

  1. the open<->satellite mirror entry for this very file stays registered;
  2. the sync driver (federation_satellite_sync.py) carries the same entry
     (two SSOT copies must not drift);
  3. the pruned runtime stays pruned — if browser/runtime/ reappears in the
     open repo without a contract update, this suite FAILS CLOSED. The canary
     screening behavior itself (32 canaries, 8 classes, fail-closed verdict,
     benign controls) is exercised by the satellite's own copy of this suite;
     the open side pins only the boundary contract (radar: a guard never rots
     silently back to life).

ZERO network, ZERO browser launches, stdlib-only.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SENTINELS_JSON = REPO_ROOT / "scripts" / "ci" / "satellite_sentinels.json"
SYNC_DRIVER = REPO_ROOT / "scripts" / "ci" / "federation_satellite_sync.py"
SELF_PATH = "tests/test_browser_injection_canary.py"
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


def test_runtime_stays_pruned_fail_closed():
    runtime_dir = REPO_ROOT / "browser" / "runtime"
    assert not runtime_dir.exists(), (
        "browser/runtime/ reappeared in the open repo after the #4934 prune; "
        "the #1665 canary corpus lives only in "
        f"{SATELLITE_REPO} — restore the prune or update the sentinel contract "
        "explicitly (never let the boundary rot silently)"
    )
