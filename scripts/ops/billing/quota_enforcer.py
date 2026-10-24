#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  SUPREMEAI — Billing Quota Enforcer                                        ║
║  Hard Quota Enforcement | Tenant Limits | Auto-Suspend                     ║
║  Priority: 🔴 High                                                         ║
║  Architecture: FastAPI + Firestore + SQLAlchemy + Redis                    ║
╚══════════════════════════════════════════════════════════════════════════════╝

Enforces hard quotas on tenants based on pricing tiers and usage data.
When a tenant exceeds their quota, the script can:
  • Mark the tenant as suspended in Firestore
  • Send alerts via Slack / Discord
  • Log enforcement actions to the transaction ledger

Usage:
    python quota_enforcer.py --enforce-all --dry-run
    python quota_enforcer.py --tenant-id <tenant_id> --notify
    python quota_enforcer.py --enforce-all --grace-hours 24

Environment:
    GOOGLE_CLOUD_PROJECT      — GCP project identifier
    DATABASE_URL              — SQLAlchemy database URL (for wallet queries)
    REDIS_URL                 — Redis URL for distributed locking (optional)
    SLACK_WEBHOOK_URL         — Alert channel (optional)
    DISCORD_WEBHOOK_URL       — Alert channel (optional)
    PRICING_TIERS_PATH        — Path to pricing_tiers.json (default: backend/config/pricing_tiers.json)
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
from sqlalchemy import select
from typing_extensions import Self

try:
    from models.wallet import TransactionLedgerEntry, UserWallet
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
    from models.wallet import TransactionLedgerEntry, UserWallet


@dataclass
class QuotaStatus:
    tenant_id: str
    tier: str
    monthly_allowance_usd: Decimal
    current_usage_usd: Decimal
    remaining_usd: Decimal
    utilization_pct: float
    status: str
    action: str = ""


@dataclass
class EnforcementReport:
    report_id: str = ""
    generated_at: str = ""
    scanned_count: int = 0
    within_quota: int = 0
    over_quota: int = 0
    suspended: int = 0
    quota_statuses: list[QuotaStatus] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.report_id:
            import hashlib
            import time

            self.report_id = hashlib.sha256(f"{time.time()}".encode()).hexdigest()[:12]
        if not self.generated_at:
            self.generated_at = datetime.now(UTC).isoformat()


