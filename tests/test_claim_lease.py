#!/usr/bin/env python3
"""tests/test_claim_lease.py — offline battery for the claim-lease drop-in core.

Dual-mode: runs under pytest (``pytest tests/test_claim_lease.py``) AND as a
plain manual runner (``python3 tests/test_claim_lease.py``). Imports ONLY the
drop-in module and the stdlib — zero I/O, zero network, deterministic
(controlled ``now`` everywhere).

Groups (fixtures 1-7 preserved from the pre-2a operator suite; T-groups are
the #375 Phase 2a regression set):
  - SSOT mode (default): comment-only claims are INVISIBLE (T-C)
  - T-A  zombie-lease: events clock beats a manipulated fresh updatedAt
  - T-B  assignee-only claim via 'assigned' event, Stage 2
  - T-F  malformed events skipped AND counted
  - T-G  excluded + bridge: labels still skip in SSOT mode
  - LEGACY mode parity (deprecated transition flag)
  - T-E  release plan builder (pure, ordered, target vocabulary)
  - DIRECT: resolve_lease_clock / prefilter / branch matching / comment
    formatter contracts
"""

from __future__ import annotations

import datetime
import os
import sys
from importlib import util as _ilu

_MODULE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "ci", "claim_lease.py"
)
_spec = _ilu.spec_from_file_location("claim_lease", _MODULE_PATH)
claim_lease = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(claim_lease)  # type: ignore[union-attr]

evaluate_graduated_claims = claim_lease.evaluate_graduated_claims
build_release_plan = claim_lease.build_release_plan
build_release_comment = claim_lease.build_release_comment
parse_lease_events = claim_lease.parse_lease_events
resolve_lease_clock = claim_lease.resolve_lease_clock
claimed_candidate_numbers = claim_lease.claimed_candidate_numbers
issue_has_remote_branch = claim_lease.issue_has_remote_branch
extract_claim_timestamp = claim_lease.extract_claim_timestamp
CLAIMED_LABELS = claim_lease.CLAIMED_LABELS
UNCLAIMED_LABEL = claim_lease.UNCLAIMED_LABEL

BASE_TIME = datetime.datetime(2026, 10, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)


def iso(minute: int, hour: int = 11) -> str:
    return f"2026-10-15T{hour:02d}:{minute:02d}:00Z"


# ---- Shared fixtures (pre-2a operator suite, preserved) ---------------------

def preserved_fixtures():
    # Issue 1: Claimed 5 min ago, no branch -> NOT stale (within 10 min window)
    iss1 = {
        "number": 1,
        "title": "task 1",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(55)}],
    }
    # Issue 2: Claimed 15 min ago, NO branch -> STALE (Stage 1)
    iss2 = {
        "number": 2,
        "title": "task 2",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(45)}],
    }
    # Issue 3: Claimed 25 min ago, branch exists -> NOT stale (within 40 min)
    iss3 = {
        "number": 3,
        "title": "task 3",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(35)}],
    }
    # Issue 4: Claimed 45 min ago, branch exists but NO PR -> STALE (Stage 2)
    iss4 = {
        "number": 4,
        "title": "task 4",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(15)}],
    }
    # Issue 5: Claimed 50 min ago, PR exists -> NOT stale (PR active)
    iss5 = {
        "number": 5,
        "title": "task 5",
        "labels": [{"name": "P1-high"}],
        "comments": [{"body": "🎯 Claiming issue", "createdAt": iso(10)}],
    }
    # Issue 6: claimed LABEL but NO claim comment, 120m old -> STAGE 1 STALE.
    # Regression (#222 fallout): a NameError on exactly this input once killed
    # the whole releaser (and the agent-loop cron step with it).
    iss6 = {
        "number": 6,
        "title": "task 6",
        "labels": [{"name": "status:claimed"}],
        "comments": [],
        "updatedAt": "2026-10-15T10:00:00Z",
    }
    # Issue 7: plain unclaimed issue — must NOT be treated as claimed.
    iss7 = {
        "number": 7,
        "title": "task 7",
        "labels": [{"name": "P2-medium"}],
        "comments": [],
        "updatedAt": "2026-10-15T10:00:00Z",
    }
    return [iss1, iss2, iss3, iss4, iss5, iss6, iss7]


