"""God-mode deployment gate override endpoint (POST /admin-api/gate/override)."""

import contextlib

from fastapi import HTTPException

from api.routes.admin_dashboard import router
from api.routes.admin_dashboard._models import GateOverridePayload
from core.config import settings
from core.logging_config import logger
from core.utils.time_utils import utc_now

with contextlib.suppress(ImportError):
    from google.cloud import firestore


@router.post("/gate/override")
async def execute_manual_gate_override(payload: GateOverridePayload):
    """
    God-Mode Admin Override Gateway.
    Manually bypasses or forces the autonomous deployment gate status.
    Directly affects CI/CD Cloud Build pipelines.
    """
    # 🛡️ ১. স্ট্রিক্ট সিকিউরিটি গেটকিপার (Master Token Cross-Matching)
    if payload.admin_secret != settings.jwt_secret:
        logger.critical(
            "🚨 [SECURITY BREACH ATTEMPT] Unauthorized attempt to access God-Mode Override Endpoint!"
        )
        raise HTTPException(
            status_code=401,
            detail="Access Denied: Invalid Administrative Secret Key Key.",
        )

    requested_status = payload.target_status.upper()
    if requested_status not in ["UNLOCKED", "LOCKED"]:
        raise HTTPException(
            status_code=400,
            detail="Malformed Request: Target status must be strictly 'UNLOCKED' or 'LOCKED'.",
        )

    try:
        # 🔗 ২. ফায়ারস্টোর গেট লিংকার অ্যাক্টিভেশন
        db = firestore.Client()
        gate_ref = db.collection("deploy_gate").document("status")

        now = utc_now()
        override_context = {
            "status": requested_status,
            "reason": f"👑 [MANUAL OVERRIDE] {payload.reason}",
            "updated_at": now,
            "override_active": True,
        }

        # ট্রানজেকশনাল রাইট ট্রিগার
        gate_ref.set(override_context)

        logger.warning(
            f"🔱 [GOD-MODE OVERRIDE] Admin has manually forced deploy_gate status to {requested_status}."
        )

        return {
            "success": True,
            "forced_status": requested_status,
            "timestamp": now.isoformat(),
            "message": f"SupremeAI 2.0 Deployment Gate has been successfully forced to {requested_status}.",
        }

    except Exception as e:
        logger.error(f"❌ Failed to commit manual gate override to Cloud Firestore: {e!s}")
        raise HTTPException(status_code=500, detail=f"Infrastructure Sync Failure: {e!s}") from e
