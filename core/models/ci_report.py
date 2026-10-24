"""
from sqlalchemy import JSON
SupremeAI 2.0 — CI Report Pydantic Model and Database Access Layer
Uses raw asyncpg via PgBouncerConnectionPool
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from database.pgbouncer_pool import get_db_pool


def now_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


class CIReportPayload(BaseModel):
    run_id: int = Field(..., description="GitHub Actions workflow run ID")
    run_number: int = Field(..., description="GitHub Actions workflow run number")
    event_name: str = Field(..., description="Trigger event name (push, pr, schedule, etc.)")
    actor: str = Field(..., description="GHA runner user/actor who triggered the run")
    workflow_name: str = Field(..., description="Name of the workflow")
    status: str = Field(..., description="Status (success, failure, cancelled, etc.)")
    runtime_seconds: int = Field(..., description="Total execution time in seconds")
    commit_sha: str = Field(..., description="Commit SHA of the run")
    branch: str = Field(..., description="Branch name of the run")
    jobs_summary: dict[str, Any] | None = Field(
        default=None, description="Detailed status of all GHA jobs run"
    )
    error_logs: str | None = Field(
        default=None, description="Logs/error information for failed runs"
    )


async def create_ci_report(payload: CIReportPayload) -> dict[str, Any] | None:
    # বাংলা মন্তব্য: গিটহাব রানার থেকে পাঠানো ওয়েবহুক পেলোড ডাটাবেসে সেভ করার ফাংশন
    pool = await get_db_pool()

    # JSONB ফিল্ড হিসেবে jobs_summary কনভার্ট করা হচ্ছে
    jobs_summary_json = json.dumps(payload.jobs_summary) if payload.jobs_summary else None

    row = await pool.fetchrow(
        """
        INSERT INTO ci_reports (
            run_id, run_number, event_name, actor, workflow_name,
            status, runtime_seconds, commit_sha, branch, jobs_summary,
            error_logs, created_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        ON CONFLICT (run_id) DO UPDATE SET
            status = EXCLUDED.status,
            runtime_seconds = EXCLUDED.runtime_seconds,
            jobs_summary = EXCLUDED.jobs_summary,
            error_logs = EXCLUDED.error_logs,
            created_at = EXCLUDED.created_at
        # বাংলা মন্তব্য: Ruff E501 (Line too long) এরর এড়াতে RETURNING স্টেটমেন্ট একাধিক লাইনে ভাঙা হলো
        RETURNING id, run_id, run_number, event_name, actor, workflow_name, status,
                  runtime_seconds, commit_sha, branch, jobs_summary, error_logs, created_at
        """,
        payload.run_id,
        payload.run_number,
        payload.event_name,
        payload.actor,
        payload.workflow_name,
        payload.status,
        payload.runtime_seconds,
        payload.commit_sha,
        payload.branch,
        jobs_summary_json,
        payload.error_logs,
        now_epoch(),
    )
    if row:
        res = dict(row)
        if res.get("jobs_summary"):
            res["jobs_summary"] = json.loads(res["jobs_summary"])
        return res
    return None


async def get_recent_ci_reports(limit: int = 20) -> list[dict[str, Any]]:
    # বাংলা মন্তব্য: ড্যাশবোর্ডে প্রদর্শনের জন্য সাম্প্রতিকতম সিআই রিপোর্টগুলো ফেচ করা হচ্ছে
    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT id, run_id, run_number, event_name, actor, workflow_name, status,
               runtime_seconds, commit_sha, branch, jobs_summary, error_logs, created_at
        FROM ci_reports
        ORDER BY created_at DESC
        LIMIT $1
        """,
        limit,
    )
    results = []
    for r in rows:
        d = dict(r)
        if d.get("jobs_summary"):
            d["jobs_summary"] = json.loads(d["jobs_summary"])
        results.append(d)
    return results


async def get_ci_report_by_run_id(run_id: int) -> dict[str, Any] | None:
    # বাংলা মন্তব্য: নির্দিষ্ট রান আইডির জন্য ডাটাবেস থেকে রিপোর্ট খোঁজা হচ্ছে
    pool = await get_db_pool()
    row = await pool.fetchrow(
        """
        SELECT id, run_id, run_number, event_name, actor, workflow_name, status,
               runtime_seconds, commit_sha, branch, jobs_summary, error_logs, created_at
        FROM ci_reports
        WHERE run_id = $1
        """,
        run_id,
    )
    if row:
        d = dict(row)
        if d.get("jobs_summary"):
            d["jobs_summary"] = json.loads(d["jobs_summary"])
        return d
    return None
