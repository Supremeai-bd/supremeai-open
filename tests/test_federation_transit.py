#!/usr/bin/env python3
"""Offline contract tests for the Federation Transit Pipeline (issue #514).

Covers the agent-side slice of the 4-Tier Transit Pipeline:

  * Tier 2 — `scripts/ci/hourly_satellite_batcher.py`: hourly cron
    contract (`0 * * * *`), ECOSYSTEM_MAP §3.1 routing matrix SSOT,
    fail-closed unrouted quarantine, monorepo-designated path split,
    40-hex SHA intake, window semantics, Tier-3 urgent bypass,
    consolidated one-batch-per-satellite planning, target-freshness
    descendant proof (fail-closed on unknown SHA / cycle) and the
    3-way ingestion guard (no blind overwrites).
  * Tier 4 — `scripts/ci/staggered_rolling_train.py`: verbatim
    11-satellite / 110-minute anti-contention schedule, no-overlap
    invariant, modulo-based deterministic slot resolution with exact
    cycle wrap, canonical repo-name normalization (`supremeai-infra`
    → `supremeai-infrastructure`), fail-closed consolidation planning
    and the Tier-3 urgent bypass.
  * Pre-Push Rebase Invariant — `scripts/agents/
    continuous_agent_loop.py`: fetch ➔ measure behind ➔ rebase ➔
    abort-on-failure fail-closed guard, wired into step_7_record
    BEFORE the fork push, with mandatory post-rebase re-verification.

Pure stdlib, fully offline (git interactions are simulated via a scripted
run_cmd double — no network, no repo mutation). Dual-mode: unittest and
pytest. Run: python3 -m unittest test_federation_transit -v
"""

from __future__ import annotations

import datetime as _dt
import inspect
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts" / "ci"))
sys.path.insert(0, str(_ROOT / "scripts" / "agents"))

import continuous_agent_loop as cal
import hourly_satellite_batcher as hb
import staggered_rolling_train as srt


def sha40(ch: str) -> str:
    """Deterministic 40-hex fixture from a single char."""
    base = format(ord(ch) % 16, "x")
    return base * 40


class CronContract(unittest.TestCase):
    def test_01_hourly_cron_is_verbatim(self):
        self.assertEqual(hb.BATCH_CRON, "0 * * * *")
        hb.validate_cron("0 * * * *")

    def test_02_other_cadences_rejected(self):
        for bad in ("*/30 * * * *", "0 0 * * *", "5 * * * *", "", "hourly"):
            with self.assertRaises(hb.BatchError, msg=bad):
                hb.validate_cron(bad)


class RoutingMatrixSSOT(unittest.TestCase):
    def test_03_every_satellite_row_resolves(self):
        expectations = {
            "studio/app.tsx": "studio",
            "examples/dashboard-preview/x.html": "studio",
            "api/gateway.ts": "api",
            "api-schemas/gateway.openapi.yaml": "api",
            "core/router.py": "core",
            "command/telegram.py": "command",
            "handlers/telegram_bot.py": "command",
            "skills/tool.json": "skills",
            "examples/langchain-mcp/README.md": "skills",
            "examples/vercel-ai/bot.ts": "skills",
            "vscode/extension.ts": "vscode",
            "agents/loop.py": "agents",
            "runner/worker.py": "agents",
            "api-schemas/agent-runner.v1.json": "agents",
            "browser/sandbox.ts": "browser",
            "sandbox/stealth.py": "browser",
            "sdk/client.ts": "sdk",
            "examples/sdk-quickstart.py": "sdk",
            "api-schemas/telemetry-log.v1.json": "sdk",
            "deployments/render.yaml": "infra",
            "infra/terraform.tf": "infra",
            "docs/archive/2026.md": "archive",
            "docs/ledger/x.md": "archive",
            "infrastructure/mcp-control-plane/src/x.ts": "mcp",
            "api-schemas/heartbeat.v1.json": "mcp",
        }
        for path, expected in expectations.items():
            self.assertEqual(hb.route_path(path), expected, msg=path)

    def test_04_monorepo_paths_never_ride_a_satellite(self):
        for path in (
            "scripts/agents/loop.py",
            "docs/SPEC.md",
            "patches/x.patch",
            "AGENTS.md",
        ):
            self.assertEqual(hb.route_path(path), "monorepo", msg=path)

    def test_05_unrouted_paths_fail_closed_to_quarantine(self):
        for path in ("README.md", "mcp.json", "api-schemas/unknown.x", "misc/file.bin"):
            self.assertIsNone(hb.route_path(path), msg=path)

    def test_06_invalid_path_rejected(self):
        for bad in ("", " leading", "trailing ", None, 7):
            with self.assertRaises(hb.BatchError, msg=repr(bad)):
                hb.route_path(bad)


