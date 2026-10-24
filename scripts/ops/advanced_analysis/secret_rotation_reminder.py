#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  SUPREMEAI — Secret Rotation Reminder                                        ║
║  secrets_registry.yaml থেকে সব সিক্রেট পার্স করে রোটেশন বয়স চেক করে           ║
║  Priority: 🔴 HIGH                                                            ║
║  Stdlib Only | No PyYAML | Regex YAML Parser                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝

প্রতিটি সিক্রেটের বয়স চেক করে রোটেশন প্রয়োজন কিনা তা নির্ধারণ করে:
  • secrets_registry.yaml থেকে সিক্রেটের নাম, গুরুত্ব ও মেটাডাটা বের করে
  • git log / file mtime থেকে শেষ আপডেটের সময় নির্ধারণ করে
  • API keys, Credentials, Configuration হিসেবে শ্রেণীবদ্ধ করে
  • Slack/Discord-এ পাঠানোর মতো সংক্ষিপ্ত রিমাইন্ডার তৈরি করে

Usage:
    python secret_rotation_reminder.py
    python secret_rotation_reminder.py --reminder
    python secret_rotation_reminder.py --json
    python secret_rotation_reminder.py --critical-days 60 --warning-days 30

Exit Codes:
    0 = সব সিক্রেট ফ্রেশ
    1 = এক বা একাধিক সিক্রেট ওভারডিউ
    2 = ত্রুটি (ফাইল খুঁজে পাওয়া যায়নি, git ত্রুটি ইত্যাদি)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# ধ্রুবক ও কনফিগারেশন
# ═══════════════════════════════════════════════════════════════════════════════

# রিপো রুট ডিরেক্টরি — এই স্ক্রিপ্ট যেখান থেকেই চালানো হোক না কেন
REPO_ROOT = Path(__file__).resolve().parent.parent

# ফাইলের অবস্থান
SECRETS_REGISTRY_PATH = REPO_ROOT / "secrets_registry.yaml"
RENDER_YAML_PATH = REPO_ROOT / "render.yaml"
ENV_FILE_PATH = REPO_ROOT / ".env"

# ডিফল্ট রোটেশন নীতি (দিন)
DEFAULT_CRITICAL_DAYS = 90   # এর বেশি হলে OVERDUE 🔴
DEFAULT_WARNING_DAYS = 60    # এর মধ্যে হলে DUE SOON 🟡

# API key প্যাটার্ন — এরা বেশি ঘনঘন রোটেট করা উচিত
API_KEY_PATTERNS = re.compile(
    r"(.*(_API_KEY|_KEY|_TOKEN|_SIGNING_SECRET|_WEBHOOK_SECRET).*)",
    re.IGNORECASE,
)

# Credential প্যাটার্ন — এরাও সংবেদনশীল
CREDENTIAL_PATTERNS = re.compile(
    r"(.*(_PASSWORD|_SECRET|_CREDENTIAL|_PRIVATE_KEY|_PASSPHRASE).*)",
    re.IGNORECASE,
)

# স্ট্যাটাস আইকন
STATUS_OVERDUE = "🔴 OVERDUE"
STATUS_DUE_SOON = "🟡 DUE SOON"
STATUS_FRESH = "🟢 FRESH"


# ═══════════════════════════════════════════════════════════════════════════════
# ডাটা ক্লাস ও টাইপ
# ═══════════════════════════════════════════════════════════════════════════════

