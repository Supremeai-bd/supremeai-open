#!/usr/bin/env python3
"""tests/test_claim_ttl_expirer.py — contract tests for scripts/agents/claim_ttl_expirer.py.

The claim TTL expirer is wired into .github/workflows/pipeline.yml
("Smart Stale Claim Expirer", best-effort `|| true`) with a repo token and
performs DESTRUCTIVE board mutations: it strips `status:claimed` from other
agents' issues. It shipped with no test face and the same destructive
fail-open defect family fixed for cleanup_stale_branches.py in #4470:

  - fire-and-forget mutations: the return codes of `gh issue comment` and
    `gh issue edit` were ignored, so a failed release still printed
    "✅ Released claim on Issue #N" — a lying audit trail (worst variant:
    the release comment was posted BEFORE the label edit, so a failed edit
    left a "claim released" comment on an issue that was still claimed).
  - non-list `gh issue list` payloads (e.g. {"message": "Bad credentials"})
    crashed the scan with AttributeError instead of failing closed.
  - one unparseable updatedAt crashed the WHOLE watchdog (a board-wide
    outage of the self-healing claim janitor) instead of keeping just the
    malformed row.

Pins the fail-closed contract hermetically (no network, no gh, no time
mocking — the pure decision pass takes `now` explicitly):
  - unknown payload != empty board: gh failure, malformed JSON, and valid
    non-list JSON all abort with exit 1 and issue zero mutations;
  - the state change (label edit) runs FIRST and the audit comment is
    posted only after a successful edit — no lying comments ever;
  - a failed edit posts no comment and exits 1; a failed comment keeps the
    (real) release and exits 1 with an honest verdict;
  - anchor hubs, fresh issues, missing/malformed updatedAt rows are kept
    without crashing; --dry-run never mutates;
  - DEFAULT_TTL_HOURS mirrors claim_thresholds.CLAIM_IDLE_RELEASE_HOURS
    (#57 SSOT — no local hardcode on a release path).

Fully offline, stdlib-only, dual mode (unittest + pytest).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "agents"))

import claim_ttl_expirer as cte  # noqa: E402
from claim_thresholds import CLAIM_IDLE_RELEASE_HOURS  # noqa: E402


class FakeRun:
    """run_cmd stand-in routing by argv[2] (gh issue list|edit|comment).

    Mirrors the (rc, stdout, stderr) tuple contract and records every call
    so ordering assertions (edit before comment) are possible.
    """

    def __init__(self, *, list_rc=0, list_out="[]", list_err="", edit_rc=0, comment_rc=0):
        self.list_rc = list_rc
        self.list_out = list_out
        self.list_err = list_err
        self.edit_rc = edit_rc
        self.comment_rc = comment_rc
        self.calls: list = []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[2] == "list":
            return (self.list_rc, self.list_out, self.list_err)
        if args[2] == "edit":
            return (self.edit_rc, "", "")
        if args[2] == "comment":
            return (self.comment_rc, "", "")
        return (0, "", "")

    def edits(self):
        return [c for c in self.calls if c[2] == "edit"]

    def comments(self):
        return [c for c in self.calls if c[2] == "comment"]


STALE_TS = "2026-01-01T00:00:00Z"  # far in the past vs real wall clock
FRESH_TS = "2999-01-01T00:00:00Z"  # far in the future -> idle < 0 -> keep


def issue(num: int, ts: str = STALE_TS, title: str = "t") -> dict:
    return {
        "number": num,
        "title": title,
        "updatedAt": ts,
        "comments": [],
        "labels": ["status:claimed"],
    }


def run_main(fake: FakeRun, *, ttl: int = 3, dry_run: bool = False) -> int:
    with mock.patch.object(cte, "run_cmd", fake):
        return cte.check_and_expire_claims(ttl_hours=ttl, dry_run=dry_run)


class FailClosed(unittest.TestCase):
    def test_gh_list_failure_aborts_with_zero_mutations(self):
        fake = FakeRun(list_rc=1, list_err="gh: Bad credentials")
        rc = run_main(fake)
        self.assertEqual(rc, 1)
        self.assertEqual(fake.edits(), [])
        self.assertEqual(fake.comments(), [])

    def test_non_list_payload_aborts_with_zero_mutations(self):
        # A gh error body is valid JSON but not a board: unknown != empty.
        fake = FakeRun(list_out='{"message": "Bad credentials"}')
        rc = run_main(fake)
        self.assertEqual(rc, 1)
        self.assertEqual(fake.edits(), [])
        self.assertEqual(fake.comments(), [])

    def test_malformed_json_aborts_with_zero_mutations(self):
        fake = FakeRun(list_out="not-json-at-all")
        rc = run_main(fake)
        self.assertEqual(rc, 1)
        self.assertEqual(fake.edits(), [])
        self.assertEqual(fake.comments(), [])

    def test_string_number_row_never_reaches_release_path(self):
        # Unknown identity (number as string) must be kept, not released.
        row = {"number": "900", "title": "t", "updatedAt": STALE_TS}
        fake = FakeRun(list_out=json.dumps([row]))
        rc = run_main(fake)
        self.assertEqual(rc, 0)
        self.assertEqual(fake.edits(), [])
        self.assertEqual(fake.comments(), [])


class HonestReleaseOrdering(unittest.TestCase):
    def test_happy_path_edits_before_comment(self):
        fake = FakeRun(list_out=json.dumps([issue(900)]))
        rc = run_main(fake)
        self.assertEqual(rc, 0)
        self.assertEqual(len(fake.edits()), 1)
        self.assertEqual(len(fake.comments()), 1)
        edit_idx = fake.calls.index(fake.edits()[0])
        comment_idx = fake.calls.index(fake.comments()[0])
        self.assertLess(edit_idx, comment_idx, "state change must precede the audit comment")
        self.assertIn("status:claimed", fake.edits()[0])
        self.assertIn("status:unclaimed", fake.edits()[0])

    def test_failed_edit_posts_no_lying_comment_and_exits_1(self):
        fake = FakeRun(list_out=json.dumps([issue(900)]), edit_rc=1)
        rc = run_main(fake)
        self.assertEqual(rc, 1)
        self.assertEqual(len(fake.edits()), 1)
        self.assertEqual(fake.comments(), [], "no 'released' comment without the state change")

    def test_failed_comment_keeps_release_and_exits_1(self):
        fake = FakeRun(list_out=json.dumps([issue(900)]), comment_rc=1)
        rc = run_main(fake)
        self.assertEqual(rc, 1)
        self.assertEqual(len(fake.edits()), 1, "the real state change stands")
        self.assertEqual(len(fake.comments()), 1, "the comment attempt was made")


class KeepRules(unittest.TestCase):
    def test_dry_run_zero_mutations(self):
        fake = FakeRun(list_out=json.dumps([issue(900)]))
        rc = run_main(fake, dry_run=True)
        self.assertEqual(rc, 0)
        self.assertEqual(fake.edits(), [])
        self.assertEqual(fake.comments(), [])

    def test_anchor_hub_never_released(self):
        fake = FakeRun(list_out=json.dumps([issue(749)]))
        rc = run_main(fake)
        self.assertEqual(rc, 0)
        self.assertEqual(fake.edits(), [])

    def test_fresh_issue_kept(self):
        fake = FakeRun(list_out=json.dumps([issue(900, ts=FRESH_TS)]))
        rc = run_main(fake)
        self.assertEqual(rc, 0)
        self.assertEqual(fake.edits(), [])

    def test_missing_updatedat_kept(self):
        row = issue(900)
        row["updatedAt"] = ""
        fake = FakeRun(list_out=json.dumps([row]))
        rc = run_main(fake)
        self.assertEqual(rc, 0)
        self.assertEqual(fake.edits(), [])

    def test_unparseable_updatedat_kept_without_crashing_scan(self):
        # One malformed row must not take the whole watchdog down.
        fake = FakeRun(list_out=json.dumps([issue(901, ts="garbage"), issue(902)]))
        rc = run_main(fake)
        self.assertEqual(rc, 0)
        self.assertEqual(len(fake.edits()), 1, "healthy sibling issue is still released")
        self.assertNotIn("901", fake.edits()[0])


class PureDecisionPass(unittest.TestCase):
    def test_collect_expired_deterministic_plan(self):
        now = dt.datetime(2026, 10, 26, 12, 0, tzinfo=dt.timezone.utc)
        rows = [
            issue(900, ts="2026-10-26T08:00:00Z"),  # 4h idle -> due
            issue(901, ts="2026-10-26T10:30:00Z"),  # 1.5h idle -> keep
            issue(749, ts="2026-01-01T00:00:00Z"),  # anchor -> keep
            issue(902, ts="garbage"),               # malformed -> keep
            {"number": "bad", "updatedAt": STALE_TS},  # non-int -> keep
        ]
        plan = cte.collect_expired(rows, now, 3.0, {749})
        self.assertEqual([p["number"] for p in plan], [900])
        self.assertAlmostEqual(plan[0]["idle_hours"], 4.0, places=6)
        # Determinism: same inputs -> same plan.
        self.assertEqual(cte.collect_expired(rows, now, 3.0, {749}), plan)


class TtlSsot(unittest.TestCase):
    def test_default_ttl_mirrors_claim_thresholds(self):
        self.assertEqual(cte.DEFAULT_TTL_HOURS, CLAIM_IDLE_RELEASE_HOURS)
        self.assertEqual(cte.DEFAULT_TTL_HOURS, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
