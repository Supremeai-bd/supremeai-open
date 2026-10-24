"""Approval executors — M17 P-B "নির্বাহক-জন্ম" (dispatch-table).

বাংলা (M17 P-B): আজ ``HITLEngine.approve()`` কেবল status-flip করে —
অনুমোদিত কাজ **কখনো execute হয় না** (frontend যে `/api/v1/hitl/approve`
পৃষ্ঠে approve করে, সেই Firestore স্টোরের রেকর্ড "approved" হয়ে জমে থাকে;
executor-সহ pending-task পৃষ্ঠ (`approval_manager`) রুট-shadow-এর পিছনে
থেকে যায় এবং তার স্টোরে শূন্য producer)। এই মডিউল approve-পরবর্তী
কার্যকরী-অর্ধ নিয়ে আসে: **data-file dispatch-table** — target_resource →
executor; অজানা target হলে fail-closed loud (নীরব no-op নিষিদ্ধ)।

প্যাটার্ন-পুনঃব্যবহার (Constitution #3): skill executor-টি `approval_manager`
রুটের প্রমাণিত SKILL_GENERATION ব্লকের সেমান্টিক যমজ — AICodeValidator
validate_before_use + realpath path-traversal guard + bounded skills-dir
write। দুই পৃষ্ঠ একই নিরাপত্তা-চুক্তিতে চলে; ৭→১ স্টোর-একত্রীকরণ M17 P-D।
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from core.code_validator import AICodeValidator
from core.logging_config import logger

# Executor চুক্তি: payload → execution-result dict। যেকোনো ব্যর্থতা
# exception দিয়ে loud — কখনো {"status": "failed"} ফেরত দিয়ে ভান নয়।
ApprovalExecutor = Callable[[dict[str, Any]], dict[str, Any]]


class ApprovalDispatchError(RuntimeError):
    """অজানা/অনুপস্থিত executor-এ fail-closed সংকেত (M17 P-B)।"""


def _skills_dir() -> str:
    """Canonical skills directory (backend/skills) — approval_manager-অনুরূপ।"""
    backend_dir = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    return os.path.join(backend_dir, "skills")


def _extract_skill_payload(payload: dict[str, Any]) -> tuple[str, str]:
    """payload থেকে (skill_name, code) বের করা — দুই স্টোরের key-চুক্তি একসাথে।

    বাংলা: HITLEngine producer (auto_skill_creator) ``code`` লেখে;
    pending-task পৃষ্ঠ ``generated_code`` — দুটোই গ্রহণযোগ্য, অনুপস্থিতে
    loud ValueError (নীরব খালি-লেখা নিষিদ্ধ)।
    """
    skill_name = payload.get("skill_name")
    code = payload.get("code", payload.get("generated_code"))
    if not skill_name or not code:
        raise ValueError(
            "approved payload missing skill_name or code — refusing silent no-op (M17 P-B)"
        )
    if not str(skill_name).replace("_", "").replace("-", "").isalnum():
        raise ValueError(f"Invalid skill name format: {skill_name!r}")
    return str(skill_name), str(code)


def execute_approved_skill(payload: dict[str, Any]) -> dict[str, Any]:
    """``skills/{name}`` অনুমোদনের executor — validate → guard → write।

    বাংলা: approval_manager-এর SKILL_GENERATION ব্লকের সেমান্টিক যমজ।
    AICodeValidator ব্যর্থ বা path-traversal ধরা পড়লে loud exception —
    ফাইল কখনো আংশিক/নীরবভাবে লেখা হয় না।
    """
    skill_name, code = _extract_skill_payload(payload)

    validation = AICodeValidator().validate_before_use(code)
    if not validation.get("can_use", False):
        raise ValueError(f"Code validation failed: {validation.get('checks', {})}")

    skills_dir = _skills_dir()
    os.makedirs(skills_dir, exist_ok=True)
    path = os.path.join(skills_dir, f"{skill_name}.py")
    real_path = os.path.realpath(path)
    if not real_path.startswith(os.path.realpath(skills_dir)):
        raise PermissionError("Path traversal attempt blocked (M17 P-B executor)")

    with open(path, "w", encoding="utf-8") as f:
        f.write(code)
    logger.info(f"✅ [M17 P-B] Approved skill '{skill_name}' deployed to {path}")
    return {"status": "executed", "target": f"skills/{skill_name}", "path": path}


# ── data-file dispatch-table: prefix → executor ─────────────────────
# নতুন producer যোগ করতে এখানে এন্ট্রি + নিজস্ব executor — নীরব
# no-op-এর রাস্তা নেই (অজানা target = fail-closed loud)।
APPROVAL_EXECUTORS: dict[str, ApprovalExecutor] = {
    "skills/": execute_approved_skill,
}


def resolve_executor(target_resource: str) -> tuple[str, ApprovalExecutor]:
    """target_resource-এর executor resolve — অজানা হলে fail-closed loud।

    বাংলা: longest-prefix ম্যাচ; মিল না পেলে ApprovalDispatchError —
    approve() স্টোরে status-flip-এর **আগেই** ব্যর্থ হয়, ফলে "approved
    কিন্তু কিছুই হয়নি" ফাঁদ কাঠামোগতভাবে অসম্ভব।
    """
    if target_resource:
        for prefix, executor in APPROVAL_EXECUTORS.items():
            if target_resource.startswith(prefix):
                return prefix, executor
    raise ApprovalDispatchError(
        f"No approval executor registered for target_resource={target_resource!r} "
        "(fail-closed, M17 P-B) — register it in APPROVAL_EXECUTORS or the "
        "producer must not suspend without an executor."
    )


def execute_approved(target_resource: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve + execute — engine.approve()-র একক প্রবেশদ্বার।"""
    prefix, executor = resolve_executor(target_resource)
    logger.info(
        f"[M17 P-B] Dispatching approved action target={target_resource!r} via '{prefix}' executor"
    )
    return executor(payload or {})
