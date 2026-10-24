"""
ci_error_report.py — SupremeAI CI ত্রুটি রিপোর্ট স্ক্রিপ্ট
=========================================================
এই স্ক্রিপ্ট GitHub Actions পাইপলাইনের **সমস্ত জবের লগ** স্ক্যান করে
সব ধরনের ত্রুটি সংগ্রহ করে এবং GitHub Step Summary-তে
বিস্তারিত বাংলা ডায়াগনস্টিক রিপোর্ট প্রকাশ করে।

শনাক্ত করা ত্রুটির ধরন:
  - Python Traceback ও Exception
  - Pytest ব্যর্থতা (FAILURES সেকশন)
  - GitHub Actions ::error:: অ্যানোটেশন
  - Node.js / npm error
  - Flutter / Dart compilation error
  - Bash / Shell script exit error
  - Docker build failure
  - Generic Error / Exception / Failed কীওয়ার্ড

ব্যবহার (CI Workflow):
  python .github/scripts/ci_error_report.py

প্রয়োজনীয় env vars:
  GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_STEP_SUMMARY, GITHUB_RUN_ID
"""

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from urllib.error import HTTPError, URLError


# ─────────────────────────────────────────────
# ত্রুটি ক্যাটাগরি সংজ্ঞা (Error Category Definitions)
# ─────────────────────────────────────────────
@dataclass
class ErrorEntry:
    category: str       # ত্রুটির ধরন
    severity: str       # P0 / P1 / P2
    text: str           # আসল ত্রুটির টেক্সট
    job_name: str = ""
    job_url: str = ""


class HTTPRedirectWithoutAuth(urllib.request.HTTPRedirectHandler):
    # বাংলা: GitHub API থেকে S3/Azure storage-এ রিডাইরেক্ট হওয়ার সময় Authorization হেডার রিমুভ করার জন্য custom handler
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req:
            new_req.headers.pop("Authorization", None)
            new_req.headers.pop("authorization", None)
        return new_req


log_opener = urllib.request.build_opener(HTTPRedirectWithoutAuth())


# ─────────────────────────────────────────────
# GitHub API Helper ফাংশন
# ─────────────────────────────────────────────
def fetch_json(url: str, token: str) -> dict:
    """GitHub API থেকে JSON ডেটা নিয়ে আসে।"""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SupremeAI-CI-Error-Report-Bot",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError) as e:
        print(f"[ERROR] API fetch failed for {url}: {e}")
    return {}


def fetch_text(url: str, token: str) -> str:
    """GitHub API থেকে Raw লগ টেক্সট নিয়ে আসে।"""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SupremeAI-CI-Error-Report-Bot",
        },
    )
    try:
        with log_opener.open(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, OSError) as e:
        print(f"[ERROR] Log fetch failed for {url}: {e}")
    return ""


