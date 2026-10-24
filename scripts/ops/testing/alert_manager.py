#!/usr/bin/env python3
"""
SupremeAI 2.0 — Alert Manager 🚨
=================================
Purpose: Multi-channel alerting system supporting SMS (Twilio), Email (SMTP/SendGrid),
         Discord webhooks, Slack, and PagerDuty. With alert deduplication,
         severity-based routing, and Bengali/English bilingual messages.
Priority: 🔴 HIGH
Author: SupremeAI Architecture Team
Date: July 20, 2026

বাংলা: মাল্টি-চ্যানেল এলার্টিং সিস্টেম — SMS, ইমেইল, ডিসকর্ড, স্ল্যাক, পেজারডিউটি
সহ এলার্ট ডিডুপ্লিকেশন, সেভেরিটি-বেজড রাউটিং, বাংলা/ইংরেজি বাইলিংগুয়াল মেসেজিং।
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any

import requests
from loguru import logger

# ── Path Setup ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from backend.core.config import settings
except ImportError:
    settings = None  # type: ignore[assignment]

# ── Configuration ───────────────────────────────────────────
ALERT_COOLDOWN_SECONDS = int(os.getenv("ALERT_COOLDOWN_SECONDS", "300"))
ALERT_DEDUP_WINDOW = int(os.getenv("ALERT_DEDUP_WINDOW", "3600"))
ALERT_HISTORY_FILE = Path(__file__).parent / ".alert_history.json"
ALERT_STATE_FILE = Path(__file__).parent / ".alert_state.json"

REQUEST_TIMEOUT = int(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))


class AlertSeverity(StrEnum):
    CRITICAL = "critical"   # P0 — Immediate action required
    WARNING = "warning"     # P1 — Action needed soon
    INFO = "info"           # P2 — Awareness
    DEBUG = "debug"         # P3 — Verbose logging


class AlertChannel(StrEnum):
    DISCORD = "discord"
    SLACK = "slack"
    EMAIL = "email"
    SMS = "sms"
    PAGERDUTY = "pagerduty"
    WEBHOOK = "webhook"


@dataclass
class Alert:
    """একটি এলার্টের সম্পূর্ণ রেপ্রেজেন্টেশন।"""
    id: str
    timestamp: str
    severity: AlertSeverity
    channel: AlertChannel
    title: str
    message: str
    message_bn: str  # Bengali translation
    source: str
    metric: str
    value: float
    threshold: float
    recipients: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: str | None = None
    sent_count: int = 0
    last_sent: str | None = None


@dataclass
class ChannelConfig:
    """Channel-specific configuration."""
    enabled: bool = True
    min_severity: AlertSeverity = AlertSeverity.INFO
    rate_limit_per_minute: int = 30
    recipients: list[str] = field(default_factory=list)
    credentials: dict[str, str] = field(default_factory=dict)


# ── Alert Deduplication ─────────────────────────────────────
class AlertDeduplicator:
    """Prevents alert spam by deduplicating similar alerts within a time window."""

    def __init__(self, window_seconds: int = ALERT_DEDUP_WINDOW):
        self.window = window_seconds
        self._recent: dict[str, float] = {}
        self._lock = asyncio.Lock()

    def _hash(self, alert: Alert) -> str:
        content = f"{alert.severity}:{alert.source}:{alert.metric}:{alert.title}:{alert.message[:50]}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def should_send(self, alert: Alert) -> bool:
        h = self._hash(alert)
        now = time.time()
        async with self._lock:
            last = self._recent.get(h, 0)
            if now - last < self.window:
                logger.info(f"⏳ Alert deduplicated: {alert.title} (hash={h})")
                return False
            self._recent[h] = now
            # Cleanup old entries
            self._recent = {k: v for k, v in self._recent.items() if now - v < self.window}
            return True


# ── Channel Providers ───────────────────────────────────────
class DiscordProvider:
    """Discord webhook alert provider with rich embeds."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, alert: Alert) -> bool:
        if not self.webhook_url:
            logger.warning("❌ Discord webhook URL not configured")
            return False

        color_map = {
            AlertSeverity.CRITICAL: 0xFF0000,   # Red
            AlertSeverity.WARNING: 0xFFA500,    # Orange
            AlertSeverity.INFO: 0x58A6FF,       # Blue
            AlertSeverity.DEBUG: 0x808080,       # Gray
        }

        embed = {
            "title": f"🚨 {alert.severity.upper()}: {alert.title}",
            "description": alert.message,
            "color": color_map.get(alert.severity, 0x808080),
            "fields": [
                {"name": "☁️ Source", "value": alert.source, "inline": True},
                {"name": "📊 Metric", "value": alert.metric, "inline": True},
                {"name": "🔢 Value", "value": f"{alert.value:.2f}", "inline": True},
                {"name": "🎯 Threshold", "value": f"{alert.threshold:.2f}", "inline": True},
                {"name": "📝 Bengali", "value": alert.message_bn[:1024], "inline": False},
            ],
            "footer": {"text": f"SupremeAI Alert Manager | ID: {alert.id[:8]}"},
            "timestamp": alert.timestamp,
        }

        payload = {
            "embeds": [embed],
            "content": f"<@&admin> **{alert.severity.upper()}** — `{alert.source}`" if alert.severity in (AlertSeverity.CRITICAL, AlertSeverity.WARNING) else None,
        }

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            logger.info(f"✅ Discord alert sent: {alert.title}")
            return True
        except requests.RequestException as e:
            logger.error(f"❌ Discord alert failed: {e}")
            return False


