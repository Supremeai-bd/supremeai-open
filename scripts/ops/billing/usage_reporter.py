#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  SUPREMEAI — Billing Usage Reporter                                         ║
║  Tenant Usage Reporting | Firestore + Transaction Ledger                   ║
║  Priority: 🟡 Medium                                                        ║
║  Architecture: FastAPI + Firestore + SQLAlchemy + Redis                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Generates per-tenant usage reports from the transaction ledger and Firestore
usage collections. Supports JSON and Markdown output formats.

Usage:
    python usage_reporter.py --tenant-id <tenant_id> --period 2026-07
    python usage_reporter.py --scan-all --period 2026-07 --format markdown
    python usage_reporter.py --tenant-id <tenant_id> --period 2026-07 --dry-run

Environment:
    GOOGLE_CLOUD_PROJECT      — GCP project identifier
    DATABASE_URL              — SQLAlchemy database URL (optional, for ledger)
    REDIS_URL                 — Redis URL for caching (optional)
    SLACK_WEBHOOK_URL         — Alert channel (optional)
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from core.config import settings


import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger
from typing_extensions import Self

try:
    from google.cloud import firestore
except ImportError:
    firestore = None

try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.future import select
except ImportError:
    AsyncSession = None
    select = None

try:
    from models.wallet import TransactionLedgerEntry
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
    from models.wallet import TransactionLedgerEntry


@dataclass
class TenantUsage:
    tenant_id: str
    period_start: datetime
    period_end: datetime
    total_spend_usd: Decimal
    total_transactions: int
    token_input_count: int
    token_output_count: int
    topup_count: int
    byoc_deployments: int
    daily_breakdown: dict[str, dict[str, Any]] = field(default_factory=dict)
    alerts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["period_start"] = self.period_start.isoformat()
        data["period_end"] = self.period_end.isoformat()
        data["total_spend_usd"] = float(self.total_spend_usd)
        for breakdown in data["daily_breakdown"].values():
            breakdown["spend_usd"] = float(breakdown.get("spend_usd", Decimal(0)))
        return data


