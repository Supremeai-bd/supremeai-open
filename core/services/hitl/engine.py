from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from core.logging_config import logger
from database.tenant_db import TenantAwareFirestore

from .dispatch import ApprovalDispatchError, execute_approved, resolve_executor
from .hitl_ledger import HITLAuditLedger

#: M17 P-D: HITLEngine suspension-এর canonical idempotency-key উপসর্গ।
_CANONICAL_KEY_PREFIX = "hitl:"

# ── #481 canonical approval contract (docs/security/HITL_APPROVAL_CONTRACT.md) ──
#: Statuses of a HITLEngine approval record (Firestore ``pending_approvals``).
STATUS_PENDING = "pending_approval"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_EXPIRED = "expired"

#: Default decision window (mirrors ``models.pending_tasks.DEFAULT_APPROVAL_TTL_SECONDS``
#: — one contract, both stores).
DEFAULT_APPROVAL_TTL_SECONDS = 24 * 60 * 60


class HITLStateError(ValueError):
    """A decision transition violates the approval state machine (#481).

    Subclasses ``ValueError`` so pre-contract callers/tests matching
    ``ValueError`` keep working unchanged.
    """


class ApprovalExpiredError(HITLStateError):
    """A decision was attempted after the approval TTL elapsed (#481)."""


class ApprovalNotAuthorizedError(HITLStateError):
    """The decision actor failed the authorization gate (#481)."""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _is_expired(expires_at: Any) -> bool:
    """TTL check (#481) — parse when possible, lexicographic UTC-ISO fallback.

    Records without ``expires_at`` (pre-contract rows) never expire.
    """
    if not expires_at:
        return False
    try:
        return datetime.fromisoformat(str(expires_at)) <= datetime.now(UTC)
    except ValueError:
        return str(expires_at) <= _utc_now_iso()


def _require_actor(admin_user_id: str, record_id: str) -> None:
    """Explicit authorization gate (#481 §3.1): the approver identity must be present.

    Route-level RBAC stays the primary gate; this is the engine-side backstop so
    a programmatic caller cannot decide with an anonymous actor.
    """
    if not str(admin_user_id or "").strip():
        raise ApprovalNotAuthorizedError(
            f"Approval {record_id} requires an explicit, authenticated approver identity (#481)"
        )


def _require_tenant_scope(record: dict[str, Any], tenant_id: str | None, record_id: str) -> None:
    """Tenant-scoping gate (#481 §3.5): record and caller tenants must match."""
    record_tenant = record.get("tenant_id")
    if record_tenant and tenant_id is not None and str(record_tenant) != str(tenant_id):
        raise ApprovalNotAuthorizedError(
            f"Approval {record_id} is scoped to tenant {record_tenant!r}; "
            f"caller supplied tenant {tenant_id!r} (#481 tenant scoping)"
        )


