from __future__ import annotations

import asyncio
import logging

"""
SupremeAI - MultiCloud Quota Monitor Agent
===================================
Purpose: Multi-cloud monitoring for Firebase, Vercel, GCP — quota, billing, error rates, anomaly detection.
Author: SupremeAI Architecture Team
Date: July 18, 2026
"""


import datetime
import json
import os
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import httpx as requests

from core.logging_config import logger

# বাংলা মন্তব্য: উইন্ডোজ টার্মিনালে ইউনিকোড/ইমোজি আউটপুট সাপোর্ট করার জন্য এনকোডিং কনফিগার করা হলো।
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except asyncio.CancelledError:
        raise
    except Exception as e:
        import logging

        logging.getLogger(__name__).exception(f"Silenced error: {e}")

# --- Path Setup (consistent with existing codebase) ---
# বাংলা মন্তব্য: পাথ সেটআপ ও কনফিগ লোড নিশ্চিত করা হচ্ছে।
try:
    from core.config import settings
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from core.config import settings

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

REQUEST_TIMEOUT = int(os.getenv("HTTP_TIMEOUT_SECONDS") or "15")
MAX_WORKERS = int(os.getenv("CLOUDWATCH_CONCURRENCY") or "5")
ANOMALY_Z_THRESHOLD = float(os.getenv("ANOMALY_Z_THRESHOLD", "2.5"))
HISTORY_FILE = Path(__file__).parent / ".cloudwatch_history.json"

DISCORD_WEBHOOK = getattr(settings, "discord_webhook_url", os.getenv("DISCORD_WEBHOOK_URL", ""))
GCP_PROJECT_ID = getattr(settings, "gcp_project_id", os.getenv("GOOGLE_CLOUD_PROJECT", ""))
VERCEL_TOKEN = os.getenv("VERCEL_OIDC_TOKEN", "")


@dataclass
class MetricSnapshot:
    """একটি মেট্রিকের স্ন্যাপশট — টাইমস্ট্যাম্প, ভ্যালু, সোর্স।"""

    timestamp: str
    source: str  # 'firebase', 'vercel', 'gcp'
    metric_name: str
    value: float
    unit: str


@dataclass
class AnomalyReport:
    """এনোমালি রিপোর্ট — কোন মেট্রিক, কতটা abnormal, সাজেশন।"""

    timestamp: str
    source: str
    metric_name: str
    current_value: float
    expected_range: tuple[float, float]
    severity: str  # 'warning', 'critical'
    suggestion: str