BRANCHES = ["feat/issue-3-contract", "fix/issue-4-repair", "fix/issue-5-patch"]
OPEN_PRS = {5}


# ---- Battery -----------------------------------------------------------------

def test_ssot_mode_comment_only_claims_invisible():
    """T-C + fixtures 1-7 under SSOT (default): only #6 is stale."""
    stale = evaluate_graduated_claims(
        preserved_fixtures(), OPEN_PRS, BRANCHES,
        now=BASE_TIME, events_by_issue={}, legacy_comments=False,
    )
    assert [s["number"] for s in stale] == [6], f"SSOT mode: expected only #6, got {stale}"
    assert stale[0]["stage"] == 1, stale[0]
    assert stale[0]["clock_source"] == "updatedAt-fallback", stale[0]
    assert stale[0]["assignees"] == [], stale[0]
    assert stale[0]["branch"] is None, stale[0]


def test_t_a_zombie_lease_events_beat_fresh_updatedat():
    """Labeled 15m ago per events; updatedAt refreshed 1m ago by unrelated
    activity. Fallback clock would see 1m (lease survives forever under
    activity — the zombie-lease defect). Events clock must expire it."""
    iss8 = {
        "number": 8,
        "title": "task 8 zombie lease",
        "labels": [{"name": "status:claimed"}],
        "comments": [],
        "updatedAt": "2026-10-15T11:59:00Z",
    }
    events8 = [
        {"event": "labeled", "label": {"name": "status:claimed"}, "created_at": iso(45)},
        {"event": "commented", "created_at": "2026-10-15T11:59:30Z"},
    ]
    stale8 = evaluate_graduated_claims(
        [iss8], set(), [], now=BASE_TIME, events_by_issue={8: events8}, legacy_comments=False
    )
    assert len(stale8) == 1 and stale8[0]["number"] == 8, f"T-A failed: {stale8}"
    assert stale8[0]["clock_source"] == "events", stale8[0]
    assert stale8[0]["stage"] == 1, stale8[0]


def test_t_b_assignee_only_claim_stage2():
    iss9 = {
        "number": 9,
        "title": "task 9 assignee claim",
        "labels": [{"name": "P1-high"}],
        "assignees": [{"login": "bot-agent-1"}],
        "comments": [],
        "updatedAt": "2026-10-15T11:59:00Z",
    }
    events9 = [{"event": "assigned", "assignee": {"login": "bot-agent-1"}, "created_at": iso(15)}]
    stale9 = evaluate_graduated_claims(
        [iss9], set(), BRANCHES + ["fix/issue-9-repair"], now=BASE_TIME,
        events_by_issue={9: events9}, legacy_comments=False,
    )
    assert len(stale9) == 1 and stale9[0]["number"] == 9 and stale9[0]["stage"] == 2, f"T-B failed: {stale9}"
    assert stale9[0]["clock_source"] == "events", stale9[0]
    assert stale9[0]["assignees"] == ["bot-agent-1"], stale9[0]
    assert stale9[0]["branch"] == "fix/issue-9-repair", stale9[0]


def test_t_b2_assignee_without_clock_never_released():
    """Assignee-only claim with NO events and NO updatedAt: claimed but
    undateable -> fail-conservative, never released."""
    iss10 = {
        "number": 10,
        "title": "task 10 undateable",
        "labels": [],
        "assignees": [{"login": "bot-agent-2"}],
        "comments": [],
    }
    stale10 = evaluate_graduated_claims(
        [iss10], set(), [], now=BASE_TIME, events_by_issue={}, legacy_comments=False
    )
    assert stale10 == [], f"fail-conservative violated: {stale10}"


