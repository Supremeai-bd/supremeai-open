"""Usage metrics aggregator — the last mile of the usage-analytics pipeline.

বাংলা (#1827): usage_metrics টেবিল + GET/POST route + DB helper + frontend
চার্ট সবই ছিল, কিন্তু কোনো writer ছিল না — তাই Usage dashboard স্থায়ীভাবে
খালি থাকত। এই agent দৈনিকভাবে in-process metrics collector + CostGuard
Redis counters থেকে aggregate করে বিদ্যমান `db.upsert_usage_metric()` দিয়ে
লেখে — কোনো manual POST লাগে না।

Delta semantics: metrics collector-এর counters process-lifetime cumulative —
তাই প্রতিটি snapshot-এর সাথে আগের snapshot মনে রেখে শুধু বৃদ্ধি (delta) লেখা
হয়, যাতে দৈনিক rows সত্যিকারের দৈনিক ব্যবহার বোঝায়।

Honest zeros: unique_users/avg_latency_ms-এর কোনো in-process data source
এখনো নেই — ভুয়া সংখ্যা না বানিয়ে 0 লেখা হয় (zero-hardcoding + honesty rules)।
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("usage_metrics_aggregator")

USAGE_METRICS_DIMENSIONS = (
    "total_requests",
    "total_tokens",
    "total_cost",
    "unique_users",
    "avg_latency_ms",
    "error_rate",
)


def _today_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


async def collect_usage_snapshot(
    tenant_id: str,
    collector: Any,
    redis: Any = None,
    last_totals: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Aggregate the in-process collectors into one usage_metrics row.

    `last_totals` (mutated in place) tracks the previous cumulative values so
    the returned row contains only the DELTA since the last call.
    """
    health = await collector.get_overall_health()
    total_requests = int(health.get("total_requests", 0))
    total_errors = int(health.get("total_errors", 0))

    # ai_tokens_total:* counters — tokens recorded per model label.
    total_tokens = sum(
        int(value)
        for key, value in getattr(collector, "_metrics", {}).items()
        if str(key).startswith("ai_tokens_total:")
    )

    total_cost = float(sum((health.get("ai_costs") or {}).values()))

    # CostGuard daily spends (Redis, 24h TTL keys) — fail-open to 0.
    if redis is not None:
        try:
            client = await redis.get_client_async()
            if client is not None:
                keys = await client.keys("cost_guard:*:spent")
                for key in keys or []:
                    raw = await client.get(key)
                    if raw:
                        total_cost += float(raw)
        except Exception as exc:  # noqa: BLE001 — aggregation never crashes the loop
            logger.warning(f"[usage-metrics] cost_guard read skipped: {exc}")

    current = {
        "total_requests": float(total_requests),
        "total_tokens": float(total_tokens),
        "total_cost": total_cost,
    }
    baseline = last_totals if last_totals is not None else {}
    delta = {k: max(0.0, current[k] - baseline.get(k, 0.0)) for k in current}
    if last_totals is not None:
        last_totals.update(current)

    return {
        "metric_date": _today_utc(),
        "total_requests": int(delta["total_requests"]),
        "total_tokens": int(delta["total_tokens"]),
        "total_cost": round(delta["total_cost"], 4),
        "unique_users": 0,  # no in-process per-user source yet — honest zero
        "avg_latency_ms": 0,  # no HTTP latency histogram yet — honest zero
        "error_rate": round(total_errors / total_requests, 4) if total_requests else 0.0,
        "tenant_id": tenant_id,
    }


async def run_aggregation_cycle(
    tenant_id: str = "tenant-supremeai",
    collector: Any = None,
    store: Any = None,
    redis: Any = None,
    last_totals: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    """One aggregation pass → upsert via the existing db helper. Never raises."""
    try:
        if collector is None:
            from monitoring.metrics_collector import metrics_collector as collector
        if store is None:
            from database.supabase_client import db as store
        if redis is None:
            try:
                from core.cache.redis_manager import redis_manager as redis
            except Exception:  # noqa: BLE001 — redis optional
                redis = None
        if last_totals is None:
            last_totals = _LAST_TOTALS

        snapshot = await collect_usage_snapshot(tenant_id, collector, redis, last_totals)

        # db.upsert_usage_metric uses the sync Supabase client — offload it.
        await asyncio.to_thread(store.upsert_usage_metric, snapshot)
        logger.info(
            f"[usage-metrics] aggregated {snapshot['metric_date']}: "
            f"requests={snapshot['total_requests']} tokens={snapshot['total_tokens']} "
            f"cost=${snapshot['total_cost']} error_rate={snapshot['error_rate']}"
        )
        return snapshot
    except Exception as exc:  # noqa: BLE001 — a failed cycle must not kill the loop
        logger.warning(f"[usage-metrics] aggregation cycle failed: {exc}")
        return None


# Process-lifetime cumulative baselines for delta computation.
_LAST_TOTALS: dict[str, float] = {}


async def run_usage_metrics_loop(
    interval_hours: int = 24,
    tenant_id: str = "tenant-supremeai",
) -> None:
    """Supervisor loop body — aggregate immediately, then every interval."""
    while True:
        await run_aggregation_cycle(tenant_id=tenant_id)
        await asyncio.sleep(max(1, interval_hours) * 3600)
