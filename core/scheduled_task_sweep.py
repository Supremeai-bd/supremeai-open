"""core/scheduled_task_sweep.py — M22 P-A: due-task sweep pulse (S10 store → জীবন্ত নির্বাহ).

বাংলা মন্তব্য: আগে `scheduled_tasks` টেবিলে ব্যবহারকারীর টাস্ক জমা হতো কিন্তু
কোনো executor ছিল না — CRUD-ই শেষ, টাস্ক কখনো চলত না (built-but-unwired)।
এই মডিউল ওই গর্ত বন্ধ করে:

- **ক্যাচআপ (cron-গর্ত-সচেতন):** `last_run_at` DB-স্থায়ী — shutdown-চলাকালীন মিস হওয়া
  due টাস্ক restart-এর পরেও নষ্ট হয় না, sweep-শুরুতে বয়স্ক-due-আগে নির্বাহ হয়।
- **দ্বৈত-নির্বাহ-প্রতিরোধ:** CAS (compare-and-set) দাবি — `last_run_at`-এর পুরোনো মান
  WHERE-এ রেখে update; যে update-এর data খালি, সে নির্বাহ থেকে বিরত। একাধিক worker
  একই টাস্ক দুবার চালাতে পারে না।
- **স্টেল-দাবি পুনর্গ্রহ:** প্রসেস-ক্র্যাশে `running` আটকে থাকা টাস্ক একটি সীমা
  (stale-claim) পার হলে আবার দাবি-যোগ্য — কাজ হারায় না (at-least-once)।
- **সৎ সীমা (False-Assurance):** `custom` cron-type-এর জন্য এই sweep প্রার্থী নয় —
  প্যার্সার P-A scope-এ নেই; ভুয়া "চলেছে" দাবি না করে `unsupported_custom` স্ট্যাটে গোনা
  হয় এবং প্রতি sweep-এ সৎভাবে জানানো হয়।

ক্যাডেন্স: `SCHEDULED_TASK_SWEEP_INTERVAL_SECONDS` (ডিফল্ট ৬০ সেকেন্ড)।
Stale-সীমা: `SCHEDULED_TASK_SWEEP_STALE_CLAIM_SECONDS` (ডিফল্ট ৯০০ সেকেন্ড)।
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from core.logging_config import logger

DEFAULT_SWEEP_INTERVAL_SECONDS = 60
DEFAULT_STALE_CLAIM_SECONDS = 900
SWEEP_BATCH_LIMIT = 200

_WARN_THROTTLE_SECONDS = 600.0


def _parse_iso(value: Any) -> datetime | None:
    """ISO-8601 পার্স — ব্যর্থ হলে None (কলার সৎভাবে invalid গুনবে, ফেক টাইম বানাবে না)।"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _aware(dt: datetime) -> datetime:
    """Naive datetime পেলে UTC ধরে নেই (DB স্তর সামঞ্জস্যের জন্য) — অন্যথায় অপরিবর্তিত।"""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def compute_due(task: dict[str, Any], now: datetime) -> bool | None:
    """বিশুদ্ধ due-নির্ণয় (টেস্ট-বান্ধব)।

    Returns:
        True  — এই মুহূর্তে নির্বাহ-প্রার্থী,
        False — এখনো due নয় (বা disabled),
        None  — এই sweep এই ধরন চালাতে পারে না (custom cron) — সৎ অসমর্থন।
    """
    if not task.get("is_active", False):
        return False

    schedule_type = task.get("schedule_type", "once")
    scheduled_time = _parse_iso(task.get("scheduled_time"))
    last_run = _aware(_parse_iso(task.get("last_run_at"))) if task.get("last_run_at") else None

    # বাংলা: last_run_status == "running" মানে আগের দাবিটি কখনো সম্পন্ন হয়নি
    # (ক্র্যাশ/স্টেল দাবি) — তাই সেটি "শেষ নির্বাহ" হিসেবে গণ্য নয়; কেবল সম্পন্ন
    # অবস্থা (success/failed) পুনরাবৃত্ত-স্লট/once-স্কিপের ভিত্তি হতে পারে।
    if task.get("last_run_status") == "running":
        last_run = None

    if schedule_type == "custom":
        # বাংলা: cron-এক্সপ্রেশন পার্সার এই P-A ধাপে নেই — ভুয়া due-হিসাব বানানোর
        # বদলে স্পষ্টভাবে "অসমর্থিত" জানাই; টাস্ক অস্পৃশ্য থাকে।
        return None

    if scheduled_time is None:
        # বাংলা: scheduled_time ছাড়া টাস্ক due-হিসাবই অসম্ভব — ফেক ডিফল্ট নয়, not-due।
        return False

    scheduled_time = _aware(scheduled_time)

    if schedule_type == "once":
        return scheduled_time <= now and last_run is None

    if schedule_type == "daily":
        step = timedelta(days=1)
    elif schedule_type == "weekly":
        step = timedelta(days=7)
    else:
        # বাংলা: অজানা schedule_type — চুপচাপ ভুয়া ধরে নেওয়ার বদলে অসমর্থন।
        return None

    # পুনরাবৃত্ত টাস্ক: শেষ সম্পন্ন স্লট = scheduled_time-এর ঘরের সময়, এখনের ঠিক আগেরটি
    slot = now.replace(
        hour=scheduled_time.hour,
        minute=scheduled_time.minute,
        second=scheduled_time.second,
        microsecond=0,
    )
    if slot > now:
        slot -= step

    if last_run is None:
        # প্রথম নির্বাহ: নির্ধারিত সময় পেরিয়েছে কি না।
        return scheduled_time <= now
    return last_run < slot