class HITLEngine:
    """
    Human-In-The-Loop Engine.
    Handles the suspension, approval, and rejection of skills/workflows that require human oversight.

    #481 canonical contract (docs/security/HITL_APPROVAL_CONTRACT.md):
    ``pending_approval → approved | rejected | expired``; terminal states absorb
    every further transition (replay-proof); approve dispatches its executor
    exactly once; records carry a 24h decision deadline and an optional tenant
    scope; every transition is stamped and ledgered (append-only hash chain).
    """

    def __init__(self, db: TenantAwareFirestore):
        # বাংলা (M17 P-C, fail-closed): আগে db-শূন্য/বিকৃত স্টোরে নীরবভাবে
        # নির্মিত হতো এবং প্রথম অপারেশনে AttributeError → নীরব []/ব্যর্থতা।
        # এখন স্টোর-চুক্তি স্পষ্ট: ব্যবহারযোগ্য `.client` ছাড়া HITLEngine গড়াই
        # নিষিদ্ধ — অনুপস্থিত স্টোর নির্মাণেই লাউড-ব্যর্থ হয়, ভান নেই।
        if db is None or getattr(db, "client", None) is None:
            raise RuntimeError(
                "HITLEngine requires a durable store exposing a usable `.client` "
                "— refusing to construct without one (fail-closed, M17 P-C)"
            )
        self.db = db
        self.collection_name = "pending_approvals"
        self.ledger = HITLAuditLedger(db=self.db)

    def suspend_for_approval(
        self,
        target_resource: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int | None = None,
        tenant_id: str | None = None,
    ) -> str:
        """
        Suspend an action for human approval.
        Returns the ID of the pending approval record.

        #481: the record carries its decision deadline (``expires_at``, default
        24h) and — when the producer knows it — the owning ``tenant_id``; both
        are enforced by :meth:`approve` / :meth:`reject`.
        """
        # Create a pending approval record
        record_id = target_resource
        now = datetime.now(UTC).isoformat()
        ttl = ttl_seconds if ttl_seconds is not None else DEFAULT_APPROVAL_TTL_SECONDS

        pending_record = {
            "id": record_id,
            "target_resource": target_resource,
            "payload": payload,
            "status": STATUS_PENDING,
            "created_at": now,
            "updated_at": now,
            "expires_at": (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat(),
            "tenant_id": tenant_id,
        }

        try:
            self.db.client.collection(self.collection_name).document(record_id).set(pending_record)
            logger.info(f"?? [HITLEngine] Suspended '{target_resource}' for human approval.")
        except Exception as e:
            logger.error(f"?[HITLEngine] Failed to suspend '{target_resource}': {e}")
            raise RuntimeError(f"Failed to suspend action for HITL: {e}")

        # M17 P-D (seven→one): canonical pending_tasks-এ write-through mirror —
        # দ্বৈত-লেখা পর্ব (Firestore = HITLEngine-authority, pending_tasks =
        # একক read-পৃষ্ঠ)। best-effort + লাউড: mirror-ব্যর্থতা suspension
        # ব্লক করে না, কিন্তু নীরবেও গিলে না।
        self._mirror_to_canonical_create(record_id, payload)

        # Log to ledger
        self.ledger.record_entry_sync(
            agent_id="system",
            action="suspend_for_approval",
            payload={"target_resource": target_resource, "record_id": record_id},
        )

        return record_id

    def get_pending_approvals(self) -> list[dict[str, Any]]:
        """
        Retrieve all pending approvals.

        বাংলা (M17 P-C): আগে স্টোর-ত্রুটিতে নীরবে [] ফেরত দিত — admin কিউ
        ফাঁকা দেখিয়ে ভান করত যে কিছুই অনুমোদনের অপেক্ষায় নেই। এখন ত্রুটি
        লাউড RuntimeError — রুট স্তরে 500 হয়ে স্পষ্ট হবে, কখনো ভান নয়।
        """
        try:
            ref = self.db.client.collection(self.collection_name)
            query = ref.where("status", "==", "pending_approval")
            docs = list(query.stream())
            records = [doc.to_dict() for doc in docs]
            # #481: expired approvals are no longer decisionable — filtered
            # read-side (same semantics as ``pending_tasks.list_pending``) so
            # the admin queue never offers a decision the contract will refuse.
            return [r for r in records if not _is_expired(r.get("expires_at"))]
        except Exception as e:
            logger.error(f"[HITLEngine] Failed to fetch pending approvals: {e}")
            raise RuntimeError(f"HITL queue is UNAVAILABLE (store read failed): {e}") from e

    def get_pending_approval(self, record_id: str) -> dict[str, Any] | None:
        """
        Retrieve a specific pending approval by ID.
        """
        try:
            doc = self.db.client.collection(self.collection_name).document(record_id).get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            logger.error(f"?[HITLEngine] Failed to fetch pending approval {record_id}: {e}")
            return None

    def approve(
        self, admin_user_id: str, record_id: str, *, tenant_id: str | None = None
    ) -> dict[str, Any]:
        """
        Approve a pending action and EXECUTE it (M17 P-B dispatch).

        #481 canonical contract (docs/security/HITL_APPROVAL_CONTRACT.md):
        ১. explicit authorization — empty actor → ``ApprovalNotAuthorizedError``;
        ২. status-flip-এর **আগেই** executor resolve — অজানা target হলে
           loud fail-closed, রেকর্ড pending-ই থাকে ("approved অথচ
           কিছুই হয়নি" ফাঁদ অসম্ভব);
        ৩. guarded terminal transition (state/expiry/tenant) — CAS via a store
           transaction when available, so two concurrent approves cannot both
           dispatch: the loser raises ``HITLStateError`` and never executes;
        ৪. duplicate/replayed approve → ``HITLStateError``, NO re-execution;
           TTL elapsed → record flips to ``expired`` + ``ApprovalExpiredError``;
        ৫. রানটাইম-ব্যর্থতা হলে execution_error রেকর্ডে + ledger
           'approval_execution_failed' + loud re-raise (নীরব ভান নেই)।
        """
        doc_ref = self.db.client.collection(self.collection_name).document(record_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise ValueError(f"Pending approval record {record_id} not found.")

        record = doc.to_dict()

        target = record.get("target_resource") or ""
        try:
            resolve_executor(target)
        except ApprovalDispatchError as exc:
            logger.error(f"[M17 P-B] approve({record_id}) fail-closed: {exc} — রেকর্ড pending-ই থাকল")
            raise

        self._transition_to_terminal(
            doc_ref,
            record,
            record_id,
            admin_user_id,
            tenant_id,
            target_status=STATUS_APPROVED,
            extra_fields={"approved_by": admin_user_id},
            ledger_action="skill_approved",
            ledger_payload={
                "target_resource": record.get("target_resource"),
                "record_id": record_id,
            },
        )

        logger.info(f"[HITLEngine] Admin {admin_user_id} approved '{record_id}'.")

        # ── M17 P-B: approve-পরবর্তী কার্যকরী-অর্ধ (dispatch executor) ──
        try:
            result = execute_approved(target, record.get("payload") or {})
        except Exception as exc:
            exec_failed_at = datetime.now(UTC).isoformat()
            doc_ref.update(
                {
                    "execution_status": "failed",
                    "execution_error": str(exc),
                    "executed_at": exec_failed_at,
                }
            )
            self.ledger.record_entry_sync(
                agent_id=admin_user_id,
                action="approval_execution_failed",
                payload={
                    "target_resource": record.get("target_resource"),
                    "record_id": record_id,
                    "error": str(exc),
                },
            )
            logger.error(
                f"[M17 P-B] Approved record '{record_id}' FAILED to execute — "
                f"target={target!r}: {exc} (loud, execution_status=failed)"
            )
            raise

        doc_ref.update(
            {
                "execution_status": "executed",
                "execution_result": result,
                "executed_at": datetime.now(UTC).isoformat(),
            }
        )
        self.ledger.record_entry_sync(
            agent_id=admin_user_id,
            action="approval_executed",
            payload={
                "target_resource": record.get("target_resource"),
                "record_id": record_id,
                "result": result,
            },
        )
        record["execution_status"] = "executed"
        record["execution_result"] = result
        return record

    def reject(
        self, admin_user_id: str, record_id: str, reason: str = "", *, tenant_id: str | None = None
    ) -> dict[str, Any]:
        """
        Reject a pending action.

        #481: same authorization/expiry/tenant/state gates as :meth:`approve`
        (without the dispatch half) — a terminal or expired record can no
        longer be rejected either.
        """
        doc_ref = self.db.client.collection(self.collection_name).document(record_id)
        doc = doc_ref.get()

        if not doc.exists:
            raise ValueError(f"Pending approval record {record_id} not found.")

        record = doc.to_dict()

        self._transition_to_terminal(
            doc_ref,
            record,
            record_id,
            admin_user_id,
            tenant_id,
            target_status=STATUS_REJECTED,
            extra_fields={"rejected_by": admin_user_id, "rejection_reason": reason},
            ledger_action="skill_rejected",
            ledger_payload={
                "target_resource": record.get("target_resource"),
                "record_id": record_id,
                "reason": reason,
            },
            reason=reason,
        )

        logger.warning(
            f"[HITLEngine] Admin {admin_user_id} rejected '{record_id}'. Reason: {reason}"
        )
        return record

    # ── #481: guarded terminal transition ─────────────────────────────────

    def _assert_decisionable(
        self, record: dict[str, Any], record_id: str, admin_user_id: str, tenant_id: str | None
    ) -> None:
        """Raise unless the record may still transition (#481 §2.1).

        Order matters: explicit actor → pending state → tenant scope → expiry.
        """
        _require_actor(admin_user_id, record_id)
        if record.get("status") != STATUS_PENDING:
            raise HITLStateError(f"Record {record_id} is not in pending state.")
        _require_tenant_scope(record, tenant_id, record_id)
        if _is_expired(record.get("expires_at")):
            raise ApprovalExpiredError(
                f"Approval {record_id} expired at {record.get('expires_at')} — "
                "expired approvals can no longer be decided (#481 replay guard)"
            )

    def _transition_to_terminal(
        self,
        doc_ref: Any,
        record: dict[str, Any],
        record_id: str,
        admin_user_id: str,
        tenant_id: str | None,
        *,
        target_status: str,
        extra_fields: dict[str, Any],
        ledger_action: str,
        ledger_payload: dict[str, Any],
        reason: str | None = None,
    ) -> None:
        """Guard + commit a terminal status-flip (#481).

        Transactional (CAS) when the store exposes ``client.transaction()`` —
        the guard re-runs against the transactional snapshot, so two concurrent
        decisions cannot both flip: the loser aborts loudly and its executor
        never runs. Stores without transaction support keep the read-guarded
        flip (sequential determinism; the canonical ``pending_tasks`` store
        mirrored under ``hitl:<record_id>`` always provides true CAS).
        """
        txn_factory = getattr(self.db.client, "transaction", None)
        try:
            if callable(txn_factory):
                self._cas_transition(
                    txn_factory,
                    doc_ref,
                    record_id,
                    admin_user_id,
                    tenant_id,
                    target_status,
                    extra_fields,
                )
            else:
                self._assert_decisionable(record, record_id, admin_user_id, tenant_id)
                doc_ref.update(
                    {**extra_fields, "status": target_status, "updated_at": _utc_now_iso()}
                )
        except ApprovalExpiredError:
            # Single expiry path for BOTH store kinds: land the deterministic
            # `expired` terminal state + ledger + canonical mirror, then raise.
            self._mark_expired(doc_ref, record_id, admin_user_id, record.get("expires_at"))
            raise

        self._mirror_to_canonical_resolve(record_id, target_status, admin_user_id, reason=reason)

        # Log to ledger
        self.ledger.record_entry_sync(
            agent_id=admin_user_id,
            action=ledger_action,
            payload=ledger_payload,
        )

        # The returned snapshot must reflect the committed transition (not the
        # pre-flip read) — deterministic response contract (#481).
        record.update({**extra_fields, "status": target_status, "updated_at": _utc_now_iso()})

    def _cas_transition(
        self,
        txn_factory: Any,
        doc_ref: Any,
        record_id: str,
        admin_user_id: str,
        tenant_id: str | None,
        target_status: str,
        extra_fields: dict[str, Any],
    ) -> None:
        """Atomic CAS flip inside a store transaction (Firestore protocol) (#481).

        Raises (without committing anything) when the transactional snapshot
        fails any guard — including expiry, which the caller lands via
        :meth:`_mark_expired` on a single code path shared with non-CAS stores.
        """
        txn = txn_factory()
        snapshot = txn.get(doc_ref)
        if not snapshot.exists:
            raise ValueError(f"Pending approval record {record_id} not found.")
        live = snapshot.to_dict() or {}
        self._assert_decisionable(live, record_id, admin_user_id, tenant_id)
        txn.update(doc_ref, {**extra_fields, "status": target_status, "updated_at": _utc_now_iso()})
        try:
            txn.commit()
        except Exception as exc:
            raise HITLStateError(
                f"Approval {record_id} transition aborted — a concurrent decision won the "
                f"CAS race (#481); re-fetch the record before retrying: {exc}"
            ) from exc

    def _mark_expired(
        self, doc_ref: Any, record_id: str, admin_user_id: str, expires_at: Any
    ) -> None:
        """Land the deterministic ``expired`` terminal state (#481 §2.1).

        Queue-exiting and replay-proof: later decisions hit the terminal guard.
        """
        now = _utc_now_iso()
        actor = str(admin_user_id or "system")
        doc_ref.update(
            {"status": STATUS_EXPIRED, "expired_at": now, "expired_by": actor, "updated_at": now}
        )
        self.ledger.record_entry_sync(
            agent_id=actor,
            action="approval_expired",
            payload={"record_id": record_id, "expires_at": str(expires_at) if expires_at else None},
        )
        self._mirror_to_canonical_resolve(
            record_id, "expired", actor, reason=f"expired at {expires_at}"
        )

    # ── M17 P-D (seven→one): canonical pending_tasks write-through ─────────
    # বাংলা: সাত প্রতিযোগী স্টোর → এক ক্যানোনিকাল read-পৃষ্ঠের প্রথম সেতু।
    # দ্বৈত-লেখা পর্বে Firestore-ই HITLEngine-authority; mirror best-effort —
    # ব্যর্থতায় লাউড warning, কখনো নীরব ভান নয়।

    def _mirror_to_canonical_create(self, record_id: str, payload: dict[str, Any]) -> None:
        key = f"{_CANONICAL_KEY_PREFIX}{record_id}"
        try:
            from models.pending_tasks import TaskType, create_pending_task, get_task_by_idempotency

            existing = get_task_by_idempotency(key)
            if existing is not None:
                # বাংলা: পুনরাবৃত্তি নিরীহ — একই hitl-record-এর mirror আগেই আছে।
                logger.debug(f"[M17 P-D] canonical mirror already present for {record_id}")
                return
            create_pending_task(
                task_type=TaskType.HITL_SUSPENSION,
                payload={**(payload or {}), "hitl_record_id": record_id},
                created_by="hitl-engine",
                risk_level="high",
                idempotency_key=key,
            )
            logger.info(f"[M17 P-D] suspension '{record_id}' mirrored to canonical pending_tasks")
        except Exception as exc:
            logger.warning(
                f"[M17 P-D] canonical mirror (create) skipped for '{record_id}': {exc!r} — "
                "Firestore record remains authoritative"
            )

    def _mirror_to_canonical_resolve(
        self,
        record_id: str,
        verdict: str,
        admin_user_id: str,
        reason: str | None = None,
    ) -> None:
        key = f"{_CANONICAL_KEY_PREFIX}{record_id}"
        try:
            from models.pending_tasks import TaskStatus, get_task_by_idempotency, update_task_status

            task = get_task_by_idempotency(key)
            if task is None:
                # বাংলা: suspension-টি mirror-হারা (পুরনো রেকর্ড) — resolve করার
                # কিছু নেই; সেটি নীরব-ভান নয়, পরিচিত দ্বৈত-লেখা-পূর্ববর্তী অবস্থা।
                logger.debug(f"[M17 P-D] no canonical mirror to resolve for {record_id}")
                return
            # #481: verdict → canonical status mapping — expiry is an
            # authoritative system cancellation of the mirrored task.
            status = {
                "approved": TaskStatus.APPROVED,
                "rejected": TaskStatus.REJECTED,
                "expired": TaskStatus.CANCELLED,
            }.get(verdict)
            if status is None:
                logger.debug(f"[M17 P-D] unmapped mirror verdict {verdict!r} for {record_id}")
                return
            updated = update_task_status(
                task.task_id,
                status,
                resolved_by=admin_user_id,
                reason=reason,
            )
            if updated is None:
                logger.warning(f"[M17 P-D] canonical mirror task for '{record_id}' vanished — loud")
            else:
                logger.info(
                    f"[M17 P-D] canonical mirror for '{record_id}' → {verdict} (by {admin_user_id})"
                )
        except Exception as exc:
            # বাংলা: CAS/TTL ব্যতিক্রমসহ সব mirror-ব্যর্থতা লাউড — Firestore রেকর্ড
            # authority থাকায় নির্বাহ-পথ অপ্রভাবিত।
            logger.warning(
                f"[M17 P-D] canonical mirror (resolve) skipped for '{record_id}': {exc!r} — "
                "Firestore record remains authoritative"
            )
