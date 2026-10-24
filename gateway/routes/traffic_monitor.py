import json
import time
from typing import Any

from fastapi import APIRouter, Depends

from api.dependencies import get_current_admin
from core.cache.redis_manager import redis_manager
from core.logging_config import logger

router = APIRouter(
    prefix="/api/admin/traffic",
    tags=["Traffic Control"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/live")
async def get_live_traffic(admin: dict = Depends(get_current_admin)) -> dict[str, Any]:
    """বাংলা মন্তব্য: রিয়েল-টাইম ট্রাফিক, p95 ল্যাটেন্সি এবং অ্যারর রেট।
    এটি স্টুডিও ক্লায়েন্ট বা ফ্লাটার ড্যাশবোর্ডে লাইভ স্ট্রিমিং এর জন্য ব্যবহার হবে।

    রেস্পন্স শেপ: TrafficData = { current_rps, window_30min, distribution }
    (frontend flat shape অনুযায়ী — wrapper নয়)।"""

    # বাংলা মন্তব্য: রেডিস মিসকনফিগ (যেমন 'mock_redis_url') বা কানেকশন এররে
    # ৫০০ না দিয়ে শূন্য মেট্রিক্স রিটার্ন করি — ট্যাব crash না করে "NO DATA" দেখায়।
    def _empty() -> dict[str, Any]:
        return {
            "current_rps": 0.0,
            "window_30min": [0] * 30,
            "distribution": {},
        }

    if not redis_manager.client:
        logger.warning("traffic/live: redis not connected — returning empty metrics")
        return _empty()

    now = int(time.time())
    current_minute = now // 60
    # Fetch data for the last 30 minutes to build a rolling window
    keys_to_fetch = [f"traffic:live:{current_minute - i}" for i in range(30)]

    window_30min = [0] * 30
    total_requests = 0
    errors = 0
    durations = []

    try:
        for offset, key in enumerate(keys_to_fetch):
            raw_data = await redis_manager.client.lrange(key, 0, 999)
            minute_count = 0
            for item_str in raw_data:
                try:
                    item = json.loads(item_str)
                    total_requests += 1
                    minute_count += 1
                    if item.get("status", 200) >= 400 or item.get("error"):
                        errors += 1
                    durations.append(item.get("duration", 0.0))
                except json.JSONDecodeError:
                    continue
            window_30min[29 - offset] = minute_count

        error_rate = (errors / total_requests) * 100 if total_requests > 0 else 0.0

        p95_latency = 0.0
        if durations:
            durations.sort()
            p95_idx = int(len(durations) * 0.95)
            p95_latency = durations[p95_idx] * 1000  # convert to ms

        # requests in the most recent minute → current rps (approx)
        current_rps = round(window_30min[-1] / 60.0, 2) if window_30min[-1] else 0.0

        return {
            "current_rps": current_rps,
            "window_30min": window_30min,
            "distribution": {},
            "error_rate_percent": round(error_rate, 2),
            "p95_latency_ms": round(p95_latency, 2),
        }
    except Exception as e:
        logger.warning(f"traffic/live degraded (redis unavailable): {e}")
        return _empty()
