#!/usr/bin/env python3
"""Federation Transit — Hourly Satellite Batcher (issue #514, Tier 2 & Tier 3).

Reference implementation of the **Hourly Staged Satellite Batching** tier and
the **Emergency Blocker Fast-Lane** of the 4-Tier Federation Transit Pipeline:

    TIER 2 (hourly, cron `0 * * * *`):
      Inspect commits landed on `supremeai-open:main` within the past hour,
      aggregate their diffs, map them to the designated federation satellites
      (ECOSYSTEM_MAP.md §3.1 routing matrix) and emit ONE consolidated batch
      plan per satellite — preventing micro-commit noise.

    TIER 3 (label-triggered bypass):
      Commits labelled `bridge:urgent` or `fast-track` bypass the hourly
      window and dispatch immediately.

Fail-closed contract (deterministic, offline, pure stdlib):

  * `validate_cron()` — the batch trigger must be exactly `0 * * * *`;
  * `route_path()` — §3.1 routing matrix is the SSOT; unknown paths are
    quarantined in `BatchPlan.unrouted` (never guessed, never dropped);
    monorepo-designated paths never ride a satellite batch (they are always
    synced via the monorepo channel — S12 boundary isolation, issue #492);
  * `assert_target_fresh()` — a batch may only apply to a satellite whose
    HEAD is a strict descendant of the last-synced SHA (or an unsynced
    target); unknown SHAs and ancestry cycles raise `FreshnessViolation`;
  * `three_way_check()` — files touched by BOTH the batch and the target
    since the last sync are conflicts; any conflict rejects the whole batch
    (no partial application — `git apply --check` semantics, fail-closed);
  * SHA intake validates the 40-hex form (same contract as #492 ingest).

Network I/O stays in the tower / CI adapters — this module is offline and
deterministic. Pure stdlib.

Run: python3 scripts/ci/hourly_satellite_batcher.py --self-test
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

# ---------------------------------------------------------------------------
# Registry & cadence (Tier 2)
# ---------------------------------------------------------------------------

#: Hourly cadence — issue #514 Tier 2, verbatim.
BATCH_CRON: Final = "0 * * * *"

_PROPRIETARY_MONOREPO: Final = "Supremeai-bd/supremeai"
_PROPRIETARY_LOWER: Final = _PROPRIETARY_MONOREPO.lower()

_UTC = _dt.timezone.utc

_SHA_RE: Final = re.compile(r"^[0-9a-f]{40}$")

# ECOSYSTEM_MAP.md §3.1 — Definitive Federation File & Domain Routing Matrix.
# (path_prefix, satellite_short). Ordered longest-prefix-first at match time;
# entries here keep the §3.1 declaration order for readability.
ROUTING_MATRIX: Final = (
    ("examples/dashboard-preview/", "studio"),
    ("infrastructure/mcp-control-plane/", "mcp"),
    ("api-schemas/dashboard.", "studio"),
    ("api-schemas/gateway.", "api"),
    ("api-schemas/task-router.", "core"),
    ("api-schemas/command.", "command"),
    ("api-schemas/agent-runner.", "agents"),
    ("api-schemas/heartbeat.", "mcp"),
    ("api-schemas/telemetry-log.", "sdk"),
    ("handlers/telegram", "command"),
    ("examples/langchain-", "skills"),
    ("examples/vercel-", "skills"),
    ("examples/sdk-", "sdk"),
    ("studio/", "studio"),
    ("api/", "api"),
    ("gateway/", "api"),
    ("core/", "core"),
    ("command/", "command"),
    ("skills/", "skills"),
    ("vscode/", "vscode"),
    ("agents/", "agents"),
    ("runner/", "agents"),
    ("browser/", "browser"),
    ("sandbox/", "browser"),
    ("sdk/", "sdk"),
    ("deployments/", "infra"),
    ("infra/", "infra"),
    ("docs/archive/", "archive"),
    ("docs/ledger/", "archive"),
    ("scripts/agents/", None),  # None ⇒ monorepo-designated (always-synced channel)
    ("docs/", None),
    ("patches/", None),
)

#: §3.1 monorepo-designated literal files (repo-root, always-synced channel).
MONOREPO_ROOT_FILES: Final = ("AGENTS.md",)  # AGENT_RULES.md deleted by #1526 (#1642)


class BatchError(ValueError):
    """Fail-closed base error for the hourly batcher."""


class FreshnessViolation(BatchError):
    """Target branch is stale or its ancestry is unverifiable (#514 invariant 3)."""


class BatchConflict(BatchError):
    """Batch touches files the target also touched since the last sync."""


# ---------------------------------------------------------------------------
# Cadence & intake validation
# ---------------------------------------------------------------------------


def validate_cron(expr: str) -> None:
    """Tier 2 trigger must be exactly the hourly cron `0 * * * *` (UTC)."""
    if expr.strip() != BATCH_CRON:
        raise BatchError(
            f"hourly batcher cron must be exactly {BATCH_CRON!r} (UTC); got {expr!r}"
        )


def validate_sha(sha: str) -> str:
    """Fail-closed 40-hex SHA intake (same contract as #492 ingest)."""
    if not isinstance(sha, str) or not _SHA_RE.match(sha):
        raise BatchError(f"commit sha must be 40-hex; got {sha!r}")
    return sha


# ---------------------------------------------------------------------------
# §3.1 routing matrix (SSOT) — path → satellite
# ---------------------------------------------------------------------------


def route_path(path: str) -> str | None:
    """Map a landed file path to its federation satellite (ECOSYSTEM_MAP §3.1).

    Returns the satellite short name (e.g. ``"studio"``), ``"monorepo"`` for
    monorepo-designated paths (always-synced channel — never a satellite
    batch), or ``None`` when the path is unrouted (fail-closed quarantine).
    """
    if not isinstance(path, str) or not path or path.strip() != path:
        raise BatchError(f"invalid path: {path!r}")
    norm = path.replace("\\", "/").lstrip("/")
    if norm in MONOREPO_ROOT_FILES:
        return "monorepo"
    for prefix, target in ROUTING_MATRIX:
        if norm.startswith(prefix):
            return target if target is not None else "monorepo"
    return None


# ---------------------------------------------------------------------------
# Tier 3 — urgent fast-lane
# ---------------------------------------------------------------------------

URGENT_LABELS: Final = ("bridge:urgent", "fast-track")


def is_urgent(labels) -> bool:
    """Tier 3 bypass: `bridge:urgent` or `fast-track` skips the hourly window."""
    try:
        label_set = frozenset(labels)
    except TypeError:
        raise BatchError(f"labels must be an iterable of strings; got {labels!r}")
    for raw in label_set:
        if not isinstance(raw, str):
            raise BatchError(f"labels must be strings; got {raw!r}")
    return bool(label_set.intersection(URGENT_LABELS))


# ---------------------------------------------------------------------------
# Intake model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LandedCommit:
    """One commit landed on `supremeai-open:main` (validated, immutable)."""

    sha: str
    files: tuple[str, ...]
    landed_at: str  # ISO-8601 UTC
    labels: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        validate_sha(self.sha)
        files = tuple(self.files)
        if not files or any(not isinstance(f, str) or not f for f in files):
            raise BatchError(f"commit {self.sha[:8]} must touch >= 1 valid path")
        object.__setattr__(self, "files", files)
        _parse_iso(self.landed_at)  # fail-closed timestamp
        object.__setattr__(self, "labels", frozenset(self.labels))


def _parse_iso(value: str) -> _dt.datetime:
    if not isinstance(value, str):
        raise BatchError(f"timestamp must be an ISO-8601 string; got {value!r}")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise BatchError(f"malformed ISO-8601 timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_UTC)
    return parsed.astimezone(_UTC)


def in_batch_window(landed_at: str, window_start: str, window_end: str) -> bool:
    """True iff the commit landed in [window_start, window_end) — hourly tier."""
    ts = _parse_iso(landed_at)
    start = _parse_iso(window_start)
    end = _parse_iso(window_end)
    if end <= start:
        raise BatchError(
            f"window_end must be after window_start; got {window_start!r}..{window_end!r}"
        )
    return start <= ts < end


# ---------------------------------------------------------------------------
# Target freshness & 3-way ingestion guard (invariant 3)
# ---------------------------------------------------------------------------


def is_descendant(head: str, base: str, parents: Mapping[str, str]) -> bool:
    """True iff `head` == `base` or reaches `base` via the parent map.

    Fail-closed: an unknown SHA or an ancestry cycle raises
    `FreshnessViolation` — we never certify freshness we cannot prove.
    """
    validate_sha(head)
    validate_sha(base)
    seen: set[str] = set()
    cur = head
    while cur != base:
        if cur in seen:
            raise FreshnessViolation(f"ancestry cycle at {cur[:8]}")
        parent = parents.get(cur)
        if parent is None:
            raise FreshnessViolation(
                f"unknown SHA {cur[:8]} — cannot prove {head[:8]} descends from {base[:8]}"
            )
        seen.add(cur)
        cur = parent
    return True


def three_way_check(
    batch_files,
    base_sha: str,
    target_head: str,
    parents: Mapping[str, str],
    commit_files: Mapping[str,],
) -> tuple[str, ...]:
    """Files touched by BOTH the batch and the target since `base_sha`.

    Models the `git apply --check` / in-memory 3-way ingestion guard from
    #514 invariant 3: the caller applies a batch only when the returned
    conflict set is EMPTY. Ancestors outside the parent map fail closed.
    """
    if not is_descendant(target_head, base_sha, parents):
        raise FreshnessViolation(
            f"target {target_head[:8]} does not descend from sync base {base_sha[:8]}"
        )
    touched: set[str] = set()
    cur = target_head
    while cur != base_sha:
        for path in commit_files.get(cur, ()):
            touched.add(path)
        cur = parents[cur]
    wanted = {f for f in batch_files if isinstance(f, str) and f}
    return tuple(sorted(touched.intersection(wanted)))


# ---------------------------------------------------------------------------
# Batch planning (one consolidated batch per satellite)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SatelliteBatch:
    """One consolidated dispatch unit for exactly one satellite."""

    satellite: str
    shas: tuple[str, ...]
    files: tuple[str, ...]
    urgent: bool


@dataclass(frozen=True)
class BatchPlan:
    """Deterministic Tier-2/Tier-3 dispatch plan for one hourly cycle."""

    window_start: str
    window_end: str
    batches: tuple[SatelliteBatch, ...]
    unrouted: tuple[tuple[str, str], ...]  # (sha, path) — fail-closed quarantine
    monorepo_paths: tuple[str, ...]  # always-synced channel (§3.1), not a satellite


def plan_batches(
    commits,
    window_start: str,
    window_end: str,
    last_synced: Mapping[str, str] | None = None,
    target_heads: Mapping[str, str] | None = None,
    parents: Mapping[str, str] | None = None,
    commit_files: Mapping[str,] | None = None,
) -> BatchPlan:
    """Aggregate windowed + urgent commits into one batch per satellite.

    - Hourly tier: only commits with `window_start <= landed_at < window_end`.
    - Tier 3: urgent commits bypass the window and flag their batch urgent.
    - Freshness/3-way guards run per satellite when sync bookkeeping is given.
    - Output is deterministic: batches sorted by satellite name; SHAs in
      landing (input) order; files deduplicated in first-seen order.
    """
    start = _parse_iso(window_start)
    end = _parse_iso(window_end)
    if end <= start:
        raise BatchError("window_end must be after window_start")

    grouped: dict[str, dict] = {}
    unrouted: list[tuple[str, str]] = []
    monorepo: list[str] = []

    for commit in commits:
        if not isinstance(commit, LandedCommit):
            raise BatchError(f"expected LandedCommit; got {type(commit).__name__}")
        urgent = is_urgent(commit.labels)
        if not urgent and not (start <= _parse_iso(commit.landed_at) < end):
            continue  # outside the hourly window and not urgent → next cycle
        for path in commit.files:
            target = route_path(path)
            if target is None:
                unrouted.append((commit.sha, path))
                continue
            if target == "monorepo":
                if path not in monorepo:
                    monorepo.append(path)
                continue
            bucket = grouped.setdefault(
                target, {"shas": [], "files": [], "urgent": False}
            )
            if commit.sha not in bucket["shas"]:
                bucket["shas"].append(commit.sha)
            if path not in bucket["files"]:
                bucket["files"].append(path)
            bucket["urgent"] = bucket["urgent"] or urgent

    batches: list[SatelliteBatch] = []
    for satellite in sorted(grouped):
        bucket = grouped[satellite]
        last = (last_synced or {}).get(satellite)
        head = (target_heads or {}).get(satellite)
        if last is not None and head is not None:
            assert parents is not None and commit_files is not None, (
                "freshness bookkeeping requires parents + commit_files maps"
            )
            if is_descendant(head, last, parents):
                conflicts = three_way_check(
                    bucket["files"], last, head, parents, commit_files
                )
                if conflicts:
                    raise BatchConflict(
                        f"satellite {satellite}: batch conflicts with target changes "
                        f"since {last[:8]}: {conflicts}"
                    )
            else:
                raise FreshnessViolation(
                    f"satellite {satellite}: HEAD {head[:8]} is behind sync base "
                    f"{last[:8]} — refresh the target before applying the batch"
                )
        batches.append(
            SatelliteBatch(
                satellite=satellite,
                shas=tuple(bucket["shas"]),
                files=tuple(bucket["files"]),
                urgent=bucket["urgent"],
            )
        )

    return BatchPlan(
        window_start=window_start,
        window_end=window_end,
        batches=tuple(batches),
        unrouted=tuple(unrouted),
        monorepo_paths=tuple(monorepo),
    )


# ---------------------------------------------------------------------------
# Self-test (offline, deterministic — guard-the-guard)
# ---------------------------------------------------------------------------


def self_test() -> bool:
    now = "2026-10-17T09:00:00Z"
    hour_ago = "2026-10-17T08:00:00Z"

    # cron contract
    validate_cron("0 * * * *")
    for bad in ("*/30 * * * *", "0 0 * * *", "hourly", ""):
        try:
            validate_cron(bad)
            raise AssertionError(f"cron {bad!r} must be rejected")
        except BatchError:
            pass

    # §3.1 routing matrix
    assert route_path("studio/app.tsx") == "studio"
    assert route_path("examples/dashboard-preview/x.html") == "studio"
    assert route_path("api/gateway.ts") == "api"
    assert route_path("api-schemas/gateway.openapi.yaml") == "api"
    assert route_path("core/router.py") == "core"
    assert route_path("command/telegram.py") == "command"
    assert route_path("handlers/telegram_bot.py") == "command"
    assert route_path("skills/new-tool.json") == "skills"
    assert route_path("examples/langchain-mcp/README.md") == "skills"
    assert route_path("vscode/extension.ts") == "vscode"
    assert route_path("agents/loop.py") == "agents"
    assert route_path("runner/worker.py") == "agents"
    assert route_path("browser/sandbox.ts") == "browser"
    assert route_path("sandbox/stealth.py") == "browser"
    assert route_path("sdk/client.ts") == "sdk"
    assert route_path("examples/sdk-quickstart.py") == "sdk"
    assert route_path("deployments/render.yaml") == "infra"
    assert route_path("infra/terraform.tf") == "infra"
    assert route_path("docs/archive/2026.md") == "archive"
    assert route_path("docs/ledger/x.md") == "archive"
    assert route_path("infrastructure/mcp-control-plane/src/x.ts") == "mcp"
    assert route_path("api-schemas/heartbeat.schema.json") == "mcp"
    # monorepo-designated: never a satellite batch
    assert route_path("scripts/agents/loop.py") == "monorepo"
    assert route_path("docs/AGENT_LOOP_SPEC.md") == "monorepo"
    assert route_path("patches/x.patch") == "monorepo"
    assert route_path("AGENTS.md") == "monorepo"
    assert route_path("AGENT_RULES.md") is None  # deleted constitution — fail-closed quarantine (#1642)
    # fail-closed quarantine
    assert route_path("README.md") is None
    assert route_path("mcp.json") is None
    assert route_path("api-schemas/unknown.x") is None

    # SHA intake
    validate_sha("a" * 40)
    for bad in ("", "short", "A" * 40, "g" * 40, 123):
        try:
            validate_sha(bad)
            raise AssertionError(f"sha {bad!r} must be rejected")
        except BatchError:
            pass

    # window semantics
    assert in_batch_window("2026-10-17T08:30:00Z", hour_ago, now)
    assert not in_batch_window("2026-10-17T07:59:59Z", hour_ago, now)
    assert not in_batch_window("2026-10-17T09:00:00Z", hour_ago, now)  # exclusive end
    try:
        in_batch_window("oops", hour_ago, now)
        raise AssertionError("malformed timestamp must be rejected")
    except BatchError:
        pass
    try:
        in_batch_window(now, now, hour_ago)
        raise AssertionError("inverted window must be rejected")
    except BatchError:
        pass

    # urgent fast-lane
    assert is_urgent(["bridge:urgent"])
    assert is_urgent(["fast-track", "repo:studio"])
    assert not is_urgent(["repo:studio"])
    assert not is_urgent([])

    # plan: windowed aggregation + urgent bypass + quarantine + monorepo split
    a1, a2, b1 = "a" * 40, "b" * 40, "c" * 40
    plan = plan_batches(
        [
            LandedCommit(
                a1, ("studio/app.tsx", "docs/ledger/x.md"), "2026-10-17T08:10:00Z"
            ),
            LandedCommit(
                a2, ("browser/sandbox.ts", "unrouted.bin"), "2026-10-17T08:20:00Z"
            ),
            LandedCommit(
                b1,
                ("api/gateway.ts",),
                "2026-10-17T07:00:00Z",
                frozenset({"fast-track"}),
            ),
            LandedCommit(
                "d" * 40, ("api/gateway.ts",), "2026-10-17T07:30:00Z"
            ),  # outside window
        ],
        hour_ago,
        now,
    )
    assert [b.satellite for b in plan.batches] == [
        "api",
        "archive",
        "browser",
        "studio",
    ]  # sorted
    api_batch = plan.batches[0]
    assert api_batch.shas == (b1,) and api_batch.urgent is True  # bypassed the window
    assert api_batch.files == ("api/gateway.ts",)
    archive_batch = plan.batches[1]
    assert (
        archive_batch.satellite == "archive"
    )  # §3.1: docs/ledger/** → archive, not monorepo
    assert archive_batch.files == ("docs/ledger/x.md",)
    studio_batch = plan.batches[3]
    assert studio_batch.shas == (a1,) and studio_batch.urgent is False
    assert studio_batch.files == ("studio/app.tsx",)
    assert plan.unrouted == ((a2, "unrouted.bin"),)
    assert (
        plan.monorepo_paths == ()
    )  # docs/ledger/** routes to archive, not the monorepo
    # consolidated, not micro-commits: one batch per satellite
    assert len(plan.batches) == len({b.satellite for b in plan.batches})

    # freshness guard
    parents = {a1: "0" * 40, "0" * 40: "1" * 40}
    assert is_descendant(a1, "0" * 40, parents)
    assert is_descendant(a1, a1, parents)  # already-synced head is a no-op
    try:
        is_descendant("9" * 40, "0" * 40, parents)
        raise AssertionError("unknown head must fail closed")
    except FreshnessViolation:
        pass
    try:
        cyclic = {"ab" * 20: "cd" * 20, "cd" * 20: "ab" * 20}
        is_descendant("ab" * 20, "0" * 40, cyclic)
        raise AssertionError("cycle must fail closed")
    except FreshnessViolation:
        pass

    # 3-way ingestion guard
    commit_files = {a2: ("browser/sandbox.ts",), "e" * 40: ("browser/other.ts",)}
    parents3 = {"e" * 40: a2, a2: "0" * 40}
    assert (
        three_way_check(
            ("browser/fresh.ts",), "0" * 40, "e" * 40, parents3, commit_files
        )
        == ()
    )
    assert three_way_check(
        ("browser/sandbox.ts",), "0" * 40, "e" * 40, parents3, commit_files
    ) == ("browser/sandbox.ts",)
    assert three_way_check(
        ("browser/other.ts",), "0" * 40, "e" * 40, parents3, commit_files
    ) == ("browser/other.ts",)
    # plan-level conflict → fail-closed whole batch
    try:
        plan_batches(
            [LandedCommit("f" * 40, ("browser/sandbox.ts",), "2026-10-17T08:40:00Z")],
            hour_ago,
            now,
            last_synced={"browser": "0" * 40},
            target_heads={"browser": "e" * 40},
            parents=parents3,
            commit_files=commit_files,
        )
        raise AssertionError("conflicting batch must be rejected")
    except BatchConflict:
        pass
    # plan-level stale target → fail-closed
    try:
        plan_batches(
            [LandedCommit(a1, ("studio/app.tsx",), "2026-10-17T08:40:00Z")],
            hour_ago,
            now,
            last_synced={"studio": "e" * 40},  # sync base newer than target head a1
            target_heads={"studio": a1},
            parents={a1: "0" * 40, "e" * 40: a1},
            commit_files={},
        )
        raise AssertionError("stale target must be rejected")
    except FreshnessViolation:
        pass

    print("self-test OK — hourly_satellite_batcher (issue #514 Tier 2 & Tier 3)")
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Hourly Satellite Batcher (issue #514)"
    )
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
