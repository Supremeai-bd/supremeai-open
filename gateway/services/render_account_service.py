"""Render Account & Preflight Management Service.

Handles account status checks, build minute calculations, cooldowns (with bounded backoff),
audit event recording, and fail-closed evaluation.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from core.clients.render_api import render_get_json
from core.logging_config import logger
from database.supabase_client import db

DEFAULT_COOLDOWN_DAYS = 10
MAX_BACKOFF_DAYS = 30


class RenderAccountService:
    """Service for querying Render accounts, computing usage, and tracking status."""

    @staticmethod
    def get_configured_accounts() -> list[dict[str, Any]]:
        """Load account configuration from RENDER_ACCOUNTS_JSON or default environment mappings."""
        raw = os.getenv("RENDER_ACCOUNTS_JSON")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [item for item in parsed if isinstance(item, dict)]
            except Exception as exc:
                logger.error(f"Failed to parse RENDER_ACCOUNTS_JSON: {exc}")

        # Fallback to standard 4 nodes if JSON not provided
        accounts = []
        node_defs = [
            ("core", "RENDER_PRIMARY_SVC_ID", "RENDER_API_KEY_1", 450.0, "free"),
            ("worker", "RENDER_WORKER_SVC_ID", "RENDER_API_KEY_2", 450.0, "free"),
            ("scraper", "RENDER_SCRAPER_SVC_ID", "RENDER_API_KEY_3", 450.0, "free"),
            ("mcp", "RENDER_MCP_SVC_ID", "RENDER_API_KEY_4", 450.0, "free"),
        ]
        for role, svc_env, key_env, default_cap, plan in node_defs:
            svc_id = os.getenv(svc_env)
            if svc_id:
                accounts.append(
                    {
                        "role": role,
                        "service_id": svc_id,
                        "api_key_env": key_env,
                        "safe_build_minutes": default_cap,
                        "plan": plan,
                    }
                )
        return accounts

    @classmethod
    def calculate_monthly_usage_minutes(cls, deploys: list[dict]) -> float:
        """Sum build durations for deploys started in the current calendar month."""
        now = datetime.now(UTC)
        total_seconds = 0.0
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
                    duration = (ended - started).total_seconds()
                    if duration > 0:
                        total_seconds += duration
            except (TypeError, ValueError):
                continue
        return total_seconds / 60.0

    @classmethod
    def get_status_overview(cls) -> dict[str, Any]:
        """Return high-level preflight report for all accounts with deployment authorization."""
        accounts_config = cls.get_configured_accounts()
        required_roles_raw = os.getenv("RENDER_REQUIRED_ROLES", "")
        required_roles = {r.strip() for r in required_roles_raw.split(",") if r.strip()}

        # Fetch persisted states from DB
        persisted_states = {row["role"]: row for row in db.get_render_account_states()}

        accounts_summary = []
        overall_ready = True

        for acc in accounts_config:
            role = acc.get("role", "unknown")
            state = persisted_states.get(role)

            if state:
                status = state.get("status", "unknown")
                recheck_at_str = state.get("recheck_at")
                now_utc = datetime.now(UTC)

                # Check if cooldown has expired and needs recheck
                if status == "cooldown" and recheck_at_str:
                    try:
                        recheck_at = datetime.fromisoformat(recheck_at_str.replace("Z", "+00:00"))
                        if now_utc >= recheck_at:
                            status = "recheck_required"
                    except Exception as e:
                        logger.debug(f"Failed to parse recheck_at timestamp: {e}")

                summary_item = {
                    "role": role,
                    "account_key": state.get("account_key", role),
                    "plan": state.get("plan", acc.get("plan", "unknown")),
                    "status": status,
                    "reason": state.get("reason"),
                    "usage_minutes": state.get("usage_minutes"),
                    "safe_build_minutes": acc.get("safe_build_minutes"),
                    "recheck_at": state.get("recheck_at"),
                    "last_checked_at": state.get("last_checked_at"),
                    "retry_count": state.get("retry_count", 0),
                    "source": "database",
                }
            else:
                # Not yet cached in DB -> unknown
                summary_item = {
                    "role": role,
                    "account_key": role,
                    "plan": acc.get("plan", "unknown"),
                    "status": "unknown",
                    "reason": "Not yet audited in DB; refresh required",
                    "usage_minutes": None,
                    "safe_build_minutes": acc.get("safe_build_minutes"),
                    "recheck_at": None,
                    "last_checked_at": None,
                    "retry_count": 0,
                    "source": "uninitialized",
                }

            if (not required_roles or role in required_roles) and summary_item["status"] != "ready":
                overall_ready = False

            accounts_summary.append(summary_item)

        return {
            "deployment_allowed": overall_ready,
            "required_roles": list(required_roles) if required_roles else "all_configured",
            "accounts": accounts_summary,
            "checked_at": datetime.now(UTC).isoformat(),
        }

    @classmethod
    def refresh_account_status(
        cls, account_role: str, force: bool = False, manual_by: str | None = None
    ) -> dict[str, Any]:
        """Audit the Render API for a given role, update DB state and event log."""
        accounts = [a for a in cls.get_configured_accounts() if a.get("role") == account_role]
        if not accounts:
            return {
                "role": account_role,
                "status": "unknown",
                "reason": f"Role '{account_role}' not found in configuration",
            }

        acc = accounts[0]
        service_id = acc.get("service_id")
        key_env = acc.get("api_key_env", "")
        api_key = os.getenv(key_env)
        safe_minutes = float(acc.get("safe_build_minutes", 450.0))
        plan = acc.get("plan", "free")
        now = datetime.now(UTC)

        # Existing record
        existing = {r["role"]: r for r in db.get_render_account_states(role=account_role)}.get(
            account_role
        )

        # Respect cooldown unless force=True
        if not force and existing and existing.get("status") == "cooldown":
            recheck_str = existing.get("recheck_at")
            if recheck_str:
                try:
                    recheck_at = datetime.fromisoformat(recheck_str.replace("Z", "+00:00"))
                    if now < recheck_at:
                        logger.info(
                            f"Render account {account_role} is in cooldown until {recheck_str}. Skipping refresh."
                        )
                        return existing
                except Exception as e:
                    logger.debug(f"Failed to parse cooldown recheck timestamp: {e}")

        if not service_id or not api_key:
            state_dict = {
                "account_key": account_role,
                "role": account_role,
                "plan": plan,
                "status": "unknown",
                "reason": "missing_credentials_or_service_id",
                "last_error": f"Missing credentials ({key_env}) or service_id",
                "last_checked_at": now.isoformat(),
            }
            db.upsert_render_account_state(state_dict)
            db.record_render_preflight_event(
                {
                    "account_key": account_role,
                    "status": "unknown",
                    "reason": "missing_credentials",
                    "metadata": {"key_env": key_env, "service_id": service_id},
                }
            )
            return state_dict

        # Query Render API for deploys (single-sourced transport — core.clients.render_api)
        try:
            payload = render_get_json(
                f"/services/{service_id}/deploys", api_key=api_key, query={"limit": 100}
            )
            deploys = payload if isinstance(payload, list) else payload.get("deploys", [])
            usage = round(cls.calculate_monthly_usage_minutes(deploys), 2)

            if usage >= safe_minutes:
                # Quota limit detected! Trigger cooldown
                current_retry = (existing.get("retry_count", 0) if existing else 0) + 1
                backoff_days = min(DEFAULT_COOLDOWN_DAYS * current_retry, MAX_BACKOFF_DAYS)
                recheck_at = now + timedelta(days=backoff_days)

                state_dict = {
                    "account_key": account_role,
                    "role": account_role,
                    "plan": plan,
                    "status": "cooldown",
                    "reason": "build_time_limit",
                    "usage_minutes": usage,
                    "usage_period_start": datetime(now.year, now.month, 1, tzinfo=UTC).isoformat(),
                    "recheck_at": recheck_at.isoformat(),
                    "last_checked_at": now.isoformat(),
                    "retry_count": current_retry,
                    "last_error": f"Estimated build usage {usage}m exceeded safe limit {safe_minutes}m",
                }
            else:
                state_dict = {
                    "account_key": account_role,
                    "role": account_role,
                    "plan": plan,
                    "status": "ready",
                    "reason": "quota_within_limits",
                    "usage_minutes": usage,
                    "usage_period_start": datetime(now.year, now.month, 1, tzinfo=UTC).isoformat(),
                    "recheck_at": None,
                    "last_checked_at": now.isoformat(),
                    "retry_count": 0,
                    "last_error": None,
                }

            db.upsert_render_account_state(state_dict)
            db.record_render_preflight_event(
                {
                    "account_key": account_role,
                    "status": state_dict["status"],
                    "reason": state_dict["reason"],
                    "usage_minutes": usage,
                    "metadata": {
                        "safe_minutes": safe_minutes,
                        "force": force,
                        "manual_by": manual_by,
                    },
                }
            )
            return state_dict

        except Exception as err:
            logger.error(f"Render API query failed for {account_role}: {err}")
            state_dict = {
                "account_key": account_role,
                "role": account_role,
                "plan": plan,
                "status": "error",
                "reason": "render_api_error",
                "last_error": str(err)[:250],
                "last_checked_at": now.isoformat(),
            }
            db.upsert_render_account_state(state_dict)
            db.record_render_preflight_event(
                {
                    "account_key": account_role,
                    "status": "error",
                    "reason": "render_api_error",
                    "metadata": {"error": str(err)[:250]},
                }
            )
            return state_dict

    @classmethod
    def manual_override(
        cls, account_role: str, status: str, reason: str, admin_user: str
    ) -> dict[str, Any]:
        """Apply an explicit manual override by an authorized admin."""
        now = datetime.now(UTC)
        state_dict = {
            "account_key": account_role,
            "role": account_role,
            "status": status,
            "reason": f"manual_override: {reason}",
            "last_checked_at": now.isoformat(),
            "metadata": {
                "manual_override": True,
                "override_by": admin_user,
                "override_at": now.isoformat(),
                "override_reason": reason,
            },
        }
        db.upsert_render_account_state(state_dict)
        db.record_render_preflight_event(
            {
                "account_key": account_role,
                "status": status,
                "reason": f"manual_override: {reason}",
                "metadata": {"override_by": admin_user},
            }
        )
        return state_dict