def _in_flight_or_stale(task: dict[str, Any], now: datetime, stale_seconds: float) -> str:
    """`running` আটকে থাকা দাবির অবস্থা: 'in_flight' (সদ্য), 'stale' (পুরোনো), নয়তো ''।"""
    if task.get("last_run_status") != "running":
        return ""
    last_run = _aware(_parse_iso(task.get("last_run_at"))) if task.get("last_run_at") else None
    if last_run is None:
        return "stale"  # বাংলা: দাবি আছে কিন্তু সময়ই নেই — অসম্পূর্ণ লেখা; পুনর্গ্রহ নিরাপদ
    age = (now - last_run).total_seconds()
    return "in_flight" if age <= stale_seconds else "stale"


async def _claim_task(client: Any, task_id: str, prev_last_run: Any, now_iso: str) -> bool:
    """CAS দাবি — পুরোনো last_run_at মিললেই কেবল দাবি সফল (দ্বৈত-নির্বাহ-প্রতিরোধ)।"""
    query = (
        client.table("scheduled_tasks")
        .update({"last_run_at": now_iso, "last_run_status": "running", "updated_at": now_iso})
        .eq("id", task_id)
    )
    if prev_last_run is None:
        query = query.is_("last_run_at", None)
    else:
        query = query.eq("last_run_at", prev_last_run)
    resp = await query.execute()
    return bool(resp.data)


async def _start_run_observation(
    task: dict[str, Any], idempotency_key: str
) -> dict[str, Any] | None:
    """টাস্ক-নির্বাহকে Run fabric-এ নিবন্ধন (M02 P-B/ERR-F01) — REQUESTED→…→RUNNING।

    বাংলা: পর্যবেক্ষণ-স্তর ব্যর্থ হলে টাস্ক-নির্বাহ আটকাবে না (observability
    secondary) — তবে কখনো নীরব নয়: লাউড loguru সতর্কতা + None ফেরত। ভুয়া
    'run তৈরি হয়েছে' দাবি নেই।
    """
    try:
        from database.session import get_db_session_context
        from runs.api import run_service as fabric_service
        from runs.bridges import observe_task_run
        from runs.state_machine import PLANNED, POLICY_CHECKED, RUNNING

        async with get_db_session_context() as session:
            run = await observe_task_run(
                session,
                fabric_service,
                task_id=str(task.get("id", "")),
                user_id=str(task.get("user_id", "")),
                title=f"Scheduled task: {task.get('title', '')}"[:200],
                idempotency_key=idempotency_key,
            )
            for next_state in (POLICY_CHECKED, PLANNED, RUNNING):
                await fabric_service.transition(
                    session, run.id, next_state, actor="scheduled-task-sweep"
                )
            await session.commit()
            return {"run_id": str(run.id)}
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(f"📅 Run-fabric observation start failed for task {task.get('id')}: {exc}")
        return None


async def _finish_run_observation(
    observation: dict[str, Any], terminal_state: str, detail: dict[str, Any]
) -> None:
    """রানকে terminal-অবস্থায় সীল করা — ব্যর্থতাও লাউড-লগ, কখনো নীরব নয়।"""
    try:
        from database.session import get_db_session_context
        from runs.api import run_service as fabric_service

        async with get_db_session_context() as session:
            await fabric_service.transition(
                session,
                observation["run_id"],
                terminal_state,
                actor="scheduled-task-sweep",
                detail=detail,
            )
            await session.commit()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            f"📅 Run-fabric observation finish failed (run {observation.get('run_id')}): {exc}"
        )


