"""Offline tests for the #1676 split-brain root-duplicate guard.

বাংলা: স্যাটেলাইট মিরর root-এ namespace-content রাখে; `<ns>/<rest>` dispatch
root `<rest>`-এর স্টেল কপি বানায়। Guard কেবল প্রমাণিত root-twin হলে (clone থেকে)
add/modify আটকায়; monorepo ও deletion বাদ। সব টেস্ট offline (tmp ফিক্সচার)।
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.bridge.bridge_intake import (
    PRIVATE_REPO,
    deletion_paths,
    split_brain_duplicates,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
INTAKE_PATH = REPO_ROOT / "scripts" / "bridge" / "bridge_intake.py"

STUDIO = "Supremeai-bd/supremeai-studio"


# ---------------------------------------------------------------------------
# Wiring pins — the guard must sit between clone and git apply, fail-closed.
# ---------------------------------------------------------------------------


def test_wiring_guard_call_present_in_process_issue() -> None:
    src = INTAKE_PATH.read_text(encoding="utf-8")
    assert "dupes = split_brain_duplicates(target_repo, Path(private_dir), mapped)" in src
    assert "split-brain guard (#1676)" in src
    # ordering: guard call must precede the land_branch checkout (apply happens after)
    guard_at = src.index("dupes = split_brain_duplicates(")
    land_at = src.index('land_branch = f"bridge-land/')
    assert guard_at < land_at, "guard must run before branch checkout/apply"


def test_wiring_deletion_paths_computed_before_guard() -> None:
    src = INTAKE_PATH.read_text(encoding="utf-8")
    assert "deleted = deletion_paths(diff)" in src
    assert "mapped = [(path_map.get(f, f), f in deleted) for f in files]" in src


# ---------------------------------------------------------------------------
# split_brain_duplicates — core semantics
# ---------------------------------------------------------------------------


def test_monorepo_target_is_exempt() -> None:
    tmp = Path(".")  # not consulted for monorepo
    assert split_brain_duplicates(PRIVATE_REPO, tmp, [("studio/package.json", False)]) == []


def test_satellite_root_twin_exists_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    got = split_brain_duplicates(STUDIO, tmp_path, [("studio/package.json", False)])
    assert got == ["studio/package.json"]


def test_satellite_no_root_twin_passes(tmp_path: Path) -> None:
    (tmp_path / "other.json").write_text("{}\n", encoding="utf-8")
    assert split_brain_duplicates(STUDIO, tmp_path, [("studio/package.json", False)]) == []


def test_deletion_is_exempt_even_with_root_twin(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    got = split_brain_duplicates(STUDIO, tmp_path, [("studio/package.json", True)])
    assert got == []


def test_root_level_path_is_exempt(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    assert split_brain_duplicates(STUDIO, tmp_path, [("package.json", False)]) == []


def test_twin_is_directory_not_file_not_flagged(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    assert split_brain_duplicates(STUDIO, tmp_path, [("studio/src/keep.ts", False)]) == []


def test_multiple_mixed_orders_report_only_real_duplicates(tmp_path: Path) -> None:
    svc = tmp_path / "src" / "services"
    svc.mkdir(parents=True)
    (svc / "apiClient.ts").write_text("export {}\n", encoding="utf-8")
    mapped = [
        ("studio/src/services/apiClient.ts", False),  # twin src/services/... exists -> flag
        ("studio/src/utils/api.ts", False),           # no twin -> pass
        ("studio/package.json", True),                # deletion -> exempt
        ("README.md", False),                          # root-level -> exempt
    ]
    got = split_brain_duplicates(STUDIO, tmp_path, mapped)
    assert got == ["studio/src/services/apiClient.ts"]


# ---------------------------------------------------------------------------
# deletion_paths — diff parser feeding the exemption
# ---------------------------------------------------------------------------


def test_deletion_paths_detects_deleted_file() -> None:
    diff = (
        "diff --git a/studio/package.json b/studio/package.json\n"
        "deleted file mode 100644\n"
        "--- a/studio/package.json\n"
        "+++ /dev/null\n"
    )
    assert deletion_paths(diff) == {"studio/package.json"}


def test_deletion_paths_ignores_modify_and_add() -> None:
    diff = (
        "diff --git a/studio/package.json b/studio/package.json\n"
        "index 1111111..2222222 100644\n"
        "--- a/studio/package.json\n"
        "+++ b/studio/package.json\n"
        "diff --git a/new.txt b/new.txt\n"
        "new file mode 100644\n"
    )
    assert deletion_paths(diff) == set()


def test_deletion_paths_empty_and_multi() -> None:
    assert deletion_paths("") == set()
    diff = (
        "diff --git a/a/x b/a/x\ndeleted file mode 100644\n"
        "diff --git a/b/y b/b/y\ndeleted file mode 100755\n"
    )
    assert deletion_paths(diff) == {"a/x", "b/y"}


# ---------------------------------------------------------------------------
# Live tree sanity: the guard must not classify the monorepo's own studio/
# workspace as a duplicate target (guard is satellite-only by PRIVATE_REPO skip).
# ---------------------------------------------------------------------------


def test_live_monorepo_studio_namespace_is_legit_workspace() -> None:
    assert (REPO_ROOT / "studio" / "package.json").is_file()
    # monorepo keeps studio/ as a workspace namespace; guard exempts PRIVATE_REPO entirely
    assert split_brain_duplicates(PRIVATE_REPO, REPO_ROOT, [("studio/package.json", False)]) == []
