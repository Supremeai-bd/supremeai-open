"""Learning Loop Agent — Sprint 4 of the Self-Evolution Zero-Cost plan.

Closes the observe → analyze → propose loop on a bounded, env-gated cycle:

    learning_events (Postgres, written by core.learning.store)
        -> hourly aggregation (provider_metrics / skill_metrics)
        -> fitness snapshots (fitness_snapshots)
        -> error-pattern scan (error_hash groups)
        -> improvement_proposals rows (NEVER auto-applied — plan §10.3)

Design contracts:
  * Evidence before adaptation (plan Principle 1): proposals are only created
    when the same error_hash fires >= ERROR_PATTERN_MIN_OCCURRENCES times
    within the scan window; every proposal carries baseline evidence.
  * No automatic production fix (plan §10.3): the agent only INSERTS
    improvement_proposals rows for human/HITL review — it never mutates
    routing, cache TTLs or skills by itself.
  * Every cycle is wrapped in try/except — a failing cycle logs and retries
    on the next tick; the agent never crashes the process.
  * Zero cost: pure PostgREST reads/aggregates, no LLM calls.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    from core.logging_config import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("core.learning.loop")

__all__ = ["LearningLoopAgent", "get_learning_loop_agent"]

# Plan §7.2 minimum-sample policy: proposals need >= 3 identical errors.
ERROR_PATTERN_MIN_OCCURRENCES = 3
# Plan §7.2 sample-size tiers for aggregate metrics.
MIN_SAMPLES_CAUTIOUS = 10
MIN_SAMPLES_NORMAL = 50

DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes, matching house loop cadence
_SCAN_HOURS = 1  # aggregation window per cycle


def _hour_window_start(hours_ago: int = 0) -> str:
    now = datetime.now(UTC)
    start = (now - timedelta(hours=hours_ago)).replace(minute=0, second=0, microsecond=0)
    return start.isoformat()


class LearningLoopAgent:
    """Periodic: aggregate → snapshot → error-pattern scan → proposals."""

    def __init__(self, interval_seconds: int = DEFAULT_INTERVAL_SECONDS):
        self.interval_seconds = max(60, int(interval_seconds))
        self._running = False
        self._task: asyncio.Task | None = None
        self.cycles_run = 0
        self.proposals_created = 0
        self.last_cycle_at: str | None = None
        self.last_error: str | None = None

    # ------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info(
            f"✅ LearningLoopAgent started (interval={self.interval_seconds}s, "
            "observe→aggregate→propose; never auto-applies)"
        )

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.debug("LearningLoopAgent task cancelled successfully during stop")
            except Exception as loop_stop_err:  # pragma: no cover
                logger.debug(f"LearningLoopAgent task stop error: {loop_stop_err}")
            self._task = None
        logger.info("LearningLoopAgent stopped.")

    async def _loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break
                await self.run_cycle()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # never crash the supervisor
                self.last_error = str(exc)[:300]
                logger.warning(f"LearningLoopAgent cycle error: {exc}")

    # ------------------------------------------------------------ cycle
    async def run_cycle(self) -> dict[str, Any]:
        """One observe→propose pass. Returns a small stats dict for observability."""
        stats: dict[str, Any] = {
            "provider_rows": 0,
            "skill_rows": 0,
            "fitness_snapshots": 0,
            "error_patterns": 0,
            "proposals": 0,
        }
        db = self._get_db()
        if db is None:
            logger.debug("LearningLoopAgent: supabase client unavailable — cycle skipped")
            return stats

        try:
            events = db.get_learning_events(limit=2000, hours=_SCAN_HOURS) or []
        except Exception as exc:
            self.last_error = str(exc)[:300]
            logger.debug(f"LearningLoopAgent: could not read learning events: {exc}")
            return stats

        if not events:
            self.cycles_run += 1
            self.last_cycle_at = datetime.now(UTC).isoformat()
            return stats

        window_start = _hour_window_start(0)

        # 1) Provider metrics rollup (plan §8.1 inputs)
        try:
            from core.learning.store import aggregate_provider_metrics

            provider_rows: list[dict] = []
            for row in aggregate_provider_metrics(events, window_start):
                if db.upsert_provider_metric(row):
                    stats["provider_rows"] += 1
                    provider_rows.append(row)
            # Sprint 5: refresh the in-process provider-score snapshot the
            # gateway reads (behind ENABLE_ADAPTIVE_ROUTING) — no network in
            # the request path, bounded change (exploration candidate only).
            if provider_rows:
                from core.learning.provider_scorer import refresh_score_snapshot

                refresh_score_snapshot(provider_rows)
        except Exception as exc:
            logger.debug(f"provider aggregation skipped: {exc}")

        # 2) Skill metrics rollup
        try:
            for row in self._aggregate_skill_metrics(events, window_start):
                if db.upsert_skill_metric(row):
                    stats["skill_rows"] += 1
        except Exception as exc:
            logger.debug(f"skill aggregation skipped: {exc}")

        # 3) Fitness snapshots per task_type (evidence for adaptive thresholds later)
        try:
            for subject_id, snapshot in self._fitness_snapshots(events).items():
                row = {
                    "subject_type": "task_type",
                    "subject_id": subject_id,
                    **snapshot,
                }
                if db.append_fitness_snapshot(row):
                    stats["fitness_snapshots"] += 1
        except Exception as exc:
            logger.debug(f"fitness snapshot skipped: {exc}")

        # 4) Error-pattern scan → improvement proposals (plan §10.1-10.3)
        try:
            proposals = self._error_pattern_proposals(events)
            stats["error_patterns"] = len(proposals)
            for proposal in proposals:
                proposal_id = db.insert_improvement_proposal(proposal)
                if proposal_id:
                    stats["proposals"] += 1
                    self.proposals_created += 1
                    db.insert_improvement_run(
                        {
                            "proposal_id": proposal_id,
                            "run_type": "BASELINE",
                            "result": "evidence_recorded",
                            "metrics": proposal.get("baseline", {}),
                            "notes": "auto-generated evidence baseline (no auto-apply)",
                        }
                    )
        except Exception as exc:
            logger.debug(f"error-pattern scan skipped: {exc}")

        self.cycles_run += 1
        self.last_cycle_at = datetime.now(UTC).isoformat()
        self.last_error = None
        if any(
            (
                stats["provider_rows"],
                stats["skill_rows"],
                stats["fitness_snapshots"],
                stats["proposals"],
            )
        ):
            logger.info(f"[LearningLoop] cycle #{self.cycles_run}: {stats}")
        return stats

    # ------------------------------------------------------------ pure helpers
    @staticmethod
    def _aggregate_skill_metrics(events: list[dict], window_start: str) -> list[dict]:
        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for event in events:
            skill_id = event.get("skill_id") or event.get("task_type")
            if not skill_id:
                continue
            key = (str(skill_id), str(event.get("task_type") or "general"))
            group = groups.setdefault(
                key,
                {"requests": 0, "successes": 0, "failures": 0, "latencies": [], "actual_cost": 0.0},
            )
            group["requests"] += 1
            if event.get("success") is True:
                group["successes"] += 1
            elif event.get("success") is False:
                group["failures"] += 1
            latency = event.get("latency_ms")
            if isinstance(latency, (int, float)) and latency >= 0:
                group["latencies"].append(int(latency))
            cost = event.get("actual_cost")
            if isinstance(cost, (int, float)):
                group["actual_cost"] += float(cost)

        from core.learning.store import _percentile

        rows: list[dict] = []
        for (skill_id, task_type), group in sorted(groups.items()):
            latencies = sorted(group["latencies"])
            rows.append(
                {
                    "window_start": window_start,
                    "skill_id": skill_id,
                    "task_type": task_type,
                    "requests": group["requests"],
                    "successes": group["successes"],
                    "failures": group["failures"],
                    "latency_p50_ms": _percentile(latencies, 50),
                    "latency_p95_ms": _percentile(latencies, 95),
                    "estimated_cost": 0.0,
                    "actual_cost": round(group["actual_cost"], 6),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            )
        return rows

    @staticmethod
    def _fitness_snapshots(events: list[dict]) -> dict[str, dict]:
        """Composite fitness per task_type: success-rate weighted latency/cost."""
        groups: dict[str, dict[str, Any]] = {}
        for event in events:
            task_type = str(event.get("task_type") or "general")
            group = groups.setdefault(
                task_type, {"successes": 0, "failures": 0, "latencies": [], "cost": 0.0}
            )
            if event.get("success") is True:
                group["successes"] += 1
            elif event.get("success") is False:
                group["failures"] += 1
            latency = event.get("latency_ms")
            if isinstance(latency, (int, float)) and latency >= 0:
                group["latencies"].append(int(latency))
            cost = event.get("actual_cost")
            if isinstance(cost, (int, float)):
                group["cost"] += float(cost)

        snapshots: dict[str, dict] = {}
        for task_type, group in groups.items():
            total = group["successes"] + group["failures"]
            if total < MIN_SAMPLES_CAUTIOUS:
                # Plan §7.2: <10 samples → insufficient evidence, snapshot only.
                continue
            success_rate = group["successes"] / float(total)
            latencies = sorted(group["latencies"])
            avg_latency = sum(latencies) / float(len(latencies)) if latencies else 0.0
            # Deterministic bounded composite in [0,1]: 70% success, 20% latency
            # (1s reference), 10% cost (0.01 reference). Weights configurable later.
            latency_score = max(0.0, 1.0 - (avg_latency / 1000.0))
            cost_score = max(0.0, 1.0 - (group["cost"] / 0.01))
            composite = round(0.70 * success_rate + 0.20 * latency_score + 0.10 * cost_score, 4)
            snapshots[task_type] = {
                "composite": min(1.0, max(0.0, composite)),
                "components": {
                    "success_rate": round(success_rate, 4),
                    "avg_latency_ms": int(avg_latency),
                    "cost_total": round(group["cost"], 6),
                    "samples": total,
                    "sample_tier": ("normal" if total >= MIN_SAMPLES_NORMAL else "cautious"),
                },
                "sample_size": total,
            }
        return snapshots

    @staticmethod
    def _error_pattern_proposals(events: list[dict]) -> list[dict]:
        """Group failures by error_hash → proposals for repeated patterns."""
        counts: dict[str, dict[str, Any]] = {}
        for event in events:
            if event.get("success") is not False:
                continue
            error_hash = str(event.get("error_hash") or "").strip()
            if not error_hash:
                continue
            entry = counts.setdefault(
                error_hash,
                {
                    "count": 0,
                    "error_class": event.get("error_class") or "unknown",
                    "providers": set(),
                    "task_types": set(),
                },
            )
            entry["count"] += 1
            if event.get("provider"):
                entry["providers"].add(str(event["provider"]))
            if event.get("task_type"):
                entry["task_types"].add(str(event["task_type"]))

        proposals: list[dict] = []
        for error_hash, entry in counts.items():
            if entry["count"] < ERROR_PATTERN_MIN_OCCURRENCES:
                continue  # plan §10.2: needs >= 3 identical errors in window
            proposals.append(
                {
                    "proposal_type": "error_pattern",
                    "target": f"error_hash:{error_hash[:16]}",
                    "reason": (
                        f"error_class={entry['error_class']} repeated {entry['count']}x "
                        f"within {_SCAN_HOURS}h on providers={sorted(entry['providers'])} "
                        f"task_types={sorted(entry['task_types'])}"
                    ),
                    "expected_benefit": "investigate/retry-policy/provider-fallback change",
                    "risk": "requires human review before any behavior change",
                    "status": "PROPOSED",
                    "proposal": {
                        "error_hash": error_hash,
                        "error_class": entry["error_class"],
                        "occurrences": entry["count"],
                        "providers": sorted(entry["providers"]),
                        "task_types": sorted(entry["task_types"]),
                        "candidate_actions": [
                            "retry_policy_change",
                            "provider_fallback",
                            "prompt_change",
                            "configuration_proposal",
                        ],
                    },
                    "baseline": {
                        "occurrences": entry["count"],
                        "window_hours": _SCAN_HOURS,
                    },
                    "created_by": "learning_loop_agent",
                }
            )
        return proposals

    @staticmethod
    def _get_db() -> Any | None:
        try:
            from database.supabase_client import db as supabase_db

            return supabase_db
        except Exception as exc:  # pragma: no cover
            logger.debug(f"learning loop db unavailable: {exc}")
            return None


_learning_loop_agent: LearningLoopAgent | None = None


def get_learning_loop_agent() -> LearningLoopAgent:
    global _learning_loop_agent
    if _learning_loop_agent is None:
        _learning_loop_agent = LearningLoopAgent()
    return _learning_loop_agent