# ─────────────────────────────────────────────
# ত্রুটি এক্সট্র্যাক্টর (Multi-Pattern Error Extractor)
# ─────────────────────────────────────────────
def extract_all_errors(log_text: str, job_name: str, job_url: str) -> list[ErrorEntry]:
    """
    একটি জবের সম্পূর্ণ লগ স্ক্যান করে সব ধরনের ত্রুটি বের করে।
    প্রতিটি ত্রুটিকে ক্যাটাগরি ও সিভারিটি দিয়ে ট্যাগ করে।
    """
    entries: list[ErrorEntry] = []

    def add(category: str, severity: str, text: str):
        truncated = text.strip()[:800] + ("..." if len(text.strip()) > 800 else "")
        entries.append(ErrorEntry(category, severity, truncated, job_name, job_url))

    # ── P0: Python Traceback (সবচেয়ে গুরুতর) ──
    tb_pattern = re.compile(
        r'(Traceback \(most recent call last\):[\s\S]+?(?=\n\S|\Z))',
        re.MULTILINE
    )
    for m in tb_pattern.finditer(log_text):
        add("Python Traceback", "P0", m.group(1))

    # ── P0: GitHub Actions ::error:: অ্যানোটেশন ──
    for m in re.finditer(r'::error[^:]*::(.+)', log_text, re.IGNORECASE):
        add("GitHub Actions Error অ্যানোটেশন", "P0", m.group(0).strip())

    # ── P0: Pytest FAILURES ব্লক ──
    pytest_pattern = re.compile(
        r'(={3,}\s+FAILURES\s+=+[\s\S]+?)(?=\n={3,}|\Z)',
        re.MULTILINE
    )
    for m in pytest_pattern.finditer(log_text):
        add("Pytest ব্যর্থতা (FAILURES)", "P0", m.group(1))

    # ── P0: Pytest short test summary (FAILED লাইন) ──
    for m in re.finditer(r'^FAILED\s+.+$', log_text, re.MULTILINE):
        add("Pytest ব্যর্থ টেস্ট", "P0", m.group(0).strip())

    # ── P1: Flutter / Dart compilation error ──
    flutter_err = re.compile(
        r'^.*\berror\b.*\.dart.*$', re.MULTILINE | re.IGNORECASE
    )
    for m in flutter_err.finditer(log_text):
        add("Flutter / Dart Compilation Error", "P1", m.group(0).strip())

    # ── P1: Node.js / npm ERR! ──
    for m in re.finditer(r'^.*(npm ERR!|node:internal.*Error).+$', log_text, re.MULTILINE | re.IGNORECASE):
        add("Node.js / npm Error", "P1", m.group(0).strip())

    # ── P1: Docker build failure ──
    for m in re.finditer(r'^.*(docker.*error|ERROR \[|failed to build).+$', log_text, re.MULTILINE | re.IGNORECASE):
        add("Docker Build Failure", "P1", m.group(0).strip())

    # ── P1: Bash / Shell exit code error ──
    for m in re.finditer(
        r'^.*(exit code [1-9]\d*|command not found|permission denied|No such file or directory).+$',
        log_text, re.MULTILINE | re.IGNORECASE
    ):
        add("Shell / Bash Error", "P1", m.group(0).strip())

    # ── P2: Generic Error / Exception / Failed (fallback) ──
    # শুধু তখনই ব্যবহার করা হয় যখন উপরের প্যাটার্ন কিছু ধরতে পারেনি
    if not entries:
        generic = re.compile(
            r'^.*(?:Error|Exception|Failed|FAILED|fatal):.*$',
            re.MULTILINE | re.IGNORECASE
        )
        for m in generic.finditer(log_text):
            line = m.group(0).strip()
            if len(line) > 15:
                add("Generic Error", "P2", line)

    # ডুপ্লিকেট বাদ দেওয়া এবং সর্বোচ্চ ১৫টি ত্রুটি
    seen: set = set()
    unique: list[ErrorEntry] = []
    for e in entries:
        key = e.text[:150]
        if key not in seen:
            seen.add(key)
            unique.append(e)
        if len(unique) >= 15:
            break
    return unique


# ─────────────────────────────────────────────
# Severity badge মেপিং (বাংলা লেবেল)
# ─────────────────────────────────────────────
SEVERITY_LABEL = {
    "P0": "🔴 P0 — জরুরি (Critical)",
    "P1": "🟠 P1 — উচ্চ অগ্রাধিকার (High)",
    "P2": "🟡 P2 — মাঝারি (Medium)",
}


# ─────────────────────────────────────────────
# Markdown রিপোর্ট তৈরি
# ─────────────────────────────────────────────
def build_error_report(all_errors: list[ErrorEntry], run_id: str, repo: str, workflow_name: str) -> str:
    """
    সংগ্রহ করা সব ত্রুটি থেকে বিস্তারিত বাংলা Markdown রিপোর্ট তৈরি করে।
    """
    if not all_errors:
        return (
            f"## ✅ CI ত্রুটি রিপোর্ট — `{workflow_name}`\n"
            f"**রান আইডি:** [{run_id}](https://github.com/{repo}/actions/runs/{run_id})\n\n"
            "🎉 **কোনো ত্রুটি শনাক্ত হয়নি! সমস্ত জব সফলভাবে সম্পন্ন হয়েছে।**\n"
        )

    # ক্যাটাগরি ও সিভারিটি অনুযায়ী গ্রুপিং
    by_severity: dict = {"P0": [], "P1": [], "P2": []}
    for e in all_errors:
        by_severity.setdefault(e.severity, []).append(e)

    p0 = len(by_severity["P0"])
    p1 = len(by_severity["P1"])
    p2 = len(by_severity["P2"])
    total = len(all_errors)

    lines = [
        f"## 🚨 CI ত্রুটি রিপোর্ট — `{workflow_name}`",
        f"**রান আইডি:** [{run_id}](https://github.com/{repo}/actions/runs/{run_id})\n",
        "### 📊 ত্রুটির সারসংক্ষেপ",
        "| সিভারিটি | সংখ্যা |",
        "|---|---|",
        f"| 🔴 P0 — জরুরি (Critical) | `{p0}`টি |",
        f"| 🟠 P1 — উচ্চ অগ্রাধিকার (High) | `{p1}`টি |",
        f"| 🟡 P2 — মাঝারি (Medium) | `{p2}`টি |",
        f"| **মোট ত্রুটি** | **`{total}`টি** |",
        "",
        "> **Admin নির্দেশনা:** P0 ত্রুটিগুলো সর্বোচ্চ অগ্রাধিকারে ঠিক করুন। P1 ও P2 পরবর্তী স্প্রিন্টে সমাধান করুন।\n",
        "---",
    ]

    # প্রতিটি সিভারিটি গ্রুপের জন্য বিস্তারিত সেকশন
    for severity_key in ("P0", "P1", "P2"):
        group = by_severity[severity_key]
        if not group:
            continue

        label = SEVERITY_LABEL[severity_key]
        lines.append(f"\n### {label} — {len(group)}টি ত্রুটি")

        # জব অনুযায়ী গ্রুপিং
        jobs_in_group: dict = {}
        for e in group:
            jobs_in_group.setdefault(e.job_name, []).append(e)

        for job_name, job_errors in jobs_in_group.items():
            job_url = job_errors[0].job_url
            lines.append(f"\n#### 📋 জব: [{job_name}]({job_url})")
            for idx, e in enumerate(job_errors, 1):
                lines.append(f"**{idx}. {e.category}**")
                lines.append(f"```\n{e.text}\n```")

        lines.append("---")

    # ত্রুটির ক্যাটাগরি ব্রেকডাউন টেবিল
    category_counts: dict = {}
    for e in all_errors:
        category_counts[e.category] = category_counts.get(e.category, 0) + 1

    lines.append("\n### 🗂️ ত্রুটির ধরন অনুযায়ী ব্রেকডাউন")
    lines.append("| ত্রুটির ধরন | সংখ্যা |")
    lines.append("|---|---|")
    for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | `{count}`টি |")

    lines.append(
        f"\n\n_রিপোর্ট তৈরি হয়েছে: SupremeAI CI Error Report Bot — "
        f"[রান দেখুন](https://github.com/{repo}/actions/runs/{run_id})_"
    )
    return "\n".join(lines) + "\n"