class ShaIntake(unittest.TestCase):
    def test_07_valid_40hex_accepted(self):
        self.assertEqual(hb.validate_sha(sha40("a")), hb.validate_sha(sha40("a")))

    def test_08_malformed_sha_rejected(self):
        for bad in ("", "abc", "G" * 40, "g" * 40, 123, None):
            with self.assertRaises(hb.BatchError, msg=repr(bad)):
                hb.validate_sha(bad)


class WindowAndUrgent(unittest.TestCase):
    WIN = ("2026-10-17T08:00:00Z", "2026-10-17T09:00:00Z")

    def test_09_window_is_half_open(self):
        start, end = self.WIN
        self.assertTrue(hb.in_batch_window("2026-10-17T08:00:00Z", start, end))
        self.assertTrue(hb.in_batch_window("2026-10-17T08:59:59Z", start, end))
        self.assertFalse(hb.in_batch_window("2026-10-17T09:00:00Z", start, end))
        self.assertFalse(hb.in_batch_window("2026-10-17T07:59:59Z", start, end))

    def test_10_malformed_and_inverted_windows_rejected(self):
        start, end = self.WIN
        with self.assertRaises(hb.BatchError):
            hb.in_batch_window("not-a-time", start, end)
        with self.assertRaises(hb.BatchError):
            hb.in_batch_window("2026-10-17T08:30:00Z", end, start)

    def test_11_tier3_urgent_labels(self):
        self.assertTrue(hb.is_urgent(["bridge:urgent"]))
        self.assertTrue(hb.is_urgent({"fast-track"}))
        self.assertFalse(hb.is_urgent(["repo:studio", "P1-high"]))
        with self.assertRaises(hb.BatchError):
            hb.is_urgent([42])
        with self.assertRaises(hb.BatchError):
            hb.is_urgent(7)


