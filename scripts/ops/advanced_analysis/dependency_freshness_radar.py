#!/usr/bin/env python3
"""
Dependency Freshness Radar — SupremeAI Codebase

অফলাইনে ডিপেন্ডেন্সি ফ্রেশনেস চেক করে। নেটওয়ার্ক কল ছাড়াই git history ও লকফাইল
মডিফিকেশন টাইম থেকে প্রতিটি প্যাকেজের শেষ আপডেটের সময় নির্ধারণ করে।

ব্যবহার:
    python scripts/dependency_freshness_radar.py
    python scripts/dependency_freshness_radar.py --json
    python scripts/dependency_freshness_radar.py --diff previous_run.json
    python scripts/dependency_freshness_radar.py --python-only
    python scripts/dependency_freshness_radar.py --js-only
    python scripts/dependency_freshness_radar.py --security-only

এক্সিট কোড:
    0 — সব ডিপেন্ডেন্সি ফ্রেশ
    1 — স্টেল ডিপেন্ডেন্সি আছে
    2 — ত্রুটি ঘটেছে
"""

import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# ধ্রুবক ও কনফিগারেশন
# ═══════════════════════════════════════════════════════════════════════════════

REPO_ROOT = Path(__file__).resolve().parent.parent

# ফাইল পথ — রিপো রুট থেকে আপেক্ষিক
PYPROJECT_TOML = REPO_ROOT / "backend" / "pyproject.toml"
REQUIREMENTS_TXT = REPO_ROOT / "backend" / "requirements.txt"
ROOT_PACKAGE_JSON = REPO_ROOT / "package.json"
FRONTEND_PACKAGE_JSON = REPO_ROOT / "frontend" / "package.json"
PNPM_LOCK = REPO_ROOT / "pnpm-lock.yaml"
POETRY_LOCK = REPO_ROOT / "backend" / "poetry.lock"

# বয়স শ্রেণী নির্ধারণের সীমা (দিন)
FRESH_THRESHOLD = 90       # 🟢 ফ্রেশ: ৯০ দিনের মধ্যে আপডেট
AGING_THRESHOLD = 180      # 🟡 এজিং: ৯০-১৮০ দিন
# 🔴 স্টেল: ১৮০ দিনের বেশি

# ডিপেন্ডেন্সি ক্যাটাগরি — নাম ছোট হাতের অক্ষরে ম্যাচ করা হবে
SECURITY_CRITICAL = {
    "cryptography", "pyjwt", "passlib", "boto3", "firebase-admin",
    "bcrypt", "defusedxml", "python-dotenv", "pydantic-settings",
    "aiohttp", "pillow", "stripe", "google-auth", "google-auth-oauthlib",
    "google-auth-httplib2", "pyasn1", "litellm", "infisical-python",
    "firebase", "ioredis", "axios", "authlib", "pynacl",
}

CORE_FRAMEWORK = {
    "fastapi", "uvicorn", "starlette-context", "sqlalchemy", "alembic",
    "pydantic", "pydantic-settings", "pydantic-extra-types", "pydantic-ai",
    "redis", "asyncpg", "aiosqlite", "react", "react-dom", "react-router-dom",
    "next", "vite", "typescript", "tailwindcss", "eslint", "vitest",
    "playwright", "@tanstack/react-query", "zustand", "framer-motion",
    "recharts", "@vitejs/plugin-react", "langfuse", "openai", "anthropic",
    "mcp", "supabase", "qdrant-client", "neo4j", "monaco-editor",
    "@xyflow/react", "lucide-react", "@dnd-kit/core", "@dnd-kit/sortable",
    "opentelemetry-sdk", "opentelemetry-api",
    "opentelemetry-instrumentation-fastapi",
    "opentelemetry-exporter-otlp-proto-grpc",
}

# বাকি সব ইউটিলিটি হিসেবে গণ্য হবে

# প্যাকেজের নাম normalize করার জন্য — বিশেষ করে JS-এর @scoped প্যাকেজ
# এবং Python-এর underscores/hyphens মিলানোর জন্য

# ═══════════════════════════════════════════════════════════════════════════════
# সাহায্যকারী ফাংশন
# ═══════════════════════════════════════════════════════════════════════════════


