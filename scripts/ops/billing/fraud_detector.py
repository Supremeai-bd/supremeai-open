#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  SUPREMEAI — Billing Fraud Detector                                        ║
║  Billing Fraud Detection | Ledger Analysis | Anomaly Scoring               ║
║  Priority: 🔴 High                                                         ║
║  Architecture: FastAPI + SQLAlchemy + Redis + Firestore                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Scans the transaction ledger and usage patterns to detect billing fraud:
  • Rapid micro-transaction bursts
  • Unusual spend spikes vs. historical baseline
  • Repeated failed top-ups
  • Same user / device patterns across multiple accounts (if IP data available)
  • BYOC abuse patterns

Usage:
    python fraud_detector.py --scan-all --threshold 3.0
    python fraud_detector.py --user-id <user_id> --days 7
    python fraud_detector.py --scan-all --alert --output-dir reports/billing

Environment:
    DATABASE_URL              — SQLAlchemy database URL (for ledger queries)
    GOOGLE_CLOUD_PROJECT      — GCP project identifier (optional)
    SLACK_WEBHOOK_URL         — Alert channel (optional)
    FRAUD_SPEND_THRESHOLD     — Default anomaly sigma threshold (default: 3.0)
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
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy import select
from typing_extensions import Self

try:
    from models.wallet import TransactionLedgerEntry, UserWallet
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
    from models.wallet import TransactionLedgerEntry, UserWallet


@dataclass
class FraudAlert:
    alert_id: str
    tenant_id: str
    alert_type: str
    severity: str
    description: str
    score: float
    evidence: dict[str, Any] = field(default_factory=dict)
    detected_at: str = ""

    def __post_init__(self) -> None:
        if not self.detected_at:
            self.detected_at = datetime.now(UTC).isoformat()


@dataclass
class FraudReport:
    report_id: str = ""
    generated_at: str = ""
    scan_window_days: int = 30
    threshold: float = 3.0
    alerts: list[FraudAlert] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.report_id:
            import hashlib
            import time

            self.report_id = hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:12]
        if not self.generated_at:
            self.generated_at = datetime.now(UTC).isoformat()


