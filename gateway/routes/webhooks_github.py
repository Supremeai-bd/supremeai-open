"""GitHub webhook ingest — event-driven orchestration entrypoint (#1802).

বাংলা: GitHub → SupremeAI orchestration chain-এর প্রবেশদ্বার।
- HMAC signature verification (fail-closed — ভুল/অনুপস্থিত signature → কোনো
  processing নয়)
- ৩টি event parse + normalize: `issues` (opened/labeled), `pull_request`
  (opened), `workflow_run` (completed with failure conclusion)
- Upstash dedup key `supremeai:orchestrate:<issue>:<event>:<delivery>` —
  একই event delivery দ্বিতীয়বার process হয় না (replay protection)
- Invalid payload → 422 + audit log (silent drop নিষিদ্ধ)

Tenant isolation (AGENTS.md §5): webhook payload-এ GitHub repo-ই tenant
boundary — repo full name settings-এর GITHUB_WEBHOOK_REPOSITORY-র সাথে
মিললে tenant-supremeai, না মিললে reject (cross-tenant ingestion বন্ধ)।

Note: `webhooks_ai.py` নামে আলাদা Telegram/Slack router আগে থেকেই আছে —
issue-র "dedicated router" বিকল্প অনুযায়ী এই নতুন ফাইল।
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from core.cache.redis_manager import redis_manager
from core.logging_config import logger

router = APIRouter(prefix="/api/webhooks", tags=["webhooks-orchestration"])

# Events the orchestration layer consumes (Phase C minimum set — #1802).
SUPPORTED_EVENTS = frozenset({"issues", "pull_request", "workflow_run"})

DEDUP_TTL_SECONDS = 7 * 24 * 3600  # 7 days of replay protection per delivery


def _webhook_secret() -> str:
    return os.getenv("GITHUB_WEBHOOK_SECRET", "")


def _allowed_repository() -> str:
    return os.getenv("GITHUB_WEBHOOK_REPOSITORY", "SaifulHaqueNiloy/supremeai")


def _verify_signature(payload: bytes, signature_header: str | None) -> bool:
    """HMAC-SHA256 verify of `X-Hub-Signature-256`. Fail-closed."""
    secret = _webhook_secret()
    if not secret:
        logger.error("[webhook-audit] REJECTED reason=secret_unconfigured — fail-closed")
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning("[webhook-audit] REJECTED reason=signature_missing")
        return False
    expected = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=").strip()
    if not hmac.compare_digest(expected, provided):
        logger.warning("[webhook-audit] REJECTED reason=signature_mismatch")
        return False
    return True


def _normalize_event(
    event: str, action: str | None, payload: dict[str, Any]
) -> dict[str, Any] | None:
    """Parse + normalize a supported GitHub event into the orchestration shape.

    Returns None for unsupported/irrelevant event-action combos (logged).
    """
    repo = (payload.get("repository") or {}).get("full_name", "")
    sender = (payload.get("sender") or {}).get("login", "")
    base = {"event": event, "action": action, "repo": repo, "sender": sender}

    if event == "issues":
        issue = payload.get("issue") or {}
        if action not in {"opened", "labeled"}:
            return None
        labels = [str(l.get("name", "")) for l in issue.get("labels", [])]
        return {
            **base,
            "number": issue.get("number"),
            "title": issue.get("title", ""),
            "labels": labels,
            "handoff_label": next((l for l in labels if l.startswith("handoff:")), None),
            "body_excerpt": (issue.get("body") or "")[:4000],
        }

    if event == "pull_request":
        pull = payload.get("pull_request") or {}
        if action != "opened":
            return None
        return {
            **base,
            "number": pull.get("number"),
            "title": pull.get("title", ""),
            "branch": (pull.get("head") or {}).get("ref", ""),
        }

    if event == "workflow_run":
        run = payload.get("workflow_run") or {}
        # Only completed runs with failure conclusions carry a signal.
        if action != "completed" or run.get("conclusion") != "failure":
            return None
        return {
            **base,
            "run_id": run.get("id"),
            "name": run.get("name", ""),
            "conclusion": run.get("conclusion"),
            "head_branch": run.get("head_branch", ""),
            "html_url": run.get("html_url", ""),
        }

    return None


def _dedup_key(normalized: dict[str, Any], delivery_id: str) -> str:
    issue_ref = normalized.get("number") or normalized.get("run_id") or "no-ref"
    return f"supremeai:orchestrate:{issue_ref}:{normalized['event']}:{delivery_id}"


async def _claim_delivery(key: str) -> bool:
    """SETNX-style claim — True = first time seeing this delivery.

    Upstash unavailable → dedup degrades (logged, fail-open for availability);
    replay protection is best-effort, unlike signature verification which is
    strictly fail-closed.
    """
    client = await redis_manager.get_client_async()
    if client is None:
        logger.warning(
            "[webhook-audit] dedup store unavailable — delivery processed without replay guard"
        )
        return True
    try:
        was_set = await client.set(key, "1", nx=True, ex=DEDUP_TTL_SECONDS)
        return bool(was_set)
    except Exception as exc:
        logger.warning(
            f"[webhook-audit] dedup store error ({exc}) — processing without replay guard"
        )
        return True


@router.post("/github")
async def github_webhook(request: Request) -> JSONResponse:
    """Receive + verify + normalize GitHub webhook deliveries."""
    raw = await request.body()
    if not _verify_signature(raw, request.headers.get("X-Hub-Signature-256")):
        return JSONResponse(status_code=401, content={"detail": "invalid webhook signature"})

    event = request.headers.get("X-GitHub-Event", "")
    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    action = request.headers.get("X-GitHub-Action")

    try:
        payload = json.loads(raw or b"{}")
    except ValueError:
        logger.error(f"[webhook-audit] REJECTED reason=invalid_json delivery={delivery_id}")
        return JSONResponse(status_code=422, content={"detail": "invalid JSON payload"})

    repo = (payload.get("repository") or {}).get("full_name", "")
    if repo != _allowed_repository():
        logger.error(
            f"[webhook-audit] REJECTED reason=repo_mismatch repo={repo} delivery={delivery_id}"
        )
        return JSONResponse(
            status_code=403, content={"detail": "repository not managed by this tenant"}
        )

    if event not in SUPPORTED_EVENTS:
        logger.info(f"[webhook-audit] ignored unsupported event={event} delivery={delivery_id}")
        return JSONResponse(status_code=202, content={"status": "ignored", "event": event})

    normalized = _normalize_event(event, action, payload)
    if normalized is None:
        return JSONResponse(
            status_code=202, content={"status": "ignored", "event": event, "action": action}
        )

    key = _dedup_key(normalized, delivery_id or "missing-delivery-id")
    if not await _claim_delivery(key):
        logger.info(f"[webhook-audit] replay suppressed delivery={delivery_id} key={key}")
        return JSONResponse(status_code=200, content={"status": "duplicate", "dedup_key": key})

    # Handoff label metadata (handoff:<lane>) parsed directly from issue labels.
    handoff = None
    if normalized.get("handoff_label"):
        target_role = str(normalized["handoff_label"]).removeprefix("handoff:").strip()
        handoff = {
            "next_agent": target_role,
            "issue": str(normalized.get("number") or ""),
            "tenant_id": "tenant-supremeai",
        }

    route = {
        "status": "processed",
        "normalized": normalized,
        "handoff": handoff,
        "dedup_key": key,
        "tenant_id": "tenant-supremeai",
    }
    logger.info(
        f"[orchestrate] event={event} action={action} number={normalized.get('number')} "
        f"handoff={route['handoff']['next_agent'] if route['handoff'] else 'n/a'}"
    )
    return JSONResponse(status_code=200, content=route)