def normalize_pkg_name(name: str) -> str:
    """প্যাকেজের নাম normalize করে — underscores, hyphens, dots একই ভাবে ধরে।
    উদাহরণ: 'python-dotenv' -> 'python_dotenv', '@tanstack/react-query' -> '@tanstack/react-query'"""
    # scoped package তার আগেই রাখি
    if name.startswith("@"):
        return name.lower()
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_version_constraint(constraint: str) -> dict:
    """ভার্সন কনস্ট্রেইন্ট পার্স করে টাইপ ও মিনিমাম ভার্সন বের করে।

    সমর্থিত ফরম্যাট:
      ^1.2.3  — caret (semver compatible)
      >=1.0   — ন্যূনতম ভার্সন
      ~2.0    — patch-level compatible
      1.2.3   — এক্স্যাক্ট পিন
      >=1.54.0,<2.0.0 — range
    """
    original = constraint.strip()
    if not original:
        return {"type": "any", "min_version": None, "is_pinned": False, "raw": original}

    # workspace রেফারেন্স — এগুলো বাদ দেওয়া হবে
    if original.startswith("workspace:") or original == "link:":
        return {"type": "workspace", "min_version": None, "is_pinned": False, "raw": original}

    # এক্স্যাক্ট ভার্সন: শুধু সংখ্যা ও ডট
    if re.match(r"^\d+\.\d+(?:\.\d+)?(?:[a-zA-Z].*)?$", original):
        return {
            "type": "exact",
            "min_version": original,
            "is_pinned": True,
            "raw": original,
        }

    # >= বা > দিয়ে শুরু হলে
    ge_match = re.match(r"^>=(\d+\.\d+(?:\.\d+)?)", original)
    if ge_match:
        return {
            "type": "minimum",
            "min_version": ge_match.group(1),
            "is_pinned": False,
            "raw": original,
        }

    # ^ দিয়ে শুরু হলে (caret range)
    caret_match = re.match(r"^\^(\d+\.\d+(?:\.\d+)?)", original)
    if caret_match:
        return {
            "type": "caret",
            "min_version": caret_match.group(1),
            "is_pinned": False,
            "raw": original,
        }

    # ~ দিয়ে শুরু হলে (tilde / patch compatible)
    tilde_match = re.match(r"^~(\d+\.\d+(?:\.\d+)?)", original)
    if tilde_match:
        return {
            "type": "tilde",
            "min_version": tilde_match.group(1),
            "is_pinned": False,
            "raw": original,
        }

    # অন্য কিছু — raw হিসেবে রাখি
    return {"type": "unknown", "min_version": None, "is_pinned": False, "raw": original}


def categorize_dep(name: str) -> str:
    """ডিপেন্ডেন্সির ক্যাটাগরি নির্ধারণ করে: security-critical, core-framework, utility।"""
    norm = normalize_pkg_name(name)
    if norm in SECURITY_CRITICAL:
        return "security-critical"
    if norm in CORE_FRAMEWORK:
        return "core-framework"
    return "utility"


def run_git(args: list[str], timeout: int = 15) -> str:
    """git কমান্ড চালায় ও আউটপুট রিটার্ন করে। ত্রুটি হলে খালি স্ট্রিং দেয়।"""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT)] + args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def get_last_bump_date(package_name: str, dep_file: str) -> datetime | None:
    """git log থেকে একটি প্যাকেজের শেষ ভার্সন বাম্পের তারিখ খোঁজে।

    দুইটি পদ্ধতি ব্যবহার করে:
    1. কমিট মেসেজে প্যাকেজের নাম আছে কিনা (যেমন: "update fastapi" বা "bump pydantic")
    2. ডিপেন্ডেন্সি ফাইলের diff-এ প্যাকেজের নাম আছে কিনা
    """
    norm_name = normalize_pkg_name(package_name)
    # hyphen/underscore উভয় রূপে খোঁজা প্রয়োজন (git history-তে ভিন্ন হতে পারে)
    alt_name = norm_name.replace("-", "_")
    search_names = list({norm_name, alt_name, package_name})

    # কমিট মেসেজে খোঁজা
    for name_variant in search_names:
        # কমিট মেসেজে প্যাকেজ নাম থাকলে (update, bump, upgrade, chore ইত্যাদি সাথে)
        log_output = run_git([
            "log", "--all", "--format=%aI", "--max-count=1",
            "--grep", name_variant,
            "--", dep_file,
        ])
        if log_output:
            try:
                return datetime.fromisoformat(log_output)
            except ValueError:
                print('Silenced error in except block')

    # diff-এ প্যাকেজ নাম আছে কিনা — -S ফ্ল্যাগ দিয়ে খোঁজা
    for name_variant in search_names:
        log_output = run_git([
            "log", "--all", "--format=%aI", "--max-count=1",
            "-S", name_variant,
            "--", dep_file,
        ])
        if log_output:
            try:
                return datetime.fromisoformat(log_output)
            except ValueError:
                print('Silenced error in except block')

    return None


def get_lockfile_mtime(lockfile_path: Path) -> datetime | None:
    """লকফাইলের মডিফিকেশন টাইম রিটার্ন করে — ফলব্যাক হিসেবে ব্যবহৃত।"""
    if not lockfile_path.exists():
        return None
    try:
        mtime = lockfile_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    except OSError:
        return None


