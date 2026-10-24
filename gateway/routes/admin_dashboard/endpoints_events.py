"""Dashboard events + standup report endpoints (GET /admin-api/events, GET /admin-api/reports)."""

import json
import os

from fastapi import HTTPException, Query

from api.routes.admin_dashboard import router
from core.logging_config import logger


@router.get("/events")
async def get_events(limit: int = Query(50, ge=1, le=200)):
    # বাংলা মন্তব্য: রিয়েল-টাইম সিস্টেম ইভেন্টগুলো (যা আগে Slack/Discord এ যেত) JSONL ফাইল থেকে রিটার্ন করার এন্ডপয়েন্ট
    events_log_path = "data/dashboard_events.jsonl"
    if not os.path.exists(events_log_path):
        events_log_path = "/app/data/dashboard_events.jsonl"

    if not os.path.exists(events_log_path):
        return []

    try:
        with open(events_log_path, encoding="utf-8") as f:
            lines = f.readlines()

        events = []
        for line in reversed(lines):
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning(f"Skipping malformed event log line: {line.strip()}")

        return events[:limit]
    except Exception as e:
        logger.error(f"Error reading events log: {e}")
        raise HTTPException(status_code=500, detail="Could not read event logs.") from e


@router.get("/reports")
async def list_reports(report_name: str | None = None):
    # বাংলা মন্তব্য: ডিরেক্টরি থেকে দৈনিক স্ট্যান্ডআপ রিপোর্টের মতো ফাইলগুলো স্ট্যান্ডআপ রিপোর্টের মতো ফাইলগুলো তালিকাভুক্ত বা নির্দিষ্ট রিপোর্ট রিট্রিভ করার এন্ডপয়েন্ট
    reports_dir = "data/reports"
    if not os.path.isdir(reports_dir):
        reports_dir = "/app/data/reports"

    if not os.path.isdir(reports_dir):
        return {"reports": []}

    if report_name:
        import re

        if not re.fullmatch(r"[A-Za-z0-9_\-]+", report_name):
            raise HTTPException(status_code=400, detail="Invalid report name.")

        file_path = os.path.join(reports_dir, f"{os.path.basename(report_name)}.md")

        # Verify resolved path is inside reports_dir (Defense in depth)
        if not os.path.realpath(file_path).startswith(os.path.realpath(reports_dir)):
            raise HTTPException(status_code=400, detail="Invalid path.")

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Report not found.")
        with open(file_path, encoding="utf-8") as f:
            return {"name": report_name, "content": f.read()}
    else:
        import glob

        report_files = glob.glob(f"{reports_dir}/*.md")
        return {"reports": [os.path.basename(f).replace(".md", "") for f in report_files]}