class SecretEntry:
    """একটি সিক্রেটের সম্পূর্ণ তথ্য ধারণ করে।"""

    __slots__ = (
        "name", "criticality_map", "note", "category",
        "age_days", "status", "last_modified", "highest_criticality",
    )

    def __init__(
        self,
        name: str,
        criticality_map: dict[str, str],
        note: str = "",
    ):
        self.name = name
        self.criticality_map = criticality_map
        self.note = note
        self.age_days: int = 0
        self.status: str = STATUS_FRESH
        self.last_modified: str = "unknown"
        # সর্বোচ্চ গুরুত্ব নির্ধারণ — critical > important > optional
        self.highest_criticality = self._compute_highest_criticality()
        # শ্রেণীবিভাগ: api_key, credential, configuration
        self.category = self._categorize()

    def _compute_highest_criticality(self) -> str:
        """সব env-তে সর্বোচ্চ criticality খুঁজে বের করে।"""
        values = self.criticality_map.values()
        if "critical" in values:
            return "critical"
        if "important" in values:
            return "important"
        return "optional"

    def _categorize(self) -> str:
        """সিক্রেটের নাম দেখে শ্রেণী নির্ধারণ করে।

        API keys ও Credentials বেশি সংবেদনশীল, তাই তাদের রোটেশন থ্রেশহোল্ড
        কম হওয়া উচিত।
        """
        if API_KEY_PATTERNS.match(self.name):
            return "api_key"
        if CREDENTIAL_PATTERNS.match(self.name):
            return "credential"
        return "configuration"

    def to_dict(self) -> dict[str, Any]:
        """ডিকশনারি হিসেবে রিটার্ন করে — JSON আউটপুটের জন্য।"""
        return {
            "name": self.name,
            "category": self.category,
            "highest_criticality": self.highest_criticality,
            "criticality": self.criticality_map,
            "note": self.note,
            "age_days": self.age_days,
            "status": self.status,
            "last_modified": self.last_modified,
        }


class RotationReport:
    """সম্পূর্ণ রোটেশন রিপোর্ট ধারণ করে।"""

    def __init__(self) -> None:
        self.secrets: list[SecretEntry] = []
        self.checked_at: str = datetime.now(timezone.utc).isoformat()
        self.files_checked: list[str] = []
        self.errors: list[str] = []

    @property
    def overdue_count(self) -> int:
        return sum(1 for s in self.secrets if s.status == STATUS_OVERDUE)

    @property
    def due_soon_count(self) -> int:
        return sum(1 for s in self.secrets if s.status == STATUS_DUE_SOON)

    @property
    def fresh_count(self) -> int:
        return sum(1 for s in self.secrets if s.status == STATUS_FRESH)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_at": self.checked_at,
            "files_checked": self.files_checked,
            "summary": {
                "total": len(self.secrets),
                "overdue": self.overdue_count,
                "due_soon": self.due_soon_count,
                "fresh": self.fresh_count,
            },
            "errors": self.errors,
            "secrets": [s.to_dict() for s in self.secrets],
        }


# ═══════════════════════════════════════════════════════════════════════════════
# রেজেক্স-ভিত্তিক YAML পার্সার (কোনো বাহ্যিক ডিপেন্ডেন্সি নেই)
# ═══════════════════════════════════════════════════════════════════════════════

def parse_yaml_registry(raw_text: str) -> list[dict[str, Any]]:
    """secrets_registry.yaml থেকে রেজেক্স দিয়ে সিক্রেটের তালিকা বের করে।

    প্রতিটি এন্ট্রি এই ফরম্যাটে থাকে:
      - name: SECRET_NAME
        criticality: {env: level, ...}
        note: "..."

    আমরা ব্লক দ্বারা ব্লক পার্স করি — প্রতিটি `- name:` থেকে পরবর্তী
    `- name:` বা ফাইলের শেষ পর্যন্ত।
    """
    entries: list[dict[str, Any]] = []
    # প্রতিটি এন্ট্রি ব্লক খুঁজে বের করি
    # প্যাটার্ন: "- name:" দিয়ে শুরু, পরবর্তী "- name:" বা ফাইল শেষে শেষ
    blocks = re.split(r"(?=^\s*-\s+name:\s+)", raw_text, flags=re.MULTILINE)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # নাম বের করা
        name_match = re.search(r"^-\s+name:\s*(.+)$", block, re.MULTILINE)
        if not name_match:
            continue
        name = name_match.group(1).strip()

        # কমেন্ট লাইন এড়িয়ে যাওয়া — YAML-এ # দিয়ে শুরু হয়
        if name.startswith("#"):
            continue

        # criticality বের করা — ইনলাইন ফরম্যাট: {key: val, key: val}
        criticality_match = re.search(r"criticality:\s*\{(.+?)\}", block)
        criticality_map: dict[str, str] = {}
        if criticality_match:
            inner = criticality_match.group(1)
            # "env: level" জোড়া পার্স করা
            pairs = re.findall(r"(\S+?):\s*(critical|important|optional)", inner)
            criticality_map = dict(pairs)

        # note বের করা
        note_match = re.search(r'note:\s*"(.+?)"', block)
        note = note_match.group(1).strip() if note_match else ""

        # যদি note-এর ভেতরে কোটেড স্ট্রিং না থাকে, unquoted-ও চেষ্টা করা
        if not note:
            note_match2 = re.search(r"note:\s*(.+?)$", block, re.MULTILINE)
            if note_match2:
                note = note_match2.group(1).strip().rstrip(",")

        entries.append({
            "name": name,
            "criticality": criticality_map,
            "note": note,
        })

    return entries


