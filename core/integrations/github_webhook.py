"""GitHub webhook listener (MESH-7, issue #962) — PR events → MESH-6 task hooks.

Master Plan §৫-এর ইভেন্ট সোর্স: Tower যেন Bolt/Lovable-এর খোলা PR track করতে পারে।

বাংলা সারসংক্ষেপ:
------------------
1. POST /api/v1/integrations/github/webhook — GitHub-এর একমাত্র ingest endpoint
2. Fail-closed HMAC-SHA256 signature verification (X-Hub-Signature-256);
   secret কনফিগার না থাকলে 503 — কখনো unsigned payload গ্রহণ নেই
3. pull_request events → MESH-6 TaskRouter hooks:
   - opened/synchronize → pytest verification task submit (mesh fleet claim করবে)
   - closed (merged) → সেই PR-এর পুরোনো pending verification task cancel
     (merge-এর পরে verification moot — Zero Zombie principle)
4. Task dispatch ব্যর্থ হলে fail-open: log + ok:false (GitHub retry-storm এড়াতে 200),
   কিন্তু signature verification কখনো fail-open নয়
5. push event → log-only (CI নিজেই হ্যান্ডল করে)

Constitution:
   - Law #11 (Think Before You Act): প্রতিটি ইভেন্টের সিদ্ধান্ত log হয়
   - Law #19 (Observable): সব ingest/submit observable logging সহ
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from core.config import settings
from core.logging_config import logger
from core.task_router import TaskRouter, get_task_router

router = APIRouter(prefix="/api/v1/integrations/github", tags=["github-webhook"])

# এই ইভেন্টগুলোতে নতুন verification task জমা হয়
_VERIFICATION_TRIGGER_ACTIONS = frozenset({"opened", "synchronize"})


def _verify_signature(raw_body: bytes, signature_header: str | None, secret: str) -> None:
    """HMAC-SHA256 যাচাই — fail-closed: কোনো path silent-pass করে না।

    Raises:
        HTTPException: 503 (secret নেই), 401 (signature নেই/ভুল ফরম্যাট/ভুল মান)
    """
    if not secret:
        # Fail-closed: secret কনফিগার না থাকলে কোনো payload ingest হবে না
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub webhook secret not configured — ingest disabled (fail-closed)",
        )
    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256 header",
        )
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header.strip()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )


def _is_verification_task(record_payload: dict[str, Any], pr_number: int) -> bool:
    return record_payload.get("source") == "github_webhook" and str(
        record_payload.get("pr_number")
    ) == str(pr_number)


@router.post("/webhook", summary="GitHub webhook ingest (HMAC-verified, PR → MESH-6 hooks)")
async def github_webhook(
    request: Request,
    task_router: TaskRouter = Depends(get_task_router),
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
    x_github_delivery: str | None = Header(default=None),
) -> dict[str, Any]:
    """GitHub event ingest → MESH-6 verification task orchestration।

    Returns:
        dict: ok + event/action + task orchestration outcome
    """
    raw_body = await request.body()
    secret = str(getattr(settings, "github_webhook_secret", "") or "")
    _verify_signature(raw_body, x_hub_signature_256, secret)

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook body is not valid JSON",
        ) from None

    event = (x_github_event or "unknown").lower()
    logger.info(
        "github_webhook: delivery=%s event=%s action=%s",
        x_github_delivery,
        event,
        payload.get("action"),
    )

    if event == "ping":
        return {"ok": True, "event": "ping", "message": "webhook active"}

    if event == "pull_request":
        action = (payload.get("action") or "").lower()
        pr = payload.get("pull_request") or {}
        pr_number = pr.get("number")
        pr_branch = (pr.get("head") or {}).get("ref")

        if action in _VERIFICATION_TRIGGER_ACTIONS and pr_number:
            task = await task_router.submit_task(
                task_type="pytest",
                title=f"Verify PR #{pr_number}: {str(pr.get('title') or '')[:120]}",
                payload={
                    "source": "github_webhook",
                    "pr_number": pr_number,
                    "pr_url": pr.get("html_url"),
                    "branch": pr_branch,
                    "sha": (pr.get("head") or {}).get("sha"),
                    "action": action,
                },
                target_role="tester",
                priority=3,
            )
            logger.info(
                "github_webhook: verification task %s submitted for PR #%s", task.task_id, pr_number
            )
            return {"ok": True, "event": event, "action": action, "task_id": task.task_id}

        if action == "closed" and pr_number:
            cancelled: list[str] = []
            for stale in await task_router.list_tasks(status="pending"):
                if _is_verification_task(stale.payload, int(pr_number)):
                    await task_router.cancel_task(stale.task_id)
                    cancelled.append(stale.task_id)
            if cancelled:
                logger.info(
                    "github_webhook: PR #%s closed — cancelled stale tasks %s", pr_number, cancelled
                )
            return {"ok": True, "event": event, "action": action, "cancelled_tasks": cancelled}

        return {"ok": True, "event": event, "action": action, "handled": False}

    # push ইত্যাদি event — CI নিজেই হ্যান্ডল করে; এখানে observability-ই যথেষ্ট
    return {"ok": True, "event": event, "handled": False}
