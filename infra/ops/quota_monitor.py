"""
SupremeAI Actions Runner Quota Monitor
Audits GitHub Actions usage against the 2,000 min/month Free-org budget
per docs/OPS_ACTIONS_QUOTA_RUNBOOK.md to prevent runaway runner burnout.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class QuotaEvaluation:
    monthly_budget_minutes: float
    used_minutes: float
    remaining_minutes: float
    days_elapsed: int
    daily_burn_rate: float
    projected_month_end_minutes: float
    status: str  # HEALTHY, WARNING, CRITICAL, EXHAUSTED
    alert_message: Optional[str] = None


@dataclass
class JobRuntimeEvaluation:
    job_name: str
    duration_seconds: float
    max_allowed_seconds: float
    is_runaway: bool
    status: str
    recommendation: Optional[str] = None


class QuotaMonitor:
    """Monitors GitHub Actions minutes and flags hanging/runaway CI matrix executions."""

    DEFAULT_MONTHLY_BUDGET = 2000.0  # Free-org budget in minutes
    DEFAULT_WARNING_THRESHOLD_PCT = 0.75  # 75% (1500 mins)
    DEFAULT_CRITICAL_THRESHOLD_PCT = 0.90  # 90% (1800 mins)
    DEFAULT_MAX_JOB_SECONDS = 600.0  # 10 minutes max per single CI step

    def __init__(
        self,
        monthly_budget_minutes: float = DEFAULT_MONTHLY_BUDGET,
        warning_pct: float = DEFAULT_WARNING_THRESHOLD_PCT,
        critical_pct: float = DEFAULT_CRITICAL_THRESHOLD_PCT,
    ):
        self.monthly_budget = monthly_budget_minutes
        self.warning_threshold = self.monthly_budget * warning_pct
        self.critical_threshold = self.monthly_budget * critical_pct

    def evaluate_usage(
        self,
        used_minutes: float,
        days_elapsed: int = 1,
        days_in_month: int = 30,
    ) -> QuotaEvaluation:
        """Evaluates cumulative usage and forecasts month-end exhaustion."""
        safe_days = max(1, days_elapsed)
        remaining = max(0.0, self.monthly_budget - used_minutes)
        daily_burn = used_minutes / safe_days
        projected = daily_burn * days_in_month

        if used_minutes >= self.monthly_budget:
            status = "EXHAUSTED"
            msg = f"EMERGENCY: Monthly runner quota exhausted ({used_minutes:.1f}/{self.monthly_budget:.1f}m)."
        elif used_minutes >= self.critical_threshold or projected > self.monthly_budget * 1.2:
            status = "CRITICAL"
            msg = (
                f"CRITICAL: Quota burn rate ({daily_burn:.1f}m/day) projects {projected:.1f}m "
                f"exceeding budget ({self.monthly_budget:.1f}m). Throttle CI immediately."
            )
        elif used_minutes >= self.warning_threshold or projected > self.monthly_budget:
            status = "WARNING"
            msg = (
                f"WARNING: Quota usage at {used_minutes:.1f}m ({used_minutes/self.monthly_budget*100:.1f}%). "
                f"Projected month-end: {projected:.1f}m."
            )
        else:
            status = "HEALTHY"
            msg = None

        return QuotaEvaluation(
            monthly_budget_minutes=self.monthly_budget,
            used_minutes=round(used_minutes, 2),
            remaining_minutes=round(remaining, 2),
            days_elapsed=safe_days,
            daily_burn_rate=round(daily_burn, 2),
            projected_month_end_minutes=round(projected, 2),
            status=status,
            alert_message=msg,
        )

    def check_job_runtime(
        self,
        job_name: str,
        duration_seconds: float,
        max_allowed_seconds: float = DEFAULT_MAX_JOB_SECONDS,
    ) -> JobRuntimeEvaluation:
        """Detects hanging or runaway workflow jobs."""
        is_runaway = duration_seconds > max_allowed_seconds
        status = "RUNAWAY" if is_runaway else "NORMAL"
        rec = None
        if is_runaway:
            rec = (
                f"Job '{job_name}' exceeded timeout threshold ({duration_seconds:.1f}s > {max_allowed_seconds:.1f}s). "
                "Terminate job to conserve Actions minutes."
            )

        return JobRuntimeEvaluation(
            job_name=job_name,
            duration_seconds=duration_seconds,
            max_allowed_seconds=max_allowed_seconds,
            is_runaway=is_runaway,
            status=status,
            recommendation=rec,
        )