class AnomalyDetector:
    """Statistical anomaly detection using Z-score and IQR."""

    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self.history: dict[str, list[float]] = {}
        self._load_history()

    def _load_history(self):
        # বাংলা মন্তব্য: এনোমালি ডিটেকশন হিস্ট্রি ফাইল থেকে লোড করা।
        if HISTORY_FILE.exists():
            try:
                self.history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
                logger.info(f"📚 Loaded {len(self.history)} metric histories")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load history: {e}")

    def _save_history(self):
        # বাংলা মন্তব্য: মেমোরি থেকে হিস্ট্রি ক্যাশে ফাইল রাইট করা।
        try:
            HISTORY_FILE.write_text(json.dumps(self.history, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️ Failed to save history: {e}")

    def _key(self, source: str, metric: str) -> str:
        return f"{source}:{metric}"

    def add_value(self, snapshot: MetricSnapshot):
        key = self._key(snapshot.source, snapshot.metric_name)
        if key not in self.history:
            self.history[key] = []
        self.history[key].append(snapshot.value)
        if len(self.history[key]) > self.window_size:
            self.history[key] = self.history[key][-self.window_size :]

    def detect(self, snapshot: MetricSnapshot) -> AnomalyReport | None:
        # বাংলা মন্তব্য: Z-score এবং IQR মেথড ব্যবহার করে এনোমালি নির্ণয়।
        key = self._key(snapshot.source, snapshot.metric_name)
        values = self.history.get(key, [])

        if len(values) < 5:
            self.add_value(snapshot)
            self._save_history()
            return None

        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0
        z_score = (snapshot.value - mean) / stdev if stdev > 0 else 0.0

        sorted_vals = sorted(values)
        q1 = sorted_vals[len(sorted_vals) // 4] if len(sorted_vals) >= 4 else sorted_vals[0]
        q3 = sorted_vals[3 * len(sorted_vals) // 4] if len(sorted_vals) >= 4 else sorted_vals[-1]
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        is_anomaly = (
            abs(z_score) > ANOMALY_Z_THRESHOLD
            or snapshot.value < lower_bound
            or snapshot.value > upper_bound
        )

        self.add_value(snapshot)
        self._save_history()

        if is_anomaly:
            severity = "critical" if abs(z_score) > ANOMALY_Z_THRESHOLD * 1.5 else "warning"
            suggestion = self._generate_suggestion(
                snapshot.source, snapshot.metric_name, snapshot.value, mean, upper_bound
            )
            return AnomalyReport(
                timestamp=snapshot.timestamp,
                source=snapshot.source,
                metric_name=snapshot.metric_name,
                current_value=snapshot.value,
                expected_range=(lower_bound, upper_bound),
                severity=severity,
                suggestion=suggestion,
            )
        return None

    def _generate_suggestion(
        self, source: str, metric: str, value: float, mean: float, upper: float
    ) -> str:
        if source == "firebase" and "quota" in metric:
            return "🔥 Firebase quota spike detected! Consider enabling Firestore caching or upgrading Blaze plan."
        elif source == "vercel" and "bandwidth" in metric:
            return "🚀 Vercel bandwidth anomaly! Enable CDN caching or check for DDoS."
        elif source == "gcp" and "billing" in metric:
            return "💰 GCP billing spike! Review recent deployments for resource leaks."
        elif mean > 0 and value > mean * 3:
            return f"⚠️ Extreme spike: {metric} is {value / mean:.1f}x normal. Immediate investigation needed."
        return f"📊 {metric} above expected range. Monitor closely for next 15 minutes."


class AlertManager:
    """Discord webhook-এ alert পাঠায়। Bengali + English bilingual format."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_alert(self, report: AnomalyReport):
        # বাংলা মন্তব্য: ডিসকর্ড ওয়েবহুকে এনোমালি এলার্ট পাঠানো।
        if not self.webhook_url:
            logger.warning("❌ Discord webhook URL not configured. Alert dropped.")
            return False

        color = 0xFF0000 if report.severity == "critical" else 0xFFA500
        embed = {
            "title": f"🚨 CloudWatchman Alert — {report.severity.upper()}",
            "color": color,
            "fields": [
                {"name": "☁️ Source", "value": report.source.upper(), "inline": True},
                {"name": "📊 Metric", "value": report.metric_name, "inline": True},
                {
                    "name": "🔢 Current Value",
                    "value": f"{report.current_value:.2f}",
                    "inline": True,
                },
                {
                    "name": "📈 Expected Range",
                    "value": f"{report.expected_range[0]:.2f} - {report.expected_range[1]:.2f}",
                    "inline": True,
                },
                {"name": "💡 Suggestion", "value": report.suggestion, "inline": False},
            ],
            "footer": {"text": f"SupremeAI CloudWatchman | {report.timestamp}"},
            "timestamp": report.timestamp,
        }

        payload = {
            "embeds": [embed],
            "content": f"<@&admin> **{report.severity.upper()}** anomaly detected in `{report.source}`!",
        }

        try:
            resp = requests.post(
                self.webhook_url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            logger.info(f"✅ Alert sent to Discord for {report.source}:{report.metric_name}")
            return True
        except requests.RequestException as e:
            logger.error(f"❌ Discord alert failed: {e}")
            return False

    def send_summary(self, snapshots: list[MetricSnapshot]):
        if not self.webhook_url or not snapshots:
            return

        lines = ["📋 **CloudWatchman Health Summary**\n"]
        for s in snapshots:
            lines.append(f"• `{s.source}` | `{s.metric_name}` = **{s.value:.2f}** {s.unit}")

        try:
            requests.post(
                self.webhook_url,
                json={"content": "\n".join(lines[:15])},
                timeout=REQUEST_TIMEOUT,
            )
        except Exception as e:
            logger.warning(f"Summary send failed: {e}")


class FirebaseMonitor:
    def __init__(self, project_id: str):
        self.project_id = project_id

    def check_firestore_quota(self) -> MetricSnapshot | None:
        if not GCP_PROJECT_ID:
            logger.warning("⚠️ GCP_PROJECT_ID not set, skipping Firestore quota check.")
            return None
        try:
            from google.cloud import monitoring_v3

            client = monitoring_v3.MetricServiceClient()
            project_name = f"projects/{GCP_PROJECT_ID}"
            now_sec = int(time.time())
            interval = monitoring_v3.TimeInterval(
                end_time={"seconds": now_sec}, start_time={"seconds": now_sec - 3600}
            )
            results = client.list_time_series(
                request={
                    "name": project_name,
                    "filter": 'metric.type="firestore.googleapis.com/document/read_count"',
                    "interval": interval,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )
            total_reads = sum(point.value.int64_value for ts in results for point in ts.points)
            return MetricSnapshot(
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                source="firebase",
                metric_name="firestore_read_count_1h",
                value=float(total_reads),
                unit="reads",
            )
        except Exception as e:
            logger.error(f"❌ Firestore quota check failed: {e}")
            return None

    def check_firebase_status(self) -> MetricSnapshot | None:
        try:
            resp = requests.get(
                "https://status.firebase.google.com/incidents.json",
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            active_incidents = [i for i in resp.json() if i.get("status") != "resolved"]
            return MetricSnapshot(
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                source="firebase",
                metric_name="active_incidents",
                value=float(len(active_incidents)),
                unit="incidents",
            )
        except Exception as e:
            logger.error(f"❌ Firebase status check failed: {e}")
            return None

    def get_all_metrics(self) -> list[MetricSnapshot]:
        metrics = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.check_firestore_quota),
                pool.submit(self.check_firebase_status),
            ]
            for future in as_completed(futures):
                res = future.result()
                if res:
                    metrics.append(res)
        return metrics


class VercelMonitor:
    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    def check_deployments(self) -> MetricSnapshot | None:
        if not self.token:
            return None
        try:
            resp = requests.get(
                "https://api.vercel.com/v6/deployments?limit=10",
                headers=self.headers,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            deployments = resp.json().get("deployments", [])
            if not deployments:
                return None
            failed = sum(1 for d in deployments if d.get("state") in ["ERROR", "CANCELED"])
            return MetricSnapshot(
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                source="vercel",
                metric_name="deployment_error_rate_pct",
                value=(failed / len(deployments)) * 100,
                unit="percent",
            )
        except Exception as e:
            logger.error(f"❌ Vercel deployment check failed: {e}")
            return None

    def check_bandwidth(self) -> MetricSnapshot | None:
        if not self.token:
            return None
        try:
            resp = requests.get(
                "https://api.vercel.com/v1/projects",
                headers=self.headers,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            total_bandwidth = sum(p.get("bandwidth", 0) for p in resp.json().get("projects", []))
            return MetricSnapshot(
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                source="vercel",
                metric_name="total_bandwidth_bytes",
                value=float(total_bandwidth),
                unit="bytes",
            )
        except Exception as e:
            logger.error(f"❌ Vercel bandwidth check failed: {e}")
            return None

    def get_all_metrics(self) -> list[MetricSnapshot]:
        metrics = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.check_deployments),
                pool.submit(self.check_bandwidth),
            ]
            for future in as_completed(futures):
                res = future.result()
                if res:
                    metrics.append(res)
        return metrics


class GCPMonitor:
    def __init__(self, project_id: str):
        self.project_id = project_id

    def check_billing(self) -> MetricSnapshot | None:
        if not self.project_id:
            return None
        try:
            from google.cloud import billing_v1

            client = billing_v1.CloudBillingClient()
            accounts = list(client.list_billing_accounts())
            return MetricSnapshot(
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                source="gcp",
                metric_name="billing_accounts_count",
                value=float(len(accounts)),
                unit="count",
            )
        except Exception as e:
            logger.error(f"❌ GCP billing check failed: {e}")
            return None

    def check_api_quota(self) -> MetricSnapshot | None:
        if not self.project_id:
            return None
        try:
            from google.cloud import monitoring_v3

            client = monitoring_v3.MetricServiceClient()
            project_name = f"projects/{self.project_id}"
            now_sec = int(time.time())
            interval = monitoring_v3.TimeInterval(
                end_time={"seconds": now_sec}, start_time={"seconds": now_sec - 3600}
            )
            results = client.list_time_series(
                request={
                    "name": project_name,
                    "filter": 'metric.type="run.googleapis.com/request_count"',
                    "interval": interval,
                    "view": monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
                }
            )
            total_requests = sum(point.value.int64_value for ts in results for point in ts.points)
            return MetricSnapshot(
                timestamp=datetime.datetime.now(datetime.UTC).isoformat(),
                source="gcp",
                metric_name="cloudrun_request_count_1h",
                value=float(total_requests),
                unit="requests",
            )
        except Exception as e:
            logger.error(f"❌ GCP API quota check failed: {e}")
            return None

    def get_all_metrics(self) -> list[MetricSnapshot]:
        metrics = []
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(self.check_billing),
                pool.submit(self.check_api_quota),
            ]
            for future in as_completed(futures):
                res = future.result()
                if res:
                    metrics.append(res)
        return metrics


class MultiCloudQuotaMonitor:
    def __init__(self):
        self.detector = AnomalyDetector(window_size=30)
        self.alerter = AlertManager(DISCORD_WEBHOOK)
        self.firebase = FirebaseMonitor(project_id=GCP_PROJECT_ID)
        self.vercel = VercelMonitor(token=VERCEL_TOKEN)
        self.gcp = GCPMonitor(project_id=GCP_PROJECT_ID)

    def run(self, send_summary: bool = True) -> list[AnomalyReport]:
        logger.info("🚀 CloudWatchman starting multi-cloud telemetry scan...")
        all_snapshots: list[MetricSnapshot] = []
        anomalies: list[AnomalyReport] = []

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(self.firebase.get_all_metrics): "firebase",
                pool.submit(self.vercel.get_all_metrics): "vercel",
                pool.submit(self.gcp.get_all_metrics): "gcp",
            }
            for future in as_completed(futures):
                source = futures[future]
                try:
                    snapshots = future.result()
                    all_snapshots.extend(snapshots)
                    logger.info(f"✅ {source.upper()}: {len(snapshots)} metrics loaded sync.")
                except Exception as e:
                    logger.error(f"❌ {source} metrics aggregator failed: {e}")

        for snapshot in all_snapshots:
            report = self.detector.detect(snapshot)
            if report:
                anomalies.append(report)
                self.alerter.send_alert(report)

        if send_summary and all_snapshots:
            self.alerter.send_summary(all_snapshots)

        logger.info(f"🏁 Telemetry sweep complete. Anomalies locked: {len(anomalies)}")
        return anomalies


def main():
    watchman = CloudWatchman()
    anomalies = watchman.run()
    if anomalies:
        pass
    else:
        pass


if __name__ == "__main__":
    main()


# Canonical aliases for backward compatibility
CloudWatchman = MultiCloudQuotaMonitor
MulticloudQuotaMonitor = MultiCloudQuotaMonitor  # noqa: E741 (PascalCase alias)