class BatchPlanning(unittest.TestCase):
    START = "2026-10-17T08:00:00Z"
    END = "2026-10-17T09:00:00Z"

    def _plan(self, commits, **kw):
        return hb.plan_batches(commits, self.START, self.END, **kw)

    def test_12_consolidated_one_batch_per_satellite(self):
        s1, s2 = sha40("1"), sha40("2")
        plan = self._plan(
            [
                hb.LandedCommit(
                    s1, ("studio/a.tsx", "studio/b.tsx"), "2026-10-17T08:10:00Z"
                ),
                hb.LandedCommit(s2, ("studio/c.tsx",), "2026-10-17T08:20:00Z"),
            ]
        )
        self.assertEqual(len(plan.batches), 1)
        batch = plan.batches[0]
        self.assertEqual(batch.satellite, "studio")
        self.assertEqual(batch.shas, (s1, s2))  # landing order kept
        self.assertEqual(batch.files, ("studio/a.tsx", "studio/b.tsx", "studio/c.tsx"))
        self.assertFalse(batch.urgent)

    def test_13_outside_window_excluded_unless_urgent(self):
        inside, outside = sha40("3"), sha40("4")
        plan = self._plan(
            [
                hb.LandedCommit(inside, ("api/x.ts",), "2026-10-17T08:30:00Z"),
                hb.LandedCommit(outside, ("api/y.ts",), "2026-10-17T07:00:00Z"),
            ]
        )
        self.assertEqual([b.shas for b in plan.batches], [(inside,)])
        bypassed = self._plan(
            [
                hb.LandedCommit(
                    outside,
                    ("api/y.ts",),
                    "2026-10-17T07:00:00Z",
                    frozenset({"bridge:urgent"}),
                ),
            ]
        )
        self.assertEqual(len(bypassed.batches), 1)
        self.assertTrue(bypassed.batches[0].urgent)
        self.assertEqual(bypassed.batches[0].shas, (outside,))

    def test_14_unrouted_quarantined_monorepo_split(self):
        s = sha40("5")
        plan = self._plan(
            [
                hb.LandedCommit(
                    s, ("misc/unknown.bin", "docs/SPEC.md"), "2026-10-17T08:10:00Z"
                ),
            ]
        )
        self.assertEqual(plan.unrouted, ((s, "misc/unknown.bin"),))
        self.assertEqual(plan.monorepo_paths, ("docs/SPEC.md",))
        self.assertEqual(plan.batches, ())

    def test_15_deterministic_sorted_output(self):
        s1, s2 = sha40("6"), sha40("7")
        plan_a = self._plan(
            [
                hb.LandedCommit(
                    s1, ("api/a.ts", "studio/b.tsx"), "2026-10-17T08:01:00Z"
                ),
                hb.LandedCommit(s2, ("browser/c.ts",), "2026-10-17T08:02:00Z"),
            ]
        )
        plan_b = self._plan(
            [
                hb.LandedCommit(s2, ("browser/c.ts",), "2026-10-17T08:02:00Z"),
                hb.LandedCommit(
                    s1, ("api/a.ts", "studio/b.tsx"), "2026-10-17T08:01:00Z"
                ),
            ]
        )
        self.assertEqual(plan_a, plan_b)
        self.assertEqual(
            [b.satellite for b in plan_a.batches],
            sorted(b.satellite for b in plan_a.batches),
        )

    def test_16_non_commit_input_rejected(self):
        with self.assertRaises(hb.BatchError):
            self._plan([("deadbeef",)])

    def test_17_landed_commit_validates_payload(self):
        with self.assertRaises(hb.BatchError):
            hb.LandedCommit("short", ("api/x.ts",), "2026-10-17T08:00:00Z")
        with self.assertRaises(hb.BatchError):
            hb.LandedCommit(sha40("8"), (), "2026-10-17T08:00:00Z")
        with self.assertRaises(hb.BatchError):
            hb.LandedCommit(sha40("9"), ("api/x.ts",), "yesterday")


