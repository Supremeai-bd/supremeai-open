"""
SupremeAI 2.0 — Merge Learning Report Pydantic Model and Database Access Layer
Founder directive (issue #1929): every merge into main gets a learning report —
WHY it was allowed as an improvement, WHAT it did, and its held/mistake history —
so SupremeAI learns from every change (vul gulo database e thakle learning hoy).
Uses raw asyncpg via PgBouncerConnectionPool (mirror of models/ci_report.py).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from database.pgbouncer_pool import get_db_pool


def now_epoch() -> int:
    return int(datetime.now(UTC).timestamp())


class MergeLearningPayload(BaseModel):
    """One merged PR = one learning row (upserted by pr_number — idempotent)."""

    pr_number: int = Field(..., description="GitHub pull request number")
    title: str = Field(..., description="PR title")
    author: str = Field(..., description="PR author (login)")
    merged_by: str | None = Field(default=None, description="Who merged (login)")
    lane: str | None = Field(
        default=None, description="Agent lane inferred from branch (planner/coder/ci/...)"
    )
    branch: str = Field(..., description="Head branch name")
    merge_sha: str | None = Field(default=None, description="Squash-merge commit SHA")
    merged_at: int = Field(..., description="Merge time (epoch seconds)")
    risk_class: str | None = Field(
        default=None, description="Unified PR Gate risk class (LOW/MEDIUM/HIGH/CRITICAL)"
    )
    gate_status: str | None = Field(
        default=None, description="Unified PR Gate verdict (PASS/BLOCKED/NEEDS-REVIEW)"
    )
    why_allowed: str | None = Field(
        default=None,
        description="Why this merge was allowed as an improvement (gate decision rationale)",
    )
    what_it_did: str | None = Field(
        default=None,
        description="What the change actually did (summary)",
    )
    held_history: list[dict[str, Any]] | None = Field(
        default=None,
        description="Mistake/blocker trail: every queue:hold / hold:merge-conflict / queue:failed event with timestamps",
    )
    linked_issues: list[int] | None = Field(
        default=None, description="Issues closed/linked by the PR"
    )
    files: list[str] | None = Field(default=None, description="Files changed")
    additions: int = Field(default=0, description="Lines added")
    deletions: int = Field(default=0, description="Lines deleted")
    lessons_ref: str | None = Field(
        default=None, description="LESSONS_LEARNED.md reference if a lesson was logged"
    )


async def upsert_merge_learning(payload: MergeLearningPayload) -> dict[str, Any] | None:
    # বাংলা মন্তব্য: PR helper রেকর্ডার থেকে পাঠানো মার্জ-লার্নিং রিপোর্ট ডাটাবেসে সেভ (আপসার্ট) করার ফাংশন
    pool = await get_db_pool()

    held_json = json.dumps(payload.held_history) if payload.held_history else None
    issues_json = json.dumps(payload.linked_issues) if payload.linked_issues else None
    files_json = json.dumps(payload.files) if payload.files else None

    row = await pool.fetchrow(
        """
        INSERT INTO merge_learning_reports (
            pr_number, title, author, merged_by, lane, branch, merge_sha,
            merged_at, risk_class, gate_status, why_allowed, what_it_did,
            held_history, linked_issues, files, additions, deletions,
            lessons_ref, created_at, updated_at
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$19)
        ON CONFLICT (pr_number) DO UPDATE SET
            title = EXCLUDED.title,
            author = EXCLUDED.author,
            merged_by = EXCLUDED.merged_by,
            lane = EXCLUDED.lane,
            branch = EXCLUDED.branch,
            merge_sha = EXCLUDED.merge_sha,
            merged_at = EXCLUDED.merged_at,
            risk_class = EXCLUDED.risk_class,
            gate_status = EXCLUDED.gate_status,
            why_allowed = EXCLUDED.why_allowed,
            what_it_did = EXCLUDED.what_it_did,
            held_history = EXCLUDED.held_history,
            linked_issues = EXCLUDED.linked_issues,
            files = EXCLUDED.files,
            additions = EXCLUDED.additions,
            deletions = EXCLUDED.deletions,
            lessons_ref = EXCLUDED.lessons_ref,
            updated_at = EXCLUDED.updated_at
        RETURNING id, pr_number, updated_at
        """,
        payload.pr_number,
        payload.title,
        payload.author,
        payload.merged_by,
        payload.lane,
        payload.branch,
        payload.merge_sha,
        payload.merged_at,
        payload.risk_class,
        payload.gate_status,
        payload.why_allowed,
        payload.what_it_did,
        held_json,
        issues_json,
        files_json,
        payload.additions,
        payload.deletions,
        payload.lessons_ref,
        now_epoch(),
    )
    return dict(row) if row else None


async def list_merge_learning(
    lane: str | None = None,
    risk_class: str | None = None,
    held_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Query the learning base — the teach-back side (agents + evolution module)."""
    pool = await get_db_pool()
    conditions: list[str] = []
    params: list[Any] = []

    if lane:
        params.append(lane)
        conditions.append(f"lane = ${len(params)}")
    if risk_class:
        params.append(risk_class)
        conditions.append(f"risk_class = ${len(params)}")
    if held_only:
        # বাংলা মন্তব্য: শুধু যেসব মার্জ আটকে ছিল (queue:hold / conflict) — ভুল থেকে শেখার তালিকা
        conditions.append("held_history IS NOT NULL AND jsonb_array_length(held_history) > 0")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.extend([limit, offset])
    rows = await pool.fetch(
        f"""
        SELECT pr_number, title, author, lane, merged_at, risk_class, gate_status,
               why_allowed, what_it_did, held_history, linked_issues, files,
               additions, deletions, lessons_ref
        FROM merge_learning_reports
        {where}
        ORDER BY merged_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]