class SlackProvider:
    """Slack webhook alert provider."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send(self, alert: Alert) -> bool:
        if not self.webhook_url:
            return False

        color = {
            AlertSeverity.CRITICAL: "#FF0000",
            AlertSeverity.WARNING: "#FFA500",
            AlertSeverity.INFO: "#58A6FF",
            AlertSeverity.DEBUG: "#808080",
        }.get(alert.severity, "#808080")

        payload = {
            "attachments": [{
                "color": color,
                "title": f"🚨 {alert.severity.upper()}: {alert.title}",
                "text": alert.message,
                "fields": [
                    {"title": "Source", "value": alert.source, "short": True},
                    {"title": "Metric", "value": alert.metric, "short": True},
                    {"title": "Value", "value": f"{alert.value:.2f}", "short": True},
                    {"title": "Threshold", "value": f"{alert.threshold:.2f}", "short": True},
                ],
                "footer": f"SupremeAI Alert Manager | {alert.id[:8]}",
                "ts": int(time.time()),
            }]
        }

        try:
            resp = requests.post(self.webhook_url, json=payload, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            logger.info(f"✅ Slack alert sent: {alert.title}")
            return True
        except requests.RequestException as e:
            logger.error(f"❌ Slack alert failed: {e}")
            return False


class EmailProvider:
    """Email alert provider via SMTP or SendGrid API."""

    def __init__(self, smtp_host: str = "", smtp_port: int = 587,
                 username: str = "", password: str = "",
                 from_addr: str = "", sendgrid_api_key: str = ""):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr or "alerts@supremeai.io"
        self.sendgrid_api_key = sendgrid_api_key

    async def send(self, alert: Alert) -> bool:
        if self.sendgrid_api_key:
            return await self._send_sendgrid(alert)
        elif self.smtp_host:
            return await self._send_smtp(alert)
        else:
            logger.warning("❌ No email credentials configured")
            return False

    async def _send_sendgrid(self, alert: Alert) -> bool:
        payload = {
            "personalizations": [{"to": [{"email": r} for r in alert.recipients]}],
            "from": {"email": self.from_addr},
            "subject": f"[{alert.severity.upper()}] SupremeAI: {alert.title}",
            "content": [
                {"type": "text/plain", "value": f"{alert.message}\n\n---\nবাংলা:\n{alert.message_bn}\n\nAlert ID: {alert.id}"},
                {"type": "text/html", "value": self._html_body(alert)},
            ],
        }
        try:
            resp = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {self.sendgrid_api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info(f"✅ SendGrid alert sent to {len(alert.recipients)} recipients")
            return True
        except requests.RequestException as e:
            logger.error(f"❌ SendGrid alert failed: {e}")
            return False

    async def _send_smtp(self, alert: Alert) -> bool:
        try:
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            import aiosmtplib

            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[{alert.severity.upper()}] SupremeAI: {alert.title}"
            msg["From"] = self.from_addr
            msg["To"] = ", ".join(alert.recipients)

            msg.attach(MIMEText(alert.message, "plain"))
            msg.attach(MIMEText(self._html_body(alert), "html"))

            await aiosmtplib.send(
                msg,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.username,
                password=self.password,
                start_tls=True,
            )
            logger.info(f"✅ SMTP alert sent to {len(alert.recipients)} recipients")
            return True
        except Exception as e:
            logger.error(f"❌ SMTP alert failed: {e}")
            return False

    def _html_body(self, alert: Alert) -> str:
        color = {"critical": "#FF0000", "warning": "#FFA500", "info": "#58A6FF", "debug": "#808080"}.get(alert.severity, "#808080")
        return f"""
        <html><body style="font-family:Segoe UI,sans-serif;background:#0d1117;color:#c9d1d9;padding:20px;">
        <div style="max-width:600px;margin:0 auto;border:1px solid #30363d;border-radius:12px;overflow:hidden;">
        <div style="background:{color};padding:16px;color:white;font-size:1.2rem;font-weight:bold;">
        🚨 {alert.severity.upper()}: {alert.title}
        </div>
        <div style="padding:20px;">
        <p><strong>Source:</strong> {alert.source}</p>
        <p><strong>Metric:</strong> {alert.metric}</p>
        <p><strong>Value:</strong> {alert.value:.2f} (Threshold: {alert.threshold:.2f})</p>
        <hr style="border-color:#30363d;">
        <p>{alert.message}</p>
        <hr style="border-color:#30363d;">
        <p style="color:#8b949e;"><strong>বাংলা:</strong><br>{alert.message_bn}</p>
        </div>
        <div style="background:#161b22;padding:12px;font-size:0.8rem;color:#8b949e;text-align:center;">
        SupremeAI Alert Manager | ID: {alert.id}
        </div></div></body></html>
        """


class SMSProvider:
    """SMS alert provider via Twilio."""

    def __init__(self, account_sid: str = "", auth_token: str = "", from_number: str = ""):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.from_number = from_number

    async def send(self, alert: Alert) -> bool:
        if not all([self.account_sid, self.auth_token, self.from_number]):
            logger.warning("❌ Twilio credentials not configured")
            return False

        # Only send SMS for CRITICAL alerts
        if alert.severity != AlertSeverity.CRITICAL:
            logger.info(f"⏭️ SMS skipped for non-critical alert: {alert.title}")
            return True  # Not a failure, just skipped

        body = f"🚨 SUPREMEAI CRITICAL: {alert.title[:40]} | {alert.source}:{alert.metric}={alert.value:.1f} | {alert.message_bn[:60]}"

        try:
            from twilio.rest import Client
            client = Client(self.account_sid, self.auth_token)

            for recipient in alert.recipients:
                message = client.messages.create(
                    body=body,
                    from_=self.from_number,
                    to=recipient,
                )
                logger.info(f"✅ SMS sent to {recipient}: {message.sid}")

            return True
        except Exception as e:
            logger.error(f"❌ Twilio SMS failed: {e}")
            return False


class PagerDutyProvider:
    """PagerDuty incident provider."""

    def __init__(self, routing_key: str = "", service_key: str = ""):
        self.routing_key = routing_key
        self.service_key = service_key

    async def send(self, alert: Alert) -> bool:
        if not self.routing_key:
            logger.warning("❌ PagerDuty routing key not configured")
            return False

        # Only trigger PagerDuty for CRITICAL
        if alert.severity != AlertSeverity.CRITICAL:
            return True

        payload = {
            "routing_key": self.routing_key,
            "event_action": "trigger",
            "dedup_key": alert.id,
            "payload": {
                "summary": f"[SupremeAI] {alert.title}",
                "severity": "critical",
                "source": alert.source,
                "custom_details": {
                    "metric": alert.metric,
                    "value": alert.value,
                    "threshold": alert.threshold,
                    "message": alert.message,
                    "message_bn": alert.message_bn,
                },
            },
        }

        try:
            resp = requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            logger.info(f"✅ PagerDuty incident triggered: {alert.title}")
            return True
        except requests.RequestException as e:
            logger.error(f"❌ PagerDuty trigger failed: {e}")
            return False


class WebhookProvider:
    """Generic webhook provider for custom integrations."""

    def __init__(self, url: str = "", headers: dict[str, str] | None = None):
        self.url = url
        self.headers = headers or {}

    async def send(self, alert: Alert) -> bool:
        if not self.url:
            return False

        payload = {
            "alert": asdict(alert),
            "supremeai_version": "2.0.0",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }

        try:
            resp = requests.post(self.url, json=payload, headers=self.headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            logger.info(f"✅ Webhook alert sent: {alert.title}")
            return True
        except requests.RequestException as e:
            logger.error(f"❌ Webhook alert failed: {e}")
            return False


# ── Alert Manager Core ──────────────────────────────────────
class AlertManager:
    """Central alert manager with routing, deduplication, and persistence."""

    def __init__(self):
        self.deduplicator = AlertDeduplicator()
        self.providers: dict[AlertChannel, Any] = {}
        self.configs: dict[AlertChannel, ChannelConfig] = {}
        self.alert_history: list[Alert] = []
        self._load_state()
        self._init_providers()

    def _init_providers(self) -> None:
        """Initialize providers from environment/config."""
        # Discord
        discord_url = os.getenv("DISCORD_WEBHOOK_URL", getattr(settings, "discord_webhook_url", ""))
        if discord_url:
            self.providers[AlertChannel.DISCORD] = DiscordProvider(discord_url)
            self.configs[AlertChannel.DISCORD] = ChannelConfig(
                enabled=True, min_severity=AlertSeverity.INFO,
                recipients=["#alerts-channel"]
            )

        # Slack
        slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
        if slack_url:
            self.providers[AlertChannel.SLACK] = SlackProvider(slack_url)
            self.configs[AlertChannel.SLACK] = ChannelConfig(
                enabled=True, min_severity=AlertSeverity.WARNING,
            )

        # Email
        sendgrid_key = os.getenv("SENDGRID_API_KEY", "")
        smtp_host = os.getenv("SMTP_HOST", "")
        if sendgrid_key or smtp_host:
            self.providers[AlertChannel.EMAIL] = EmailProvider(
                smtp_host=smtp_host,
                smtp_port=int(os.getenv("SMTP_PORT", "587")),
                username=os.getenv("SMTP_USER", ""),
                password=os.getenv("SMTP_PASS", ""),
                from_addr=os.getenv("ALERT_FROM_EMAIL", "alerts@supremeai.io"),
                sendgrid_api_key=sendgrid_key,
            )
            self.configs[AlertChannel.EMAIL] = ChannelConfig(
                enabled=True, min_severity=AlertSeverity.WARNING,
                recipients=os.getenv("ALERT_EMAILS", "").split(","),
            )

        # SMS (Twilio)
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
        if twilio_sid:
            self.providers[AlertChannel.SMS] = SMSProvider(
                account_sid=twilio_sid,
                auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
                from_number=os.getenv("TWILIO_FROM_NUMBER", ""),
            )
            self.configs[AlertChannel.SMS] = ChannelConfig(
                enabled=True, min_severity=AlertSeverity.CRITICAL,
                recipients=os.getenv("ALERT_PHONES", "").split(","),
            )

        # PagerDuty
        pd_key = os.getenv("PAGERDUTY_ROUTING_KEY", "")
        if pd_key:
            self.providers[AlertChannel.PAGERDUTY] = PagerDutyProvider(routing_key=pd_key)
            self.configs[AlertChannel.PAGERDUTY] = ChannelConfig(
                enabled=True, min_severity=AlertSeverity.CRITICAL,
            )

        # Generic Webhook
        webhook_url = os.getenv("ALERT_WEBHOOK_URL", "")
        if webhook_url:
            self.providers[AlertChannel.WEBHOOK] = WebhookProvider(
                url=webhook_url,
                headers={"X-SupremeAI-Source": "alert-manager"},
            )
            self.configs[AlertChannel.WEBHOOK] = ChannelConfig(
                enabled=True, min_severity=AlertSeverity.INFO,
            )

        logger.info(f"🔔 AlertManager initialized with {len(self.providers)} channels")

    def _load_state(self) -> None:
        if ALERT_STATE_FILE.exists():
            try:
                data = json.loads(ALERT_STATE_FILE.read_text(encoding="utf-8"))
                self.alert_history = [Alert(**a) for a in data.get("alerts", [])]
                logger.info(f"📚 Loaded {len(self.alert_history)} historical alerts")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load alert state: {e}")

    def _save_state(self) -> None:
        try:
            data = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "alerts": [asdict(a) for a in self.alert_history[-500:]],  # Keep last 500
            }
            ALERT_STATE_FILE.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save alert state: {e}")

    def create_alert(
        self,
        severity: AlertSeverity | str,
        title: str,
        message: str,
        message_bn: str,
        source: str,
        metric: str,
        value: float,
        threshold: float,
        channels: list[AlertChannel] | None = None,
        recipients: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Alert:
        """Create a new alert with auto-generated ID."""
        alert_id = hashlib.sha256(
            f"{title}:{source}:{metric}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]

        if isinstance(severity, str):
            severity = AlertSeverity(severity)

        alert = Alert(
            id=alert_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            severity=severity,
            channel=AlertChannel.DISCORD,  # Default, will be overridden per-channel
            title=title,
            message=message,
            message_bn=message_bn,
            source=source,
            metric=metric,
            value=value,
            threshold=threshold,
            recipients=recipients or [],
            metadata=metadata or {},
        )
        return alert

    async def send(self, alert: Alert, channels: list[AlertChannel] | None = None) -> dict[str, bool]:
        """Send alert to specified channels with deduplication and severity filtering."""
        if not await self.deduplicator.should_send(alert):
            return {"deduplicated": True}

        targets = channels or list(self.providers.keys())
        results: dict[str, bool] = {}

        for channel in targets:
            if channel not in self.providers:
                results[channel.value] = False
                continue

            config = self.configs.get(channel, ChannelConfig())
            if not config.enabled:
                results[channel.value] = False
                continue

            # Severity filter
            severity_order = [AlertSeverity.DEBUG, AlertSeverity.INFO, AlertSeverity.WARNING, AlertSeverity.CRITICAL]
            if severity_order.index(alert.severity) < severity_order.index(config.min_severity):
                results[channel.value] = False
                continue

            # Update alert for this channel
            alert.channel = channel
            alert.recipients = alert.recipients or config.recipients
            alert.last_sent = datetime.now(timezone.utc).isoformat()
            alert.sent_count += 1

            provider = self.providers[channel]
            try:
                success = await provider.send(alert)
                results[channel.value] = success
            except Exception as e:
                logger.error(f"❌ Provider {channel.value} failed: {e}")
                results[channel.value] = False

        # Persist if any succeeded
        if any(results.values()):
            self.alert_history.append(alert)
            self._save_state()

        return results

    async def acknowledge(self, alert_id: str) -> bool:
        for alert in self.alert_history:
            if alert.id == alert_id:
                alert.acknowledged = True
                self._save_state()
                logger.info(f"✅ Alert acknowledged: {alert_id}")
                return True
        return False

    async def resolve(self, alert_id: str) -> bool:
        for alert in self.alert_history:
            if alert.id == alert_id:
                alert.resolved = True
                alert.resolved_at = datetime.now(timezone.utc).isoformat()
                self._save_state()
                logger.info(f"✅ Alert resolved: {alert_id}")
                return True
        return False

    def get_active_alerts(self, severity: AlertSeverity | None = None) -> list[Alert]:
        alerts = [a for a in self.alert_history if not a.resolved]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return sorted(alerts, key=lambda a: a.timestamp, reverse=True)

    def get_stats(self) -> dict[str, Any]:
        total = len(self.alert_history)
        active = len([a for a in self.alert_history if not a.resolved])
        by_severity = {}
        for a in self.alert_history:
            by_severity[a.severity.value] = by_severity.get(a.severity.value, 0) + 1
        return {
            "total_alerts": total,
            "active_alerts": active,
            "by_severity": by_severity,
            "channels_configured": len(self.providers),
        }


# ── Convenience Functions ───────────────────────────────────
_manager: AlertManager | None = None


def get_manager() -> AlertManager:
    global _manager
    if _manager is None:
        _manager = AlertManager()
    return _manager


async def alert(
    severity: str,
    title: str,
    message: str,
    message_bn: str,
    source: str,
    metric: str,
    value: float,
    threshold: float,
    **kwargs: Any,
) -> dict[str, bool]:
    """Fire-and-forget alert helper."""
    mgr = get_manager()
    alert_obj = mgr.create_alert(
        severity=severity,
        title=title,
        message=message,
        message_bn=message_bn,
        source=source,
        metric=metric,
        value=value,
        threshold=threshold,
        **kwargs,
    )
    return await mgr.send(alert_obj)


# ── CLI / Test ──────────────────────────────────────────────
async def demo():
    """Demo all alert channels."""
    mgr = get_manager()

    test_alert = mgr.create_alert(
        severity=AlertSeverity.CRITICAL,
        title="Database Connection Pool Exhausted",
        message="The PostgreSQL connection pool has reached 95% capacity. New requests are being queued.",
        message_bn="পোস্টগ্রেস কানেকশন পুল ৯৫% ক্ষমতায় পৌঁছেছে। নতুন রিকোয়েস্ট কিউতে রাখা হচ্ছে।",
        source="database",
        metric="connection_pool_usage_pct",
        value=95.0,
        threshold=80.0,
        recipients=["admin@supremeai.io"],
    )

    print(f"🚨 Sending test alert: {test_alert.title}")
    results = await mgr.send(test_alert)
    for channel, success in results.items():
        status = "✅" if success else "❌"
        print(f"   {status} {channel}")

    print(f"\n📊 Alert Stats: {mgr.get_stats()}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SupremeAI Alert Manager")
    parser.add_argument("--demo", action="store_true", help="Run demo alert")
    parser.add_argument("--stats", action="store_true", help="Show alert statistics")
    args = parser.parse_args()

    if args.demo:
        asyncio.run(demo())
    elif args.stats:
        mgr = get_manager()
        stats = mgr.get_stats()
        print(json.dumps(stats, indent=2))
    else:
        print("Usage: python alert_manager.py --demo | --stats")
        print("\nEnvironment variables required:")
        print("  DISCORD_WEBHOOK_URL, SLACK_WEBHOOK_URL, SENDGRID_API_KEY")
        print("  SMTP_HOST, TWILIO_ACCOUNT_SID, PAGERDUTY_ROUTING_KEY")
        print("  ALERT_WEBHOOK_URL, ALERT_EMAILS, ALERT_PHONES")


if __name__ == "__main__":
    main()