class FreshnessAndThreeWay(unittest.TestCase):
    def test_18_descendant_proof(self):
        base, head = sha40("a"), sha40("b")
        parents = {head: base}
        self.assertTrue(hb.is_descendant(head, base, parents))
        self.assertTrue(hb.is_descendant(head, head, parents))  # no-op sync

    def test_19_unknown_sha_fails_closed(self):
        base, head, ghost = sha40("a"), sha40("b"), sha40("c")
        with self.assertRaises(hb.FreshnessViolation):
            hb.is_descendant(head, base, {base: ghost})  # head unreachable

    def test_20_ancestry_cycle_fails_closed(self):
        x, y, outside = sha40("d"), sha40("e"), sha40("0")
        with self.assertRaises(hb.FreshnessViolation):
            # x → y → x cycle; base lies outside the cycle → proof impossible
            hb.is_descendant(x, outside, {x: y, y: x})

    def test_21_three_way_conflict_detection(self):
        base, mid, head = sha40("1"), sha40("2"), sha40("3")
        parents = {head: mid, mid: base}
        commit_files = {mid: ("browser/a.ts",), head: ("browser/b.ts",)}
        self.assertEqual(
            hb.three_way_check(
                ("browser/fresh.ts",), base, head, parents, commit_files
            ),
            (),
        )
        self.assertEqual(
            hb.three_way_check(("browser/a.ts",), base, head, parents, commit_files),
            ("browser/a.ts",),
        )
        self.assertEqual(
            hb.three_way_check(("browser/b.ts",), base, head, parents, commit_files),
            ("browser/b.ts",),
        )

    def test_22_three_way_requires_descendant_target(self):
        base, head = sha40("4"), sha40("5")
        with self.assertRaises(hb.FreshnessViolation):
            hb.three_way_check(("x",), base, head, {head: sha40("6")}, {})

    def test_23_plan_rejects_conflicting_batch(self):
        base, head = sha40("7"), sha40("8")
        commit = hb.LandedCommit(head, ("browser/a.ts",), "2026-10-17T08:10:00Z")
        with self.assertRaises(hb.BatchConflict):
            hb.plan_batches(
                [commit],
                "2026-10-17T08:00:00Z",
                "2026-10-17T09:00:00Z",
                last_synced={"browser": base},
                target_heads={"browser": head},
                parents={head: base},
                commit_files={head: ("browser/a.ts",)},
            )

    def test_24_plan_rejects_stale_target(self):
        older, mid, head = sha40("1"), sha40("2"), sha40("3")
        commit = hb.LandedCommit(mid, ("studio/a.tsx",), "2026-10-17T08:10:00Z")
        with self.assertRaises(hb.FreshnessViolation):
            # sync base (head) is NEWER than the target HEAD (mid) → stale target
            hb.plan_batches(
                [commit],
                "2026-10-17T08:00:00Z",
                "2026-10-17T09:00:00Z",
                last_synced={"studio": head},
                target_heads={"studio": mid},
                parents={head: mid, mid: older},
                commit_files={},
            )


