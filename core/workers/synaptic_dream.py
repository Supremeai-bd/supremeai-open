"""backend/workers/synaptic_dream.py — Synaptic Memory Dream Cycle Worker.

Governs Memory Consolidation:
- Prunes transient, low-importance ai_memory rows past the retention horizon.
- Reports honest counts (issue #440 doctrine: real work or loud failure — the
  previous implementation returned hardcoded pruned=5 / consolidated=2 without
  touching any store).
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from core.logging_config import logger

# বাংলা: M01 P-C (issue #453 Wave 4) — ক্যাডেন্স zero-hardcode নীতির প্রতি সম্মান
# রেখে ডিফল্ট-মান কেবল env-অনুপস্থিতির fallback হিসেবে (scheduled_task_sweep প্যাটার্ন),
# প্রকৃত মান সবসময় SYNAPTIC_DREAM_INTERVAL_SECONDS env দিয়ে নিয়ন্ত্রিত।
DEFAULT_DREAM_INTERVAL_SECONDS = 86400  # রাত্রিক চক্র — ডিফল্ট ২৪ ঘণ্টা
_WARN_THROTTLE_SECONDS = 600.0


class DreamCycleReport(BaseModel):
    pruned_count: int = 0
    consolidated_count: int = 0
    duration_ms: float = 0.0
    status: str = "completed"
    message: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class SynapticDreamWorker:
    """Scheduled memory hygiene and consolidation engine."""

    # Rows with importance below this are treated as transient.
    PRUNE_IMPORTANCE_THRESHOLD = 0.2

    def __init__(self, vector_store: Any = None) -> None:
        self.vector_store = vector_store

    async def execute_dream_cycle(
        self,
        tenant_id: str | None = None,
        retention_days: int = 30,
    ) -> DreamCycleReport:
        start_time = time.perf_counter()
        logger.info(f"[SynapticDream] Starting memory dream cycle for tenant={tenant_id or 'all'}")

        pruned = 0
        consolidated = 0
        message = ""

        try:
            cutoff_date = datetime.now(UTC) - timedelta(days=retention_days)

            # 1. REAL prune: delete low-importance ai_memory rows past the
            #    retention horizon via the Supabase service client.
            try:
                from database.supabase_client import db

                result = (
                    db.client.table("ai_memory")
                    .delete()
                    .lt("importance_score", self.PRUNE_IMPORTANCE_THRESHOLD)
                    .lt("created_at", cutoff_date.isoformat())
                    .select("id")
                    .execute()
                )
                pruned = len(result.data or [])
                logger.info(
                    f"[SynapticDream] Pruned {pruned} transient records "
                    f"(importance<{self.PRUNE_IMPORTANCE_THRESHOLD}, older than {cutoff_date.date()})"
                )
            except Exception as store_exc:
                # Honest degradation — never invent a count.
                logger.error(f"[SynapticDream] prune store unavailable: {store_exc}")
                return DreamCycleReport(
                    pruned_count=0,
                    consolidated_count=0,
                    duration_ms=(time.perf_counter() - start_time) * 1000.0,
                    status="degraded_no_store",
                    message=f"Memory store unavailable — nothing pruned ({store_exc!r})",
                )

            # 2. Episodic→durable consolidation has no real pass yet. The old
            #    code faked "consolidated=2" every cycle; report 0 honestly
            #    until a real consolidation pass exists.
            consolidated = 0
            message = "episodic consolidation not implemented yet — real prune counts only"

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            return DreamCycleReport(
                pruned_count=pruned,
                consolidated_count=consolidated,
                duration_ms=elapsed_ms,
                status="completed",
                message=message,
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            logger.error(f"[SynapticDream] Dream cycle failed: {exc}", exc_info=True)
            return DreamCycleReport(
                pruned_count=pruned,
                consolidated_count=consolidated,
                duration_ms=elapsed_ms,
                status=f"failed: {exc}",
            )


synaptic_dream_worker = SynapticDreamWorker()


def resolve_dream_interval() -> int:
    """Env-চালিত dream-cycle ক্যাডেন্স রেজলভ করে (scheduled_task_sweep প্যাটার্ন)।

    বাংলা: অবৈধ env-মানে ডিফল্টে ফেরা — কিন্তু চুপ না করে সৎ সতর্কতা দেওয়া
    (False-Assurance নীতি: নীরব fallback নিষিদ্ধ)।
    """
    try:
        return int(
            os.getenv("SYNAPTIC_DREAM_INTERVAL_SECONDS", str(DEFAULT_DREAM_INTERVAL_SECONDS))
        )
    except ValueError:
        # বাংলা: অবৈধ env-মান — ডিফল্টে ফিরছি, লাউড-লগ ছাড়া নয়।
        logger.warning(
            "🧠 SYNAPTIC_DREAM_INTERVAL_SECONDS অবৈধ — "
            f"ডিফল্ট {DEFAULT_DREAM_INTERVAL_SECONDS}s ব্যবহৃত হচ্ছে।"
        )
        return DEFAULT_DREAM_INTERVAL_SECONDS


async def run_synaptic_dream_loop() -> None:
    """AgentSupervisor-নিবন্ধিত চিরন্তন dream-স্পন্দন (stdlib asyncio)।

    বাংলা: M01 P-C — synaptic_dream worker-টি নির্মিত কিন্তু কোনো scheduler-এ
    wired ছিল না (plan: "scheduled consolidation নেই")। এই লুপ worker-এর
    consolidation/prune লজিক স্পর্শ করে না — কেবল নিবন্ধন-স্পন্দন দেয়।
    store-অনুপস্থিতে লুপ বাঁচে কিন্তু থ্রটল-করা সৎ সতর্কতা দেয়।
    """
    last_warn_monotonic = 0.0
    while True:
        interval = resolve_dream_interval()
        try:
            report = await synaptic_dream_worker.execute_dream_cycle()
            if report.status == "degraded_no_store":
                now_mono = time.monotonic()
                if now_mono - last_warn_monotonic > _WARN_THROTTLE_SECONDS:
                    logger.warning(
                        "🧠 SynapticDream idle — memory store অনুপস্থিত; "
                        f"store এলেই চক্র স্বয়ংক্রিয় ({report.message})"
                    )
                    last_warn_monotonic = now_mono
            elif report.status != "completed":
                now_mono = time.monotonic()
                if now_mono - last_warn_monotonic > _WARN_THROTTLE_SECONDS:
                    logger.warning(f"⚠️ SynapticDream চক্র অসম্পূর্ণ (পরের চক্রে পুনরায়): {report.status}")
                    last_warn_monotonic = now_mono
            else:
                logger.info(
                    f"🧠 SynapticDream চক্র সম্পন্ন: pruned={report.pruned_count} "
                    f"consolidated={report.consolidated_count} "
                    f"duration_ms={report.duration_ms:.1f}"
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # বাংলা: একটি চক্রের ব্যর্থতা পুরো লুপ মেরে ফেলবে না (supervisor
            # restart-খরচ বাঁচাতে), কিন্তু নীরবে গিলবেও না — থ্রটল-করা সৎ সতর্কতা।
            now_mono = time.monotonic()
            if now_mono - last_warn_monotonic > _WARN_THROTTLE_SECONDS:
                logger.warning(f"⚠️ SynapticDream চক্র ব্যর্থ (পরের চক্রে পুনরায়): {exc}")
                last_warn_monotonic = now_mono

        await asyncio.sleep(interval)