async def sweep_due_tasks_once(now: datetime | None = None) -> dict[str, Any]:
    """একটি পূর্ণ sweep-চক্র — active টাস্ক পড়ে, due গুলো CAS-দাবি করে নির্বাহ করে।

    স্ট্যাট ফেরত দেয় (scanned/due/executed/failed/claimed_by_other/in_flight/
    unsupported_custom/invalid_time/once_consumed/db_available) — সংখ্যাগুলোই সৎ
    অবজারভেবিলিটি; কোনো ফল নীরবে গিলে ফেলা হয় না।
    """
    now = _aware(now) if now else datetime.now(UTC)
    now_iso = now.isoformat()
    stats: dict[str, Any] = {
        "scanned": 0,
        "due": 0,
        "executed": 0,
        "failed": 0,
        "claimed_by_other": 0,
        "in_flight": 0,
        "stale_taken_over": 0,
        "unsupported_custom": 0,
        "invalid_time": 0,
        "once_consumed": 0,
        "db_available": True,
    }

    # বাংলা: লেজি ইমপোর্ট — এই মডিউল core-এ, রুট-স্তরের সাথে সার্কুলার ইমপোর্ট এড়াতে।
    from api.routes.scheduled_tasks import (
        _ensure_schema,
        _row_to_task,
        execute_task_and_record,
    )
    from database.supabase_client import db as supabase_db

    client = supabase_db.client
    if not client:
        stats["db_available"] = False
        return stats

    # বাংলা: টেবিল না থাকলে নির্বাহ-চেষ্টাই ভুয়া হতো — আগে স্কিমা নিশ্চিত (একবারই, ফ্ল্যাগ-গার্ডেড)।
    try:
        _ensure_schema()
    except Exception as schema_exc:
        stats["db_available"] = False
        logger.warning(f"📅 Scheduled-task sweep schema check failed: {schema_exc}")
        return stats

    stale_seconds = float(
        os.getenv("SCHEDULED_TASK_SWEEP_STALE_CLAIM_SECONDS", str(DEFAULT_STALE_CLAIM_SECONDS))
    )

    rows_resp = await (
        client.table("scheduled_tasks")
        .select("*")
        .eq("is_active", True)
        .order("scheduled_time", desc=False)  # বয়স্ক-due-আগে (ক্যাচআপ শৃঙ্খলা)
        .limit(SWEEP_BATCH_LIMIT)
        .execute()
    )
    rows = list(rows_resp.data or [])
    stats["scanned"] = len(rows)

    unsupported_logged = False
    for row in rows:
        task = _row_to_task(row)

        flight_state = _in_flight_or_stale(task, now, stale_seconds)
        if flight_state == "in_flight":
            stats["in_flight"] += 1
            continue
        if flight_state == "stale":
            # বাংলা: অন্য worker দাবি করে ক্র্যাশ করেছে — at-least-once পুনর্গ্রহ;
            # CAS এখনো সেই পুরোনো টাইমস্ট্যাম্পেই বাঁধবে, তাই দ্বৈত-নির্বাহ হয় না।
            stats["stale_taken_over"] += 1

        due = compute_due(task, now)
        if due is None:
            stats["unsupported_custom"] += 1
            if not unsupported_logged:
                logger.warning(
                    "📅 Scheduled-task sweep: custom-cron টাস্ক এই sweep-এ অসমর্থিত "
                    f"(task_id={task.get('id')}) — P-A সীমা, ভুয়া নির্বাহ-দাবি নয়।"
                )
                unsupported_logged = True
            continue
        if not due:
            # বাংলা: unparseable scheduled_time-ও not-due হিসেবেই আসে — কিন্তু চুপচাপ
            # নয়, সৎ গণনায় ধরা পড়বে যেন মালিক দেখতে পান।
            if task.get("scheduled_time") and _parse_iso(task.get("scheduled_time")) is None:
                stats["invalid_time"] += 1
            continue

        stats["due"] += 1
        claimed = await _claim_task(client, task["id"], task.get("last_run_at"), now_iso)
        if not claimed:
            # বাংলা: মাঝপথে অন্য worker দাবি করে ফেলেছে — আমরা বিরত; এটাই CAS-এর কাজ।
            stats["claimed_by_other"] += 1
            continue

        # বাংলা (M02 P-B): প্রকৃত নির্বাহ Run fabric-এ পর্যবেক্ষিত হয় —
        # idempotency-key দাবি-টাইমস্ট্যাম্প বাঁধা, প্রতি-চেষ্টায় স্বতন্ত্র রান।
        observation = await _start_run_observation(task, f"scheduled-task:{task['id']}:{now_iso}")

        try:
            result = await execute_task_and_record(task, str(task.get("user_id", "")))
        except asyncio.CancelledError:
            if observation:
                await _finish_run_observation(observation, "failed", {"reason": "sweep cancelled"})
            raise
        except Exception as exec_exc:
            # বাংলা: শেয়ার্ড পথের বাইরে ব্যর্থতা (যেমন DB-লেখা নিজেই ভাঙল) — নীরব গিলে
            # ফেলা মানে ভুয়া "সব ঠিক আছে"; সৎ লগ + failed-গণনা, রানও সৎভাবে failed।
            logger.error(f"📅 Sweep execution crashed for task {task.get('id')}: {exec_exc}")
            stats["failed"] += 1
            if observation:
                await _finish_run_observation(
                    observation, "failed", {"reason": str(exec_exc)[:200]}
                )
            continue

        terminal = "succeeded" if result.get("status") == "success" else "failed"
        if observation:
            await _finish_run_observation(
                observation, terminal, {"execution_status": result.get("status")}
            )
        if terminal == "succeeded":
            stats["executed"] += 1
        else:
            stats["failed"] += 1

        if task.get("schedule_type") == "once":
            # বাংলা: once-টাস্ক সফল হোক বা সৎভাবে ব্যর্থ — একবার নির্বাহ-চেষ্টা সম্পন্ন;
            # consume না করলে এটি প্রতি sweep-এ বারবার চলত (লুপিং-খরচ)।
            await (
                client.table("scheduled_tasks")
                .update({"is_active": False, "updated_at": datetime.now(UTC).isoformat()})
                .eq("id", task["id"])
                .execute()
            )
            stats["once_consumed"] += 1

    return stats