def classify_age(days: float | None, is_pinned: bool) -> dict:
    """দিনের হিসাবে বয়স থেকে শ্রেণী নির্ধারণ করে।

    রিটার্নস: {emoji, label, days}
    """
    # এক্স্যাক্ট পিন করা থাকলে — সম্ভবত ইচ্ছাকৃতভাবে পুরনো রাখা হয়েছে
    if is_pinned:
        return {"emoji": "🔵", "label": "PINNED", "days": days}

    if days is None:
        # কোনো git history পাওয়া যায়নি — lockfile mtime ব্যবহার করা হবে
        return {"emoji": "⚪", "label": "UNKNOWN", "days": None}

    if days <= FRESH_THRESHOLD:
        return {"emoji": "🟢", "label": "FRESH", "days": days}
    elif days <= AGING_THRESHOLD:
        return {"emoji": "🟡", "label": "AGING", "days": days}
    else:
        return {"emoji": "🔴", "label": "STALE", "days": days}


def get_update_command(ecosystem: str, package_name: str) -> str:
    """ডিপেন্ডেন্সি আপডেটের জন্য কমান্ড সাজেস্ট করে।"""
    if ecosystem == "python":
        return f"poetry update {package_name}"
    else:
        return f"pnpm update {package_name}"


def days_ago(dt: datetime) -> float:
    """একটি datetime থেকে আজ পর্যন্ত কতদিন হয়েছে তা বের করে।"""
    now = datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (now - dt).total_seconds() / 86400


# ═══════════════════════════════════════════════════════════════════════════════
# পার্সার — pyproject.toml, package.json
# ═══════════════════════════════════════════════════════════════════════════════


def parse_pyproject_toml(path: Path) -> list[dict]:
    """pyproject.toml থেকে Poetry ডিপেন্ডেন্সি পার্স করে।

    [tool.poetry.dependencies] এবং [tool.poetry.group.dev.dependencies] থেকে
    প্যাকেজের নাম ও ভার্সন কনস্ট্রেইন্ট বের করে।
    """
    if not path.exists():
        return []

    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"⚠️  pyproject.toml পড়তে সমস্যা: {e}", file=sys.stderr)
        return []

    deps = []
    poetry = data.get("tool", {}).get("poetry", {})

    # মূল dependencies
    for section_key, dep_type in [
        ("dependencies", "runtime"),
        ("dev-dependencies", "dev"),
    ]:
        section = poetry.get(section_key, {})
        for pkg_name, value in section.items():
            if pkg_name == "python":
                continue  # python নিজে ডিপেন্ডেন্সি নয়

            # ভার্সন কনস্ট্রেইন্ট বের করা
            if isinstance(value, str):
                constraint_raw = value
            elif isinstance(value, dict):
                constraint_raw = value.get("version", "")
            else:
                constraint_raw = str(value)

            # comments বাদ দেওয়া
            constraint_raw = re.sub(r"#.*$", "", constraint_raw).strip()

            # শুধু version part নেওয়া (extras, markers বাদ)
            constraint_clean = re.split(r";\s*python", constraint_raw)[0].strip()
            constraint_clean = re.sub(r"\[.*?\]", "", constraint_clean).strip()

            parsed = parse_version_constraint(constraint_clean)

            deps.append({
                "name": pkg_name,
                "normalized": normalize_pkg_name(pkg_name),
                "constraint_raw": constraint_raw,
                "constraint_parsed": parsed,
                "dep_type": dep_type,
                "ecosystem": "python",
                "source_file": str(path.relative_to(REPO_ROOT)),
                "category": categorize_dep(pkg_name),
            })

    # group.dev.dependencies-ও চেক করি (নতুন poetry format)
    groups = poetry.get("group", {})
    for group_name, group_data in groups.items():
        if group_name == "dev":
            group_deps = group_data.get("dependencies", {})
            for pkg_name, value in group_deps.items():
                if pkg_name == "python":
                    continue
                # ইতিমধ্যে dev-dependencies থেকে পার্স হয়ে থাকলে স্কিপ
                if any(d["name"] == pkg_name and d["dep_type"] == "dev" for d in deps):
                    continue

                if isinstance(value, str):
                    constraint_raw = value
                elif isinstance(value, dict):
                    constraint_raw = value.get("version", "")
                else:
                    constraint_raw = str(value)

                constraint_raw = re.sub(r"#.*$", "", constraint_raw).strip()
                constraint_clean = re.split(r";\s*python", constraint_raw)[0].strip()
                constraint_clean = re.sub(r"\[.*?\]", "", constraint_clean).strip()

                parsed = parse_version_constraint(constraint_clean)

                deps.append({
                    "name": pkg_name,
                    "normalized": normalize_pkg_name(pkg_name),
                    "constraint_raw": constraint_raw,
                    "constraint_parsed": parsed,
                    "dep_type": "dev",
                    "ecosystem": "python",
                    "source_file": str(path.relative_to(REPO_ROOT)),
                    "category": categorize_dep(pkg_name),
                })

    return deps


