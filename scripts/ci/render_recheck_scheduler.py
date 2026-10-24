#!/usr/bin/env python3
"""Daily idempotent scheduler for Render account cooldown rechecks.

Queries database records where status == 'cooldown' or status == 'recheck_required'
and recheck_at <= now(). Calls RenderAccountService to perform a live audit.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from core.logging_config import logger
from database.supabase_client import db
from services.render_account_service import RenderAccountService


def main() -> int:
    logger.info("🔍 Running Render Account Cooldown Recheck Scheduler...")
    now = datetime.now(timezone.utc)
    records = db.get_render_account_states()

    rechecked_count = 0
    for record in records:
        role = record.get("role")
        status = record.get("status")
        recheck_at_str = record.get("recheck_at")

        should_recheck = False
        if status in ("cooldown", "recheck_required"):
            if not recheck_at_str:
                should_recheck = True
            else:
                try:
                    recheck_at = datetime.fromisoformat(recheck_at_str.replace("Z", "+00:00"))
                    if now >= recheck_at:
                        should_recheck = True
                except Exception:
                    should_recheck = True

        if should_recheck and role:
            logger.info(f"⏳ Rechecking cooled-down account role: {role}")
            res = RenderAccountService.refresh_account_status(
                account_role=role,
                force=False,
                manual_by="scheduler_cron",
            )
            logger.info(f"✅ Recheck outcome for {role}: status={res.get('status')}")
            rechecked_count += 1

    logger.info(f"🎉 Render account recheck job completed. Total rechecked: {rechecked_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
