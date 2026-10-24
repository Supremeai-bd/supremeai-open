"""Fail-fast DB schema gate (issue #478).

বাংলা: প্রোডাকশনে স্কিমা-ড্রিফট নীরবে চলতে দেবে না — রেডিনেস প্রোব স্কিমা
অবস্থা রিপোর্ট করবে এবং প্রোডাকশনে প্রয়োজনীয় টেবিল মিসিং হলে 503 দেবে।
Read path is REST-only (PostgREST), so no extra driver deps and **no
credentials ever appear in results or logs**.

English: read-only required-table probe used by the readiness probe
(``/api/v1/health/ready``). Pure read; never raises; result cached briefly
so frequent probe polling doesn't hammer PostgREST. When the REST endpoint
can't be resolved the gate reports ``checked=False`` (honest "unknown" —
never fabricated success).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

# Required tables per issue #478 evidence (docs/audits/MANUAL_STEPS.md 7.9):
# these are written at boot / runtime by persistence + memory subsystems.
# NOTE: the canonical checkpoint table is `task_checkpoints` (verified live
# against production 2026-09-19; a literal `checkpoints` table does not exist
# — the schema contract also names `task_checkpoints`).
REQUIRED_TABLES: tuple[str, ...] = (
    "automation_executions",
    "ai_memory",
    "task_checkpoints",
)

_CACHE_TTL_SECONDS = 60.0
_cache: dict[str, Any] = {"checked_at": 0.0, "status": None}


def _rest_base_and_key() -> tuple[str, str] | None:
    """Resolve the PostgREST base URL + service key via the settings SSoT.

    বাংলা: configuration scanner-এর নিয়ম মেনে সরাসরি os.getenv() নয় —
    settings.supabase_url / settings.supabase_service_key (Single Source
    of Truth) ব্যবহার করা হয়েছে। শুধু পড়া হয়, লেখা হয় না।
    """
    try:
        from core.config import settings

        base = (getattr(settings, "supabase_url", "") or "").rstrip("/")
        key = getattr(settings, "supabase_service_key", "") or getattr(settings, "supabase_key", "")
    except Exception:  # noqa: BLE001 — very-early-boot safety; settings is heavy
        return None
    if not base or not key:
        return None
    return base, key


def _probe_table(base: str, key: str, table: str) -> str:
    """Return 'present' | 'missing' | 'unknown' for one table (HEAD-like read)."""
    import urllib.error
    import urllib.request

    url = f"{base}/rest/v1/{table}?select=*&limit=1"
    req = urllib.request.Request(
        url, headers={"apikey": key, "Authorization": f"Bearer {key}"}, method="GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return "present" if resp.status == 200 else "unknown"
    except urllib.error.HTTPError as exc:
        # PostgREST: missing table/relation surfaces as 404 (PGRST205/42P01 in body)
        if exc.code == 404:
            return "missing"
        return "unknown"
    except Exception:  # noqa: BLE001 — network hiccup → unknown, never crash
        return "unknown"


def check_schema_status(force: bool = False) -> dict[str, Any]:
    """Probe required tables via REST. Never raises; never logs credentials."""
    now = time.monotonic()
    if (
        not force
        and _cache["status"] is not None
        and (now - _cache["checked_at"]) < _CACHE_TTL_SECONDS
    ):
        return dict(_cache["status"])

    resolved = _rest_base_and_key()
    if resolved is None:
        status: dict[str, Any] = {
            "checked": False,
            "reason": "no REST endpoint resolvable (SUPABASE_URL / service key unset)",
            "missing": [],
            "present": [],
        }
        _cache["checked_at"] = now
        _cache["status"] = status
        return dict(status)

    base, key = resolved
    present: list[str] = []
    missing: list[str] = []
    unknown: list[str] = []
    for table in REQUIRED_TABLES:
        state = _probe_table(base, key, table)
        if state == "present":
            present.append(table)
        elif state == "missing":
            missing.append(table)
        else:
            unknown.append(table)

    status = {
        "checked": True,
        "missing": missing,
        "present": present,
        "unknown": unknown,
        "checked_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "error": None,
    }
    _cache["checked_at"] = now
    _cache["status"] = status
    return dict(status)


def production_schema_incompatible() -> str | None:
    """Return a fail-closed reason string when production schema is broken.

    বাংলা: প্রোডাকশনে টেবিল মিসিং = রেডিনেস 503-এর কারণ; None মানে সব ঠিক
    বা যাচাই অসম্ভব (unknown ≠ ব্যর্থ — মিথ্যা সবুজ নিষিদ্ধ, কিন্তু মিথ্যা লালও নয়)।
    """
    status = check_schema_status()
    if not status.get("checked"):
        return None
    return (
        None
        if not status.get("missing")
        else ("missing required table(s): " + ", ".join(status["missing"]))
    )