class RollingSchedule(unittest.TestCase):
    def test_25_verbatim_tier4_schedule(self):
        self.assertEqual(
            [(s.minute, s.satellite) for s in srt.ROLLING_SCHEDULE],
            [
                (0, "open"),
                (10, "studio"),
                (20, "browser"),
                (30, "api"),
                (40, "skills"),
                (50, "vscode"),
                (60, "command"),
                (70, "agents"),
                (80, "archive"),
                (90, "infra"),
                (100, "sdk"),
            ],
        )
        self.assertEqual(srt.CYCLE_MINUTES, 110)
        self.assertEqual(srt.SLOT_MINUTES, 10)
        srt.assert_no_overlap()

    def test_26_schedule_invariant_enforced(self):
        with self.assertRaises(srt.TrainError):
            srt.assert_no_overlap((srt.ROLLING_SCHEDULE[0], srt.ROLLING_SCHEDULE[0]))
        with self.assertRaises(srt.TrainError):
            srt.assert_no_overlap((srt.Slot(0, "open"), srt.Slot(5, "studio")))
        with self.assertRaises(srt.TrainError):
            srt.assert_no_overlap(tuple(srt.ROLLING_SCHEDULE)[:10])
        with self.assertRaises(srt.TrainError):
            srt.assert_no_overlap(tuple(reversed(srt.ROLLING_SCHEDULE)))

    def test_27_canonical_repo_names(self):
        self.assertEqual(srt.full_repo_name("open"), "Supremeai-bd/supremeai-open")
        self.assertEqual(
            srt.full_repo_name("infra"), "Supremeai-bd/supremeai-infrastructure"
        )
        self.assertEqual(
            srt.full_repo_name("supremeai-infra"),
            "Supremeai-bd/supremeai-infrastructure",
        )  # issue alias
        self.assertEqual(srt.full_repo_name(" SDK "), "Supremeai-bd/supremeai-sdk")
        for bad in ("core", "", "supremeai", "unknown"):
            with self.assertRaises(srt.TrainError, msg=bad):
                srt.full_repo_name(bad)

    def test_28_deterministic_slot_resolution_and_wrap(self):
        epoch = _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)
        self.assertEqual(srt.active_slot(epoch).satellite, "open")
        self.assertEqual(
            srt.active_slot(epoch + _dt.timedelta(minutes=10)).satellite, "studio"
        )
        self.assertEqual(
            srt.active_slot(epoch + _dt.timedelta(minutes=109)).satellite, "sdk"
        )
        self.assertEqual(
            srt.active_slot(epoch + _dt.timedelta(minutes=110)).satellite, "open"
        )
        self.assertEqual(
            srt.active_slot(epoch + _dt.timedelta(minutes=110 + 45)).satellite, "skills"
        )
        self.assertEqual(
            srt.active_slot(_dt.datetime(1970, 1, 1, 0, 30)).satellite,
            "api",
        )  # naive=UTC

    def test_29_slot_type_and_bounds_enforced(self):
        with self.assertRaises(srt.TrainError):
            srt.active_slot("now")
        start, end = srt.slot_bounds(
            _dt.datetime(1970, 1, 1, 0, 12, tzinfo=_dt.timezone.utc)
        )
        self.assertEqual((end - start).total_seconds(), srt.SLOT_MINUTES * 60)

    def test_30_consolidation_plan_happy_path(self):
        base, head = sha40("1"), sha40("2")
        plan = srt.plan_consolidation(
            "archive",
            (head,),
            ("docs/ledger/c.md",),
            last_synced=base,
            target_head=head,
            parents={head: base},
            commit_files={head: ("docs/ledger/a.md",)},
        )
        self.assertEqual(plan.target, "Supremeai-bd/supremeai-archive")
        self.assertEqual(plan.satellite, "archive")

    def test_31_consolidation_fail_closed_paths(self):
        base, mid, head = sha40("3"), sha40("5"), sha40("4")
        with self.assertRaises(srt.BatchConflict):
            srt.plan_consolidation(
                "archive",
                (head,),
                ("docs/ledger/a.md",),
                last_synced=base,
                target_head=head,
                parents={head: base},
                commit_files={head: ("docs/ledger/a.md",)},
            )
        with self.assertRaises(srt.FreshnessViolation):
            # target HEAD (mid) is an ancestor of the sync base (head) → stale
            srt.plan_consolidation(
                "archive",
                (mid,),
                ("docs/ledger/c.md",),
                last_synced=head,
                target_head=mid,
                parents={head: mid, mid: base},
                commit_files={},
            )
        with self.assertRaises(srt.TrainError):
            srt.plan_consolidation(
                "sdk", (head,), ("sdk/x.ts",), last_synced=base, target_head=head
            )  # no bookkeeping
        with self.assertRaises(srt.TrainError):
            srt.plan_consolidation(
                "core", (head,), ("core/x.py",), last_synced=None, target_head=None
            )
        with self.assertRaises(srt.TrainError):
            srt.plan_consolidation(
                "studio", (), ("studio/x.tsx",), last_synced=None, target_head=None
            )

    def test_32_tier3_urgent_bypass(self):
        class Item:
            def __init__(self, urgent):
                self.urgent = urgent

        picked = srt.urgent_bypass([Item(True), Item(False), Item(True)])
        self.assertEqual(len(picked), 2)
        self.assertTrue(all(i.urgent for i in picked))
        self.assertEqual(srt.urgent_bypass([]), ())


