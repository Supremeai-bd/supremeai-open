from __future__ import annotations

import os
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

from core.config import settings
from core.logging_config import logger


class MonthlyCostReporter:
    def __init__(self) -> None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(base_dir, "data")
        self.db_path = os.path.join(self.data_dir, "supreme_memory.db")
        self.admin_chat_id = getattr(settings, "admin_telegram_chat_id", "")
        self.telegram_bot_token = getattr(settings, "telegram_bot_token", "")

    def _get_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def generate_report(self, month: str) -> dict[str, Any]:
        start, end = self._month_range(month)
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(cost), COUNT(*), AVG(cost) FROM tasks WHERE timestamp >= ? AND timestamp < ?",
            (start.isoformat(), end.isoformat()),
        )
        row = cursor.fetchone()
        conn.close()
        total_cost = row[0] or 0.0
        total_calls = row[1] or 0
        avg_cost = row[2] or 0.0
        return {
            "month": month,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "total_cost_usd": round(total_cost, 4),
            "total_calls": total_calls,
            "average_cost_per_call": round(avg_cost, 4),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def _month_range(self, month: str) -> tuple[datetime, datetime]:
        start = (
            datetime.strptime(month, "%Y-%m") if "-" in month else datetime.strptime(month, "%Y%m")
        )
        next_month = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = next_month
        return start, end

    async def send_to_admin(self, report: dict[str, Any]) -> bool:
        text = (
            f"Monthly Cost Report - {report['month']}\n"
            f"Total cost: ${report['total_cost_usd']:.4f}\n"
            f"Total calls: {report['total_calls']}\n"
            f"Avg cost/call: ${report['average_cost_per_call']:.4f}"
        )
        if not self.telegram_bot_token or not self.admin_chat_id:
            logger.warning("Telegram credentials not configured; cost report not sent")
            return False
        try:
            import httpx

            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(url, json={"chat_id": self.admin_chat_id, "text": text})
            return True
        except Exception as exc:
            logger.error(f"Failed to send monthly cost report: {exc}")
            return False

    def schedule_monthly(self) -> None:
        # next run = start of the FOLLOWING month, i.e. the END of the current
        # month window. _month_range returns (window_start, window_end); the
        # previous unpack took window_start, logging the current month start
        # as the "next run" (off-by-one-month in the scheduler log).
        _, next_run = self._month_range(datetime.now(UTC).strftime("%Y-%m"))
        logger.info(f"Monthly cost run scheduled for {next_run.isoformat()}")