def test_t_f_malformed_events_skip_and_count():
    events10 = [
        "not-a-dict",
        {"event": "labeled", "label": {"name": "status:claimed"}, "created_at": "not-a-timestamp"},
        {"event": "labeled", "label": {"name": "status:claimed"}, "created_at": iso(45)},
    ]
    parsed, malformed = parse_lease_events(events10)
    assert malformed == 2, f"T-F malformed count: {malformed}"
    assert len(parsed) == 1 and parsed[0][1] == "labeled", parsed


def test_t_g_exclusions_in_ssot_mode():
    iss11 = {
        "number": 11,
        "title": "task 11 excluded",
        "labels": [{"name": "status:claimed"}, {"name": "state:seq-hold"}],
        "updatedAt": "2026-10-15T09:00:00Z",
    }
    iss12 = {
        "number": 12,
        "title": "Bridge Work Order — anything",
        "labels": [{"name": "bridge:queued"}, {"name": "status:claimed"}],
        "updatedAt": "2026-10-15T09:00:00Z",
    }
    iss13 = {
        "number": 13,
        "title": "audit( quarterly review",
        "labels": [{"name": "status:claimed"}],
        "updatedAt": "2026-10-15T09:00:00Z",
    }
    stale_g = evaluate_graduated_claims(
        [iss11, iss12, iss13], set(), [], now=BASE_TIME, events_by_issue={}, legacy_comments=False
    )
    assert stale_g == [], f"T-G failed: {stale_g}"


def test_legacy_mode_parity():
    """Deprecated --legacy-comments semantics: original suite results."""
    stale_legacy = evaluate_graduated_claims(
        preserved_fixtures(), OPEN_PRS, BRANCHES,
        now=BASE_TIME, events_by_issue={}, legacy_comments=True,
    )
    assert len(stale_legacy) == 3, f"Legacy mode: expected 3 stale issues, got {len(stale_legacy)}"
    assert stale_legacy[0]["number"] == 2 and stale_legacy[0]["stage"] == 1, stale_legacy[0]
    assert stale_legacy[1]["number"] == 4 and stale_legacy[1]["stage"] == 2, stale_legacy[1]
    assert stale_legacy[2]["number"] == 6 and stale_legacy[2]["stage"] == 1, stale_legacy[2]
    assert all(s["number"] != 7 for s in stale_legacy), "Unlabeled issue must not be treated as claimed"
    assert all(
        s["clock_source"] == "legacy-comments" for s in stale_legacy if s["number"] in (2, 4)
    ), "comment-derived claims must be tagged legacy-comments"
    assert all(s["number"] not in (3, 5) for s in stale_legacy), stale_legacy


def test_t_e_release_plan_builder():
    plan = build_release_plan(
        ["status:claimed", "P1-high", "status:in-progress"], ["bot-agent-1", "bot-agent-2"]
    )
    assert plan[0] == {"op": "remove_label", "label": "status:claimed"}, plan
    assert plan[1] == {"op": "remove_label", "label": "status:in-progress"}, plan
    assert plan[2] == {"op": "add_label", "label": "status:unclaimed"}, plan
    assert plan[3] == {"op": "remove_assignees", "assignees": ["bot-agent-1", "bot-agent-2"]}, plan

    plan2 = build_release_plan(["status:claimed"], ["bot-agent-1"], keep_assignees=True)
    assert all(p["op"] != "remove_assignees" for p in plan2), plan2

    plan3 = build_release_plan(None)
    assert [p["label"] for p in plan3 if p["op"] == "remove_label"] == sorted(CLAIMED_LABELS), plan3
    assert any(p["op"] == "add_label" and p["label"] == "status:unclaimed" for p in plan3), plan3
    assert all(p["op"] != "remove_assignees" for p in plan3), plan3

    plan4 = build_release_plan(["P1-high"], [])
    assert all(p["op"] != "remove_label" for p in plan4), plan4
    assert plan4[0] == {"op": "add_label", "label": "status:unclaimed"}, plan4


