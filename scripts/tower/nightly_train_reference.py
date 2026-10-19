#!/usr/bin/env python3
"""S12 — Hub-and-Spoke Nightly Consolidation Engine (issue #492).

Reference implementation of the **Nightly Consolidation Train** with
**MCP Tower Boundary Isolation**:

    DAYTIME — fast distributed work in the 11 lightweight satellites;
    the proprietary monorepo (`Supremeai-bd/supremeai`) is OUTSIDE the
    MCP Tower's direct operational scope, protecting the `supremeai-core`
    moat and credential vaults from any external agent surface.

    NIGHTLY (cron `0 0 * * *`, 00:00 UTC) — one authoritative train:
      Phase 1  Ingress & Satellite Pull (SHAs of the 11 satellites)
      Phase 2  Full-spectrum heavy verification (exclusive to the train)
      Phase 3  Atomic landing + `nightly-YYYYMMDD` tag + parity records
      Phase 4  Telemetry heartbeat to the public embassy & Studio console

Deterministic, fail-closed contract:

  * `assert_tower_target()` — any MCP tool targeting `Supremeai-bd/supremeai`
    directly raises `TowerBoundaryViolation` (criterion 1 & 2);
  * `validate_cron()` — the train trigger must be exactly `0 0 * * *` UTC
    (criterion 3);
  * `is_heavy_suite()` / `assert_suite_allowed()` — heavy integration and
    database suites are rejected in daytime lanes and run exclusively in
    the train (criterion 4);
  * `ConsolidationRun` — SHA ingest, staging plan, parity verdict per
    satellite (100% parity or isolated-commit P0 incident structure),
    `nightly-YYYYMMDD` tag synthesis (criterion 5 and Phase 3);
  * network I/O stays in the tower/private-repo adapters — this module is
    offline and deterministic.

Pure stdlib. Run: python3 scripts/tower/nightly_train_reference.py --self-test
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final

# ---------------------------------------------------------------------------
# Registry & boundary (criterion 1 & 2)
# ---------------------------------------------------------------------------

#: The 11 canonical satellites (issue #492, verbatim list).
CANONICAL_SATELLITES: Final = (
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
)

PROPRIETARY_MONOREPO: Final = "Supremeai-bd/supremeai"
PUBLIC_EMBASSY: Final = "Supremeai-bd/supremeai-open"
STUDIO_SATELLITE: Final = "Supremeai-bd/supremeai-studio"

SATELLITE_FULL_NAMES: Final[Mapping[str, str]] = MappingProxyType(
    {sat: f"Supremeai-bd/supremeai-{sat}" for sat in CANONICAL_SATELLITES}
)


class TowerBoundaryViolation(ValueError):
    """Raised when an MCP tool targets the proprietary monorepo directly."""


def is_monorepo(target: str) -> bool:
    normalized = target.strip().lower()
    return normalized in (
        PROPRIETARY_MONOREPO.lower(),
        "supremeai",
        "supremeai-bd/supremeai",
    )


def assert_tower_target(target: str) -> str:
    """MCP Tower routing gate: satellites only, monorepo never."""
    if is_monorepo(target):
        raise TowerBoundaryViolation(
            f"{PROPRIETARY_MONOREPO} is outside MCP Tower's direct "
            "operational scope (issue #492) — route agent work to the 11 "
            f"canonical satellites {CANONICAL_SATELLITES}"
        )
    short = target.rstrip("/").rsplit("/", 1)[-1].lower()
    short = short.removeprefix("supremeai-")
    if short not in CANONICAL_SATELLITES:
        raise TowerBoundaryViolation(
            f"{target!r} is not a canonical satellite ({CANONICAL_SATELLITES})"
        )
    return SATELLITE_FULL_NAMES[short] if short in CANONICAL_SATELLITES else str(target)


# ---------------------------------------------------------------------------
# Schedule & heavy-suite gating (criterion 3 & 4)
# ---------------------------------------------------------------------------

NIGHTLY_CRON_UTC: Final = "0 0 * * *"
CRON_FIELDS: Final = 5


class ScheduleError(ValueError):
    """Raised when the train trigger deviates from the nightly contract."""


def validate_cron(expr: str, tz: str = "UTC") -> None:
    """The consolidation train fires at exactly 00:00 UTC nightly."""
    fields = expr.split()
    if len(fields) != CRON_FIELDS or tuple(fields) != ("0", "0", "*", "*", "*"):
        raise ScheduleError(
            f"nightly train cron must be exactly {NIGHTLY_CRON_UTC!r} "
            f"(00:00 UTC), got {expr!r}"
        )
    if tz.upper() != "UTC":
        raise ScheduleError(f"nightly train timezone must be UTC, got {tz!r}")


HEAVY_SUITE_MARKERS: Final = (
    "integration",
    "e2e",
    "end-to-end",
    "migration",
    "db_migrate",
    "fallback_probe",
    "cross_boundary",
    "full_battery",
    "multi_model",
)


def is_heavy_suite(suite_name: str) -> bool:
    """Heavy verification runs EXCLUSIVELY in the nightly train."""
    lowered = suite_name.lower()
    return any(marker in lowered for marker in HEAVY_SUITE_MARKERS)


def assert_suite_allowed(suite_name: str, lane: str) -> None:
    """Daytime lanes may not run heavy suites; the train may."""
    if lane == "nightly_train":
        return
    if is_heavy_suite(suite_name):
        raise ScheduleError(
            f"heavy suite {suite_name!r} is exclusive to the nightly train "
            f"(issue #492 criterion 4) — daytime lane {lane!r} rejected"
        )


# ---------------------------------------------------------------------------
# Consolidation run (Phase 1-4)
# ---------------------------------------------------------------------------

PHASE_1_INGRESS: Final = "PHASE_1_INGRESS"
PHASE_2_HEAVY_VERIFY: Final = "PHASE_2_HEAVY_VERIFY"
PHASE_3_LANDING: Final = "PHASE_3_LANDING"
PHASE_4_TELEMETRY: Final = "PHASE_4_TELEMETRY"
PHASES: Final = (
    PHASE_1_INGRESS,
    PHASE_2_HEAVY_VERIFY,
    PHASE_3_LANDING,
    PHASE_4_TELEMETRY,
)

PARITY_VERDICTS: Final = ("PARITY", "DRIFT", "MISSING")


class TrainError(ValueError):
    """Raised when a consolidation run violates its contract."""


@dataclass(frozen=True)
class SatelliteHead:
    satellite: str  # canonical short name
    sha: str  # latest stable head commit SHA


@dataclass(frozen=True)
class ParityRecord:
    satellite: str
    verdict: str  # PARITY | DRIFT | MISSING
    expected_sha: str
    observed_sha: str
    isolated_commit: str = ""  # Phase 4: commit isolated for regression
    p0_incident: bool = False


@dataclass(frozen=True)
class ConsolidationRun:
    run_date: str  # YYYYMMDD (UTC)
    satellite_heads: tuple[SatelliteHead, ...] = field(default_factory=tuple)
    parity_records: tuple[ParityRecord, ...] = field(default_factory=tuple)
    heavy_suites: tuple[str, ...] = field(default_factory=tuple)
    landed: bool = False
    release_tag: str = ""

    @property
    def tag(self) -> str:
        """Phase 3: daily release tag contract — nightly-YYYYMMDD."""
        if not re.fullmatch(r"\d{8}", self.run_date):
            raise TrainError(f"run_date must be YYYYMMDD, got {self.run_date!r}")
        return f"nightly-{self.run_date}"


def ingest_heads(heads: tuple[SatelliteHead, ...]) -> tuple[SatelliteHead, ...]:
    """Phase 1: fail-closed ingest — all 11 satellites, 40-hex SHAs, unique."""
    seen: set[str] = set()
    for head in heads:
        if head.satellite not in CANONICAL_SATELLITES:
            raise TrainError(f"unknown satellite {head.satellite!r}")
        if not re.fullmatch(r"[0-9a-f]{40}", head.sha):
            raise TrainError(
                f"satellite {head.satellite!r} sha malformed: {head.sha!r}"
            )
        if head.satellite in seen:
            raise TrainError(f"duplicate head for {head.satellite!r}")
        seen.add(head.satellite)
    missing = set(CANONICAL_SATELLITES) - seen
    if missing:
        raise TrainError(
            f"Phase 1 incomplete — missing satellite heads: {sorted(missing)}"
        )
    return heads


def verify_parity(
    run: ConsolidationRun, expected: Mapping[str, str]
) -> tuple[ParityRecord, ...]:
    """Phase 2/3 support: per-satellite parity against the staging manifest."""
    records: list[ParityRecord] = []
    for head in run.satellite_heads:
        exp = expected.get(head.satellite)
        if exp is None:
            records.append(
                ParityRecord(
                    head.satellite, "MISSING", expected_sha="", observed_sha=head.sha
                )
            )
        elif exp == head.sha:
            records.append(
                ParityRecord(
                    head.satellite, "PARITY", expected_sha=exp, observed_sha=head.sha
                )
            )
        else:
            records.append(
                ParityRecord(
                    head.satellite,
                    "DRIFT",
                    expected_sha=exp,
                    observed_sha=head.sha,
                    isolated_commit=head.sha,
                    p0_incident=True,
                )
            )
    missing = [
        sat for sat in CANONICAL_SATELLITES if sat not in {r.satellite for r in records}
    ]
    for sat in missing:
        records.append(
            ParityRecord(
                sat, "MISSING", expected_sha="", observed_sha="", p0_incident=True
            )
        )
    return tuple(records)


def full_parity(records: tuple[ParityRecord, ...]) -> bool:
    """100% parity gate — any DRIFT/MISSING blocks the broadcast."""
    return bool(records) and all(r.verdict == "PARITY" for r in records)


def build_heartbeat(run_date: str, records: tuple[ParityRecord, ...]) -> dict:
    """Phase 4: telemetry heartbeat for Studio dashboard + public board."""
    if not re.fullmatch(r"\d{8}", run_date):
        raise TrainError(f"run_date must be YYYYMMDD, got {run_date!r}")
    if not records:
        raise TrainError("heartbeat requires parity records")
    return {
        "type": "nightly_train_heartbeat",
        "run_date": run_date,
        "tag": f"nightly-{run_date}",
        "parity": "100%" if full_parity(records) else "REGRESSION",
        "satellites": {
            r.satellite: {"verdict": r.verdict, "sha": r.observed_sha} for r in records
        },
        "incidents": [
            {
                "satellite": r.satellite,
                "isolated_commit": r.isolated_commit,
                "severity": "P0-critical",
            }
            for r in records
            if r.p0_incident
        ],
        "broadcast_targets": (PUBLIC_EMBASSY, STUDIO_SATELLITE),
    }


def assert_train_order(phases: tuple[str, ...]) -> None:
    """The train runs Phase 1→2→3→4, in order, no skips."""
    if phases != PHASES:
        raise TrainError(f"train phases must run in order {PHASES}, got {phases}")


def self_test() -> bool:
    # Boundary: monorepo is unreachable, satellites resolve.
    for bad in (PROPRIETARY_MONOREPO, "supremeai", "Supremeai-bd/supremeai"):
        try:
            assert_tower_target(bad)
            raise SystemExit(f"tower boundary failed open: {bad}")
        except TowerBoundaryViolation:
            pass
    assert assert_tower_target("Supremeai-bd/supremeai-studio") == STUDIO_SATELLITE
    assert assert_tower_target(PUBLIC_EMBASSY) == PUBLIC_EMBASSY
    for sat in CANONICAL_SATELLITES:
        assert assert_tower_target(f"Supremeai-bd/supremeai-{sat}")
    try:
        assert_tower_target("Supremeai-bd/unknown-repo")
        raise SystemExit("satellite allowlist failed open")
    except TowerBoundaryViolation:
        pass

    # Cron contract.
    validate_cron(NIGHTLY_CRON_UTC)
    for bad_expr, bad_tz in (
        ("0 1 * * *", "UTC"),
        ("0 0 * * *", "EST"),
        ("30 0 * * *", "UTC"),
        ("0 0 1 * *", "UTC"),
        ("0 0 * * * *", "UTC"),
    ):
        try:
            validate_cron(bad_expr, bad_tz)
            raise SystemExit(f"cron gate failed open: {bad_expr}/{bad_tz}")
        except ScheduleError:
            pass

    # Heavy-suite exclusivity.
    for suite in (
        "integration_smoke",
        "e2e_gateway",
        "db_migrate_0042",
        "multi_model_fallback_probe",
        "cross_boundary_contracts",
    ):
        assert is_heavy_suite(suite), suite
        try:
            assert_suite_allowed(suite, "daytime_satellite")
            raise SystemExit(f"heavy-suite gate failed open: {suite}")
        except ScheduleError:
            pass
        assert_suite_allowed(suite, "nightly_train")  # allowed at night
    assert not is_heavy_suite("unit_ledger")
    assert_suite_allowed("unit_ledger", "daytime_satellite")

    # Ingest: all 11, fail-closed.
    sha = "a" * 40
    heads = tuple(
        SatelliteHead(s, sha.replace("a", format(i, "x") * 40 if False else "b" * 40))
        for i, s in enumerate(CANONICAL_SATELLITES)
    )
    heads = tuple(SatelliteHead(s, "b" * 40) for s in CANONICAL_SATELLITES)
    assert len(ingest_heads(heads)) == 11
    for broken in (
        heads[:10],  # missing one
        heads + (SatelliteHead("open", "b" * 40),),  # duplicate
        heads + (SatelliteHead("unknown-sat", "b" * 40),),  # not canonical
        heads[:-1] + (SatelliteHead("sdk", "tooshort"),),  # malformed sha
    ):
        try:
            ingest_heads(broken)  # type: ignore[arg-type]
            raise SystemExit(f"ingest gate failed open: {broken!r}")
        except TrainError:
            pass

    # Parity: 100% vs drift with P0 incident.
    run = ConsolidationRun(run_date="20261018", satellite_heads=heads)
    assert run.tag == "nightly-20261018"
    expected = {s: "b" * 40 for s in CANONICAL_SATELLITES}
    records = verify_parity(run, expected)
    assert full_parity(records)
    drifted_heads = tuple(
        SatelliteHead("api", "c" * 40) if s == "api" else h
        for s, h in ((h.satellite, h) for h in heads)
    )
    run2 = ConsolidationRun(run_date="20261018", satellite_heads=drifted_heads)
    records2 = verify_parity(run2, expected)
    assert not full_parity(records2)
    api_record = next(r for r in records2 if r.satellite == "api")
    assert api_record.verdict == "DRIFT" and api_record.p0_incident
    assert api_record.isolated_commit == "c" * 40

    # Heartbeat: regression path lists incidents + broadcast targets.
    heartbeat = build_heartbeat("20261018", records2)
    assert heartbeat["parity"] == "REGRESSION"
    assert heartbeat["incidents"][0]["severity"] == "P0-critical"
    assert heartbeat["broadcast_targets"] == (PUBLIC_EMBASSY, STUDIO_SATELLITE)
    clean = build_heartbeat("20261018", records)
    assert clean["parity"] == "100%"
    for broken in (
        lambda: build_heartbeat("202610", records),
        lambda: build_heartbeat("2026-10-18", records),
        lambda: build_heartbeat("20261018", ()),
    ):
        try:
            broken()
            raise SystemExit("heartbeat gate failed open")
        except TrainError:
            pass

    # Tag contract + phase order.
    try:
        ConsolidationRun(run_date="18-10-2026").tag
        raise SystemExit("tag gate failed open")
    except TrainError:
        pass
    assert_train_order(PHASES)
    for bad_order in (PHASES[::-1], PHASES[1:], PHASES[:3]):
        try:
            assert_train_order(bad_order)  # type: ignore[arg-type]
            raise SystemExit(f"phase-order gate failed open: {bad_order}")
        except TrainError:
            pass

    return True


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--check-target", metavar="REPO", help="simulate an MCP Tower routing decision"
    )
    args = parser.parse_args()
    if args.self_test:
        self_test()
        print("SELF-TEST OK: nightly_train_reference")
        return 0
    if args.check_target:
        try:
            print(f"ALLOW -> {assert_tower_target(args.check_target)}")
            return 0
        except TowerBoundaryViolation as exc:
            print(f"BLOCK -> {exc}")
            return 2
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
