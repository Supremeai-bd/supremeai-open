"""Workload Admission Controller (#3156).

বাংলা: এই মডিউলটি workload amplification attack প্রতিরোধ করে —
request rate limit একা যথেষ্ট নয় কারণ একটি request ২০টি agent ×
১০টি parallel task × huge prompt-এ বিস্ফোরিত হতে পারে।

AdmissionController তিনটি dimension-এ check করে BEFORE expensive execution:
  ১. agent_count — user/tenant প্রতি সর্বোচ্চ concurrent agent
  ২. parallelism — প্রতি task-এ সর্বোচ্চ parallel sub-task
  ৩. prompt_tokens — প্রতি request-এ সর্বোচ্চ prompt size (estimated)

Verdict: ALLOW / THROTTLE (429) / REJECT (422)
Configurable via env vars (WORKLOAD_MAX_AGENTS, WORKLOAD_MAX_PARALLELISM,
WORKLOAD_MAX_PROMPT_TOKENS)।
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.monitoring.logging_config import logger


class AdmissionVerdict(StrEnum):
    ALLOW = "allow"
    THROTTLE = "throttle"
    REJECT = "reject"


@dataclass
class AdmissionRequest:
    """Workload admission request — what the caller wants to do."""

    user_id: str
    tenant_id: str | None = None
    agent_count: int = 1
    parallelism: int = 1
    prompt_text: str = ""
    retry_count: int = 0
    queue_depth: int = 0


@dataclass
class AdmissionResult:
    """Workload admission result — verdict + reason + evidence."""

    verdict: AdmissionVerdict
    reason: str
    http_status: int
    evidence: dict[str, Any] = field(default_factory=dict)


# ── Configurable limits (env-driven, zero-hardcode) ──────────────────────────


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


MAX_AGENTS_PER_USER = _env_int("WORKLOAD_MAX_AGENTS", 5)
MAX_PARALLELISM = _env_int("WORKLOAD_MAX_PARALLELISM", 10)
MAX_PROMPT_TOKENS = _env_int("WORKLOAD_MAX_PROMPT_TOKENS", 32000)
MAX_RETRIES = _env_int("WORKLOAD_MAX_RETRIES", 3)
MAX_QUEUE_DEPTH = _env_int("WORKLOAD_MAX_QUEUE_DEPTH", 50)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate — ~4 chars per token (zero-cost, no tokenizer dep)."""
    return max(1, len(text) // 4)


class WorkloadAdmissionController:
    """Admission gate for expensive AI workload (#3156).

    বাংলা: প্রতিটি expensive execution (LLM call, agent spawn, tool fan-out)
    এর আগে এই controller check করবে। verdict-ভিত্তিক response:
      ALLOW → proceed
      THROTTLE → 429 (retry later)
      REJECT → 422 (permanent — limit exceeded, don't retry)
    """

    def __init__(self):
        self._active_agents: dict[str, int] = {}  # user_id → current count
        self._last_check: float = time.time()

    def admit(self, req: AdmissionRequest) -> AdmissionResult:
        """Check workload admission for a request. Returns verdict + evidence."""
        evidence: dict[str, Any] = {
            "user_id": req.user_id,
            "tenant_id": req.tenant_id,
            "agent_count": req.agent_count,
            "parallelism": req.parallelism,
            "retry_count": req.retry_count,
            "queue_depth": req.queue_depth,
            "limits": {
                "max_agents": MAX_AGENTS_PER_USER,
                "max_parallelism": MAX_PARALLELISM,
                "max_prompt_tokens": MAX_PROMPT_TOKENS,
                "max_retries": MAX_RETRIES,
                "max_queue_depth": MAX_QUEUE_DEPTH,
            },
        }

        # 1. Agent count check
        if req.agent_count > MAX_AGENTS_PER_USER:
            reason = (
                f"agent_count={req.agent_count} exceeds max={MAX_AGENTS_PER_USER} "
                f"(user={req.user_id})"
            )
            logger.warning(f"[WorkloadAdmission] REJECT: {reason}")
            return AdmissionResult(
                verdict=AdmissionVerdict.REJECT,
                reason=reason,
                http_status=422,
                evidence=evidence,
            )

        # 2. Parallelism check
        if req.parallelism > MAX_PARALLELISM:
            reason = (
                f"parallelism={req.parallelism} exceeds max={MAX_PARALLELISM} (user={req.user_id})"
            )
            logger.warning(f"[WorkloadAdmission] REJECT: {reason}")
            return AdmissionResult(
                verdict=AdmissionVerdict.REJECT,
                reason=reason,
                http_status=422,
                evidence=evidence,
            )

        # 3. Prompt token check
        prompt_tokens = _estimate_tokens(req.prompt_text)
        evidence["prompt_tokens_estimated"] = prompt_tokens
        if prompt_tokens > MAX_PROMPT_TOKENS:
            reason = (
                f"prompt_tokens≈{prompt_tokens} exceeds max={MAX_PROMPT_TOKENS} "
                f"(user={req.user_id})"
            )
            logger.warning(f"[WorkloadAdmission] REJECT: {reason}")
            return AdmissionResult(
                verdict=AdmissionVerdict.REJECT,
                reason=reason,
                http_status=422,
                evidence=evidence,
            )

        # 4. Retry count check
        if req.retry_count > MAX_RETRIES:
            reason = (
                f"retry_count={req.retry_count} exceeds max={MAX_RETRIES} "
                f"(user={req.user_id}) — possible retry-based amplification"
            )
            logger.warning(f"[WorkloadAdmission] THROTTLE: {reason}")
            return AdmissionResult(
                verdict=AdmissionVerdict.THROTTLE,
                reason=reason,
                http_status=429,
                evidence=evidence,
            )

        # 5. Queue depth check
        if req.queue_depth > MAX_QUEUE_DEPTH:
            reason = (
                f"queue_depth={req.queue_depth} exceeds max={MAX_QUEUE_DEPTH} "
                f"(user={req.user_id}) — backpressure needed"
            )
            logger.warning(f"[WorkloadAdmission] THROTTLE: {reason}")
            return AdmissionResult(
                verdict=AdmissionVerdict.THROTTLE,
                reason=reason,
                http_status=429,
                evidence=evidence,
            )

        # All checks passed → ALLOW
        logger.debug(
            f"[WorkloadAdmission] ALLOW: user={req.user_id} agents={req.agent_count} "
            f"parallelism={req.parallelism} tokens≈{prompt_tokens}"
        )
        return AdmissionResult(
            verdict=AdmissionVerdict.ALLOW,
            reason="within all workload limits",
            http_status=200,
            evidence=evidence,
        )


# Singleton
_controller: WorkloadAdmissionController | None = None


def get_admission_controller() -> WorkloadAdmissionController:
    global _controller
    if _controller is None:
        _controller = WorkloadAdmissionController()
    return _controller


__all__ = [
    "AdmissionVerdict",
    "AdmissionRequest",
    "AdmissionResult",
    "WorkloadAdmissionController",
    "get_admission_controller",
]
