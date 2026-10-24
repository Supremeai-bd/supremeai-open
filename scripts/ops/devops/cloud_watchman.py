#!/usr/bin/env python3
"""
SupremeAI - CloudWatchman Agent ☁️
===================================
Multi-cloud monitoring: Firebase, Vercel, GCP quota/billing/error rate.
Anomaly detection with statistical thresholding.

Author: SupremeAI Core
Date: July 18, 2026
"""

import argparse
import concurrent.futures
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, stdev

import requests

logger = logging.getLogger(__name__)

# --- Path Setup ---
# বাংলা মন্তব্য: পাথ সেটআপ এবং কোর কনফিগারেশন ইম্পোর্ট
try:
    from backend.core.config import settings
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
    sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from core.config import settings

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')

CACHE_FILE = Path(__file__).parent / ".cloud_watchman_cache.json"
ALERT_STATE_FILE = Path(__file__).parent / ".cloud_watchman_alerts.json"
REQUEST_TIMEOUT = int(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
MAX_WORKERS = int(os.getenv("CLOUD_WATCHMAN_CONCURRENCY", "5"))

# Anomaly threshold: Z-score or percentage
ANOMALY_Z_THRESHOLD = float(os.getenv("ANOMALY_Z_THRESHOLD", "2.5"))
ANOMALY_PCT_THRESHOLD = float(os.getenv("ANOMALY_PCT_THRESHOLD", "50.0"))


@dataclass
class MetricPoint:
    name: str
    value: float
    unit: str
    timestamp: str
    source: str  # "firebase", "vercel", "gcp", "render"


@dataclass
class Anomaly:
    metric: str
    current_value: float
    expected_range: str
    severity: str  # CRITICAL, HIGH, LOW
    message: str


@dataclass
class ServiceReport:
    source: str
    healthy: bool
    metrics: list[MetricPoint] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    raw_status: dict = field(default_factory=dict)


# --- API Clients ---

class RenderClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

    def get_services(self) -> list[dict]:
        resp = requests.get("https://api.render.com/v1/services?limit=20", headers=self.headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    def get_deploys(self, service_id: str, limit: int = 5) -> list[dict]:
        resp = requests.get(f"https://api.render.com/v1/services/{service_id}/deploys?limit={limit}", headers=self.headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()


class VercelClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"}

    def get_deployments(self, project_id: str | None = None, limit: int = 10) -> list[dict]:
        url = "https://api.vercel.com/v6/deployments"
        params = {"limit": limit}
        if project_id:
            params["projectId"] = project_id
        resp = requests.get(url, headers=self.headers, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("deployments", [])

    def get_projects(self) -> list[dict]:
        resp = requests.get("https://api.vercel.com/v9/projects", headers=self.headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("projects", [])


class GCPClient:
    def __init__(self, access_token: str | None = None):
        self.access_token = access_token or self._get_access_token()
        self.project = "supremeai-a"  # From .firebaserc

    def _get_access_token(self) -> str:
        try:
            import subprocess
            result = subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as e:
            logger.warning(f"Failed to obtain GCP access token: {e}")
        return ""

    def get_service_usage(self) -> list[dict]:
        if not self.access_token:
            return []
        headers = {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}
        url = f"https://serviceusage.googleapis.com/v1/projects/{self.project}/services"
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("services", [])

    def get_monitoring_metrics(self, metric_type: str = "compute.googleapis.com/quota/instances") -> list[dict]:
        if not self.access_token:
            return []
        headers = {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}
        now = datetime.utcnow()
        start = (now - timedelta(hours=1)).isoformat("T") + "Z"
        end = now.isoformat("T") + "Z"
        url = (
            f"https://monitoring.googleapis.com/v3/projects/{self.project}/timeSeries"
            f'?filter=metric.type="{metric_type}"&interval.startTime={start}&interval.endTime={end}'
        )
        resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 403:
            logging.warning("GCP Monitoring API access denied. Enable Cloud Monitoring API.")
            return []
        resp.raise_for_status()
        return resp.json().get("timeSeries", [])


# --- Anomaly Detection ---

def detect_anomaly(metric_name: str, current: float, history: list[float]) -> Anomaly | None:
    if len(history) < 3:
        return None

    avg = mean(history)
    if avg == 0:
        if current > 0:
            return Anomaly(metric_name, current, "0 (baseline)", "HIGH", f"First non-zero value detected: {current}")
        return None

    pct_dev = abs(current - avg) / avg * 100
    if pct_dev < ANOMALY_PCT_THRESHOLD:
        return None

    if len(history) >= 5:
        try:
            z = abs(current - avg) / stdev(history)
            if z < ANOMALY_Z_THRESHOLD:
                return None
            severity = "CRITICAL" if z > 4 else "HIGH"
        except Exception:
            severity = "HIGH"
    else:
        severity = "HIGH"

    return Anomaly(
        metric=metric_name,
        current_value=current,
        expected_range=f"{avg:.2f} ± {ANOMALY_PCT_THRESHOLD}%",
        severity=severity,
        message=f"{metric_name} is {current} (expected ~{avg:.2f}). Deviation: {pct_dev:.1f}%"
    )


# --- Cache & State ---

def load_cache() -> dict:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Silenced error: {e}")
    return {}

def save_cache(cache: dict):
    CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

def load_alert_state() -> dict:
    if ALERT_STATE_FILE.exists():
        try:
            return json.loads(ALERT_STATE_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception(f"Silenced error: {e}")
    return {}

def save_alert_state(state: dict):
    ALERT_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# --- Report Generation ---

def generate_markdown_report(reports: list[ServiceReport], output_path: Path):
    lines = [
        "# ☁️ CloudWatchman Multi-Cloud Monitoring Report",
        f"**Generated:** {datetime.now().isoformat()}",
        f"**Sources Checked:** {len(reports)}",
        "",
        "## Health Overview",
        "| Source | Status | Metrics | Anomalies |",
        "|--------|--------|---------|-----------|",
    ]

    total_anomalies = 0
    for r in reports:
        status = "🟢 Healthy" if r.healthy else "🔴 Unhealthy"
        anom_count = len(r.anomalies)
        total_anomalies += anom_count
        lines.append(f"| {r.source} | {status} | {len(r.metrics)} | {anom_count} |")

    lines.extend([
        "",
        f"**Total Anomalies:** {total_anomalies}",
        "",
        "---",
        "",
        "## Anomalies & Alerts",
    ])

    for r in reports:
        if not r.anomalies:
            continue
        lines.append(f"### {r.source}")
        lines.append("")
        lines.append("| Metric | Severity | Current | Expected | Message |")
        lines.append("|--------|----------|---------|----------|---------|")
        for a in r.anomalies:
            lines.append(f"| {a.metric} | {a.severity} | {a.current_value} | {a.expected_range} | {a.message} |")
        lines.append("")

    lines.extend([
        "",
        "## Latest Metrics",
    ])
    for r in reports:
        if not r.metrics:
            continue
        lines.append(f"### {r.source}")
        lines.append("")
        lines.append("| Metric | Value | Unit | Timestamp |")
        lines.append("|--------|-------|------|-----------|")
        for m in r.metrics:
            lines.append(f"| {m.name} | {m.value} | {m.unit} | {m.timestamp} |")
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logging.info(f"✅ CloudWatchman report saved to {output_path}")


# --- Main Orchestrator ---

def check_render(render_key: str | None) -> ServiceReport:
    report = ServiceReport(source="Render", healthy=True)
    if not render_key:
        report.healthy = False
        report.anomalies.append(Anomaly("api_key", 0, "present", "CRITICAL", "Render API key not configured"))
        return report

    try:
        client = RenderClient(render_key)
        services = client.get_services()
        failed_deploys = 0
        for srv in services:
            service = srv.get("service", {})
            srv_id = service.get("id")
            name = service.get("name", "unknown")
            suspended = service.get("suspended") == "suspended"
            if suspended:
                report.anomalies.append(Anomaly(f"render_{name}_suspended", 1, "0", "HIGH", f"Service {name} is suspended"))
                report.healthy = False

            deploys = client.get_deploys(srv_id, limit=3)
            for d in deploys:
                dep = d.get("deploy", {})
                status = dep.get("status")
                if status in {"failed", "canceled"}:
                    failed_deploys += 1
                report.metrics.append(MetricPoint(
                    name=f"render_{name}_deploy_status",
                    value=1 if status == "live" else 0,
                    unit="boolean",
                    timestamp=datetime.now().isoformat(),
                    source="render"
                ))

        if failed_deploys > 0:
            report.healthy = False
            report.anomalies.append(Anomaly("render_failed_deploys", failed_deploys, "0", "HIGH", f"{failed_deploys} recent failed deploy(s) detected"))

    except Exception as e:
        report.healthy = False
        report.anomalies.append(Anomaly("render_api", 0, "ok", "CRITICAL", f"Render API error: {e}"))

    return report


def check_vercel(vercel_token: str | None) -> ServiceReport:
    report = ServiceReport(source="Vercel", healthy=True)
    if not vercel_token:
        report.healthy = False
        report.anomalies.append(Anomaly("api_token", 0, "present", "CRITICAL", "Vercel token not configured"))
        return report

    try:
        client = VercelClient(vercel_token)
        projects = client.get_projects()
        for proj in projects:
            name = proj.get("name", "unknown")
            deploys = client.get_deployments(project_id=proj.get("id"), limit=1)
            for dep in deploys:
                state = dep.get("state")  # READY, ERROR, CANCELED
                report.metrics.append(MetricPoint(
                    name=f"vercel_{name}_deploy_state",
                    value=1 if state == "READY" else 0,
                    unit="boolean",
                    timestamp=datetime.now().isoformat(),
                    source="vercel"
                ))
                if state == "ERROR":
                    report.healthy = False
                    report.anomalies.append(Anomaly(f"vercel_{name}_deploy", 0, "READY", "HIGH", f"Vercel project {name} latest deployment failed"))
    except Exception as e:
        report.healthy = False
        report.anomalies.append(Anomaly("vercel_api", 0, "ok", "CRITICAL", f"Vercel API error: {e}"))

    return report


def check_gcp(gcp_token: str | None, cache: dict) -> ServiceReport:
    # বাংলা মন্তব্য: জিসিপি এবং ফায়ারবেজ হেলথ চেক ও অ্যানোমালি ডিটেকশন প্রসেস।
    report = ServiceReport(source="GCP/Firebase", healthy=True)
    client = GCPClient(access_token=gcp_token)

    try:
        services = client.get_service_usage()
        enabled = sum(1 for s in services if s.get("state") == "ENABLED")
        report.metrics.append(MetricPoint(
            name="gcp_enabled_services",
            value=enabled,
            unit="count",
            timestamp=datetime.now().isoformat(),
            source="gcp"
        ))

        metrics = client.get_monitoring_metrics()
        for ts in metrics:
            metric_type = ts.get("metric", {}).get("type", "unknown")
            points = ts.get("points", [])
            if points:
                latest = points[0]
                value = latest.get("value", {}).get("int64Value") or latest.get("value", {}).get("doubleValue", 0)
                report.metrics.append(MetricPoint(
                    name=f"gcp_{metric_type}",
                    value=float(value),
                    unit="count",
                    timestamp=datetime.now().isoformat(),
                    source="gcp"
                ))

                key = f"gcp_{metric_type}"
                history = cache.get("history", {}).get(key, [])
                anomaly = detect_anomaly(key, float(value), history)
                if anomaly:
                    report.anomalies.append(anomaly)

                if "history" not in cache:
                    cache["history"] = {}
                if key not in cache["history"]:
                    cache["history"][key] = []
                cache["history"][key].append(float(value))
                cache["history"][key] = cache["history"][key][-20:]
    except Exception as e:
        report.healthy = False
        report.anomalies.append(Anomaly("gcp_api", 0, "ok", "CRITICAL", f"GCP API error: {e}"))

    return report


def main(dry_run: bool = False, force: bool = False, output: str = "cloud_watchman_report.md"):
    # বাংলা মন্তব্য: ক্লাউড ওয়াচম্যান এর মূল অর্কেস্ট্রেশন ফাংশন।
    vercel_token = os.getenv("VERCEL_TOKEN")
    render_key = settings.render_api_key if hasattr(settings, "render_api_key") else os.getenv("RENDER_API_KEY")
    gcp_token = os.getenv("GCP_ACCESS_TOKEN")

    cache = load_cache()
    reports: list[ServiceReport] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(check_render, render_key): "Render",
            executor.submit(check_vercel, vercel_token): "Vercel",
            executor.submit(check_gcp, gcp_token, cache): "GCP/Firebase",
        }

        for fut in concurrent.futures.as_completed(futures):
            source = futures[fut]
            try:
                report = fut.result()
                reports.append(report)
            except Exception as e:
                logging.error(f"Error checking {source}: {e}")
                reports.append(ServiceReport(source=source, healthy=False, anomalies=[
                    Anomaly("system_error", 0, "ok", "CRITICAL", f"Failed to run check for {source}: {e}")
                ]))

    if not dry_run:
        save_cache(cache)

    generate_markdown_report(reports, Path(output))

    unhealthy = any(not r.healthy for r in reports)
    if unhealthy:
        logging.warning("⚠️ Some services are reported as Unhealthy!")
        sys.exit(1)
    else:
        logging.info("✅ All services are healthy!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CloudWatchman: Multi-cloud SRE monitoring agent")
    parser.add_argument("--dry-run", action="store_true", help="Run without saving cache or state.")
    parser.add_argument("-o", "--output", type=str, default="cloud_watchman_report.md", help="Output report file path.")
    args = parser.parse_args()

    main(dry_run=args.dry_run, output=args.output)
