from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from core.config import settings
from core.logging_config import logger


class HealthChecker:
    def __init__(self) -> None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(base_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.error_history_path = os.path.join(self.data_dir, "error_history.jsonl")
        self.telegram_bot_token = getattr(settings, "telegram_bot_token", "")
        self.admin_chat_id = getattr(settings, "admin_telegram_chat_id", "")

    def run_health_check(self) -> dict[str, Any]:
        dependencies = [
            "fastapi",
            "pydantic",
            "sqlite3",
            "sympy",
            "matplotlib",
            "PIL",
            "chromadb",
        ]
        dep_status = {}
        for dep in dependencies:
            try:
                __import__(dep)
                dep_status[dep] = "OK"
            except ImportError:
                dep_status[dep] = "MISSING"

        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_exists = os.path.exists(os.path.join(base_dir, ".env"))
        db_exists = os.path.exists(os.path.join(base_dir, "data", "supreme_memory.db"))

        overall_status = "HEALTHY"
        if "MISSING" in dep_status.values() or not env_exists:
            overall_status = "WARNING"

        report = {
            "overall_status": overall_status,
            "dependencies": dep_status,
            "env_file_configured": env_exists,
            "sqlite_db_exists": db_exists,
            "python_version": sys.version,
        }
        report_path = os.path.join(self.data_dir, "health_status.json")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=4)
        except Exception as exc:
            logger.error(f"Failed to write health report: {exc}")
        return report

    def log_error(self, error: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            **error,
        }
        try:
            with open(self.error_history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as exc:
            logger.error(f"Failed to log error: {exc}")

    def detect_anomalies(self) -> list[dict[str, Any]]:
        anomalies: list[dict[str, Any]] = []
        error_count = 0
        rate_spike = False
        latency_delta = 0.0
        failed_api_calls = 0
        if os.path.exists(self.error_history_path):
            recent_errors: list[dict[str, Any]] = []
            cutoff = datetime.now(UTC) - timedelta(minutes=10)
            with open(self.error_history_path, encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        ts = datetime.fromisoformat(record["timestamp"])
                        if ts >= cutoff:
                            recent_errors.append(record)
                    except Exception as e:
                        try:
                            import loguru

                            loguru.logger.error(f"Tool execution error: {e}")
                        except Exception as e:
                            logger.warning(f"Exception suppressed: {e}")
                        continue
            error_count = len(recent_errors)
            if error_count > 20:
                rate_spike = True
                anomalies.append(
                    {
                        "type": "error_rate_spike",
                        "details": f"{error_count} errors in last 10 minutes",
                        "severity": "HIGH",
                    }
                )
        if rate_spike:
            failed_api_calls = error_count
            anomalies.append(
                {
                    "type": "failed_api_calls",
                    "details": f"Estimated {failed_api_calls} failed calls",
                    "severity": "MEDIUM",
                }
            )
        if latency_delta > 2.0:
            anomalies.append(
                {
                    "type": "latency_increase",
                    "details": f"Latency increased by {latency_delta:.2f}s",
                    "severity": "MEDIUM",
                }
            )
        return anomalies

    async def report_to_admin(self, anomalies: list[dict[str, Any]]) -> bool:
        if not anomalies:
            return False
        lines = ["Anomaly Detection Alert"]
        for anomaly in anomalies:
            lines.append(
                "[" + anomaly["severity"] + "] " + anomaly["type"] + ": " + anomaly["details"]
            )
        text = "\n".join(lines)
        if not self.telegram_bot_token or not self.admin_chat_id:
            logger.warning("Telegram credentials not configured; anomaly report not sent")
            return False
        try:
            import httpx

            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json={"chat_id": self.admin_chat_id, "text": text})
            return True
        except Exception as exc:
            logger.error(f"Failed to report anomaly: {exc}")
            return False

    def propose_solutions(self, anomaly: dict[str, Any]) -> list[str]:
        anomaly_type = anomaly.get("type")
        if anomaly_type == "error_rate_spike":
            return [
                "Check logs for new exceptions",
                "Verify recent API deployments",
                "Enable circuit breaker",
            ]
        if anomaly_type == "failed_api_calls":
            return [
                "Verify provider API keys",
                "Switch to fallback provider",
                "Review rate limits",
            ]
        if anomaly_type == "latency_increase":
            return [
                "Enable query caching",
                "Review database indexes",
                "Scale horizontally",
            ]
        return ["Investigate system logs", "Run HealthChecker.run_health_check()"]
