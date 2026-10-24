"""Render preflight orchestrator and lifecycle service.

Handles dynamic account status evaluation, cooldown management, bounded backoffs,
Render API usage calculations, and manual override tracking.
"""

from __future__ import annotations

import logging
import os
import urllib.error
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from core.clients.render_api import render_get_json

logger = logging.getLogger(__name__)

from backend.core.contracts.redaction import redact as redact_secrets
from backend.core.contracts.render_preflight_store import RenderPreflightStore


def calculate_deploy_usage_minutes(deploys: list[dict[str, Any]]) -> float:
    """Accurately calculates total build minutes for current calendar month."""
    now = datetime.now(UTC)
    total = 0.0
    for item in deploys:
        deploy = item.get("deploy", item)
        created = deploy.get("createdAt")
        finished = deploy.get("finishedAt")
        if not created or not finished:
            continue
        try:
            started = datetime.fromisoformat(created.replace("Z", "+00:00"))
            ended = datetime.fromisoformat(finished.replace("Z", "+00:00"))
            if started.year == now.year and started.month == now.month:
                total += max(0.0, (ended - started).total_seconds() / 60.0)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


class RenderPreflightService:
    """Service orchestrating Render deploy checks, cooldowns, and admin actions."""

    DEFAULT_COOLDOWN_DAYS = 10
    MAX_BACKOFF_DAYS = 30

    def __init__(self, store: RenderPreflightStore | None = None) -> None:
        self.store = store or RenderPreflightStore()

    def get_account_status(
        self, account_role: str | None = None
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Read-only tool: get_render_account_status(account_role?: string)."""
        if account_role:
            account = self.store.get_account(account_role)
            if not account:
                return {
                    "account_role": account_role,
                    "status": "unknown",
                    "reason_code": "unregistered_account",
                    "usage_minutes": None,
                    "safe_build_minutes": 450.0,
                    "last_checked_at": None,
                    "recheck_at": None,
                    "reset_at": None,
                    "source": "cached",
                }
            return {
                "account_role": account["account_role"],
                "status": account["status"],
                "reason_code": account.get("reason_code"),
                "usage_minutes": account.get("usage_minutes"),
                "safe_build_minutes": account.get("safe_build_minutes", 450.0),
                "last_checked_at": account.get("last_checked_at"),
                "recheck_at": account.get("recheck_at"),
                "reset_at": account.get("reset_at"),
                "source": "manual_override" if account.get("manual_override") else "cached",
            }
        return [
            {
                "account_role": acc["account_role"],
                "status": acc["status"],
                "reason_code": acc.get("reason_code"),
                "usage_minutes": acc.get("usage_minutes"),
                "safe_build_minutes": acc.get("safe_build_minutes", 450.0),
                "last_checked_at": acc.get("last_checked_at"),
                "recheck_at": acc.get("recheck_at"),
                "reset_at": acc.get("reset_at"),
                "source": "manual_override" if acc.get("manual_override") else "cached",
            }
            for acc in self.store.get_all_accounts()
        ]

    def refresh_account_status(
        self,
        account_role: str,
        service_id: str | None = None,
        api_key: str | None = None,
        safe_build_minutes: float = 450.0,
        force: bool = False,
        workflow_run_id: str | None = None,
        commit_sha: str | None = None,
    ) -> dict[str, Any]:
        """Controlled refresh tool: queries Render API, evaluates limit/cooldown, persists state."""
        existing = self.store.get_account(account_role)
        svc_id = service_id or (existing.get("service_id") if existing else None) or ""

        if not svc_id or not api_key:
            return self.store.upsert_account_and_record_event(
                account_role=account_role,
                service_id=svc_id or "unconfigured",
                status="unknown",
                reason_code="missing_credentials",
                reason_message="Missing Render service_id or API key",
                safe_build_minutes=safe_build_minutes,
                event_type="check",
                workflow_run_id=workflow_run_id,
                commit_sha=commit_sha,
            )

        now = datetime.now(UTC)

        # Check if already in cooldown and recheck date has not arrived yet (unless forced)
        if existing and existing.get("status") == "cooldown" and not force:
            recheck_str = existing.get("recheck_at")
            if recheck_str:
                try:
                    recheck_dt = datetime.fromisoformat(recheck_str.replace("Z", "+00:00"))
                    if now < recheck_dt:
                        # Retain existing cooldown without moving recheck_at forward
                        return existing
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "Unparsable recheck_at (%r) for account_role=%s: %s — "
                        "proceeding with a live recheck instead of silently ignoring it",
                        recheck_str,
                        account_role,
                        exc,
                    )

        # Query Render API (single-sourced transport — core.clients.render_api)
        try:
            data = render_get_json(
                f"/services/{svc_id}/deploys", api_key=api_key, query={"limit": 100}
            )
        except urllib.error.HTTPError as err:
            err_msg = f"HTTP {err.code}: {err.reason}"
            if err.code == 429 or "limit" in err.reason.lower():
                recheck_date = (now + timedelta(days=self.DEFAULT_COOLDOWN_DAYS)).isoformat()
                return self.store.upsert_account_and_record_event(
                    account_role=account_role,
                    service_id=svc_id,
                    status="cooldown",
                    reason_code="build_time_limit",
                    reason_message=err_msg,
                    detected_at=now.isoformat(),
                    recheck_at=recheck_date,
                    last_error=err_msg,
                    event_type="limit_detected",
                    increment_retry=True,
                    workflow_run_id=workflow_run_id,
                    commit_sha=commit_sha,
                )
            return self.store.upsert_account_and_record_event(
                account_role=account_role,
                service_id=svc_id,
                status="error",
                reason_code="api_error",
                reason_message=err_msg,
                last_error=err_msg,
                event_type="check",
                workflow_run_id=workflow_run_id,
                commit_sha=commit_sha,
            )
        except Exception as exc:
            return self.store.upsert_account_and_record_event(
                account_role=account_role,
                service_id=svc_id,
                status="unknown",
                reason_code="api_unavailable",
                reason_message=str(exc)[:160],
                last_error=str(exc)[:160],
                event_type="check",
                workflow_run_id=workflow_run_id,
                commit_sha=commit_sha,
            )

        deploys = data if isinstance(data, list) else data.get("deploys", [])
        usage = calculate_deploy_usage_minutes(deploys)

        if usage >= safe_build_minutes:
            recheck_date = (now + timedelta(days=self.DEFAULT_COOLDOWN_DAYS)).isoformat()
            # Bounded backoff if retry_count > 0
            if existing and existing.get("retry_count", 0) > 0:
                retry = existing["retry_count"]
                backoff_days = min(self.DEFAULT_COOLDOWN_DAYS * (2**retry), self.MAX_BACKOFF_DAYS)
                recheck_date = (now + timedelta(days=backoff_days)).isoformat()

            return self.store.upsert_account_and_record_event(
                account_role=account_role,
                service_id=svc_id,
                status="cooldown",
                reason_code="build_time_limit",
                reason_message=f"Usage {usage}m >= cap {safe_build_minutes}m",
                usage_minutes=usage,
                safe_build_minutes=safe_build_minutes,
                detected_at=now.isoformat(),
                recheck_at=recheck_date,
                payload={"deploys_count": len(deploys), "calculated_usage": usage},
                event_type="limit_detected",
                increment_retry=True,
                workflow_run_id=workflow_run_id,
                commit_sha=commit_sha,
            )

        # Usage under cap -> READY
        return self.store.upsert_account_and_record_event(
            account_role=account_role,
            service_id=svc_id,
            status="ready",
            reason_code=None,
            reason_message=f"Usage {usage}m < cap {safe_build_minutes}m",
            usage_minutes=usage,
            safe_build_minutes=safe_build_minutes,
            recheck_at=None,
            payload={"deploys_count": len(deploys), "calculated_usage": usage},
            event_type="ready",
            increment_retry=False,
            workflow_run_id=workflow_run_id,
            commit_sha=commit_sha,
        )

    def get_deploy_preflight(self, required_roles: list[str] | None = None) -> dict[str, Any]:
        """Summary tool: get_render_deploy_preflight()."""
        all_accounts = self.store.get_all_accounts()
        roles_to_check = set(required_roles or [])

        blocked_accounts = []
        next_rechecks = []
        accounts_summary = []

        for acc in all_accounts:
            role = acc["account_role"]
            status = acc.get("status", "unknown")
            is_required = not roles_to_check or (role in roles_to_check)

            if is_required and status != "ready":
                blocked_accounts.append(role)

            if acc.get("recheck_at"):
                next_rechecks.append(acc["recheck_at"])

            accounts_summary.append(
                {
                    "role": role,
                    "status": status,
                    "reason": acc.get("reason_code") or acc.get("reason_message"),
                    "usage_minutes": acc.get("usage_minutes"),
                    "safe_build_minutes": acc.get("safe_build_minutes", 450.0),
                    "recheck_at": acc.get("recheck_at"),
                    "manual_override": acc.get("manual_override", False),
                }
            )

        build_allowed = len(blocked_accounts) == 0 and len(all_accounts) > 0
        earliest_recheck = sorted(next_rechecks)[0] if next_rechecks else None

        return {
            "build_allowed": build_allowed,
            "blocked_accounts": blocked_accounts,
            "recheck_at": earliest_recheck,
            "accounts": accounts_summary,
            "status": "ready" if build_allowed else "blocked",
        }

    def manual_override(self, account_role: str, approved_by: str, reason: str) -> dict[str, Any]:
        """Admin override with mandatory rationale."""
        return self.store.set_manual_override(account_role, approved_by, reason)

    def run_scheduled_rechecks(self, role_api_keys: dict[str, str]) -> list[dict[str, Any]]:
        """Finds records whose recheck_at <= now(), re-evaluates capacity."""
        now = datetime.now(UTC)
        results = []
        for acc in self.store.get_all_accounts():
            recheck_str = acc.get("recheck_at")
            if not recheck_str:
                continue
            try:
                recheck_dt = datetime.fromisoformat(recheck_str.replace("Z", "+00:00"))
                if recheck_dt <= now:
                    role = acc["account_role"]
                    api_key = role_api_keys.get(role)
                    if api_key:
                        res = self.refresh_account_status(
                            account_role=role,
                            service_id=acc["service_id"],
                            api_key=api_key,
                            safe_build_minutes=acc.get("safe_build_minutes", 450.0),
                            force=True,
                        )
                        results.append(res)
            except Exception:
                continue
        return results
