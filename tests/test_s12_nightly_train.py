#!/usr/bin/env python3
"""Offline contract tests for the S12 Nightly Consolidation Train
(issue #492).

Covers: MCP Tower boundary isolation (monorepo unreachable, 11-satellite
allowlist), the nightly cron contract (`0 0 * * *` UTC), heavy-suite
daytime exclusivity, fail-closed satellite-head ingest (all 11, unique,
40-hex), parity verification with P0 incident isolation, the
`nightly-YYYYMMDD` tag contract, the Phase 1-4 order gate and the
telemetry heartbeat broadcast (public embassy + Studio).

Pure stdlib. Run: python3 -m unittest test_s12_nightly_train -v
"""

import subprocess
import sys
import unittest
from pathlib import Path

TOWER = Path(__file__).resolve().parent.parent / "scripts" / "tower"
sys.path.insert(0, str(TOWER))

import nightly_train_reference as nt


def heads(sha: str = "b" * 40) -> tuple:
    return tuple(nt.SatelliteHead(s, sha) for s in nt.CANONICAL_SATELLITES)


class TowerBoundaryIsolation(unittest.TestCase):
    def test_01_monorepo_unreachable(self):
        for bad in (
            nt.PROPRIETARY_MONOREPO,
            "supremeai",
            "Supremeai-bd/supremeai",
            " supremeai ",
        ):
            with self.assertRaises(nt.TowerBoundaryViolation, msg=bad):
                nt.assert_tower_target(bad)

    def test_02_eleven_satellites_resolve(self):
        self.assertEqual(len(nt.CANONICAL_SATELLITES), 11)
        self.assertEqual(
            nt.CANONICAL_SATELLITES,
            (
                "open",
                "studio",
                "browser",
                "command",
                "skills",
                "vscode",
                "agents",
                "api",
                "infra",
                "sdk",
                "core",
            ),
        )
        for sat in nt.CANONICAL_SATELLITES:
            self.assertEqual(
                nt.assert_tower_target(f"Supremeai-bd/supremeai-{sat}"),
                f"Supremeai-bd/supremeai-{sat}",
            )

    def test_03_unknown_repo_rejected(self):
        with self.assertRaises(nt.TowerBoundaryViolation):
            nt.assert_tower_target("Supremeai-bd/unknown-repo")
        with self.assertRaises(nt.TowerBoundaryViolation):
            nt.assert_tower_target("some-org/random")

    def test_04_moat_and_vault_outside_tower(self):
        # The boundary rationale: core moat + vaults isolated from agents.
        self.assertTrue(nt.is_monorepo("Supremeai-BD/SupremeAI"))  # case-insensitive
        self.assertFalse(nt.is_monorepo("Supremeai-bd/supremeai-core"))
        # NOTE: the `core` SATELLITE is a satellite; only the bare monorepo
        # is isolated — documented distinction, both resolve via allowlist.
        nt.assert_tower_target("Supremeai-bd/supremeai-core")


class ScheduleContract(unittest.TestCase):
    def test_05_nightly_cron_exact(self):
        self.assertEqual(nt.NIGHTLY_CRON_UTC, "0 0 * * *")
        nt.validate_cron(nt.NIGHTLY_CRON_UTC)

    def test_06_cron_deviations_rejected(self):
        for expr, tz in (
            ("0 1 * * *", "UTC"),
            ("30 0 * * *", "UTC"),
            ("0 0 1 * *", "UTC"),
            ("0 0 * * *", "EST"),
            ("*/5 * * * *", "UTC"),
        ):
            with self.assertRaises(nt.ScheduleError, msg=(expr, tz)):
                nt.validate_cron(expr, tz)

    def test_07_heavy_suites_night_only(self):
        for suite in (
            "integration_smoke",
            "e2e_gateway_routing",
            "db_migrate_0007",
            "multi_model_fallback_probe",
            "cross_boundary_contract_check",
            "full_battery",
        ):
            self.assertTrue(nt.is_heavy_suite(suite), suite)
            with self.assertRaises(nt.ScheduleError):
                nt.assert_suite_allowed(suite, "daytime_satellite")
            nt.assert_suite_allowed(suite, "nightly_train")

    def test_08_light_suites_anytime(self):
        self.assertFalse(nt.is_heavy_suite("unit_ledger"))
        self.assertFalse(nt.is_heavy_suite("lint"))
        nt.assert_suite_allowed("unit_ledger", "daytime_satellite")
        nt.assert_suite_allowed("lint", "nightly_train")


