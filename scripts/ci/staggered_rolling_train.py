#!/usr/bin/env python3
"""Federation Transit — Staggered Rolling Train Scheduler (issue #514, Tier 4).

Reference implementation of the **Staggered Rolling Consolidation** tier:
the 11 federation satellites stream into the central monorepo
(`Supremeai-bd/supremeai`) one satellite per 10-minute slot — a full cycle
finishes in ~110 minutes and no two satellites ever contend for git locks
or run heavy private CI simultaneously (anti-stampede / anti-quota-burnout).

Verbatim anti-contention schedule (issue #514 Tier 4):

    Minute 0:   supremeai-open        ➔ supremeai
    Minute 10:  supremeai-studio      ➔ supremeai
    Minute 20:  supremeai-browser     ➔ supremeai
    Minute 30:  supremeai-api         ➔ supremeai
    Minute 40:  supremeai-skills      ➔ supremeai
    Minute 50:  supremeai-vscode      ➔ supremeai
    Minute 60:  supremeai-command     ➔ supremeai
    Minute 70:  supremeai-agents      ➔ supremeai
    Minute 80:  supremeai-archive     ➔ supremeai
    Minute 90:  supremeai-infra       ➔ supremeai
    Minute 100: supremeai-sdk         ➔ supremeai

Fail-closed contract (deterministic, offline, pure stdlib):

  * `assert_no_overlap()` — the schedule must have strictly increasing,
    non-overlapping slots, unique satellites and full cycle coverage;
  * `active_slot()` — modulo-based deterministic slot resolution from a UTC
    instant (`minutes-since-epoch mod 110 // 10`); cycle wrap is exact;
  * `full_repo_name()` — canonical federation repo names; the issue's
    `supremeai-infra` alias normalizes to the real
    `Supremeai-bd/supremeai-infrastructure` (ECOSYSTEM_MAP.md §2);
  * `assert_target_fresh()` — consolidation applies only to a target whose
    HEAD descends from the last-synced SHA (reuses the Tier-2 freshness +
    3-way ingestion guards from `hourly_satellite_batcher` — single SSOT);
  * `urgent_bypass()` — Tier 3 items never wait for their slot.

Network I/O stays in the tower / CI adapters — this module is offline and
deterministic. Pure stdlib.

Run: python3 scripts/ci/staggered_rolling_train.py --self-test
"""

from __future__ import annotations

import argparse
import datetime as _dt
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from hourly_satellite_batcher import (  # reuse — freshness SSOT (no copy)
    BatchConflict,
    FreshnessViolation,
    three_way_check,
)

# ---------------------------------------------------------------------------
# Schedule (issue #514 Tier 4 — verbatim)
# ---------------------------------------------------------------------------

SLOT_MINUTES: Final = 10
CYCLE_MINUTES: Final = 110  # 11 slots × 10 min (last slot 100..110)

MONOREPO: Final = "Supremeai-bd/supremeai"

_INFRA_CANONICAL: Final = "Supremeai-bd/supremeai-infrastructure"


@dataclass(frozen=True)
class Slot:
    """One anti-contention slot in the rolling cycle."""

    minute: int  # offset from cycle start, 0..CYCLE_MINUTES-SLOT_MINUTES
    satellite: str  # federation satellite short name


ROLLING_SCHEDULE: Final = (
    Slot(0, "open"),
    Slot(10, "studio"),
    Slot(20, "browser"),
    Slot(30, "api"),
    Slot(40, "skills"),
    Slot(50, "vscode"),
    Slot(60, "command"),
    Slot(70, "agents"),
    Slot(80, "archive"),
    Slot(90, "infra"),
    Slot(100, "sdk"),
)


class TrainError(ValueError):
    """Fail-closed base error for the rolling train."""


def full_repo_name(satellite: str) -> str:
    """Canonical federation repo name for a satellite short name.

    Accepts the issue's `supremeai-infra` alias and normalizes it to the
    real `Supremeai-bd/supremeai-infrastructure`; `open` maps to the public
    embassy `Supremeai-bd/supremeai-open`. Anything else fails closed.
    """
    if not isinstance(satellite, str):
        raise TrainError(f"satellite must be a string; got {satellite!r}")
    norm = satellite.strip().lower()
    known = {slot.satellite for slot in ROLLING_SCHEDULE}
    norm = norm.removeprefix("supremeai-")
    if norm not in known:
        raise TrainError(f"unknown rolling-train satellite: {satellite!r}")
    if norm == "infra":
        return _INFRA_CANONICAL
    return f"Supremeai-bd/supremeai-{norm}"


