"""Feature-flag endpoints
(GET/POST /admin-api/feature-flags, PUT /admin-api/feature-flags/{flag_id}).

Issue #1818 bug-3 fix: these endpoints used to serve a hardcoded in-process
list of fake flags (``new_chat_ui`` / ``rag_v2`` / ``dark_mode``) whose names
no runtime code path ever read, and whose mutations died with the process.
They are now backed by the REAL Supabase ``feature_flags`` table (bootstrapped
in database/supabase_client.py) and expose the SAME canonical ``feature_name``
keys the runtime checker (core/feature_flags.py) reads — so an admin toggle
survives restart and actually affects runtime gating (the write path also
resets the runtime flag cache).
"""

from fastapi import HTTPException

from api.routes.admin_dashboard import router
from core.feature_flags import RUNTIME_FLAG_NAMES, feature_flags
from core.logging_config import logger
from core.utils.time_utils import utc_now


def _require_db():
    """Resolve the Supabase wrapper — honest 503 when unavailable.

    The old fake endpoints always returned 200 with fabricated data; this
    surface must never lie about persistence capability.
    """
    from database.supabase_client import db

    if not db:
        raise HTTPException(
            status_code=503,
            detail=(
                "Supabase client unavailable — feature flags cannot be read or "
                "persisted (env tier keeps runtime gating working; admin "
                "management requires the DB)."
            ),
        )
    return db


def _row_to_flag(row: dict) -> dict:
    return {
        "id": str(row.get("id")),
        "name": row.get("feature_name"),
        "description": row.get("description") or "",
        "enabled": bool(row.get("enabled", False)),
        "rollout": row.get("rollout_percentage", 100),
        "environment": "production",
        "source": "db",
    }


@router.get("/feature-flags")
def get_feature_flags():
    """List flags from the real table.

    Canonical runtime flag names that have no DB row yet are surfaced as
    disabled defaults (``source: 'default'``) so the admin UI always shows
    the full toggle set the runtime actually reads.
    """
    db = _require_db()
    try:
        res = db.client.table("feature_flags").select("*").execute()
    except Exception as exc:
        logger.warning(f"[feature-flags] table read failed: {exc}")
        raise HTTPException(
            status_code=503, detail=f"feature_flags table unreachable: {exc}"
        ) from exc
    rows = {r.get("feature_name"): r for r in (res.data or [])}
    flags: list[dict] = []
    for name in sorted(set(rows) | set(RUNTIME_FLAG_NAMES)):
        row = rows.get(name)
        if row:
            flags.append(_row_to_flag(row))
        else:
            flags.append(
                {
                    "id": None,
                    "name": name,
                    "description": "Runtime premium flag (no DB row yet — toggle to persist)",
                    "enabled": False,
                    "rollout": 0,
                    "environment": "production",
                    "source": "default",
                }
            )
    return {"flags": flags}


# CI FIX: frontend hooks.ts calls POST /admin-api/feature-flags to create
# new flags. POST is an idempotent upsert matched by feature_name.
@router.post("/feature-flags")
def create_feature_flag(payload: dict):
    """Create or update a flag row (upsert on feature_name) — persisted."""
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Flag 'name' is required")
    db = _require_db()
    row = {
        "feature_name": name,
        "enabled": bool(payload.get("enabled", False)),
        "rollout_percentage": int(payload.get("rollout", 100)),
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    if payload.get("allowed_users") is not None:
        row["allowed_users"] = list(payload["allowed_users"])
    try:
        db.client.table("feature_flags").upsert(row, on_conflict="feature_name").execute()
    except Exception as exc:
        logger.warning(f"[feature-flags] upsert failed for '{name}': {exc}")
        raise HTTPException(status_code=503, detail=f"feature_flags upsert failed: {exc}") from exc
    # Runtime reads through the (cached) checker — drop the cache so the
    # admin toggle takes effect on the next request without a restart.
    feature_flags.reset_cache()
    return {
        "status": "success",
        "flag": {
            "name": name,
            "enabled": row["enabled"],
            "rollout": row["rollout_percentage"],
        },
    }


@router.put("/feature-flags/{flag_id}")
def update_feature_flag(flag_id: str, payload: dict):
    """Update an existing flag row by numeric id — persisted."""
    updates: dict = {}
    if "enabled" in payload:
        updates["enabled"] = bool(payload["enabled"])
    if "rollout" in payload:
        updates["rollout_percentage"] = int(payload["rollout"])
    if "allowed_users" in payload:
        updates["allowed_users"] = list(payload["allowed_users"] or [])
    if not updates:
        raise HTTPException(status_code=422, detail="No updatable fields provided")
    updates["updated_at"] = utc_now()

    db = _require_db()
    try:
        res = db.client.table("feature_flags").update(updates).eq("id", int(flag_id)).execute()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="flag_id must be numeric") from exc
    except Exception as exc:
        logger.warning(f"[feature-flags] update failed for id={flag_id}: {exc}")
        raise HTTPException(status_code=503, detail=f"feature_flags update failed: {exc}") from exc
    if not res.data:
        raise HTTPException(status_code=404, detail="Flag not found")
    feature_flags.reset_cache()
    return {"status": "success", "flag": _row_to_flag(res.data[0])}