def parse_render_yaml_env_vars(raw_text: str) -> list[str]:
    """render.yaml থেকে env var নাম বের করে।

    এগুলো অতিরিক্ত সিক্রেট হিসেবে বিবেচিত হতে পারে।
    """
    env_keys: list[str] = []
    # envVars ব্লকের ভেতরে key: খুঁজে বের করা
    # ইনডেন্টেশন সহ key: pattern
    matches = re.findall(r"^\s+key:\s*(.+)$", raw_text, re.MULTILINE)
    for m in matches:
        key = m.strip().strip('"').strip("'")
        # কমেন্ট এড়ানো
        if key and not key.startswith("#"):
            env_keys.append(key)
    return env_keys


# ═══════════════════════════════════════════════════════════════════════════════
# বয়স নির্ধারণ — git log ও file mtime
# ═══════════════════════════════════════════════════════════════════════════════

def get_git_last_modified(filepath: Path) -> datetime | None:
    """git log থেকে ফাইলের শেষ কমিটের তারিখ বের করে।

    এটি সবচেয়ে নির্ভরযোগ্য উৎস কারণ ফাইল mtime পরিবর্তন হতে পারে
    (যেমন git checkout বা rebase-এর সময়)।
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%aI", "--", str(filepath)],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(REPO_ROOT),
        )
        if result.returncode == 0 and result.stdout.strip():
            # ISO 8601 ফরম্যাট পার্স করা
            date_str = result.stdout.strip()
            # টাইমজোন সহ বা বিনা টাইমজোন
            if "+" in date_str or date_str.endswith("Z"):
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            else:
                # টাইমজোন না থাকলে UTC ধরে নেওয়া
                return datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        # git পাওয়া যায়নি বা রিপো নেই
        pass
    return None


def get_file_mtime(filepath: Path) -> datetime | None:
    """ফাইলের মডিফিকেশন টাইম বের করে — ফলব্যাক হিসেবে।

    git log ব্যর্থ হলে এটি ব্যবহার করা হয়।
    """
    if filepath.exists():
        try:
            mtime = filepath.stat().st_mtime
            return datetime.fromtimestamp(mtime, tz=timezone.utc)
        except OSError:
            print('Silenced error in except block')
    return None


def determine_last_modified(
    filepath: Path,
) -> tuple[datetime | None, str]:
    """ফাইলের শেষ পরিবর্তনের তারিখ নির্ধারণ করে।

    প্রথমে git log চেষ্টা করে, ব্যর্থ হলে file mtime ব্যবহার করে।
    (source, datetime) টাপল রিটার্ন করে।
    """
    git_date = get_git_last_modified(filepath)
    if git_date is not None:
        return git_date, "git"

    mtime = get_file_mtime(filepath)
    if mtime is not None:
        return mtime, "mtime"

    return None, "unknown"


def compute_age_days(last_modified: datetime | None) -> int:
    """আজ থেকে শেষ পরিবর্তনের মধ্যে কতদিন তা বের করে।

    তারিখ না পাওয়া গেলে সর্বোচ্চ বয়স ধরে নেওয়া হয় (সতর্কতামূলক)।
    """
    if last_modified is None:
        # তারিখ জানা না থাকলে সবচেয়ে কঠোর অনুমান — অনেক পুরনো
        return 9999
    now = datetime.now(timezone.utc)
    delta = now - last_modified
    return max(0, delta.days)


# ═══════════════════════════════════════════════════════════════════════════════
# স্ট্যাটাস নির্ধারণ
# ═══════════════════════════════════════════════════════════════════════════════

def determine_status(
    age_days: int,
    category: str,
    critical_days: int,
    warning_days: int,
) -> str:
    """সিক্রেটের বয়স ও শ্রেণী অনুযায়ী স্ট্যাটাস নির্ধারণ করে।

    API keys ও Credentials-এর থ্রেশহোল্ড কম — তারা বেশি ঝুঁকিপূর্ণ।
    যেমন: critical_days=90 হলে API key-এর জন্য 90*0.6=54 দিনে OVERDUE।
    """
    # API key ও Credential-এর জন্য থ্রেশহোল্ড কমিয়ে দেওয়া হয়
    if category in ("api_key", "credential"):
        effective_critical = int(critical_days * 0.6)
        effective_warning = int(warning_days * 0.6)
    else:
        effective_critical = critical_days
        effective_warning = warning_days

    if age_days > effective_critical:
        return STATUS_OVERDUE
    elif age_days >= effective_warning:
        return STATUS_DUE_SOON
    else:
        return STATUS_FRESH


def get_rotation_suggestion(secret: SecretEntry) -> str:
    """প্রতিটি ওভারডিউ সিক্রেটের জন্য রোটেশন কমান্ড/সাজেশন তৈরি করে।

    ব্যবহারকারীকে নির্দিষ্ট পদক্ষেপ বলে দেয়।
    """
    name = secret.name
    if secret.category == "api_key":
        return (
            f"  → Infisical-এ রোটেট করুন: "
            f"infisical update --env=production --secret-name={name}"
        )
    elif secret.category == "credential":
        return (
            f"  → নতুন {name} তৈরি করুন ও Render/Infisical-এ আপডেট করুন"
        )
    else:
        return (
            f"  → পর্যালোচনা করুন: {name} "
            f"(কনফিগারেশন মান, রোটেশন ঐচ্ছিক)"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# মূল লজিক
# ═══════════════════════════════════════════════════════════════════════════════

def build_rotation_report(
    critical_days: int,
    warning_days: int,
) -> RotationReport:
    """সম্পূর্ণ রোটেশন রিপোর্ট তৈরি করে।

    ধাপসমূহ:
    1. secrets_registry.yaml পার্স করা
    2. render.yaml থেকে অতিরিক্ত env var সংগ্রহ করা