class FraudDetector:
    """Analyzes billing transactions for fraud indicators."""

    def __init__(self, threshold: float = 3.0) -> None:
        self.database_url = os.environ["DATABASE_URL"] if "DATABASE_URL" in os.environ else settings.database_url
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "")
        self.fraud_spend_threshold = float(os.getenv("FRAUD_SPEND_THRESHOLD", str(threshold)))
        self.db_session: Any = None
        self._http = None

    async def __aenter__(self) -> Self:
        if self.database_url:
            try:
                from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
                engine = create_async_engine(
                    self.database_url,
                    prepared_statement_cache_size=0,
                    connect_args={"statement_cache_size": 0}
                )
                self.db_session = AsyncSession(engine)
                logger.info("Database session initialized for fraud detection")
            except Exception as e:
                logger.warning(f"Database session init failed: {e}")

        if self.slack_webhook:
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

    async def get_tenant_ids(self) -> list[str]:
        if not self.db_session:
            return []

        try:
            result = await self.db_session.execute(select(UserWallet.user_id))
            return [row[0] for row in result.fetchall()]
        except Exception as e:
            logger.error(f"Failed to fetch tenant list: {e}")
            return []

    async def get_ledger_entries(
        self, tenant_id: str, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        if not self.db_session:
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
            logger.error(f"Ledger query failed for {tenant_id}: {e}")
            return []

    def _detect_rapid_microtransactions(
        self, entries: list[dict[str, Any]], tenant_id: str
    ) -> FraudAlert | None:
        token_entries = [e for e in entries if e.get("transaction_type") == "token_usage"]
        if len(token_entries) < 20:
            return None

        timestamps = []
        for e in token_entries:
            ts = e.get("timestamp")
            if ts:
                try:
                    timestamps.append(datetime.fromisoformat(ts.replace("Z", "+00:00")))
                except Exception:
                    continue

        timestamps.sort()
        burst_count = 0
        for i in range(len(timestamps) - 9):
            window = timestamps[i + 9] - timestamps[i]
            if window <= timedelta(minutes=5):
                burst_count += 1

        if burst_count >= 3:
            return FraudAlert(
                alert_id=f"burst-{tenant_id[:8]}",
                tenant_id=tenant_id,
                alert_type="rapid_microtransactions",
                severity="high",
                description=f"Detected {burst_count} micro-transaction bursts (10+ txns in <5 min)",
                score=float(burst_count),
                evidence={"burst_count": burst_count, "total_token_txns": len(token_entries)},
            )
        return None

    def _detect_spend_spike(
        self, entries: list[dict[str, Any]], tenant_id: str
    ) -> FraudAlert | None:
        daily_spend: dict[str, Decimal] = {}
        for e in entries:
            ts = e.get("timestamp", "")[:10]
            if not ts:
                continue
            daily_spend[ts] = daily_spend.get(ts, Decimal(0)) + Decimal(str(e.get("amount_usd", 0)))

        if len(daily_spend) < 2:
            return None

        values = list(daily_spend.values())
        avg_spend = sum(values) / len(values)
        max_spend = max(values)

        if avg_spend == 0:
            return None

        z_score = float((max_spend - avg_spend) / avg_spend)
        if z_score > self.fraud_spend_threshold:
            return FraudAlert(
                alert_id=f"spike-{tenant_id[:8]}",
                tenant_id=tenant_id,
                alert_type="spend_spike",
                severity="medium",
                description=f"Spend spike detected (z-score {z_score:.2f}, threshold {self.fraud_spend_threshold})",
                score=z_score,
                evidence={"avg_daily_spend": float(avg_spend), "max_daily_spend": float(max_spend)},
            )
        return None

    def _detect_failed_topups(
        self, entries: list[dict[str, Any]], tenant_id: str
    ) -> FraudAlert | None:
        topup_entries = [e for e in entries if e.get("transaction_type") == "topup"]
        failed_count = sum(1 for e in topup_entries if "fail" in e.get("description", "").lower())
        if failed_count >= 5:
            return FraudAlert(
                alert_id=f"failtopup-{tenant_id[:8]}",
                tenant_id=tenant_id,
                alert_type="repeated_failed_topups",
                severity="high",
                description=f"Multiple failed top-up attempts: {failed_count}",
                score=float(failed_count),
                evidence={"failed_topups": failed_count, "total_topups": len(topup_entries)},
            )
        return None

    def _detect_byoc_abuse(
        self, entries: list[dict[str, Any]], tenant_id: str
    ) -> FraudAlert | None:
        byoc_entries = [e for e in entries if e.get("transaction_type") == "byoc_deployment"]
        byoc_count = len(byoc_entries)
        if byoc_count > 20:
            total_byoc_spend = sum(Decimal(str(e.get("amount_usd", 0))) for e in byoc_entries)
            return FraudAlert(
                alert_id=f"byoc-{tenant_id[:8]}",
                tenant_id=tenant_id,
                alert_type="byoc_abuse",
                severity="medium",
                description=f"Unusually high BYOC deployment count: {byoc_count}",
                score=float(byoc_count),
                evidence={"byoc_count": byoc_count, "total_byoc_spend": float(total_byoc_spend)},
            )
        return None

    async def scan_tenant(
        self, tenant_id: str, days: int = 30
    ) -> list[FraudAlert]:
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        entries = await self.get_ledger_entries(tenant_id, start, end)

        if not entries:
            return []

        alerts = []
        for detector in [
            self._detect_rapid_microtransactions,
            self._detect_spend_spike,
            self._detect_failed_topups,
            self._detect_byoc_abuse,
        ]:
            alert = detector(entries, tenant_id)
            if alert:
                alerts.append(alert)

        return alerts

    async def scan_all(self, days: int = 30) -> FraudReport:
        tenant_ids = await self.get_tenant_ids()
        report = FraudReport(scan_window_days=days)
        all_alerts: list[FraudAlert] = []

        for tenant_id in tenant_ids:
            try:
                alerts = await self.scan_tenant(tenant_id, days)
                all_alerts.extend(alerts)
            except Exception as e:
                logger.error(f"Fraud scan failed for {tenant_id}: {e}")

        report.alerts = all_alerts
        report.summary = {
            "total_tenants_scanned": len(tenant_ids),
            "total_alerts": len(all_alerts),
            "high_severity": sum(1 for a in all_alerts if a.severity == "high"),
            "medium_severity": sum(1 for a in all_alerts if a.severity == "medium"),
            "low_severity": sum(1 for a in all_alerts if a.severity == "low"),
        }
        return report

    async def send_alerts(self, report: FraudReport) -> None:
        if not self._http or not self.slack_webhook:
            return
        if not report.alerts:
            return

        lines = [
            "🚨 *SupremeAI Fraud Detection Report*",
            f"Scan Window: {report.scan_window_days}d | Threshold: {report.threshold}σ",
            f"Total Alerts: {len(report.alerts)}",
            "",
        ]
        for alert in report.alerts[:20]:
            lines.append(
                f"• [{alert.severity.upper()}] {alert.tenant_id}: {alert.description}"
            )

        if len(report.alerts) > 20:
            lines.append(f"... and {len(report.alerts) - 20} more alerts")

        message = "\n".join(lines)
        try:
            await self._http.post(self.slack_webhook, json={"text": message})
            logger.success("Fraud alerts sent to Slack")
        except Exception as e:
            logger.error(f"Slack alert failed: {e}")

    def write_report(self, report: FraudReport, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"fraud-report-{report.report_id}.json"
        data = asdict(report)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Fraud report written: {path}")
        return path


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI Billing Fraud Detector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--user-id", type=str, help="Scan specific user/tenant")
    parser.add_argument("--scan-all", action="store_true", help="Scan all tenants")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days")
    parser.add_argument("--threshold", type=float, default=3.0, help="Z-score threshold for anomalies")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/billing"))
    parser.add_argument("--alert", action="store_true", help="Send alerts on detection")

    args = parser.parse_args()

    if not args.user_id and not args.scan_all:
        parser.error("Either --user-id or --scan-all is required")

    async with FraudDetector(threshold=args.threshold) as detector:
        if args.scan_all:
            report = await detector.scan_all(days=args.days)
            logger.info(
                f"Scan complete: {report.summary.get('total_alerts', 0)} alerts across "
                f"{report.summary.get('total_tenants_scanned', 0)} tenants"
            )
            if args.alert:
                await detector.send_alerts(report)
            detector.write_report(report, args.output_dir)

            if report.summary.get("high_severity", 0) > 0:
                logger.error(f"❌ {report.summary['high_severity']} HIGH severity alerts detected")
                return 1

        elif args.user_id:
            alerts = await detector.scan_tenant(args.user_id, days=args.days)
            if alerts:
                logger.warning(f"⚠️ {len(alerts)} fraud indicators for {args.user_id}")
                for alert in alerts:
                    logger.warning(
                        f"  [{alert.severity}] {alert.alert_type}: {alert.description} (score={alert.score:.2f})"
                    )
                if args.alert:
                    fake_report = FraudReport(
                        scan_window_days=args.days,
                        threshold=args.threshold,
                        alerts=alerts,
                    )
                    await detector.send_alerts(fake_report)
                return 1 if any(a.severity == "high" for a in alerts) else 0
            else:
                logger.success(f"✅ No fraud indicators for {args.user_id}")

    logger.success("✅ Fraud detection completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