def test_direct_resolve_lease_clock_contract():
    # events win
    dt, src = resolve_lease_clock(
        {"updatedAt": "2026-10-15T11:59:00Z"},
        [{"event": "assigned", "created_at": iso(30)}],
        True, ["a"],
    )
    assert src == "events" and dt is not None, (dt, src)
    # fallback tagged
    dt, src = resolve_lease_clock(
        {"updatedAt": "2026-10-15T11:00:00Z"}, [], True, []
    )
    assert src == "updatedAt-fallback" and dt is not None, (dt, src)
    # fail-conservative None/None
    dt, src = resolve_lease_clock({}, [], False, [])
    assert dt is None and src is None, (dt, src)
    # no claimed markers + no events -> None even with updatedAt present
    dt, src = resolve_lease_clock({"updatedAt": "2026-10-15T11:00:00Z"}, [], False, [])
    assert dt is None and src is None, (dt, src)


def test_direct_candidate_prefilter():
    issues = preserved_fixtures()
    # 6 carries status:claimed; 1-5 only comments (legacy, not SSOT-visible)
    assert claimed_candidate_numbers(issues) == [6], claimed_candidate_numbers(issues)
    iss_a = {"number": 20, "labels": [], "assignees": [{"login": "x"}]}
    assert claimed_candidate_numbers([iss_a]) == [20]


def test_direct_branch_matching():
    branches = ["feat/issue-3-contract", "fix/issue-4-repair", "bridge/task-77-x"]
    hit, name = issue_has_remote_branch(3, branches)
    assert hit and name == "feat/issue-3-contract", (hit, name)
    hit, name = issue_has_remote_branch(4, branches)
    assert hit and name == "fix/issue-4-repair", (hit, name)
    hit, name = issue_has_remote_branch(77, branches)
    assert hit and name == "bridge/task-77-x", (hit, name)
    hit, name = issue_has_remote_branch(99, branches)
    assert not hit and name is None, (hit, name)
    # numeric-substring must NOT false-positive (12 vs 123) — matcher delta
    hit, name = issue_has_remote_branch(12, ["feat/issue-123-x"])
    assert not hit, (hit, name)
    # legacy forms still match with boundary discipline
    hit, name = issue_has_remote_branch(12, ["issue12"])
    assert hit and name == "issue12", (hit, name)
    hit, name = issue_has_remote_branch(12, ["agent-work-issue-12-b"])
    assert hit and name == "agent-work-issue-12-b", (hit, name)


def test_direct_release_comment_formatter():
    c1 = build_release_comment(1, "No branch created within 10.0m of claim", 15.2)
    assert "Stage 1" in c1 and "status:unclaimed" in c1 and "clearing agent assignees" in c1, c1
    c2 = build_release_comment(2, "no PR", 41.0, keep_assignees=True)
    assert "Stage 2" in c2 and "clearing agent assignees" not in c2, c2


def test_direct_legacy_clock():
    iss = preserved_fixtures()[1]  # iss2: claim comment 15m ago
    dt = extract_claim_timestamp(iss)
    assert dt is not None and dt.strftime("%H:%M") == "11:45", dt
    iss6 = preserved_fixtures()[5]  # claimed label, no comments -> updatedAt
    dt6 = extract_claim_timestamp(iss6)
    assert dt6 is not None and dt6.strftime("%H:%M") == "10:00", dt6


def test_determinism_byte_identical():
    """Same inputs -> byte-identical stale records (no wall-clock leakage)."""
    a = evaluate_graduated_claims(
        preserved_fixtures(), OPEN_PRS, BRANCHES,
        now=BASE_TIME, events_by_issue={}, legacy_comments=False,
    )
    b = evaluate_graduated_claims(
        preserved_fixtures(), OPEN_PRS, BRANCHES,
        now=BASE_TIME, events_by_issue={}, legacy_comments=False,
    )
    assert repr(a) == repr(b), "nondeterministic output detected"


# ---- Manual runner --------------------------------------------------------------

def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"✅ claim_lease battery passed: {len(tests)} test groups, all asserts green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