class ConsolidationRun(unittest.TestCase):
    def test_09_ingest_all_eleven_fail_closed(self):
        self.assertEqual(len(nt.ingest_heads(heads())), 11)
        with self.assertRaises(nt.TrainError):
            nt.ingest_heads(heads()[:10])  # missing satellite
        with self.assertRaises(nt.TrainError):
            nt.ingest_heads(heads() + heads()[:1])  # duplicate
        with self.assertRaises(nt.TrainError):
            nt.ingest_heads(heads() + (nt.SatelliteHead("unknown", "b" * 40),))
        with self.assertRaises(nt.TrainError):
            nt.ingest_heads((nt.SatelliteHead("api", "zzz"),) + heads()[1:])
        with self.assertRaises(nt.TrainError):
            nt.ingest_heads((nt.SatelliteHead("api", "b" * 39),) + heads()[1:])

    def test_10_tag_contract(self):
        run = nt.ConsolidationRun(run_date="20261018", satellite_heads=heads())
        self.assertEqual(run.tag, "nightly-20261018")
        with self.assertRaises(nt.TrainError):
            nt.ConsolidationRun(run_date="2026-10-18").tag
        with self.assertRaises(nt.TrainError):
            nt.ConsolidationRun(run_date="202610").tag

    def test_11_parity_happy_and_drift(self):
        expected = {s: "b" * 40 for s in nt.CANONICAL_SATELLITES}
        run = nt.ConsolidationRun(run_date="20261018", satellite_heads=heads())
        records = nt.verify_parity(run, expected)
        self.assertTrue(nt.full_parity(records))
        self.assertEqual(len(records), 11)

        drifted = tuple(
            nt.SatelliteHead("sdk", "c" * 40) if s == "sdk" else h
            for s, h in ((h.satellite, h) for h in heads())
        )
        run2 = nt.ConsolidationRun(run_date="20261018", satellite_heads=drifted)
        records2 = nt.verify_parity(run2, expected)
        self.assertFalse(nt.full_parity(records2))
        sdk = next(r for r in records2 if r.satellite == "sdk")
        self.assertEqual(sdk.verdict, "DRIFT")
        self.assertTrue(sdk.p0_incident)
        self.assertEqual(sdk.isolated_commit, "c" * 40)
        self.assertEqual(sdk.expected_sha, "b" * 40)

    def test_12_missing_satellite_flagged(self):
        expected = {s: "b" * 40 for s in nt.CANONICAL_SATELLITES}
        partial = nt.ConsolidationRun(
            run_date="20261018", satellite_heads=heads()[:10]
        )  # 'vscode' missing (index 5)
        records = nt.verify_parity(partial, expected)
        missing = [r for r in records if r.verdict == "MISSING"]
        self.assertEqual(len(missing), 1)
        self.assertFalse(missing[0].satellite in {h.satellite for h in heads()[:10]})
        self.assertTrue(missing[0].p0_incident)

    def test_13_phase_order_gate(self):
        nt.assert_train_order(nt.PHASES)
        self.assertEqual(
            nt.PHASES,
            (
                "PHASE_1_INGRESS",
                "PHASE_2_HEAVY_VERIFY",
                "PHASE_3_LANDING",
                "PHASE_4_TELEMETRY",
            ),
        )
        for bad in (nt.PHASES[::-1], nt.PHASES[1:], nt.PHASES[:3]):
            with self.assertRaises(nt.TrainError):
                nt.assert_train_order(bad)


class TelemetryHeartbeat(unittest.TestCase):
    def test_14_clean_broadcast(self):
        expected = {s: "b" * 40 for s in nt.CANONICAL_SATELLITES}
        run = nt.ConsolidationRun(run_date="20261018", satellite_heads=heads())
        hb = nt.build_heartbeat("20261018", nt.verify_parity(run, expected))
        self.assertEqual(hb["parity"], "100%")
        self.assertEqual(hb["tag"], "nightly-20261018")
        self.assertEqual(
            hb["broadcast_targets"], (nt.PUBLIC_EMBASSY, nt.STUDIO_SATELLITE)
        )
        self.assertEqual(hb["incidents"], [])
        self.assertEqual(len(hb["satellites"]), 11)

    def test_15_regression_broadcast(self):
        expected = {s: "b" * 40 for s in nt.CANONICAL_SATELLITES}
        drifted = tuple(
            nt.SatelliteHead("api", "c" * 40) if s == "api" else h
            for s, h in ((h.satellite, h) for h in heads())
        )
        run = nt.ConsolidationRun(run_date="20261018", satellite_heads=drifted)
        hb = nt.build_heartbeat("20261018", nt.verify_parity(run, expected))
        self.assertEqual(hb["parity"], "REGRESSION")
        self.assertEqual(
            hb["incidents"],
            [
                {
                    "satellite": "api",
                    "isolated_commit": "c" * 40,
                    "severity": "P0-critical",
                }
            ],
        )

    def test_16_heartbeat_fail_closed(self):
        expected = {s: "b" * 40 for s in nt.CANONICAL_SATELLITES}
        run = nt.ConsolidationRun(run_date="20261018", satellite_heads=heads())
        records = nt.verify_parity(run, expected)
        with self.assertRaises(nt.TrainError):
            nt.build_heartbeat("202610", records)
        with self.assertRaises(nt.TrainError):
            nt.build_heartbeat("20261018", ())


class CliSmoke(unittest.TestCase):
    def test_17_boundary_cli_exit_codes(self):
        allowed = subprocess.run(
            [
                sys.executable,
                str(TOWER / "nightly_train_reference.py"),
                "--check-target",
                "Supremeai-bd/supremeai-api",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(allowed.returncode, 0)
        self.assertIn("ALLOW", allowed.stdout)
        blocked = subprocess.run(
            [
                sys.executable,
                str(TOWER / "nightly_train_reference.py"),
                "--check-target",
                "Supremeai-bd/supremeai",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(blocked.returncode, 2)
        self.assertIn("BLOCK", blocked.stdout)

    def test_18_self_test_entrypoint_green(self):
        self.assertTrue(nt.self_test())


if __name__ == "__main__":
    unittest.main(verbosity=2)
