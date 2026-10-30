#!/usr/bin/env python3
"""Offline tests for the cmd_sync solver-lane blindness fix (#2547).

Root cause (live-proven, #2516/#2547 census): the solver lane opens PRs
directly on the OPEN repo with head `bridge/<task_id>`, but cmd_sync only
scanned BRIDGE_TARGET_REPOS and only recognized `bridge-land/` refs — so a
merged solver-lane PR never reported LANDED and its public work-order stayed
open forever (the 12-row stranded cohort #2156..#2214, filed 2026-10-28,
still open on 2026-10-30).

Fix under test:
  1. closed-PR scan includes OPEN_REPO first (probe-era #2265 convention);
  2. both lane prefixes recognized via strip_lane_prefix (TASK_ID_RE-bound);
  3. landed/rejected loop and the in-gates reconciliation loop share the same
     two-lane recognition;
  4. BRIDGE_TARGET_REPOS SSOT untouched.

Network-free: gh_paged / gh / ensure_public_labels are monkeypatched at
module level; the close PATCH and label PUTs are recorded, not assumed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bridge import bridge_intake as intake  # noqa: E402

TASK = "bridge-20261030-sync-lane-fix"
OPEN = intake.OPEN_REPO


def _pr(number: int, repo: str, head_ref: str, merged_at: str | None = "2026-10-30T09:00:00Z"):
    return {
        "number": number,
        "head": {"ref": head_ref},
        "merged_at": merged_at,
        "merge_commit_sha": "abc123def4567890" if merged_at else None,
    }


def _wo_issue(number: int, task_id: str, labels: list[str] | None = None) -> dict:
    return {
        "number": number,
        "state": "open",
        "html_url": f"https://github.com/{OPEN}/issues/{number}",
        "labels": [{"name": name} for name in (labels if labels is not None else ["bridge:in-gates"])],
        "body": f"### Task ID\n\n{task_id}\n\n### Objective\n\nsolver-lane landing test",
    }


class _FakeGitHub:
    """Records every call; serves canned paged lists keyed by path prefix."""

    def __init__(self):
        self.paged_calls: list[str] = []
        self.gh_calls: list[tuple[str, str, dict | None]] = []
        self.paged_by_path: dict[str, list[dict]] = {}

    def feed(self, path_prefix: str, items: list[dict]) -> None:
        self.paged_by_path[path_prefix] = items

    def fake_gh_paged(self, path: str, token: str, max_pages: int = 10):
        self.paged_calls.append(path)
        for prefix, items in self.paged_by_path.items():
            if path.startswith(prefix):
                return list(items)
        return []

    def fake_gh(self, method: str, path: str, token: str, payload: dict | None = None):
        self.gh_calls.append((method, path, payload))
        return 200, {}

    def patched_paths(self, method: str) -> list[str]:
        return [p for m, p, _ in self.gh_calls if m == method]


@pytest.fixture()
def fake_github(monkeypatch: pytest.MonkeyPatch) -> _FakeGitHub:
    fake = _FakeGitHub()
    monkeypatch.setattr(intake, "gh_paged", fake.fake_gh_paged)
    monkeypatch.setattr(intake, "gh", fake.fake_gh)
    monkeypatch.setattr(intake, "ensure_public_labels", lambda token: None)
    return fake


def test_solver_lane_merged_pr_closes_public_issue(fake_github: _FakeGitHub):
    """The stranded-class fix: solver PR `bridge/<tid>` merged on OPEN repo."""
    fake_github.feed(f"/repos/{OPEN}/pulls?state=closed", [_pr(3300, OPEN, f"bridge/{TASK}")])
    fake_github.feed(f"/repos/{OPEN}/issues?state=open", [_wo_issue(2547, TASK)])
    state = fake_github.feed  # keep type-checkers happy about fixture reuse
    rc = intake.cmd_sync("t0k3n")
    assert rc == 0
    # The public work-order must be closed via PATCH (state completed).
    patches = fake_github.patched_paths("PATCH")
    assert f"/repos/{OPEN}/issues/2547" in patches
    # ...with the landed label stamped before closing.
    assert any(
        m == "PUT" and "/issues/2547/labels" in p for m, p, _ in fake_github.gh_calls
    )


def test_v2_lane_landed_pr_still_closes_public_issue(fake_github: _FakeGitHub):
    """Regression guard: the private-satellite `bridge-land/` lane is intact."""
    first_private = intake.BRIDGE_TARGET_REPOS[0]
    fake_github.feed(f"/repos/{first_private}/pulls?state=closed", [_pr(2100, first_private, f"bridge-land/{TASK}")])
    fake_github.feed(f"/repos/{OPEN}/issues?state=open", [_wo_issue(2547, TASK)])
    rc = intake.cmd_sync("t0k3n")
    assert rc == 0
    assert f"/repos/{OPEN}/issues/2547" in fake_github.patched_paths("PATCH")


def test_solver_lane_unmerged_pr_reports_rejected(fake_github: _FakeGitHub):
    """A closed-but-unmerged solver PR must reject, never close as landed."""
    fake_github.feed(f"/repos/{OPEN}/pulls?state=closed", [_pr(3300, OPEN, f"bridge/{TASK}", merged_at=None)])
    fake_github.feed(f"/repos/{OPEN}/issues?state=open", [_wo_issue(2547, TASK)])
    rc = intake.cmd_sync("t0k3n")
    assert rc == 0
    # No close PATCH, and a rejected label PUT is present.
    assert not fake_github.patched_paths("PATCH")
    assert any(
        m == "PUT" and "/issues/2547/labels" in p
        for m, p, payload in fake_github.gh_calls
        if payload and intake.LABEL_REJECTED in (payload or {}).get("labels", [])
    )


def test_open_solver_pr_reconciles_to_in_gates(fake_github: _FakeGitHub):
    """Open solver-lane PR on OPEN repo reconciles its WO to bridge:in-gates."""
    fake_github.feed(f"/repos/{OPEN}/pulls?state=open", [_pr(3301, OPEN, f"bridge/{TASK}", merged_at=None)])
    # WO currently carries only the stale queued label — reconciliation must
    # overwrite it to bridge:in-gates (the E2E-proven stale-label cleanup).
    fake_github.feed(f"/repos/{OPEN}/issues?state=open", [_wo_issue(2547, TASK, labels=["bridge:queued"])])
    rc = intake.cmd_sync("t0k3n")
    assert rc == 0
    assert any(
        m == "PUT" and "/issues/2547/labels" in p
        for m, p, payload in fake_github.gh_calls
        if payload and intake.LABEL_INGATES in (payload or {}).get("labels", [])
    )


def test_strip_lane_prefix_rejects_non_task_refs():
    """Non-bridge and shape-invalid refs are never lane candidates."""
    assert intake.strip_lane_prefix(f"bridge/{TASK}") == TASK
    assert intake.strip_lane_prefix(f"bridge-land/{TASK}") == TASK
    assert intake.strip_lane_prefix("bridge/notes") is None          # not a task-id shape
    assert intake.strip_lane_prefix("bridge-land/notes") is None      # not a task-id shape
    assert intake.strip_lane_prefix("feature/awesome") is None
    assert intake.strip_lane_prefix("bridge/") is None                # empty tail
    assert intake.strip_lane_prefix("") is None


def test_closed_scan_includes_open_repo_before_satellites(fake_github: _FakeGitHub):
    """OPEN_REPO is scanned first — the one-cheap-call probe-era convention."""
    fake_github.feed(f"/repos/{OPEN}/pulls?state=closed", [])
    rc = intake.cmd_sync("t0k3n")
    assert rc == 0
    pulls_scans = [p for p in fake_github.paged_calls if "state=closed" in p]
    assert pulls_scans[0].startswith(f"/repos/{OPEN}/")
    # The routing SSOT tuple is untouched (7 satellites, OPEN_REPO not inside).
    assert intake.BRIDGE_TARGET_REPOS == (
        "Supremeai-bd/supremeai",
        "Supremeai-bd/supremeai-studio",
        "Supremeai-bd/supremeai-api",
        "Supremeai-bd/supremeai-core",
        "Supremeai-bd/supremeai-vscode",
        "Supremeai-bd/supremeai-browser",
        "Supremeai-bd/supremeai-archive",
    )
    assert OPEN not in intake.BRIDGE_TARGET_REPOS


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