class QuotaEnforcer:
    """Enforces hard quotas on tenant billing accounts."""

    def __init__(self, pricing_path: str | None = None) -> None:
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        self.database_url = settings.database_url
        self.redis_url = os.getenv("REDIS_URL", "")
        self.slack_webhook = os.getenv("SLACK_WEBHOOK_URL", "")
        self.discord_webhook = os.getenv("DISCORD_WEBHOOK_URL", "")

        if pricing_path:
            self.pricing_path = Path(pricing_path)
        else:
            default = Path(__file__).resolve().parents[3] / "backend" / "config" / "pricing_tiers.json"
            self.pricing_path = default

        self.pricing_tiers = self._load_pricing_tiers()
        self.db_session: Any = None
        self.firestore_client: Any = None
        self._http = None
        self._redis_lock: Any = None

    def _load_pricing_tiers(self) -> dict[str, Any]:
        if not self.pricing_path.exists():
            logger.warning(f"Pricing tiers file not found: {self.pricing_path}")
            return {}
        try:
            with open(self.pricing_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load pricing tiers: {e}")
            return {}

    async def __aenter__(self) -> Self:
        if self.project_id:
            try:
                from google.cloud import firestore
                self.firestore_client = firestore.Client(project=self.project_id)
                logger.info("Firestore client initialized")
            except Exception as e:
                logger.warning(f"Firestore init failed: {e}")

        if self.database_url:
            try:
                from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
                engine = create_async_engine(
                    self.database_url,
                    prepared_statement_cache_size=0,
                    connect_args={"statement_cache_size": 0}
                )
                self.db_session = AsyncSession(engine)
                logger.info("Database session initialized")
            except Exception as e:
                logger.warning(f"Database init failed: {e}")

        if self.redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis_lock = aioredis.from_url(self.redis_url, socket_connect_timeout=5)
                await self._redis_lock.ping()
                logger.info("Redis lock client initialized")
            except Exception as e:
                logger.warning(f"Redis init failed: {e}")

        if self.slack_webhook or self.discord_webhook:
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
        if self._redis_lock:
            try:
                await self._redis_lock.aclose()
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Silenced error: {e}")

    async def get_all_tenant_ids(self) -> list[str]:
        if not self.firestore_client:
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

    async def get_wallet(self, tenant_id: str) -> dict[str, Any] | None:
        if not self.db_session:
            return None

        try:
            result = await self.db_session.execute(
                select(UserWallet).where(UserWallet.user_id == tenant_id)
            )
            wallet = result.scalars().first()
            if not wallet:
                return None
            return {
                "user_id": wallet.user_id,
                "balance_usd": wallet.balance_usd,
                "monthly_allowance_usd": wallet.monthly_allowance_usd,
                "version": wallet.version,
            }
        except Exception as e:
            logger.error(f"Wallet query failed for {tenant_id}: {e}")
            return None

    async def get_tenant_tier(self, tenant_id: str) -> str:
        if not self.firestore_client:
            return "free"

        try:
            doc = (
                self.firestore_client.collection("tenants")
                .document(tenant_id)
                .collection("limits")
                .document("default")
                .get()
            )
            if doc.exists:
                data = doc.to_dict()
                tier = data.get("billing_tier") or data.get("tier")
                if tier:
                    return tier
        except Exception as e:
            logger.error(f"Failed to read tenant tier for {tenant_id}: {e}")

        return "free"

    def get_tier_allowance(self, tier: str) -> Decimal:
        tiers = self.pricing_tiers.get("tiers", {})
        tier_data = tiers.get(tier, tiers.get("free", {}))
        allowance = tier_data.get("monthly_credits_usd", 0.0)
        return Decimal(str(allowance))

    async def get_current_usage_usd(self, tenant_id: str) -> Decimal:
        if not self.db_session:
            return Decimal(0)

        try:
            now = datetime.now(UTC)
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            result = await self.db_session.execute(
                select(TransactionLedgerEntry)
                .where(TransactionLedgerEntry.user_id == tenant_id)
                .where(TransactionLedgerEntry.timestamp >= month_start)
            )
            entries = result.scalars().all()
            total = sum((entry.amount_usd for entry in entries), Decimal(0))
            return total
        except Exception as e:
            logger.error(f"Usage query failed for {tenant_id}: {e}")
            return Decimal(0)

    async def check_tenant_quota(self, tenant_id: str) -> QuotaStatus | None:
        wallet = await self.get_wallet(tenant_id)
        if not wallet:
            return None

        tier = await self.get_tenant_tier(tenant_id)
        allowance = self.get_tier_allowance(tier)
        current_usage = await self.get_current_usage_usd(tenant_id)
        remaining = max(allowance - current_usage, Decimal(0))
        utilization = float(current_usage / allowance * 100) if allowance > 0 else 0.0

        if utilization >= 100:
            status = "exceeded"
            action = "suspend"
        elif utilization >= 80:
            status = "warning"
            action = "notify"
        else:
            status = "ok"
            action = "none"

        return QuotaStatus(
            tenant_id=tenant_id,
            tier=tier,
            monthly_allowance_usd=allowance,
            current_usage_usd=current_usage,
            remaining_usd=remaining,
            utilization_pct=utilization,
            status=status,
            action=action,
        )

    async def suspend_tenant(self, tenant_id: str, dry_run: bool = False) -> bool:
        if not self.firestore_client:
            logger.warning(f"Cannot suspend {tenant_id}: Firestore not available")
            return False

        try:
            tenant_ref = self.firestore_client.collection("tenants").document(tenant_id)
            if dry_run:
                logger.info(f"[DRY-RUN] Would suspend tenant {tenant_id}")
                return True

            await tenant_ref.update({"status": "suspended", "suspended_at": datetime.now(UTC).isoformat()})
            logger.info(f"Tenant {tenant_id} suspended")
            return True
        except Exception as e:
            logger.error(f"Failed to suspend tenant {tenant_id}: {e}")
            return False

    async def enforce_all(
        self, grace_hours: int = 0, dry_run: bool = False, notify: bool = False
    ) -> EnforcementReport:
        tenant_ids = await self.get_all_tenant_ids()
        report = EnforcementReport(scanned_count=len(tenant_ids))

        for tenant_id in tenant_ids:
            try:
                status = await self.check_tenant_quota(tenant_id)
                if not status:
                    continue

                report.quota_statuses.append(status)

                if status.status == "exceeded":
                    report.over_quota += 1
                    if not dry_run:
                        await self.suspend_tenant(tenant_id, dry_run=False)
                        report.suspended += 1
                    else:
                        logger.info(f"[DRY-RUN] Would suspend {tenant_id} (over quota)")
                        report.suspended += 1

                    if notify:
                        await self._send_quota_alert(status)

                elif status.status == "warning":
                    if notify:
                        await self._send_quota_alert(status)

                else:
                    report.within_quota += 1

            except Exception as e:
                logger.error(f"Quota enforcement failed for {tenant_id}: {e}")

        return report

    async def _send_quota_alert(self, status: QuotaStatus) -> None:
        if not self._http:
            return

        message = (
            f"🚨 *Quota Alert — {status.tenant_id}*\n"
            f"Tier: {status.tier} | Status: {status.status.upper()}\n"
            f"Usage: ${status.current_usage_usd:.4f} / ${status.monthly_allowance_usd:.4f} "
            f"({status.utilization_pct:.1f}%)\n"
            f"Action: {status.action}"
        )

        for webhook_url, label in [
            (self.slack_webhook, "Slack"),
            (self.discord_webhook, "Discord"),
        ]:
            if not webhook_url:
                continue
            try:
                payload = {"text": message} if label == "Slack" else {"content": message}
                await self._http.post(webhook_url, json=payload)
                logger.info(f"Quota alert sent to {label} for {status.tenant_id}")
            except Exception as e:
                logger.error(f"{label} alert failed for {status.tenant_id}: {e}")

    def write_report(self, report: EnforcementReport, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"quota-enforcement-{report.report_id}.json"
        data = asdict(report)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        logger.info(f"Enforcement report written: {path}")
        return path


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="SupremeAI Billing Quota Enforcer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--tenant-id", type=str, help="Check/enforce quota for specific tenant")
    parser.add_argument("--enforce-all", action="store_true", help="Enforce quotas on all tenants")
    parser.add_argument("--grace-hours", type=int, default=0, help="Grace period before suspension")
    parser.add_argument("--pricing-path", type=str, help="Path to pricing_tiers.json")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without making changes")
    parser.add_argument("--notify", action="store_true", help="Send alerts for warnings/exceedances")
    parser.add_argument("--output-dir", type=Path, default=Path("reports/billing"))

    args = parser.parse_args()

    if not args.tenant_id and not args.enforce_all:
        parser.error("Either --tenant-id or --enforce-all is required")

    async with QuotaEnforcer(pricing_path=args.pricing_path) as enforcer:
        if args.enforce_all:
            report = await enforcer.enforce_all(
                grace_hours=args.grace_hours,
                dry_run=args.dry_run,
                notify=args.notify,
            )
            enforcer.write_report(report, args.output_dir)
            logger.info(
                f"Enforcement complete: {report.over_quota} over quota, "
                f"{report.suspended} suspended, {report.within_quota} within quota"
            )
            if report.over_quota > 0:
                logger.error(f"❌ {report.over_quota} tenants over quota")
                return 1

        elif args.tenant_id:
            status = await enforcer.check_tenant_quota(args.tenant_id)
            if not status:
                logger.error(f"Tenant {args.tenant_id} not found or no wallet")
                return 1

            logger.info(
                f"Tenant {status.tenant_id}: tier={status.tier}, "
                f"usage=${status.current_usage_usd:.4f}/${status.monthly_allowance_usd:.4f} "
                f"({status.utilization_pct:.1f}%), status={status.status}"
            )

            if status.status == "exceeded" and not args.dry_run:
                await enforcer.suspend_tenant(args.tenant_id, dry_run=False)
                logger.warning(f"Tenant {args.tenant_id} suspended due to quota exceedance")
                return 1
            elif status.status == "exceeded" and args.dry_run:
                logger.warning(f"[DRY-RUN] Would suspend tenant {args.tenant_id}")

    logger.success("✅ Quota enforcement completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