class PrePushRebaseGuard(unittest.TestCase):
    """#514 invariant 1 — the guard is simulated via a scripted run_cmd."""

    @staticmethod
    def _script(script):
        def fake_run(cmd, cwd=None, check=False):
            text = " ".join(cmd)
            for prefix, outcome in script:
                if text.startswith(prefix):
                    return outcome
            return (0, "", "")

        return fake_run

    def setUp(self):
        self._original = cal.run_cmd
        self._original_log = cal.log
        cal.log = lambda *a, **k: None

    def tearDown(self):
        cal.run_cmd = self._original
        cal.log = self._original_log

    def test_33_fresh_base_passes_without_rebase(self):
        cal.run_cmd = self._script(
            [
                ("git rev-list", (0, "0\n", "")),
            ]
        )
        fresh, behind, _detail = cal.pre_push_rebase_guard()
        self.assertTrue(fresh)
        self.assertEqual(behind, 0)

    def test_34_stale_base_rebases_and_reports(self):
        cal.run_cmd = self._script(
            [
                ("git rev-list", (0, "3\n", "")),
                ("git rebase", (0, "", "")),
            ]
        )
        fresh, behind, detail = cal.pre_push_rebase_guard()
        self.assertTrue(fresh)
        self.assertEqual(behind, 3)
        self.assertIn("rebased", detail)

    def test_35_failed_rebase_aborts_fail_closed(self):
        seen = []
        script = [
            ("git rev-list", (0, "3\n", "")),
            ("git rebase", (1, "", "conflict")),
        ]

        def fake_run(cmd, cwd=None, check=False):
            text = " ".join(cmd)
            seen.append(text)
            for prefix, outcome in script:
                if text.startswith(prefix):
                    return outcome
            return (0, "", "")

        cal.run_cmd = fake_run
        fresh, behind, detail = cal.pre_push_rebase_guard()
        self.assertFalse(fresh)
        self.assertEqual(behind, 3)
        self.assertIn("aborted", detail)
        self.assertTrue(
            any("rebase --abort" in t for t in seen),
            "rebase --abort must run on failure",
        )

    def test_36_unverifiable_base_fails_closed(self):
        cal.run_cmd = self._script(
            [
                ("git fetch", (128, "", "network down")),
            ]
        )
        fresh, _behind, detail = cal.pre_push_rebase_guard()
        self.assertFalse(fresh)
        self.assertIn("fetch", detail)

        cal.run_cmd = self._script(
            [
                ("git rev-list", (1, "", "fatal")),
            ]
        )
        fresh, _, detail = cal.pre_push_rebase_guard()
        self.assertFalse(fresh)
        self.assertIn("behind-count", detail)

        cal.run_cmd = self._script(
            [
                ("git rev-list", (0, "not-a-number\n", "")),
            ]
        )
        fresh, _, detail = cal.pre_push_rebase_guard()
        self.assertFalse(fresh)
        self.assertIn("unparseable", detail)

    def test_37_fabricated_push_pipeline_stays_gone_guard_remains(self):
        # #1526/#1551 removed the fabricated step pipeline (step_4_branch,
        # step_6_verify, step_7_record, push_branch_to_fork, run_cycle): they
        # returned success without doing work (U2) and had zero dispatch-path
        # callers — branch/push/record belong to the bridge pipeline. The
        # honest #514 rebase guard stays as the library surface, fail-closed.
        for ghost in (
            "step_4_branch",
            "step_6_verify",
            "step_7_record",
            "push_branch_to_fork",
            "run_cycle",
        ):
            self.assertFalse(
                hasattr(cal, ghost),
                f"{ghost} was removed as fabricated success (U2) — it must not return",
            )
        doc = cal.pre_push_rebase_guard.__doc__ or ""
        self.assertIn("#514 Pre-Push Rebase Invariant", doc)
        self.assertIn("Fail-closed", doc)

    def test_38_guard_contract_documented(self):
        doc = cal.pre_push_rebase_guard.__doc__ or ""
        self.assertIn("#514", doc)
        self.assertIn("Fail-closed", doc)

    def test_39_pre_work_fresh_base_passes(self):
        cal.run_cmd = self._script(
            [
                ("git rev-list", (0, "0\n", "")),
            ]
        )
        synced, behind, detail = cal.pre_work_rebase_guard()
        self.assertTrue(synced)
        self.assertEqual(behind, 0)
        self.assertIn("fresh", detail)

    def test_40_pre_work_stale_base_rebases(self):
        cal.run_cmd = self._script(
            [
                ("git rev-list", (0, "2\n", "")),
                ("git rebase", (0, "", "")),
            ]
        )
        synced, behind, detail = cal.pre_work_rebase_guard()
        self.assertTrue(synced)
        self.assertEqual(behind, 2)
        self.assertIn("rebased", detail)

    def test_41_pre_work_failed_rebase_aborts_fail_closed(self):
        seen = []
        script = [
            ("git rev-list", (0, "2\n", "")),
            ("git rebase", (1, "", "conflict")),
        ]

        def fake_run(cmd, cwd=None, check=False):
            text = " ".join(cmd)
            seen.append(text)
            for prefix, outcome in script:
                if text.startswith(prefix):
                    return outcome
            return (0, "", "")

        cal.run_cmd = fake_run
        synced, behind, detail = cal.pre_work_rebase_guard()
        self.assertFalse(synced)
        self.assertEqual(behind, 2)
        self.assertIn("aborted", detail)
        self.assertTrue(any("rebase --abort" in t for t in seen))

    def test_42_pre_work_guard_delegates_to_pre_push_guard(self):
        # Start-of-Work Rebase Mandate: one honest implementation, no
        # duplicated rebase logic — pre_work delegates to pre_push.
        doc = cal.pre_work_rebase_guard.__doc__ or ""
        self.assertIn("Start-of-Work Rebase Mandate", doc)
        source = inspect.getsource(cal.pre_work_rebase_guard)
        self.assertIn("pre_push_rebase_guard()", source)

    def test_43_dispatch_cycle_wires_work_start_freshness(self):
        # #3891 wire-zero root fix (U6 mechanical guard): the guard stayed
        # defined-but-unwired since #1551 and a stale-tree loop run re-derived
        # fixed failures as live ground truth ("zombie darkness"). The dispatch
        # cycle MUST call the wiring helper pre-dispatch — removing the call
        # re-breaks the loop leg and fails this test.
        source = inspect.getsource(cal.run_dispatch_cycle)
        self.assertIn("wire_work_start_freshness", source)

    def test_44_freshness_helper_offline_skip_honest(self):
        # offline = no fetch (network call) — the guard is honestly skipped,
        # same discipline as step_2_rules()'s offline behavior.
        calls = []

        def counting_run(cmd, cwd=None, check=False):
            calls.append(" ".join(cmd))
            return (0, "", "")

        cal.run_cmd = counting_run
        line = cal.wire_work_start_freshness(True)
        self.assertIn("offline", line)
        self.assertIn("skipped", line)
        self.assertEqual(calls, [], "offline mode must not invoke any git command")

    def test_45_freshness_helper_fresh_tree(self):
        cal.run_cmd = self._script(
            [
                ("git fetch", (0, "", "")),
                ("git rev-list", (0, "0\n", "")),
            ]
        )
        line = cal.wire_work_start_freshness(False)
        self.assertIn("fresh", line)
        self.assertIn("0 behind", line)

    def test_46_freshness_helper_stale_tree_auto_rebases(self):
        cal.run_cmd = self._script(
            [
                ("git fetch", (0, "", "")),
                ("git rev-list", (0, "55\n", "")),
                ("git rebase", (0, "", "")),
            ]
        )
        line = cal.wire_work_start_freshness(False)
        self.assertIn("55", line)
        self.assertIn("auto-rebased", line)

    def test_47_freshness_helper_fail_proceeds_tagged(self):
        # Scout #3891 remedy-3: hard-abort rejected — a guard failure yields
        # the honest behind-count and dispatch proceeds tagged.
        cal.run_cmd = self._script(
            [
                ("git fetch", (128, "", "network down")),
            ]
        )
        line = cal.wire_work_start_freshness(False)
        self.assertIn("could not sync", line)
        self.assertIn("proceeds tagged", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
