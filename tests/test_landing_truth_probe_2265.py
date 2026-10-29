#!/usr/bin/env python3
"""Offline tests for the landing_truth_probe lane-2 blindness fix (#2265).

The probe (#2158 fallback protocol) stamps honest landing truth before any
terminal `bridge:rejected`. R56 (#2265) proved it structurally blind to the
direct solver lane: OPEN_REPO was absent from the probe's repo iteration and
the head filter knew only `bridge-land/<task_id>` while the solver lane lands
`bridge/<taskId>` PRs on the open repo — 15 WOs stranded open post-merge
(75% of the queue window). Layer 2 additionally discarded its fetched
100-commit page: gh_paged raises its fail-honest cap AFTER extending items,
so `max_pages=1` on a high-volume repo = scan nothing, return "unknown"
(live-proven: #2212/#2228 blank verdicts, reason "pagination cap reached
(1 pages)").

Fix under test:
  1. probe-local repo order = OPEN_REPO first + BRIDGE_TARGET_REPOS (the
     sync/routing tuple stays untouched);
  2. both head prefixes probed (v2 `bridge-land/`, solver `bridge/`);
  3. layer 2 fetches via cap-tolerant gh_first_page and always scans what it
     fetched, noting the newest-100 window honestly in evidence;
  4. three-state contract unchanged (landed / absent / unknown fail-closed).

Network-free: gh_paged and gh_first_page are monkeypatched at module level;
call order is recorded so the "open repo first, one cheap call" property is
asserted, not just the verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bridge import bridge_intake as intake  # noqa: E402

TASK = "bridge-20261028-render2225-buildplane-evidence"
OPEN = intake.OPEN_REPO
FIRST_PRIVATE = intake.BRIDGE_TARGET_REPOS[0]


def _pr(number: int, repo: str, head_ref: str, merged_at: str | None = "2026-10-28T19:30:00Z"):
    return {
        "number": number,
        "head": {"ref": head_ref},
        "merged_at": merged_at,
        "merge_commit_sha": "abc123def4567890" if merged_at else None,
    }


def _commit(sha: str, first_line: str):
    return {"sha": sha, "commit": {"message": first_line + "\n\nbody"}}


class _Recorder:
    """Records (repo, head-ref) layer-1 lookups and serves canned responses."""

    def __init__(self, pulls_by_head=None, commits_by_repo=None, error_on=()):
        self.calls: list[tuple[str, str]] = []
        self.pulls = pulls_by_head or {}
        self.commits = commits_by_repo or {}
        self.error_on = set(error_on)

    def fake_gh_paged(self, path: str, token: str, max_pages: int = 10):
        head = path.split("head=", 1)[1].split("&", 1)[0] if "head=" in path else ""
        repo = path.split("/repos/", 1)[1].split("/pulls", 1)[0] if "/pulls" in path else ""
        self.calls.append((repo, head))
        if (repo, head) in self.error_on:
            raise intake.BridgeError(f"github GET {path} -> HTTP 500: boom")
        return list(self.pulls.get((repo, head), []))

    def fake_gh_first_page(self, path: str, token: str):
        repo = path.split("/repos/", 1)[1].split("/commits", 1)[0]
        if (repo, "") in self.error_on:
            raise intake.BridgeError(f"github GET {path} -> HTTP 500: boom")
        items, has_more = self.commits.get(repo, ([], False))
        return list(items), has_more


def test_solver_lane_open_repo_pr_is_found_first_call(monkeypatch):
    """The 15-WO stranded class: solver PR on the open repo, head bridge/<tid>.

    Must return landed on the FIRST layer-1 call (open repo, solver prefix) —
    the option-A "one cheap call" property.
    """
    rec = _Recorder(
        pulls_by_head={
            (OPEN, f"Supremeai-bd:bridge/{TASK}"): [_pr(2248, OPEN, f"bridge/{TASK}")],
        }
    )
    monkeypatch.setattr(intake, "gh_paged", rec.fake_gh_paged)
    monkeypatch.setattr(intake, "gh_first_page", rec.fake_gh_first_page)
    state, ev = intake.landing_truth_probe("t0k3n", TASK)
    assert state == "landed"
    assert "#2248" in ev and OPEN in ev
    assert rec.calls[0] == (OPEN, f"Supremeai-bd:bridge/{TASK}")


def test_v2_lane_private_repo_pr_still_found(monkeypatch):
    """v2-lane regression guard: bridge-land/ PR on a private target still lands."""
    rec = _Recorder(
        pulls_by_head={
            (FIRST_PRIVATE, f"Supremeai-bd:bridge-land/{TASK}"): [
                _pr(2100, FIRST_PRIVATE, f"bridge-land/{TASK}")
            ],
        }
    )
    monkeypatch.setattr(intake, "gh_paged", rec.fake_gh_paged)
    monkeypatch.setattr(intake, "gh_first_page", rec.fake_gh_first_page)
    state, ev = intake.landing_truth_probe("t0k3n", TASK)
    assert state == "landed"
    assert f"#{2100}" in ev and FIRST_PRIVATE in ev


def test_closed_unmerged_pr_is_not_landing_evidence(monkeypatch):
    """A closed-but-unmerged PR (merged_at null) must NOT stamp landed."""
    rec = _Recorder(
        pulls_by_head={
            (OPEN, f"Supremeai-bd:bridge/{TASK}"): [_pr(2248, OPEN, f"bridge/{TASK}", merged_at=None)],
        }
    )
    monkeypatch.setattr(intake, "gh_paged", rec.fake_gh_paged)
    monkeypatch.setattr(intake, "gh_first_page", rec.fake_gh_first_page)
    state, ev = intake.landing_truth_probe("t0k3n", TASK)
    assert state == "absent"
    assert ev == ""


def test_layer2_squash_hit_on_open_repo_with_window_note(monkeypatch):
    """Layer 2 finds the squash commit on the open repo and notes the window."""
    rec = _Recorder(
        commits_by_repo={
            OPEN: ([_commit("deadbeefcafe", f"feat(bridge): report receipt ({TASK}) (#2248)")], True),
        }
    )
    monkeypatch.setattr(intake, "gh_paged", rec.fake_gh_paged)
    monkeypatch.setattr(intake, "gh_first_page", rec.fake_gh_first_page)
    state, ev = intake.landing_truth_probe("t0k3n", TASK)
    assert state == "landed"
    assert "deadbeef" in ev and OPEN in ev and "newest-100 window" in ev


def test_layer2_scans_fetched_page_even_when_more_pages_exist(monkeypatch):
    """The #2265 dead-code fix: has_more=True must not discard the fetched page.

    Regression for the raise-after-fetch behavior: under gh_paged(max_pages=1)
    the 100 fetched commits were thrown away on every high-volume repo.
    """
    hit_on_last = _commit("f00dcafe1234", f"bridge({TASK}): landed work")
    filler = [_commit(f"sha{i:03d}", f"unrelated commit {i}") for i in range(99)]
    rec = _Recorder(commits_by_repo={OPEN: (filler + [hit_on_last], True)})
    monkeypatch.setattr(intake, "gh_paged", rec.fake_gh_paged)
    monkeypatch.setattr(intake, "gh_first_page", rec.fake_gh_first_page)
    state, ev = intake.landing_truth_probe("t0k3n", TASK)
    assert state == "landed"
    assert "f00dcafe" in ev


def test_api_errors_yield_unknown_fail_closed(monkeypatch):
    """API failure anywhere -> ("unknown", reason) — never a honest-looking absent."""
    rec = _Recorder(error_on={(OPEN, f"Supremeai-bd:bridge/{TASK}")})
    monkeypatch.setattr(intake, "gh_paged", rec.fake_gh_paged)
    monkeypatch.setattr(intake, "gh_first_page", rec.fake_gh_first_page)
    state, ev = intake.landing_truth_probe("t0k3n", TASK)
    assert state == "unknown"
    # reason is contractually truncated to 60 chars per error — assert shape.
    assert "pulls github GET" in ev


def test_clean_negative_is_absent(monkeypatch):
    """Two definitively-negative layers -> ("absent", "") — the honest rejection."""
    rec = _Recorder()
    monkeypatch.setattr(intake, "gh_paged", rec.fake_gh_paged)
    monkeypatch.setattr(intake, "gh_first_page", rec.fake_gh_first_page)
    state, ev = intake.landing_truth_probe("t0k3n", TASK)
    assert state == "absent"
    assert ev == ""


def test_probe_repo_order_open_first_then_private_tuple():
    """OPEN_REPO leads the probe order; the BRIDGE_TARGET_REPOS tuple itself is untouched."""
    rec = _Recorder()
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(intake, "gh_paged", rec.fake_gh_paged)
        monkeypatch.setattr(intake, "gh_first_page", rec.fake_gh_first_page)
        intake.landing_truth_probe("t0k3n", TASK)
    finally:
        monkeypatch.undo()
    looked_at = [repo for repo, _head in rec.calls]
    assert looked_at[0] == OPEN
    assert set(looked_at) == {OPEN} | set(intake.BRIDGE_TARGET_REPOS)
    # BRIDGE_TARGET_REPOS (sync/routing SSOT) must remain exactly as before.
    assert intake.BRIDGE_TARGET_REPOS == (
        "Supremeai-bd/supremeai",
        "Supremeai-bd/supremeai-studio",
        "Supremeai-bd/supremeai-api",
        "Supremeai-bd/supremeai-core",
        "Supremeai-bd/supremeai-vscode",
        "Supremeai-bd/supremeai-browser",
        "Supremeai-bd/supremeai-archive",
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
