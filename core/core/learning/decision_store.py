"""Decision store — record / verify / supersede / query agent decisions (#4052).

বাংলা: Roadmap v2 §3.2-র recorder+verifier+query API — এক মডিউলে (P2: কোনো
অযৌক্তিক ফাইল-বিভাজন নয়)। Storage = `models.decision_metadata.DecisionMetadata`
টেবিল (backend-native SQLAlchemy; issue-র Prisma উল্লেখের deviation PR-তে
ঘোষিত)।

U4 (Existing Work First): নতুন learning system তৈরি হয়নি —
  * পার্সিস্টেন্স: বিদ্যমান models/Base + database/session ব্যবহার করে;
  * scripts/agents/ecosystem_learning.py (agent-run JSONL traces) আলাদা
    granularity-তে অক্ষত — দুটো একই বাস্তবতার ভিন্ন স্তর, duplicate নয়
    (trace = এক run-এর সারসংক্ষেপ; decision = এক নাম-স্তরের সিদ্ধান্ত সহ
    verification/supersession)।

Privacy: evidence/policy_context কখনো raw prompt/response ধারণ করবে না —
caller-দায়িত্ব + store-লেভেল hard-trim (JSON size cap)।
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from core.logging_config import logger
from database.session import get_db_session_context
from models.decision_metadata import DECISION_OUTCOMES, DECISION_STATUSES, DecisionMetadata

# বাংলা: JSON কলামের নিরাপদ সাইজ সীমা (512MB free-tier বান্ধব; বিশাল
# evidence dump আটকায়)।
_MAX_EVIDENCE_ITEMS = 32
_MAX_POLICY_KEYS = 32
_MAX_STR = 2000

__all__ = [
    "record_decision",
    "update_verification",
    "supersede_decision",
    "query_decisions",
    "get_decision",
]


def _trim_json_list(items: list[Any] | None) -> list[Any]:
    if not items:
        return []
    return [str(i)[:_MAX_STR] for i in list(items)[:_MAX_EVIDENCE_ITEMS]]


def _trim_json_obj(obj: dict[str, Any] | None) -> dict[str, Any] | None:
    if not obj:
        return None
    return {str(k)[:120]: str(v)[:_MAX_STR] for k, v in list(obj.items())[:_MAX_POLICY_KEYS]}


async def record_decision(
    *,
    agent_type: str,
    task_type: str,
    decision: str,
    why: str,
    evidence: list[str] | None = None,
    confidence: float | None = None,
    outcome: str = "pending",
    reusability: str = "medium",
    expiry: datetime | None = None,
    policy_context: dict[str, Any] | None = None,
    tenant_id: str | None = None,
    supersedes: str | None = None,
) -> dict[str, Any]:
    """একটি সিদ্ধান্ত রেকর্ড করে (13-field metadata schema, acceptance #1/#2/#4)।

    বাংলা: fail-honest — agent_type/task_type/decision/why ছাড়া সিদ্ধান্ত
    রেকর্ড হবে না (ValueError); outcome অজানা মানে 'pending'।
    """
    if not agent_type or not task_type or not decision or not why:
        raise ValueError(
            "record_decision requires agent_type, task_type, decision and why (fail-honest)"
        )
    if outcome not in DECISION_OUTCOMES:
        outcome = "pending"
    if supersedes:
        # acceptance #5: নতুন সিদ্ধান্ত তৈরির সাথে সাথেই পুরোনোটা deprecated হয়।
        await _mark_deprecated(supersedes)

    row = DecisionMetadata(
        agent_type=str(agent_type)[:50],
        task_type=str(task_type)[:50],
        decision=str(decision)[:255],
        why=str(why)[:_MAX_STR],
        evidence=_trim_json_list(evidence),
        confidence=None if confidence is None else max(0.0, min(1.0, float(confidence))),
        outcome=outcome,
        reusability=reusability if reusability in ("low", "medium", "high") else "medium",
        expiry=expiry,
        policy_context=_trim_json_obj(policy_context),
        tenant_id=tenant_id,
        supersedes=supersedes,
        status="active",
    )

    async with get_db_session_context() as session:
        session.add(row)
        await session.commit()
        await session.refresh(row)
        result = row.to_dict()

    logger.info(
        "[decision_store] recorded "
        f"id={result['id']} agent={result['agent_type']} task={result['task_type']} "
        f"outcome={result['outcome']} supersedes={result['supersedes']}"
    )
    return result


async def update_verification(decision_id: str, verification: str) -> dict[str, Any] | None:
    """Task শেষে `verification` পূরণ করে (acceptance #3 — CI/test/regression ফল)।

    বাংলা: verification হলো learning-এর মূল চাবিকাঠি — সিদ্ধান্ত নেওয়ার পরে
    প্রমাণ। অজানা id-তে None রিটার্ন (চুপচাপ ভুয়া success নয় — U2)।
    """
    if not decision_id or not verification:
        return None
    async with get_db_session_context() as session:
        row = (
            await session.execute(
                select(DecisionMetadata).where(DecisionMetadata.id == decision_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        row.verification = str(verification)[:_MAX_STR]
        row.updated_at = datetime.now(UTC)
        await session.commit()
        return row.to_dict()


async def supersede_decision(
    new_decision: dict[str, Any], old_decision_id: str
) -> dict[str, Any] | None:
    """প্রোভেন্যান্স চেইন: নতুন সিদ্ধান্ত পুরোনোর রেফারেন্স রাখে (acceptance #5)।

    বাংলা: old decision DELETED হয় না — শুধু `status='deprecated'`। আগে থেকে
    রেকর্ড করা new_decision dict-এ supersedes ফিল্ড সেট করে দেয় এই ফাংশন।
    """
    if not old_decision_id:
        return None
    async with get_db_session_context() as session:
        old = (
            await session.execute(
                select(DecisionMetadata).where(DecisionMetadata.id == old_decision_id)
            )
        ).scalar_one_or_none()
        if old is None:
            return None  # fail-honest: অজানা old id-তে chain বানানো হবে না
        old.status = "deprecated"
        old.updated_at = datetime.now(UTC)
        await session.commit()

    new_decision = dict(new_decision)
    new_decision["supersedes"] = old_decision_id
    return await record_decision(**new_decision)


async def _mark_deprecated(old_id: str) -> bool:
    async with get_db_session_context() as session:
        result = await session.execute(
            update(DecisionMetadata)
            .where(DecisionMetadata.id == old_id, DecisionMetadata.status == "active")
            .values(status="deprecated", updated_at=datetime.now(UTC))
        )
        await session.commit()
        return bool(result.rowcount)


async def query_decisions(
    *,
    agent_type: str | None = None,
    task_type: str | None = None,
    outcome: str | None = None,
    since: datetime | None = None,
    status: str = "active",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """ফিল্টার-সহ query (acceptance #6 — admin API-র ভিত্তি)।

    বাংলা: status default 'active' — deprecated সিদ্ধান্ত provenance চেইনে
    দেখা যায় কিন্তু ডিফল্ট তালিকায় আসে না; status=None দিলে সব।
    """
    if status is not None and status not in DECISION_STATUSES:
        raise ValueError(f"status must be one of {DECISION_STATUSES} or None")
    limit = max(1, min(int(limit), 500))

    stmt = select(DecisionMetadata).order_by(DecisionMetadata.created_at.desc()).limit(limit)
    if agent_type:
        stmt = stmt.where(DecisionMetadata.agent_type == agent_type)
    if task_type:
        stmt = stmt.where(DecisionMetadata.task_type == task_type)
    if outcome:
        stmt = stmt.where(DecisionMetadata.outcome == outcome)
    if since:
        stmt = stmt.where(DecisionMetadata.created_at >= since)
    if status is not None:
        stmt = stmt.where(DecisionMetadata.status == status)

    async with get_db_session_context() as session:
        rows = (await session.execute(stmt)).scalars().all()
        return [r.to_dict() for r in rows]


async def get_decision(decision_id: str) -> dict[str, Any] | None:
    """এক সিদ্ধান্ত id ধরে (provenance chain walk-এর জন্য)।"""
    if not decision_id:
        return None
    async with get_db_session_context() as session:
        row = (
            await session.execute(
                select(DecisionMetadata).where(DecisionMetadata.id == decision_id)
            )
        ).scalar_one_or_none()
        return row.to_dict() if row else None