def parse_package_json(path: Path) -> list[dict]:
    """package.json থেকে dependencies ও devDependencies পার্স করে।"""
    if not path.exists():
        return []

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️  {path} পড়তে সমস্যা: {e}", file=sys.stderr)
        return []

    deps = []
    rel_path = str(path.relative_to(REPO_ROOT))

    for section_key, dep_type in [
        ("dependencies", "runtime"),
        ("devDependencies", "dev"),
    ]:
        section = data.get(section_key, {})
        for pkg_name, version in section.items():
            # workspace রেফারেন্স বাদ দেওয়া
            if isinstance(version, str) and version.startswith("workspace:"):
                continue
            # scoped types packages যেগুলো আসলে devDeps (@types/*)
            # তাদের ক্যাটাগরি ইউটিলিটি

            parsed = parse_version_constraint(str(version))

            deps.append({
                "name": pkg_name,
                "normalized": normalize_pkg_name(pkg_name),
                "constraint_raw": str(version),
                "constraint_parsed": parsed,
                "dep_type": dep_type,
                "ecosystem": "js",
                "source_file": rel_path,
                "category": categorize_dep(pkg_name),
            })

    # overrides-ও চেক করি — এগুলো গুরুত্বপূর্ণ কারণ সরাসরি ভার্সন নিয়ন্ত্রণ করে
    overrides = data.get("overrides", {})
    for pkg_name, version in overrides.items():
        if any(d["name"] == pkg_name for d in deps):
            continue  # ইতিমধ্যে আছে
        parsed = parse_version_constraint(str(version))
        deps.append({
            "name": pkg_name,
            "normalized": normalize_pkg_name(pkg_name),
            "constraint_raw": str(version),
            "constraint_parsed": parsed,
            "dep_type": "override",
            "ecosystem": "js",
            "source_file": rel_path,
            "category": categorize_dep(pkg_name),
        })

    return deps


# ═══════════════════════════════════════════════════════════════════════════════
# ফ্রেশনেস বিশ্লেষণ
# ═══════════════════════════════════════════════════════════════════════════════


def analyze_freshness(deps: list[dict]) -> list[dict]:
    """প্রতিটি ডিপেন্ডেন্সির ফ্রেশনেস বিশ্লেষণ করে।

    git log ও lockfile mtime থেকে শেষ আপডেটের তারিখ বের করে বয়স শ্রেণী
    নির্ধারণ করে।
    """
    # লকফাইল mtime ফলব্যাক হিসেবে রাখি
    python_lock_mtime = get_lockfile_mtime(POETRY_LOCK)
    js_lock_mtime = get_lockfile_mtime(PNPM_LOCK)

    # git-এর শুরুর তারিখ বের করি (ফলব্যাকের জন্য)
    first_commit_date = None
    first_log = run_git(["log", "--reverse", "--format=%aI", "--max-count=1"])
    if first_log:
        try:
            first_commit_date = datetime.fromisoformat(first_log)
        except ValueError:
            print('Silenced error in except block')

    enriched = []
    for dep in deps:
        pkg_name = dep["name"]
        ecosystem = dep["ecosystem"]
        source_file = dep["source_file"]
        is_pinned = dep["constraint_parsed"]["is_pinned"]

        # git log থেকে শেষ বাম্পের তারিখ
        last_bump = get_last_bump_date(pkg_name, source_file)

        # ফলব্যাক ১: সেই ইকোসিস্টেমের লকফাইলের mtime
        # ফলব্যাক ২: রিপোর প্রথম কমিট
        # ফলব্যাক ৩: None (UNKNOWN)
        if last_bump is None:
            if ecosystem == "python" and python_lock_mtime:
                last_bump = python_lock_mtime
            elif ecosystem == "js" and js_lock_mtime:
                last_bump = js_lock_mtime
            elif first_commit_date:
                last_bump = first_commit_date

        days = days_ago(last_bump) if last_bump else None
        age_info = classify_age(days, is_pinned)

        enriched_dep = {
            **dep,
            "last_bump_date": last_bump.isoformat() if last_bump else None,
            "days_since_bump": round(days, 1) if days else None,
            "age": age_info,
            "priority": _calc_priority(dep, age_info),
            "update_command": get_update_command(ecosystem, pkg_name),
        }
        enriched.append(enriched_dep)

    return enriched


def _calc_priority(dep: dict, age_info: dict) -> str:
    """প্রায়োরিটি নির্ধারণ করে। security-critical + STALE = HIGH।"""
    category = dep["category"]
    label = age_info["label"]

    if category == "security-critical" and label == "STALE":
        return "HIGH"
    if category == "security-critical" and label == "AGING":
        return "MEDIUM"
    if label == "STALE":
        return "MEDIUM"
    if label == "AGING":
        return "LOW"
    return "INFO"


