"""Admin HITL queue — Firestore-backed pending approvals (M17 P-A/P-C).

বাংলা (route-ownership): এই রুট `hitl_admin` মাউন্ট-অগ্রাধিকারে
`/api/v1/hitl/{pending,approve,reject}`-এর মালিক — ফ্রন্টএন্ড ApprovalQueue
এই চুক্তিতেই খাওয়া (data/hooks.ts)। executor-যুক্ত pending-task পৃষ্ঠ
(`approval_manager`) আলাদা স্টোরে থাকে; ৭→১ স্টোর-একত্রীকরণ M17 P-D-তে।

M17 P-C সৎ-সেমান্টিকস ফিক্স: আগে `get_tenant_db`-এর TenantAwareFirestore
পাঠানো হতো, কিন্তু HITLEngine-এর স্টোর-চুক্তি হলো কাঁচা ক্লায়েন্ট
(`.client`) — ফলে প্রতিটি অপারেশন নীরবে ব্যর্থ/খালি [] ফেরত দিত (fake-empty
কিউ)। এখন গ্লোবাল firestore ক্লায়েন্ট সরাসরি সমাধান করা হয়; সমাধান
না হলে লাউড 503 — নীরব খালি-কিউ ভান নেই।
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from api.dependencies import get_current_admin
from services.hitl.dispatch import ApprovalDispatchError
from services.hitl.engine import (
    ApprovalExpiredError,
    ApprovalNotAuthorizedError,
    HITLEngine,
    HITLStateError,
)
from services.hitl.resume_token import (
    ResumeTokenAlreadyUsedError,
    ResumeTokenError,
    ResumeTokenExpiredError,
    consume_resume_token,
)

router = APIRouter()


class RejectionRequest(BaseModel):
    reason: str


def _decision_error_response(exc: Exception) -> HTTPException:
    """#481 deterministic error mapping (mirrors approval_manager conventions).

    403 unauthorized actor/tenant · 404 unknown record · 409 already decided
    (duplicate/replay/CAS race) · 410 expired · 400 fail-closed dispatch ·
    500 execution failure after the approval committed (loud, never faked).
    """
    if isinstance(exc, ApprovalExpiredError):
        return HTTPException(status_code=status.HTTP_410_GONE, detail=str(exc))
    if isinstance(exc, ApprovalNotAuthorizedError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ApprovalDispatchError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(exc, HITLStateError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, ValueError):
        if "not found" in str(exc):
            return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
        # post-approval executor failure (validation etc.) — loud 500
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Approval decision recorded; execution failed",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Approval decision recorded; execution failed",
    )


def _actor_id(current_admin: dict) -> str:
    """Approver identity from the verified token (never the request body) (#481)."""
    return str(
        current_admin.get("user_id")
        or current_admin.get("sub")
        or current_admin.get("email")
        or "admin"
    )


def _hitl_engine() -> HITLEngine:
    """Resolve the global Firestore client and build a contract-valid HITLEngine.

    বাংলা: admin approvals টেন্যান্ট-স্কোপড নয় (গ্লোবাল কিউ) — তাই
    TenantAwareFirestore নয়, কাঁচা ক্লায়েন্টের shim। ক্লায়েন্ট অনুপস্থিতে
    fail-closed 503 (কোনো অবস্থায় নীরব [] নয়)।
    """

    class _ClientShim:
        # HITLEngine-এর স্টোর-চুক্তি: `.client` + `.collection()`।
        def __init__(self, client):
            self.client = client

        def collection(self, name: str):
            return self.client.collection(name)

    try:
        from services.storage.gcp_firestore import get_firestore_client

        client = get_firestore_client()
    except Exception as e:  # বাংলা: সমাধান-ব্যর্থতা লাউড — নীরব [] নয়
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"HITL store unavailable: {type(e).__name__}",
        ) from e
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="HITL store unavailable (Firestore client not configured).",
        )
    return HITLEngine(db=_ClientShim(client))


@router.get("/pending", dependencies=[Depends(get_current_admin)])
async def get_pending_approvals():
    """
    Get all pending actions requiring human approval.
    """
    engine = _hitl_engine()
    return engine.get_pending_approvals()


@router.post("/approve/{record_id}", dependencies=[Depends(get_current_admin)])
async def approve_pending_action(
    record_id: str,
    current_admin: dict = Depends(get_current_admin),
):
    """
    Approve a pending action and dispatch its executor (#481 contract).

    Errors: 403 unauthorized · 404 unknown record · 409 already decided ·
    410 expired · 400 unknown target · 500 execution failure.
    """
    engine = _hitl_engine()
    try:
        record = engine.approve(
            admin_user_id=_actor_id(current_admin),
            record_id=record_id,
            tenant_id=current_admin.get("tenant_id"),
        )

        return {"status": "success", "message": f"Record {record_id} approved.", "record": record}
    except Exception as e:
        raise _decision_error_response(e) from e


@router.post("/reject/{record_id}", dependencies=[Depends(get_current_admin)])
async def reject_pending_action(
    record_id: str,
    payload: RejectionRequest,
    current_admin: dict = Depends(get_current_admin),
):
    """
    Reject a pending action (#481 contract; same error mapping as approve).
    """
    engine = _hitl_engine()
    try:
        record = engine.reject(
            admin_user_id=_actor_id(current_admin),
            record_id=record_id,
            reason=payload.reason,
            tenant_id=current_admin.get("tenant_id"),
        )
        return {"status": "success", "message": f"Record {record_id} rejected.", "record": record}
    except Exception as e:
        raise _decision_error_response(e) from e


class ResumeDecisionRequest(BaseModel):
    decision: str  # "approve" | "reject"
    reason: str = ""


@router.get("/resume/{record_id}")
async def resume_decision_via_token(
    record_id: str,
    token: str = Query(min_length=8),
    decision: str = Query(default="approve", pattern="^(approve|reject)$"),
    reason: str = Query(default=""),
):
    """M17 P-A "one-bridge-many-doors" (issue #1278): approve/reject WITHOUT a
    dashboard session — the one-time resume token IS the credential.

    Any channel (Telegram/email/mobile browser) opens this URL; the engine's
    existing CAS + dispatch contract does the rest. Errors: 403 forged/
    unknown token · 404 unknown record · 409 replay/already-decided ·
    410 expired token · 400 unknown target · 500 execution failure.
    """
    engine = _hitl_engine()
    try:
        actor_id = consume_resume_token(engine, record_id, token)
    except ResumeTokenAlreadyUsedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    except ResumeTokenExpiredError as e:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail=str(e)) from e
    except ResumeTokenError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise _decision_error_response(e) from e

    if not actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Token has no bound actor."
        )

    try:
        if decision == "approve":
            record = engine.approve(admin_user_id=actor_id, record_id=record_id)
            return {"status": "success", "decision": "approve", "record": record}
        record = engine.reject(admin_user_id=actor_id, record_id=record_id, reason=reason)
        return {"status": "success", "decision": "reject", "record": record}
    except Exception as e:
        raise _decision_error_response(e) from e