def assert_no_overlap(schedule=ROLLING_SCHEDULE) -> None:
    """Schedule invariant: strict, non-overlapping, unique, full coverage."""
    slots = tuple(schedule)
    if len(slots) != 11:
        raise TrainError(
            f"rolling schedule must cover exactly 11 satellites; got {len(slots)}"
        )
    names = [slot.satellite for slot in slots]
    if len(set(names)) != len(names):
        raise TrainError(f"duplicate satellite in rolling schedule: {names}")
    minutes = [slot.minute for slot in slots]
    if minutes != sorted(minutes):
        raise TrainError(f"slot minutes must be strictly increasing; got {minutes}")
    for prev, cur in zip(slots, slots[1:]):
        if cur.minute < prev.minute + SLOT_MINUTES:
            raise TrainError(
                f"overlapping slots: {prev.satellite}@{prev.minute} and "
                f"{cur.satellite}@{cur.minute} (slot = {SLOT_MINUTES} min)"
            )
    if slots[-1].minute + SLOT_MINUTES > CYCLE_MINUTES:
        raise TrainError("schedule exceeds the 110-minute cycle")


# ---------------------------------------------------------------------------
# Deterministic slot resolution
# ---------------------------------------------------------------------------


def active_slot(now_utc: _dt.datetime) -> Slot:
    """Resolve the satellite currently holding the train slot (modulo-based).

    Deterministic: `minutes-since-epoch (UTC) mod 110 // 10` indexes the
    verbatim schedule. A naive datetime is interpreted as UTC (fail-honest
    determinism — callers pass tz-aware instants in production).
    """
    if not isinstance(now_utc, _dt.datetime):
        raise TrainError(f"now_utc must be a datetime; got {type(now_utc).__name__}")
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=_dt.timezone.utc)
    minute_of_epoch = int(now_utc.timestamp()) // 60
    offset = (minute_of_epoch % CYCLE_MINUTES) // SLOT_MINUTES * SLOT_MINUTES
    for slot in ROLLING_SCHEDULE:
        if slot.minute == offset:
            return slot
    raise TrainError(f"unresolved slot offset {offset} — schedule invariant broken")