# ═══════════════════════════════════════════════════════════════════════════════
# রিপোর্ট জেনারেটর
# ═══════════════════════════════════════════════════════════════════════════════


def build_report(enriched_deps: list[dict]) -> dict:
    """সম্পূর্ণ রিপোর্ট ডিকশনারি তৈরি করে — JSON আউটপুট ও টেক্সট রিপোর্ট উভয়ের জন্য।"""
    now = datetime.now(tz=timezone.utc).isoformat()

    # ইকোসিস্টেম অনুযায়ী আলাদা করা
    python_deps = [d for d in enriched_deps if d["ecosystem"] == "python"]
    js_deps = [d for d in enriched_deps if d["ecosystem"] == "js"]

    # স্ট্যাটিসটিক্স
    def calc_stats(deps_list):
        labels = [d["age"]["label"] for d in deps_list]
        return {
            "total": len(deps_list),
            "fresh": labels.count("FRESH"),
            "aging": labels.count("AGING"),
            "stale": labels.count("STALE"),
            "pinned": labels.count("PINNED"),
            "unknown": labels.count("UNKNOWN"),
            "security_critical": sum(1 for d in deps_list if d["category"] == "security-critical"),
            "core_framework": sum(1 for d in deps_list if d["category"] == "core-framework"),
            "utility": sum(1 for d in deps_list if d["category"] == "utility"),
        }

    # সর্টিং: HIGH priority প্রথম, তারপর age অনুযায়ী কমে থেকে বেশি
    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    sorted_deps = sorted(
        enriched_deps,
        key=lambda d: (
            priority_order.get(d["priority"], 99),
            -(d["days_since_bump"] or 0),
        ),
    )

    return {
        "generated_at": now,
        "repo_root": str(REPO_ROOT),
        "thresholds": {
            "fresh_days": FRESH_THRESHOLD,
            "aging_days": AGING_THRESHOLD,
        },
        "python": {
            "stats": calc_stats(python_deps),
            "deps": python_deps,
        },
        "js": {
            "stats": calc_stats(js_deps),
            "deps": js_deps,
        },
        "all": sorted_deps,
        "has_stale": any(d["age"]["label"] == "STALE" for d in enriched_deps),
    }


def render_text_report(report: dict) -> str:
    """টার্মিনালে দেখানোর জন্য টেক্সট রিপোর্ট তৈরি করে।

    ভিজ্যুয়াল রাডার/টাইমলাইন সহ।
    """
    lines = []
    sep = "═" * 72
    thin_sep = "─" * 72

    lines.append("")
    lines.append(sep)
    lines.append("  🔍 DEPENDENCY FRESHNESS RADAR — SupremeAI")
    lines.append(f"  📅 তারিখ: {report['generated_at'][:19]}")
    lines.append(sep)
    lines.append("")

    # ইকোসিস্টেম অনুযায়ী সারাংশ
    for ecosystem_name, key in [("🐍 Python", "python"), ("📦 JavaScript/TypeScript", "js")]:
        stats = report[key]["stats"]
        if stats["total"] == 0:
            continue
        lines.append(f"  {ecosystem_name} Dependencies ({stats['total']} packages)")
        lines.append(thin_sep)
        lines.append(
            f"    🟢 ফ্রেশ: {stats['fresh']}  |  "
            f"🟡 এজিং: {stats['aging']}  |  "
            f"🔴 স্টেল: {stats['stale']}  |  "
            f"🔵 পিন্ড: {stats['pinned']}  |  "
            f"⚪ অজানা: {stats['unknown']}"
        )
        lines.append(
            f"    🔒 সিকিউরিটি-ক্রিটিক্যাল: {stats['security_critical']}  |  "
            f"🏗️ কোর ফ্রেমওয়ার্ক: {stats['core_framework']}  |  "
            f"🔧 ইউটিলিটি: {stats['utility']}"
        )
        lines.append("")

    # ভিজ্যুয়াল টাইমলাইন / রাডার
    lines.append("  📊 VISUAL RADAR — শেষ আপডেট টাইমলাইন")
    lines.append(thin_sep)
    lines.append("")
    lines.append(render_timeline(report))
    lines.append("")

    # স্টেল ডিপেন্ডেন্সি তালিকা (প্রায়োরিটি অনুযায়ী সর্টেড)
    stale_deps = [d for d in report["all"] if d["age"]["label"] == "STALE"]
    aging_deps = [d for d in report["all"] if d["age"]["label"] == "AGING"]

    if stale_deps:
        lines.append(f"  🔴 STALE DEPENDENCIES ({len(stale_deps)} packages)")
        lines.append(thin_sep)
        for dep in stale_deps:
            lines.append(render_dep_line(dep))
        lines.append("")

    if aging_deps:
        lines.append(f"  🟡 AGING DEPENDENCIES ({len(aging_deps)} packages)")
        lines.append(thin_sep)
        for dep in aging_deps:
            lines.append(render_dep_line(dep))
        lines.append("")

    # পিন্ড ডিপেন্ডেন্সি
    pinned_deps = [d for d in report["all"] if d["age"]["label"] == "PINNED"]
    if pinned_deps:
        lines.append(f"  🔵 PINNED DEPENDENCIES ({len(pinned_deps)} packages)")
        lines.append(thin_sep)
        for dep in pinned_deps:
            lines.append(render_dep_line(dep))
        lines.append("")

    # HIGH priority আপডেট সাজেস্টন
    high_priority = [d for d in report["all"] if d["priority"] == "HIGH"]
    if high_priority:
        lines.append("  🚨 HIGH PRIORITY — এই প্যাকেজগুলো এখনই আপডেট করুন:")
        lines.append(thin_sep)
        for dep in high_priority:
            lines.append(f"    $ {dep['update_command']}")
        lines.append("")

    # সব আপডেট কমান্ড
    lines.append("  💡 সব আপডেট কমান্ড:")
    lines.append(thin_sep)
    lines.append("    Python:   poetry update                  (সব) বা poetry update PACKAGE")
    lines.append("    JS/TS:    pnpm update                    (সব) বা pnpm update PACKAGE")
    lines.append("")
    lines.append(sep)

    return "\n".join(lines)