n    3. প্রতিটি ফাইলের শেষ পরিবর্তনের তারিখ নির্ধারণ করা
    4. প্রতিটি সিক্রেটের বয়স ও স্ট্যাটাস হিসাব করা
    """
    report = RotationReport()

    # ── ধাপ ১: secrets_registry.yaml পার্স করা ──
    if not SECRETS_REGISTRY_PATH.exists():
        report.errors.append(
            f"secrets_registry.yaml পাওয়া যায়নি: {SECRETS_REGISTRY_PATH}"
        )
        return report

    try:
        raw = SECRETS_REGISTRY_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        report.errors.append(f"secrets_registry.yaml পড়তে ত্রুটি: {exc}")
        return report

    entries = parse_yaml_registry(raw)
    if not entries:
        report.errors.append("secrets_registry.yaml-এ কোনো সিক্রেট পাওয়া যায়নি")
        return report

    # ── ধাপ ২: render.yaml থেকে অতিরিক্ত env var ──
    render_env_names: set[str] = set()
    if RENDER_YAML_PATH.exists():
        try:
            render_raw = RENDER_YAML_PATH.read_text(encoding="utf-8")
            render_env_names = set(parse_render_yaml_env_vars(render_raw))
        except OSError as exc:
            report.errors.append(f"render.yaml পড়তে ত্রুটি: {exc}")

    # ── ধাপ ৩: ফাইল মডিফিকেশন তারিখ সংগ্রহ ──
    # প্রতিটি সিক্রেট ফাইলের তারিখ ম্যাপিং
    file_dates: dict[str, tuple[datetime | None, str]] = {}

    for fpath in [SECRETS_REGISTRY_PATH, RENDER_YAML_PATH, ENV_FILE_PATH]:
        if fpath.exists():
            dt, source = determine_last_modified(fpath)
            file_dates[fpath.name] = (dt, source)
            report.files_checked.append(fpath.name)

    # ── ধাপ ৪: প্রতিটি সিক্রেটের বয়স ও স্ট্যাটাস হিসাব ──
    # সবচেয়ে সাম্প্রতিক পরিবর্তনের তারিখ ব্যবহার করা হবে
    all_dates = [
        dt for dt, _ in file_dates.values() if dt is not None
    ]
    most_recent_date = max(all_dates) if all_dates else None

    for entry in entries:
        secret = SecretEntry(
            name=entry["name"],
            criticality_map=entry["criticality"],
            note=entry.get("note", ""),
        )

        # বয়স নির্ধারণ — সবচেয়ে সাম্প্রতিক ফাইল পরিবর্তনের উপর ভিত্তি করে
        # এটি রক্ষণশীল অনুমান: সব সিক্রেট একই সময়ে আপডেট হয়ে থাকতে পারে
        secret.age_days = compute_age_days(most_recent_date)

        # শেষ পরিবর্তনের তথ্য
        if most_recent_date is not None:
            secret.last_modified = most_recent_date.strftime("%Y-%m-%d %H:%M UTC")
        else:
            secret.last_modified = "unknown (git ও mtime উভয় ব্যর্থ)"

        # স্ট্যাটাস নির্ধারণ — শ্রেণী অনুযায়ী থ্রেশহোল্ড পরিবর্তন হয়
        secret.status = determine_status(
            secret.age_days,
            secret.category,
            critical_days,
            warning_days,
        )

        report.secrets.append(secret)

    # render.yaml থেকে আসা env var যা registry-তে নেই — তাদেরও যোগ করা
    registry_names = {e["name"] for e in entries}
    for env_name in sorted(render_env_names - registry_names):
        secret = SecretEntry(
            name=env_name,
            criticality_map={},
            note="render.yaml থেকে সংগৃহীত (registry-তে নেই)",
        )
        secret.age_days = compute_age_days(most_recent_date)
        if most_recent_date is not None:
            secret.last_modified = most_recent_date.strftime("%Y-%m-%d %H:%M UTC")
        secret.status = determine_status(
            secret.age_days,
            secret.category,
            critical_days,
            warning_days,
        )
        report.secrets.append(secret)

    # নাম অনুসারে সাজানো
    report.secrets.sort(key=lambda s: s.name)

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# আউটপুট ফরম্যাটার
# ═══════════════════════════════════════════════════════════════════════════════

def format_full_report(report: RotationReport) -> str:
    """সম্পূর্ণ রিপোর্ট টার্মিনালে দেখানোর জন্য ফরম্যাট করে।

    প্রতিটি সিক্রেট তার বয়স, স্ট্যাটাস ও গুরুত্ব সহ দেখায়।
    CRITICAL + OVERDUE সিক্রেটে ডাবল অ্যালার্ট দেওয়া হয়।
    """
    lines: list[str] = []
    lines.append("")
    lines.append("╔══════════════════════════════════════════════════════════════════════════════╗")
    lines.append("║  🔐 SUPREMEAI — Secret Rotation Reminder                               ║")
    lines.append("╚══════════════════════════════════════════════════════════════════════════════╝")
    lines.append(f"  পরীক্ষার সময়: {report.checked_at}")
    lines.append(f"  ফাইল চেক করা হয়েছে: {', '.join(report.files_checked) or 'কোনোটি নয়'}")
    lines.append("")

    # সারাংশ
    lines.append("── সারাংশ ──────────────────────────────────────────────────────────")
    lines.append(f"  মোট সিক্রেট: {len(report.secrets)}")
    lines.append(f"  🔴 ওভারডিউ:   {report.overdue_count}")
    lines.append(f"  🟡 শীঘ্রই:   {report.due_soon_count}")
    lines.append(f"  🟢 ফ্রেশ:     {report.fresh_count}")
    lines.append("")

    # ত্রুটি থাকলে দেখানো
    if report.errors:
        lines.append("── ত্রুটি ───────────────────────────────────────────────────────────")
        for err in report.errors:
            lines.append(f"  ⚠️  {err}")
        lines.append("")

    # ওভারডিউ সিক্রেট — সবচেয়ে গুরুত্বপূর্ণ
    overdue_secrets = [s for s in report.secrets if s.status == STATUS_OVERDUE]
    if overdue_secrets:
        lines.append("── 🔴 ওভারডিউ সিক্রেট (তৎক্ষণাৎ রোটেশন প্রয়োজন) ─────────────────")
        for s in overdue_secrets:
            # ডাবল অ্যালার্ট: CRITICAL ও OVERDUE উভয় হলে
            double_alert = ""
            if s.highest_criticality == "critical":
                double_alert = "  ⚠️⚠️ CRITICAL + OVERDUE — অবিলম্বে রোটেট করুন!"
            lines.append(f"")
            lines.append(f"  {s.status} | {s.name}")
            lines.append(f"    শ্রেণী: {s.category} | গুরুত্ব: {s.highest_criticality} | বয়স: {s.age_days} দিন")
            if s.note:
                lines.append(f"    বিবরণ: {s.note}")
            lines.append(get_rotation_suggestion(s))
            if double_alert:
                lines.append(double_alert)

        lines.append("")

    # শীঘ্রই রোটেশন প্রয়োজন
    due_soon_secrets = [s for s in report.secrets if s.status == STATUS_DUE_SOON]
    if due_soon_secrets:
        lines.append("── 🟡 শীঘ্রই রোটেশন প্রয়োজন ───────────────────────────────────")
        for s in due_soon_secrets:
            lines.append(f"")
            lines.append(f"  {s.status} | {s.name}")
            lines.append(f"    শ্রেণী: {s.category} | গুরুত্ব: {s.highest_criticality} | বয়স: {s.age_days} দিন")
            if s.note:
                lines.append(f"    বিবরণ: {s.note}")
        lines.append("")

    # ফ্রেশ সিক্রেট
    fresh_secrets = [s for s in report.secrets if s.status == STATUS_FRESH]
    if fresh_secrets:
        lines.append("── 🟢 ফ্রেশ সিক্রেট ───────────────────────────────────────────")
        for s in fresh_secrets:
            crit_marker = "" if s.highest_criticality == "optional" else f" [{s.highest_criticality}]"
            lines.append(
                f"  🟢 {s.name:<45s} {s.age_days:>4d}d  {s.category:<15s}{crit_marker}"
            )
        lines.append("")

    # শ্রেণী অনুসারে সারাংশ
    lines.append("── শ্রেণী অনুসারে ────────────────────────────────────────────────────")
    for cat_name, cat_label in [
        ("api_key", "API Keys"),
        ("credential", "Credentials"),
        ("configuration", "Configuration"),
    ]:
        cat_secrets = [s for s in report.secrets if s.category == cat_name]
        if cat_secrets:
            cat_overdue = sum(1 for s in cat_secrets if s.status == STATUS_OVERDUE)
            cat_due = sum(1 for s in cat_secrets if s.status == STATUS_DUE_SOON)
            cat_fresh = sum(1 for s in cat_secrets if s.status == STATUS_FRESH)
            lines.append(
                f"  {cat_label:<15s}: {len(cat_secrets)} total | "
                f"🔴 {cat_overdue} | 🟡 {cat_due} | 🟢 {cat_fresh}"
            )
    lines.append("")

    return "\n".join(lines)


def format_reminder(report: RotationReport) -> str:
    """Slack/Discord-এ পাঠানোর জন্য সংক্ষিপ্ত রিমাইন্ডার তৈরি করে।

    শুধুমাত্র ওভারডিউ আইটেম দেখায় — সবাই জানতে চায় কী কী ভাঙা।
    """
    if report.overdue_count == 0 and report.due_soon_count == 0:
        return (
            "🔐 *SupremeAI Secret Rotation*: সব সিক্রেট ফ্রেশ — কোনো পদক্ষেপের প্রয়োজন নেই ✅"
        )

    lines: list[str] = []
    lines.append("🔐 *SupremeAI Secret Rotation Reminder*")
    lines.append("")

    if report.overdue_count > 0:
        lines.append(f"🔴 *{report.overdue_count} OVERDUE* (তৎক্ষণাৎ রোটেশন প্রয়োজন):")
        for s in report.secrets:
            if s.status != STATUS_OVERDUE:
                continue
            marker = " ⚠️CRITICAL" if s.highest_criticality == "critical" else ""
            lines.append(f"  • `{s.name}` — {s.age_days}d old [{s.category}]{marker}")
        lines.append("")

    if report.due_soon_count > 0:
        lines.append(f"🟡 *{report.due_soon_count} DUE SOON*:")
        for s in report.secrets:
            if s.status != STATUS_DUE_SOON:
                continue
            lines.append(f"  • `{s.name}` — {s.age_days}d old [{s.category}]")
        lines.append("")

    lines.append(f"📊 মোট: {len(report.secrets)} | 🟢 ফ্রেশ: {report.fresh_count}")
    return "\n".join(lines)


def format_json(report: RotationReport) -> str:
    """JSON ফরম্যাটে রিপোর্ট রিটার্ন করে — CI/CD pipeline-এ ব্যবহারের জন্য।"""
    return json.dumps(report.to_dict(), indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI এন্ট্রি পয়েন্ট
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> int:
    """মূল ফাংশন — আর্গুমেন্ট পার্স করে রিপোর্ট তৈরি করে।

    এক্সিট কোড:
      0 = সব সিক্রেট ফ্রেশ (কোনো সমস্যা নেই)
      1 = এক বা একাধিক সিক্রেট ওভারডিউ (মনোযোগ প্রয়োজন)
      2 = ত্রুটি ঘটেছে (ফাইল নেই, git ব্যর্থ ইত্যাদি)
    """
    parser = argparse.ArgumentParser(
        description="SupremeAI Secret Rotation Reminder — সিক্রেট রোটেশনের স্থিতি পরীক্ষা করুন",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
উদাহরণ:
  %(prog)s                          # সম্পূর্ণ রিপোর্ট
  %(prog)s --reminder               # Slack/Discord ফরম্যাট
  %(prog)s --json                   # JSON আউটপুট
  %(prog)s --critical-days 60       # কাস্টম থ্রেশহোল্ড
  %(prog)s --critical-days 60 --warning-days 30

এক্সিট কোড: 0=ফ্রেশ, 1=ওভারডিউ, 2=ত্রুটি
        """,
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="JSON ফরম্যাটে আউটপুট (CI/CD-এ ব্যবহারের জন্য)",
    )
    parser.add_argument(
        "--reminder",
        action="store_true",
        help="সংক্ষিপ্ত রিমাইন্ডার (Slack/Discord webhook-এ পাঠানোর জন্য)",
    )
    parser.add_argument(
        "--critical-days",
        type=int,
        default=DEFAULT_CRITICAL_DAYS,
        help=f"OVERDUE থ্রেশহোল্ড দিন (ডিফল্ট: {DEFAULT_CRITICAL_DAYS})",
    )
    parser.add_argument(
        "--warning-days",
        type=int,
        default=DEFAULT_WARNING_DAYS,
        help=f"DUE SOON থ্রেশহোল্ড দিন (ডিফল্ট: {DEFAULT_WARNING_DAYS})",
    )

    args = parser.parse_args()

    # থ্রেশহোল্ড যাচাই — warning < critical হতে হবে
    if args.warning_days >= args.critical_days:
        print(
            f"ত্রুটি: --warning-days ({args.warning_days}) অবশ্যই "
            f"--critical-days ({args.critical_days}) থেকে কম হতে হবে",
            file=sys.stderr,
        )
        return 2

    # রিপোর্ট তৈরি করা
    report = build_rotation_report(
        critical_days=args.critical_days,
        warning_days=args.warning_days,
    )

    # ত্রুটি থাকলে এক্সিট কোড 2
    has_errors = len(report.errors) > 0 and len(report.secrets) == 0

    # আউটপুট ফরম্যাট নির্বাচন
    if args.json_output:
        print(format_json(report))
    elif args.reminder:
        print(format_reminder(report))
    else:
        print(format_full_report(report))

    # এক্সিট কোড নির্ধারণ
    if has_errors:
        return 2
    if report.overdue_count > 0:
        return 1
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# স্ক্রিপ্ট এক্সিকিউশন
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    sys.exit(main())