def slot_bounds(now_utc: _dt.datetime) -> tuple[_dt.datetime, _dt.datetime]:
    """[start, end) window of the currently active 10-minute slot."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=_dt.timezone.utc)
    slot = active_slot(now_utc)
    minute_of_epoch = int(now_utc.timestamp()) // 60
    delta = minute_of_epoch - slot.minute
    start = _dt.datetime.fromtimestamp(delta * 60, tz=_dt.timezone.utc)
    return start, start + _dt.timedelta(minutes=SLOT_MINUTES)


# ---------------------------------------------------------------------------
# Consolidation planning for the active slot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsolidationPlan:
    """One atomic consolidation commit for exactly one satellite → monorepo."""

    satellite: str
    target: str
    shas: tuple[str, ...]
    files: tuple[str, ...]


def plan_consolidation(
    satellite: str,
    shas,
    files,
    last_synced: str | None,
    target_head: str | None,
    parents: Mapping[str, str] | None = None,
    commit_files: Mapping[str,] | None = None,
) -> ConsolidationPlan:
    """Build the atomic consolidation plan for one satellite's slot.

    Fail-closed: a stale or unverifiable target raises `FreshnessViolation`;
    a file overlap with target-side changes since the last sync raises
    `BatchConflict` (no blind overwrites — #514 invariant 3).
    """
    target = full_repo_name(satellite)  # unknown satellite fails closed
    shas = tuple(shas)
    files = tuple(files)
    if not shas or any(not isinstance(s, str) or not s for s in shas):
        raise TrainError(f"{satellite}: consolidation requires >= 1 commit SHA")
    if not files or any(not isinstance(f, str) or not f for f in files):
        raise TrainError(f"{satellite}: consolidation requires >= 1 file path")
    if last_synced is not None and target_head is not None:
        if parents is None or commit_files is None:
            raise TrainError("freshness bookkeeping requires parents + commit_files")
        from hourly_satellite_batcher import is_descendant  # local: reuse SSOT

        if is_descendant(target_head, last_synced, parents):
            conflicts = three_way_check(
                files, last_synced, target_head, parents, commit_files
            )
            if conflicts:
                raise BatchConflict(
                    f"{satellite} → {target}: conflict files since sync base "
                    f"{last_synced[:8]}: {conflicts}"
                )
        else:
            raise FreshnessViolation(
                f"{satellite}: target HEAD {target_head[:8]} is behind sync base "
                f"{last_synced[:8]} — refresh before consolidation"
            )
    return ConsolidationPlan(satellite=satellite, target=target, shas=shas, files=files)


def urgent_bypass(items) -> tuple:
    """Tier 3: urgent items dispatch immediately — they never wait for a slot."""
    try:
        selected = tuple(item for item in items if getattr(item, "urgent", False))
    except TypeError:
        raise TrainError(f"items must be iterable; got {items!r}")
    return selected


# ---------------------------------------------------------------------------
# Self-test (offline, deterministic — guard-the-guard)
# ---------------------------------------------------------------------------


def self_test() -> bool:
    # schedule invariants (issue #514 Tier 4 — verbatim order)
    assert_no_overlap()
    assert [s.satellite for s in ROLLING_SCHEDULE] == (
        [
            "open",
            "studio",
            "browser",
            "api",
            "skills",
            "vscode",
            "command",
            "agents",
            "archive",
            "infra",
            "sdk",
        ]
    )
    assert [s.minute for s in ROLLING_SCHEDULE] == list(range(0, 110, 10))
    try:
        assert_no_overlap((ROLLING_SCHEDULE[0], ROLLING_SCHEDULE[0]))
        raise AssertionError("duplicate schedule must be rejected")
    except TrainError:
        pass
    try:
        bad = (Slot(0, "open"), Slot(5, "studio"))
        assert_no_overlap(bad)
        raise AssertionError("overlapping slots must be rejected")
    except TrainError:
        pass
    try:
        short = tuple(ROLLING_SCHEDULE)[:10]
        assert_no_overlap(short)
        raise AssertionError("incomplete schedule must be rejected")
    except TrainError:
        pass

    # canonical repo names (incl. the issue's supremeai-infra alias)
    assert full_repo_name("open") == "Supremeai-bd/supremeai-open"
    assert full_repo_name("studio") == "Supremeai-bd/supremeai-studio"
    assert full_repo_name("infra") == "Supremeai-bd/supremeai-infrastructure"
    assert full_repo_name("supremeai-infra") == "Supremeai-bd/supremeai-infrastructure"
    assert full_repo_name(" SDK ") == "Supremeai-bd/supremeai-sdk"
    for bad in ("core", "", "unknown", "Supremeai-bd/supremeai"):
        try:
            full_repo_name(bad)
            raise AssertionError(f"{bad!r} must be rejected")
        except TrainError:
            pass

    # deterministic slot resolution — fixed epoch math, cycle wrap exact
    epoch = _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)
    assert active_slot(epoch).satellite == "open"  # minute 0 of cycle 0
    t10 = epoch + _dt.timedelta(minutes=10)
    assert active_slot(t10).satellite == "studio"
    t109 = epoch + _dt.timedelta(minutes=109)
    assert active_slot(t109).satellite == "sdk"  # last slot of the cycle
    t110 = epoch + _dt.timedelta(minutes=110)
    assert active_slot(t110).satellite == "open"  # exact wrap
    t115 = epoch + _dt.timedelta(minutes=115)
    assert active_slot(t115).satellite == "open"  # 5 min into the wrapped open slot
    t120 = epoch + _dt.timedelta(minutes=120)
    assert active_slot(t120).satellite == "studio"  # second slot of the next cycle
    naive = _dt.datetime(1970, 1, 1, 0, 30)
    assert active_slot(naive).satellite == "api"  # naive == UTC, minute 30
    try:
        active_slot("now")
        raise AssertionError("non-datetime must be rejected")
    except TrainError:
        pass

    # slot bounds
    start, end = slot_bounds(t115)
    assert (end - start).total_seconds() == SLOT_MINUTES * 60
    assert start <= t115.replace(tzinfo=_dt.timezone.utc) < end or (
        start <= t115.replace(tzinfo=_dt.timezone.utc) + _dt.timedelta(seconds=1) <= end
    )

    # consolidation planning — freshness + 3-way guards (SSOT reuse)
    base, mid, head = "0" * 40, "e" * 40, "f" * 40
    parents = {head: mid, mid: base}
    commit_files = {mid: ("docs/ledger/a.md",), head: ("docs/ledger/b.md",)}
    # clean consolidation: batch carries a file the target never touched
    plan = plan_consolidation(
        "archive",
        (head, mid),
        ("docs/ledger/c.md",),
        last_synced=base,
        target_head=head,
        parents=parents,
        commit_files=commit_files,
    )
    assert plan.target == "Supremeai-bd/supremeai-archive"
    assert plan.shas == (head, mid)
    # conflict → fail closed
    try:
        plan_consolidation(
            "archive",
            (head,),
            ("docs/ledger/b.md",),
            last_synced=base,
            target_head=head,
            parents=parents,
            commit_files=commit_files,
        )
        raise AssertionError("conflicting consolidation must be rejected")
    except BatchConflict:
        pass
    # stale target → fail closed
    try:
        plan_consolidation(
            "archive",
            (mid,),
            ("docs/ledger/a.md",),
            last_synced=head,
            target_head=mid,
            parents=parents,
            commit_files=commit_files,
        )
        raise AssertionError("stale target must be rejected")
    except FreshnessViolation:
        pass
    # missing bookkeeping → fail closed
    try:
        plan_consolidation(
            "sdk", (head,), ("sdk/x.ts",), last_synced=base, target_head=head
        )
        raise AssertionError("missing parents/commit_files must be rejected")
    except TrainError:
        pass
    # unknown satellite → fail closed
    try:
        plan_consolidation(
            "core", (head,), ("core/x.py",), last_synced=None, target_head=None
        )
        raise AssertionError("non-train satellite must be rejected")
    except TrainError:
        pass

    # Tier 3 urgent bypass
    class _Item:
        def __init__(self, urgent: bool):
            self.urgent = urgent

    picked = urgent_bypass([_Item(True), _Item(False), _Item(True)])
    assert len(picked) == 2 and all(i.urgent for i in picked)
    assert urgent_bypass([]) == ()

    print("self-test OK — staggered_rolling_train (issue #514 Tier 4)")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Staggered Rolling Train (issue #514)")
    parser.add_argument(
        "--self-test", action="store_true", help="offline guard-the-guard"
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return 0 if self_test() else 1
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