def render_dep_line(dep: dict) -> str:
    """একটি ডিপেন্ডেন্সির জন্য এক লাইনের রিপোর্ট তৈরি করে।"""
    emoji = dep["age"]["emoji"]
    name = dep["name"]
    constraint = dep["constraint_parsed"]["raw"]
    days = dep["days_since_bump"]
    category_short = {
        "security-critical": "🔒SEC",
        "core-framework": "🏗️CORE",
        "utility": "🔧UTIL",
    }.get(dep["category"], "❓")
    priority = dep["priority"]
    source = dep["source_file"]

    days_str = f"{int(days)}d ago" if days else "N/A"

    line = (
        f"    {emoji} {name:<30} {constraint:<20} "
        f"{category_short:<10} [{priority:<6}] {days_str:<12} ({source})"
    )
    return line


def render_timeline(report: dict) -> str:
    """প্রতিটি ডিপেন্ডেন্সির জন্য ভিজ্যুয়াল টাইমলাইন রেন্ডার করে।

    ৩৬৫ দিনের একটি অনুভূমিক বারে প্রতিটি ডিপেন্ডেন্সির অবস্থান দেখায়।
    বাম দিক = পুরনো, ডান দিক = নতুন।
    """
    max_days = 365
    bar_width = 50
    lines = []
    lines.append(f"    {'':>30} {'← পুরনো (365d+)':>24} {'নতুন (আজ) →':>16}")
    lines.append(f"    {'':>30} {'├' + '─' * bar_width + '┤'}")

    # শুধু runtime ডিপেন্ডেন্সি দেখাই (dev বাদ)
    runtime_deps = [
        d for d in report["all"]
        if d["dep_type"] == "runtime" and d["days_since_bump"] is not None
    ]

    # নাম অনুযায়ী সর্ট করি
    runtime_deps.sort(key=lambda d: d["name"])

    for dep in runtime_deps:
        name = dep["name"][:28]
        days = dep["days_since_bump"]
        emoji = dep["age"]["emoji"]

        # বারের অবস্থান নির্ধারণ
        if days >= max_days:
            pos = 0
        else:
            pos = int((1 - days / max_days) * bar_width)

        bar = " " * pos + emoji + " " * (bar_width - pos - 1)
        lines.append(f"    {name:>28} │{bar}│ {int(days)}d")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# ডিফ মোড — আগের রানের সাথে তুলনা
# ═══════════════════════════════════════════════════════════════════════════════