# ─────────────────────────────────────────────
# মূল ফাংশন
# ─────────────────────────────────────────────
def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    run_id_env = os.environ.get("GITHUB_RUN_ID")

    if not all([token, repo, summary_file]):
        print("[ERROR] GITHUB_TOKEN, GITHUB_REPOSITORY অথবা GITHUB_STEP_SUMMARY পাওয়া যায়নি।")
        return

    # বর্তমান রান ফেচ করা
    if run_id_env:
        run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id_env}"
        run = fetch_json(run_url, token)
        if not run:
            print(f"[ERROR] Run {run_id_env} ফেচ করা ব্যর্থ হয়েছে।")
            return
    else:
        runs_url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=1"
        data = fetch_json(runs_url, token)
        runs = data.get("workflow_runs", [])
        if not runs:
            print("[ERROR] কোনো workflow run পাওয়া যায়নি।")
            return
        run = runs[0]

    run_id = run.get("id")
    workflow_name = run.get("name", "SupremeAI Pipeline")
    print(f"[INFO] Workflow: {workflow_name} | Run ID: {run_id}")

    # সমস্ত জব নিয়ে আসা
    jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    jobs_data = fetch_json(jobs_url, token)
    all_jobs = jobs_data.get("jobs", [])
    print(f"[INFO] মোট {len(all_jobs)}টি জব পাওয়া গেছে।")

    # প্রতিটি জবের লগ স্ক্যান করে ত্রুটি সংগ্রহ
    all_errors: list[ErrorEntry] = []
    for job in all_jobs:
        # স্কিপড / বাতিল জব এড়িয়ে যাওয়া
        if job.get("conclusion") in ("skipped", "cancelled"):
            continue

        job_name = job["name"]
        job_url = job["html_url"]
        print(f"[SCAN] জব স্ক্যান করা হচ্ছে: {job_name} ({job.get('conclusion', 'in_progress')})")

        log_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job['id']}/logs"
        log_text = fetch_text(log_url, token)

        if log_text:
            errors = extract_all_errors(log_text, job_name, job_url)
            if errors:
                print(f"  → {len(errors)}টি ত্রুটি শনাক্ত হয়েছে।")
            all_errors.extend(errors)
        else:
            print("  → লগ ডাউনলোড হয়নি।")

    # Markdown রিপোর্ট তৈরি ও Step Summary-তে লেখা
    report = build_error_report(all_errors, str(run_id), repo, workflow_name)
    with open(summary_file, "a", encoding="utf-8") as f:
        f.write(report)

    print(
        f"[DONE] মোট {len(all_errors)}টি ত্রুটি সহ রিপোর্ট তৈরি সম্পন্ন "
        f"({len(all_jobs)} জব স্ক্যান)।"
    )


if __name__ == "__main__":
    main()