class UsageReporter:
    """Collects and reports tenant billing usage."""

    def __init__(self, project_id: str | None = None) -> None:
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self.database_url = os.environ["DATABASE_URL"] if "DATABASE_URL" in os.environ else settings.database_url
        self.redis_url = os.getenv("REDIS_URL", "")
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "")
        self.db_session: AsyncSession | None = None
        self.firestore_client: Any = None
        self._http = None

    async def __aenter__(self) -> Self:
        if firestore and self.project_id:
            try:
                self.firestore_client = firestore.Client(project=self.project_id)
                logger.info("Firestore client initialized")
            except Exception as e:
                logger.warning(f"Firestore client init failed: {e}")

        if AsyncSession and self.database_url:
            try:
                from sqlalchemy.ext.asyncio import create_async_engine
                engine = create_async_engine(
                    self.database_url,
                    prepared_statement_cache_size=0,
                    connect_args={"statement_cache_size": 0}
                )
                self.db_session = AsyncSession(engine)
                logger.info("Database session initialized")
            except Exception as e:
                logger.warning(f"Database session init failed: {e}")

        if self.redis_url:
            try:
                import httpx
                self._http = httpx.AsyncClient(timeout=10.0)
            except Exception as e:
                logger.warning(f"HTTP client init failed: {e}")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.db_session:
            try:
                await self.db_session.close()
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Silenced error: {e}")
        if self._http:
            try:
                await self._http.aclose()
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Silenced error: {e}")

    async def get_all_tenants(self) -> list[str]:
        """Retrieve all tenant IDs from Firestore tenants collection."""
        if not self.firestore_client:
            logger.warning("Firestore not available; returning empty tenant list")
            return []

        try:
            tenants_ref = self.firestore_client.collection("tenants")
            docs = tenants_ref.stream()
            tenant_ids = []
            async for doc in docs:
                data = doc.to_dict()
                tenant_id = data.get("tenant_id") or doc.id
                if tenant_id:
                    tenant_ids.append(tenant_id)
            return tenant_ids
        except Exception as e:
            logger.error(f"Failed to list tenants: {e}")
            return []

    async def get_tenant_usage_from_firestore(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> dict[str, Any]:
        """Read usage data from Firestore tenant usage subcollection."""
        usage: dict[str, Any] = {
            "api_calls": 0,
            "storage_mb": 0,
            "compute_minutes": 0,
            "tokens_input": 0,
            "tokens_output": 0,
        }

        if not self.firestore_client:
            return usage

        try:
            usage_ref = (
                self.firestore_client.collection("tenants")
                .document(tenant_id)
                .collection("usage")
            )

            docs = usage_ref.stream()
            async for doc in docs:
                data = doc.to_dict()
                current_period = data.get("current_period", {})
                if isinstance(current_period, dict):
                    usage["api_calls"] += current_period.get("api_calls", 0)
                    usage["storage_mb"] += current_period.get("storage_mb", 0)
                    usage["compute_minutes"] += current_period.get("compute_minutes", 0)
        except Exception as e:
            logger.error(f"Failed to read Firestore usage for {tenant_id}: {e}")

        return usage

    async def get_ledger_entries(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """Query transaction ledger for a tenant within a time window."""
        if not self.db_session or not select:
            logger.warning("Database not available for ledger query")
            return []

        try:
            result = await self.db_session.execute(
                select(TransactionLedgerEntry)
                .where(TransactionLedgerEntry.user_id == tenant_id)
                .where(TransactionLedgerEntry.timestamp >= start)
                .where(TransactionLedgerEntry.timestamp < end)
                .order_by(TransactionLedgerEntry.timestamp.asc())
            )
            entries = result.scalars().all()
            return [
                {
                    "transaction_id": entry.transaction_id,
                    "user_id": entry.user_id,
                    "amount_usd": float(entry.amount_usd),
                    "transaction_type": entry.transaction_type,
                    "description": entry.description,
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                }
                for entry in entries
            ]
        except Exception as e:
            logger.error(f"Failed to query ledger for {tenant_id}: {e}")
            return []

    def _build_daily_breakdown(
        self, entries: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        breakdown: dict[str, dict[str, Any]] = {}
        for entry in entries:
            ts = entry.get("timestamp")
            if not ts:
                continue
            day = ts[:10]
            if day not in breakdown:
                breakdown[day] = {
                    "spend_usd": Decimal(0),
                    "transactions": 0,
                    "topups": 0,
                    "byoc": 0,
                    "token_usage": 0,
                }
            bd = breakdown[day]
            bd["transactions"] += 1
            bd["spend_usd"] += Decimal(str(entry.get("amount_usd", 0)))
            t_type = entry.get("transaction_type", "")
            if t_type == "topup":
                bd["topups"] += 1
            elif t_type == "byoc_deployment":
                bd["byoc"] += 1
            elif t_type == "token_usage":
                bd["token_usage"] += 1
        return breakdown

    async def generate_tenant_report(
        self, tenant_id: str, start: datetime, end: datetime, dry_run: bool = False
    ) -> TenantUsage:
        """Generate a full usage report for a single tenant."""
        logger.info(f"Generating usage report for tenant: {tenant_id}")

        fs_usage = await self.get_tenant_usage_from_firestore(tenant_id, start, end)
        ledger_entries = await self.get_ledger_entries(tenant_id, start, end)

        total_spend = sum(Decimal(str(e.get("amount_usd", 0))) for e in ledger_entries)
        topup_count = sum(1 for e in ledger_entries if e.get("transaction_type") == "topup")
        byoc_count = sum(
            1 for e in ledger_entries if e.get("transaction_type") == "byoc_deployment"
        )
        token_in = sum(
            1 for e in ledger_entries if e.get("transaction_type") == "token_usage"
        )

        daily_breakdown = self._build_daily_breakdown(ledger_entries)

        alerts = []
        if total_spend > Decimal("100.0"):
            alerts.append(f"High spend: ${total_spend:.2f} exceeds $100 threshold")
        if topup_count > 10:
            alerts.append(f"Frequent topups: {topup_count} in period")
        if byoc_count > 5:
            alerts.append(f"High BYOC activity: {byoc_count} deployments")

        report = TenantUsage(
            tenant_id=tenant_id,
            period_start=start,
            period_end=end,
            total_spend_usd=total_spend,
            total_transactions=len(ledger_entries),
            token_input_count=token_in,
            token_output_count=fs_usage.get("tokens_output", 0),
            topup_count=topup_count,
            byoc_deployments=byoc_count,
            daily_breakdown=daily_breakdown,
            alerts=alerts,
        )

        if not dry_run and alerts and self.slack_webhook and self._http:
            await self._send_slack_alert(tenant_id, alerts)

        return report

    async def _send_slack_alert(self, tenant_id: str, alerts: list[str]) -> None:
        if not self._http or not self.slack_webhook:
            return
        message = (
            f"⚠️ *Billing Usage Alert — Tenant {tenant_id}*\n"
            + "\n".join(f"• {alert}" for alert in alerts)
        )
        try:
            await self._http.post(self.slack_webhook, json={"text": message})
        except Exception as e:
            logger.error(f"Slack alert failed: {e}")

    def write_json_report(self, report: TenantUsage, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"usage-{report.tenant_id}-{report.period_start.strftime('%Y%m')}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        logger.info(f"JSON report written: {path}")
        return path

    def write_markdown_report(self, report: TenantUsage, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"usage-{report.tenant_id}-{report.period_start.strftime('%Y%m')}.md"
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 📊 Usage Report — {report.tenant_id}\n\n")
            f.write(f"**Period:** {report.period_start.date()} to {report.period_end.date()}\n\n")
            f.write("## Summary\n\n")
            f.write("| Metric | Value |\n")
            f.write("| --- | --- |\n")
            f.write(f"| Total Spend | ${report.total_spend_usd:.4f} |\n")
            f.write(f"| Total Transactions | {report.total_transactions} |\n")
            f.write(f"| Token Usage Events | {report.token_input_count} |\n")
            f.write(f"| Top-ups | {report.topup_count} |\n")
            f.write(f"| BYOC Deployments | {report.byoc_deployments} |\n\n")

            if report.daily_breakdown:
                f.write("## Daily Breakdown\n\n")
                f.write("| Date | Spend | Txns | Top-ups | BYOC |\n")
                f.write("| --- | --- | --- | --- | --- |\n")
                f.writelines(f"| {day} | ${bd['spend_usd']:.4f} | {bd['transactions']} | "
                        f"{bd['topups']} | {bd['byoc']} |\n" for day, bd in sorted(report.daily_breakdown.items()))
                f.write("\n")

            if report.alerts:
                f.write("## Alerts\n\n")
                f.writelines(f"- ⚠️ {alert}\n" for alert in report.alerts)
        logger.info(f"Markdown report written: {path}")
        return path


def _parse_period(period: str) -> tuple[datetime, datetime]:
    try:
        if "-" in period:
            start = datetime.strptime(period, "%Y-%m").replace(tzinfo=UTC)
        else:
            start = datetime.strptime(period, "%Y%m").replace(tzinfo=UTC)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    except Exception as e:
        logger.error(f"Invalid period format '{period}'. Use YYYY-MM or YYYYMM: {e}")
        raise SystemExit(1)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI Billing Usage Reporter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--tenant-id", type=str, help="Specific tenant ID to report on")
    parser.add_argument("--scan-all", action="store_true", help="Report on all tenants")
    parser.add_argument("--period", type=str, required=True, help="Billing period (YYYY-MM or YYYYMM)")
    parser.add_argument("--format", type=str, choices=["json", "markdown", "both"], default="json")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/billing"))
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing reports")

    args = parser.parse_args()

    if not args.tenant_id and not args.scan_all:
        parser.error("Either --tenant-id or --scan-all is required")

    start, end = _parse_period(args.period)

    async with UsageReporter() as reporter:
        tenant_ids = (
            [args.tenant_id] if args.tenant_id else await reporter.get_all_tenants()
        )

        if not tenant_ids:
            logger.warning("No tenants found")
            return 0

        reports: list[TenantUsage] = []
        for tenant_id in tenant_ids:
            try:
                report = await reporter.generate_tenant_report(
                    tenant_id, start, end, dry_run=args.dry_run
                )
                reports.append(report)
                logger.info(
                    f"Tenant {tenant_id}: spend=${report.total_spend_usd:.4f}, "
                    f"txns={report.total_transactions}"
                )
            except Exception as e:
                logger.error(f"Failed to generate report for {tenant_id}: {e}")

        if args.dry_run:
            logger.info("Dry-run mode — skipping report writes")
            return 0

        for report in reports:
            if args.format in ("json", "both"):
                reporter.write_json_report(report, args.output_dir)
            if args.format in ("markdown", "both"):
                reporter.write_markdown_report(report, args.output_dir)

    total_spend = sum(r.total_spend_usd for r in reports)
    logger.success(f"✅ Reports generated for {len(reports)} tenant(s). Total spend: ${total_spend:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