def load_previous_report(path: str) -> dict | None:
    """আগের রানের JSON রিপোর্ট লোড করে।"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️  আগের রিপোর্ট লোড করতে সমস্যা ({path}): {e}", file=sys.stderr)
        return None


def render_diff_report(current: dict, previous: dict) -> str:
    """বর্তমান ও আগের রিপোর্টের মধ্যে পার্থক্য দেখায়।"""
    lines = []
    sep = "═" * 72

    lines.append("")
    lines.append(sep)
    lines.append("  📊 DEPENDENCY FRESHNESS — DIFF REPORT")
    lines.append(f"  আগের: {previous.get('generated_at', 'N/A')[:19]}")
    lines.append(f"  বর্তমান: {current.get('generated_at', 'N/A')[:19]}")
    lines.append(sep)
    lines.append("")

    # আগের ও বর্তমান ডিপেন্ডেন্সি ম্যাপ তৈরি
    prev_map = {}
    for dep in previous.get("all", []):
        key = (dep["ecosystem"], dep["name"])
        prev_map[key] = dep

    curr_map = {}
    for dep in current.get("all", []):
        key = (dep["ecosystem"], dep["name"])
        curr_map[key] = dep

    changes = []

    # নতুন ডিপেন্ডেন্সি
    for key in curr_map:
        if key not in prev_map:
            changes.append(("➕ নতুন", curr_map[key]))

    # সরানো ডিপেন্ডেন্সি
    for key in prev_map:
        if key not in curr_map:
            changes.append(("➖ সরানো", prev_map[key]))

    # পরিবর্তিত ডিপেন্ডেন্সি
    for key in curr_map:
        if key in prev_map:
            curr = curr_map[key]
            prev = prev_map[key]
            diffs = []

            # ভার্সন কনস্ট্রেইন্ট পরিবর্তন
            if curr["constraint_parsed"]["raw"] != prev["constraint_parsed"]["raw"]:
                diffs.append(
                    f"ভার্সন: {prev['constraint_parsed']['raw']} → {curr['constraint_parsed']['raw']}"
                )

            # বয়স শ্রেণী পরিবর্তন
            if curr["age"]["label"] != prev["age"]["label"]:
                diffs.append(
                    f"শ্রেণী: {prev['age']['emoji']} {prev['age']['label']} → "
                    f"{curr['age']['emoji']} {curr['age']['label']}"
                )

            # প্রায়োরিটি পরিবর্তন
            if curr["priority"] != prev["priority"]:
                diffs.append(
                    f"প্রায়োরিটি: {prev['priority']} → {curr['priority']}"
                )

            if diffs:
                changes.append(("🔄 পরিবর্তিত", curr, diffs))

    if not changes:
        lines.append("  ✅ কোনো পরিবর্তন নেই — সব একই আছে।")
        lines.append("")
        return "\n".join(lines)

    # পরিবর্তনগুলো গ্রুপ করে দেখানো
    added = [c for c in changes if c[0] == "➕ নতুন"]
    removed = [c for c in changes if c[0] == "➖ সরানো"]
    modified = [c for c in changes if c[0] == "🔄 পরিবর্তিত"]

    if added:
        lines.append(f"  ➕ নতুন ডিপেন্ডেন্সি ({len(added)}):")
        lines.append("─" * 72)
        for _, dep in added:
            lines.append(
                f"    {dep['age']['emoji']} {dep['name']:<30} {dep['constraint_parsed']['raw']:<15} "
                f"[{dep['ecosystem']}]"
            )
        lines.append("")

    if removed:
        lines.append(f"  ➖ সরানো ডিপেন্ডেন্সি ({len(removed)}):")
        lines.append("─" * 72)
        for _, dep in removed:
            lines.append(
                f"    {dep['age']['emoji']} {dep['name']:<30} {dep['constraint_parsed']['raw']:<15} "
                f"[{dep['ecosystem']}]"
            )
        lines.append("")

    if modified:
        lines.append(f"  🔄 পরিবর্তিত ডিপেন্ডেন্সি ({len(modified)}):")
        lines.append("─" * 72)
        for _, dep, diffs in modified:
            lines.append(f"    {dep['age']['emoji']} {dep['name']}:")
            for diff in diffs:
                lines.append(f"        • {diff}")
        lines.append("")

    # সারাংশ তুলনা
    prev_python_stale = previous.get("python", {}).get("stats", {}).get("stale", 0)
    curr_python_stale = current.get("python", {}).get("stats", {}).get("stale", 0)
    prev_js_stale = previous.get("js", {}).get("stats", {}).get("stale", 0)
    curr_js_stale = current.get("js", {}).get("stats", {}).get("stale", 0)

    lines.append("  📈 স্টেল ডিপেন্ডেন্সি পরিবর্তন:")
    lines.append("─" * 72)
    lines.append(f"    Python: {prev_python_stale} → {curr_python_stale}")
    lines.append(f"    JS/TS:  {prev_js_stale} → {curr_js_stale}")
    total_prev = prev_python_stale + prev_js_stale
    total_curr = curr_python_stale + curr_js_stale
    if total_curr < total_prev:
        lines.append(f"    ✅ মোট {total_prev - total_curr}টি স্টেল ডিপেন্ডেন্সি কমেছে!")
    elif total_curr > total_prev:
        lines.append(f"    ⚠️  মোট {total_curr - total_prev}টি নতুন স্টেল ডিপেন্ডেন্সি যোগ হয়েছে।")
    else:
        lines.append(f"    ➡️  মোট স্টেল সংখ্যা অপরিবর্তিত।")
    lines.append("")
    lines.append(sep)

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI আর্গুমেন্ট পার্সিং
# ═══════════════════════════════════════════════════════════════════════════════


def parse_args(argv: list[str]) -> dict:
    """CLI আর্গুমেন্ট পার্স করে — argparse ব্যবহার না করে (শুধু stdlib re, sys)।"""
    args = {
        "json": False,
        "diff": None,
        "python_only": False,
        "js_only": False,
        "ecosystem": None,
        "security_only": False,
    }

    i = 1
    while i < len(argv):
        arg = argv[i]
        if arg == "--json":
            args["json"] = True
        elif arg == "--diff":
            if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
                i += 1
                args["diff"] = argv[i]
            else:
                print("⚠️  --diff এর পর ফাইল পথ দিন", file=sys.stderr)
                args["diff"] = ""
        elif arg == "--python-only":
            args["python_only"] = True
        elif arg == "--js-only":
            args["js_only"] = True
        elif arg == "--ecosystem":
            if i + 1 < len(argv):
                i += 1
                args["ecosystem"] = argv[i].lower()
        elif arg == "--security-only":
            args["security_only"] = True
        elif arg in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        else:
            print(f"⚠️  অজানা আর্গুমেন্ট: {arg}", file=sys.stderr)
        i += 1

    return args


# ═══════════════════════════════════════════════════════════════════════════════
# মূল ফাংশন
# ═══════════════════════════════════════════════════════════════════════════════


def collect_all_deps(args: dict) -> list[dict]:
    """সব ডিপেন্ডেন্সি ফাইল থেকে ডিপেন্ডেন্সি সংগ্রহ করে।"""
    all_deps = []
    errors = []

    # Python deps
    want_python = (
        not args["js_only"]
        and (args["ecosystem"] is None or args["ecosystem"] == "python")
    )

    # JS deps
    want_js = (
        not args["python_only"]
        and (args["ecosystem"] is None or args["ecosystem"] == "js")
    )

    if want_python:
        pyproject_deps = parse_pyproject_toml(PYPROJECT_TOML)
        if pyproject_deps:
            all_deps.extend(pyproject_deps)
        else:
            errors.append(f"pyproject.toml থেকে কোনো ডিপেন্ডেন্সি পাওয়া যায়নি")

    if want_js:
        root_deps = parse_package_json(ROOT_PACKAGE_JSON)
        if root_deps:
            all_deps.extend(root_deps)

        frontend_deps = parse_package_json(FRONTEND_PACKAGE_JSON)
        if frontend_deps:
            all_deps.extend(frontend_deps)

        if not root_deps and not frontend_deps:
            errors.append("package.json ফাইল থেকে কোনো ডিপেন্ডেন্সি পাওয়া যায়নি")

    if not all_deps:
        errors.append("কোনো ডিপেন্ডেন্সি পাওয়া যায়নি — ফাইল পথ চেক করুন")

    return all_deps, errors


def filter_deps(deps: list[dict], args: dict) -> list[dict]:
    """আর্গুমেন্ট অনুযায়ী ডিপেন্ডেন্সি ফিল্টার করে।"""
    filtered = deps

    if args["security_only"]:
        filtered = [d for d in filtered if d["category"] == "security-critical"]

    return filtered


def main() -> int:
    """মূল এন্ট্রি পয়েন্ট। রিটার্ন করে এক্সিট কোড (0, 1, বা 2)।"""
    args = parse_args(sys.argv)

    # ডিপেন্ডেন্সি সংগ্রহ
    all_deps, errors = collect_all_deps(args)
    if errors and not all_deps:
        for err in errors:
            print(f"❌ {err}", file=sys.stderr)
        return 2

    # ফিল্টারিং
    filtered_deps = filter_deps(all_deps, args)

    # ফ্রেশনেস বিশ্লেষণ
    enriched_deps = analyze_freshness(filtered_deps)

    # রিপোর্ট তৈরি
    report = build_report(enriched_deps)

    # ডিফ মোড
    if args["diff"]:
        prev = load_previous_report(args["diff"])
        if prev:
            diff_text = render_diff_report(report, prev)
            if args["json"]:
                # JSON মোডেও ডিফ রিপোর্ট মেটাডেটা যোগ করি
                report["diff"] = {
                    "previous_run": args["diff"],
                    "previous_generated_at": prev.get("generated_at"),
                }
                print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
            else:
                print(diff_text)
            return 1 if report["has_stale"] else 0
        else:
            print("⚠️  ডিফ মোড বাদ দেওয়া হয়েছে — আগের রিপোর্ট পাওয়া যায়নি", file=sys.stderr)
            # ডিফ ফাইল না পাওয়া ত্রুটি নয়, তাই এগিয়ে যাই

    # JSON আউটপুট
    if args["json"]:
        print(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        return 1 if report["has_stale"] else 0

    # টেক্সট রিপোর্ট
    text_report = render_text_report(report)
    print(text_report)

    # এক্সিট কোড
    if report["has_stale"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