async def run_due_task_sweep_loop() -> None:
    """AgentSupervisor-নিবন্ধিত চিরন্তন sweep-স্পন্দন (stdlib asyncio)।

    বাংলা: S11 Scheduled Tasks ব্যবহারকারী-মুখী ফিচার — ব্যবহারকারী টাস্ক বানিয়ে
    "এটা চলবে" বোঝেন; তাই এই এজেন্ট env-gated নয় (ভুয়া ফিচার-প্রতিশ্রুতি এড়াতে)।
    DB অনুপস্থিতিতে লুপ বাঁচে কিন্তু প্রতি ~১০ মিনিটে একবার সৎ সতর্কতা দেয়।
    """
    last_warn_monotonic = 0.0
    while True:
        try:
            interval = int(
                os.getenv(
                    "SCHEDULED_TASK_SWEEP_INTERVAL_SECONDS", str(DEFAULT_SWEEP_INTERVAL_SECONDS)
                )
            )
        except ValueError:
            # বাংলা: অবৈধ env-মানে ডিফল্টে ফেরা — কিন্তু চুপ না করে জানানো হয়।
            logger.warning(
                "📅 SCHEDULED_TASK_SWEEP_INTERVAL_SECONDS অবৈধ — "
                f"ডিফল্ট {DEFAULT_SWEEP_INTERVAL_SECONDS}s ব্যবহৃত হচ্ছে।"
            )
            interval = DEFAULT_SWEEP_INTERVAL_SECONDS

        try:
            stats = await sweep_due_tasks_once()
            if not stats["db_available"]:
                now_mono = time.monotonic()
                if now_mono - last_warn_monotonic > _WARN_THROTTLE_SECONDS:
                    logger.warning(
                        "📅 Scheduled-task sweep idle — database অনুপস্থিত "
                        "(supabase client None); DB এলেই নির্বাহ স্বয়ংক্রিয়।"
                    )
                    last_warn_monotonic = now_mono
            elif stats["executed"] or stats["failed"] or stats["due"]:
                logger.info(f"📅 Scheduled-task sweep চক্র সম্পন্ন: {stats}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # বাংলা: একটি চক্রের ব্যর্থতা পুরো লুপ মেরে ফেলবে না (supervisor restart-এর
            # খরচ বাঁচাতে), কিন্তু নীরবেও গিলবে না — থ্রটল-করা সৎ সতর্কতা।
            now_mono = time.monotonic()
            if now_mono - last_warn_monotonic > _WARN_THROTTLE_SECONDS:
                logger.warning(f"⚠️ Scheduled-task sweep চক্র ব্যর্থ (পরের চক্রে পুনরায়): {exc}")
                last_warn_monotonic = now_mono

        await asyncio.sleep(interval)
