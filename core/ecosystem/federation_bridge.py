"""Canonical Run adapters for browser, MCP, and remediation execution.

বাংলা: বিদ্যমান execution engines বদলানো নয়; শুধু unified observability boundary-তে
correlation তৈরি করা।
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from runs.bridges import observe_mcp_run
from runs.models import Run
from runs.service import RunService


async def observe_browser_run(
    session: AsyncSession,
    service: RunService,
    *,
    user_id: str,
    url: str,
    action: str = "fetch",
    browser_session_id: str | None = None,
    idempotency_key: str | None = None,
    **budget_limits: Any,
) -> Run:
    """Create the canonical run before BrowserAgent execution."""
    return await service.create_run(
        session,
        run_type="browser",
        user_id=user_id,
        title=f"browser:{action}",
        source_type="browser",
        source_ref=browser_session_id or url,
        idempotency_key=idempotency_key or str(uuid.uuid5(uuid.NAMESPACE_URL, url)),
        **budget_limits,
    )


async def observe_remediation_run(
    session: AsyncSession,
    service: RunService,
    *,
    user_id: str,
    fix_id: str,
    tenant_id: str,
    impact_score: float,
    idempotency_key: str | None = None,
    **budget_limits: Any,
) -> Run:
    """Record a self-healing proposal as a governed canonical run.

    বাংলা (M06 হাইজিন-ফিক্স): আগে ``run_type="remediation"`` পাঠানো হতো —
    যা RunType-enum-এ (mission/agent/tool/mcp/browser/code/automation/
    pipeline) অস্তিত্বই নেই; প্রথম প্রকৃত কলে create_run বৈধতা-ধাপে
    ValueError ছুড়ে দিত (latent bug — ফাংশনটি এ পর্যন্ত কোনো production
    caller-বিহীন)। স্ব-নিরাময়-প্রস্তাব = স্বায়ত্তশাসিত agent-run — তাই
    বৈধ ``"agent"`` ম্যাপ; source_type="self_healing" আলাদাত্ব বহন করে।
    """
    return await service.create_run(
        session,
        run_type="agent",
        user_id=user_id,
        title=f"remediation:{fix_id}",
        source_type="self_healing",
        source_ref=fix_id,
        correlation_id=tenant_id,
        idempotency_key=idempotency_key or f"remediation:{fix_id}",
        **budget_limits,
    )


__all__ = ["observe_browser_run", "observe_mcp_run", "observe_remediation_run"]
