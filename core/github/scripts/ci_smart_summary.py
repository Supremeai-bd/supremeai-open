import json
import os
import re
import urllib.request
from urllib.error import HTTPError, URLError


class HTTPRedirectWithoutAuth(urllib.request.HTTPRedirectHandler):
    # বাংলা: GitHub API থেকে S3/Azure storage-এ রিডাইরেক্ট হওয়ার সময় Authorization হেডার রিমুভ করার জন্য custom handler
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req:
            new_req.headers.pop("Authorization", None)
            new_req.headers.pop("authorization", None)
        return new_req


log_opener = urllib.request.build_opener(HTTPRedirectWithoutAuth())


def fetch_json(url: str, token: str) -> dict:
    """Fetch JSON from GitHub API using standard urllib.request (zero dependencies)."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SupremeAI-CI-Summary-Bot",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, OSError) as e:
        print(f"⚠️ API fetch error for {url}: {e}")
    return {}


def fetch_text(url: str, token: str) -> str:
    """Fetch raw text/logs from GitHub API using urllib.request with redirect auth stripping."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "SupremeAI-CI-Summary-Bot",
        },
    )
    try:
        with log_opener.open(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, OSError) as e:
        print(f"⚠️ Log fetch error for {url}: {e}")
    return ""


def extract_errors(log_text: str) -> list:
    """লগ টেক্সট থেকে Python ট্রেসব্যাক ও ত্রুটির মেসেজ বের করে।"""
    errors = []

    # Python traceback খোঁজা
    traceback_pattern = re.compile(r'(Traceback \(most recent call last\):[\s\S]+?(?:\n\S|$))', re.MULTILINE)
    for match in traceback_pattern.finditer(log_text):
        errors.append(match.group(1).strip())

    # Pytest ব্যর্থতা খোঁজা
    pytest_pattern = re.compile(r'(_{3,}\s+.*?_{3,}\n[\s\S]+?)(?=\n_{3,}|\Z)', re.MULTILINE)
    for match in pytest_pattern.finditer(log_text):
        if 'E   ' in match.group(1) or 'FAILURES' in match.group(1):
            errors.append(match.group(1).strip())

    # কোনো ত্রুটি না পেলে generic error খোঁজা
    if not errors:
        error_pattern = re.compile(r'^.*?(?:Error|Exception|Failed):.*$', re.MULTILINE | re.IGNORECASE)
        for match in error_pattern.finditer(log_text):
            errors.append(match.group(0).strip())

    # সর্বোচ্চ ৫টি ইউনিক ত্রুটি ফেরত দেওয়া
    return list(dict.fromkeys([e[:1000] + ('...' if len(e) > 1000 else '') for e in errors]))[:5]


def extract_warnings(log_text: str) -> list:
    """
    লগ টেক্সট থেকে সব ধরনের সতর্কতা (Warning) সংগ্রহ করে।
    শনাক্ত করে: GitHub Actions ::warning::, Python warnings,
    npm WARN, Flutter/Dart warnings এবং generic WARNING লাইন।
    """
    warnings = []

    # GitHub Actions ::warning:: অ্যানোটেশন
    for match in re.finditer(r'::warning[^:]*::(.+)', log_text, re.IGNORECASE):
        warnings.append(("GitHub Actions অ্যানোটেশন", match.group(0).strip()))

    # Python Warning (DeprecationWarning, UserWarning, FutureWarning ইত্যাদি)
    py_warn = re.compile(
        r'^.*(DeprecationWarning|UserWarning|RuntimeWarning|FutureWarning|'
        r'PendingDeprecationWarning|ResourceWarning|SyntaxWarning|UnicodeWarning|'
        r'ImportWarning|EncodingWarning)[:\s].+$',
        re.MULTILINE | re.IGNORECASE
    )
    for match in py_warn.finditer(log_text):
        warnings.append(("Python Warning", match.group(0).strip()))

    # npm / Node.js WARN
    for match in re.finditer(r'^.*(npm warn|npm WARN)\s+.+$', log_text, re.MULTILINE | re.IGNORECASE):
        warnings.append(("npm / Node.js WARN", match.group(0).strip()))

    # Flutter / Dart warning বা hint
    for match in re.finditer(r'^.*\b(warning|hint)\b.*\.dart.*$', log_text, re.MULTILINE | re.IGNORECASE):
        warnings.append(("Flutter / Dart Warning", match.group(0).strip()))

    # Generic WARNING কীওয়ার্ড (অন্য সব টুল)
    generic = re.compile(
        r'^(?!.*(?:npm warn|DeprecationWarning|UserWarning|RuntimeWarning|FutureWarning|::warning))'
        r'.*\bWARNING\b.*$',
        re.MULTILINE | re.IGNORECASE
    )
    for match in generic.finditer(log_text):
        line = match.group(0).strip()
        if len(line) > 20:
            warnings.append(("সাধারণ Warning", line))

    # ডুপ্লিকেট বাদ দিয়ে সর্বোচ্চ ১০টি warning ফেরত দেওয়া
    seen = set()
    unique = []
    for category, text in warnings:
        key = text[:200]
        if key not in seen:
            seen.add(key)
            unique.append((category, text[:500] + ('...' if len(text) > 500 else '')))
        if len(unique) >= 10:
            break
    return unique


def build_warnings_section(all_jobs: list, repo: str, token: str) -> list:
    """
    সব জবের লগ স্ক্যান করে warnings সংগ্রহ করে
    এবং বাংলায় ফরম্যাট করা সেকশন লাইন ফেরত দেয়।
    """
    jobs_with_warnings = {}
    for job in all_jobs:
        # স্কিপড বা বাতিল জব বাদ দেওয়া
        if job.get("conclusion") in ("skipped", "cancelled"):
            continue
        log_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job['id']}/logs"
        log_text = fetch_text(log_url, token)
        if log_text:
            found = extract_warnings(log_text)
            if found:
                jobs_with_warnings[job["name"]] = {"url": job["html_url"], "warnings": found}

    if not jobs_with_warnings:
        return []

    total_warn = sum(len(v["warnings"]) for v in jobs_with_warnings.values())
    section = [
        f"\n### ⚠️ সতর্কতা সংগ্রহ — মোট `{total_warn}`টি Warning শনাক্ত",
        "_এই সতর্কতাগুলো এখনই সিস্টেম ভাঙেনি, কিন্তু ভবিষ্যতে সমস্যা তৈরি করতে পারে। Admin-কে পর্যালোচনা করতে অনুরোধ করা হচ্ছে।_\n"
    ]
    for job_name, data in jobs_with_warnings.items():
        section.append(f"#### ⚠️ জব: [{job_name}]({data['url']})")
        for idx, (category, text) in enumerate(data["warnings"], 1):
            section.append(f"**{idx}. [{category}]**")
            section.append(f"```\n{text}\n```")
        section.append("---")
    return section


def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    run_id_env = os.environ.get("GITHUB_RUN_ID")

    if not all([token, repo, summary_file]):
        print("Missing GITHUB_TOKEN, GITHUB_REPOSITORY, or GITHUB_STEP_SUMMARY")
        return

    if run_id_env:
        # Fetch current run details directly
        run_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id_env}"
        run = fetch_json(run_url, token)
        if not run:
            print(f"Failed to fetch run {run_id_env}")
            return
    else:
        # Fallback: Fetch latest run
        print("Fetching latest workflow runs...")
        runs_url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=1"
        data = fetch_json(runs_url, token)
        runs = data.get("workflow_runs", [])
        if not runs:
            print("Failed to fetch runs")
            return
        run = runs[0]

    run_id = run.get("id")
    workflow_name = run.get("name", "SupremeAI Pipeline")

    # Fetch ALL jobs for this run dynamically (no hardcoding)
    jobs_url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100"
    jobs_data = fetch_json(jobs_url, token)
    all_jobs = jobs_data.get("jobs", [])
    total_jobs = len(all_jobs)
    passed_jobs = [j for j in all_jobs if j["conclusion"] == "success"]
    failed_jobs = [j for j in all_jobs if j["conclusion"] == "failure"]
    skipped_jobs = [j for j in all_jobs if j["conclusion"] in ["skipped", "cancelled"]]
    in_progress_jobs = [j for j in all_jobs if j["conclusion"] is None]

    status_icon = "🟢" if len(failed_jobs) == 0 else "🚨"
    summary_lines = [
        f"### {status_icon} স্মার্ট সিআই পাইপলাইন সারসংক্ষেপ — `{workflow_name}`",
        f"**রান আইডি (Run ID):** [{run_id}](https://github.com/{repo}/actions/runs/{run_id}) | **কমিট (Commit):** `{run.get('head_sha', '')[:7]}`",
        f"- 📊 **মোট রান হওয়া জব:** `{total_jobs}`টি",
        f"- ✅ **পাস করেছে:** `{len(passed_jobs)}`টি | ❌ **ব্যর্থ (Failed):** `{len(failed_jobs)}`টি | ⏭️ **স্কিপড/বাতিল:** `{len(skipped_jobs)}`টি | ⏳ **চলমান:** `{len(in_progress_jobs)}`টি\n"
    ]

    if not failed_jobs:
        summary_lines.append("🎉 **অভিনন্দন! কোনো ত্রুটি ছাড়াই পাইপলাইনের সমস্ত জব শতভাগ পাস করেছে!**")
    else:
        summary_lines.append("### 🔴 ব্যর্থ হওয়া জবের বিশ্লেষণ ও মূল কারণ (Bangla Diagnosis)")
        for job in failed_jobs:
            job_name = job["name"]
            job_url = job["html_url"]
            summary_lines.append(f"#### ❌ ব্যর্থ জব: [{job_name}]({job_url})")

            log_url = f"https://api.github.com/repos/{repo}/actions/jobs/{job['id']}/logs"
            log_text = fetch_text(log_url, token)

            if log_text:
                errors = extract_errors(log_text)
                if errors:
                    for idx, err in enumerate(errors, 1):
                        summary_lines.append(f"**আসল ত্রুটির ট্রেসব্যাক (Error Stacktrace #{idx}):**")
                        summary_lines.append("```python\n" + err + "\n```")
                else:
                    summary_lines.append("_লগ ফাইল থেকে সুনির্দিষ্ট ত্রুটি এক্সট্র্যাক্ট করা যায়নি। লিংক থেকে সরাসরি লগ পর্যবেক্ষণ করুন।_")
            else:
                summary_lines.append("_লগ ফাইল ডাউনলোড ব্যর্থ হয়েছে অথবা খালি পাওয়া গেছে।_")

            summary_lines.append("---")

    # ——— সতর্কতা (Warnings) সেকশন — সব জবের লগ স্ক্যান করে ———
    warnings_section = build_warnings_section(all_jobs, repo, token)
    if warnings_section:
        summary_lines.extend(warnings_section)
    else:
        summary_lines.append("\n✅ **কোনো সতর্কতা (Warning) শনাক্ত হয়নি।**")

    with open(summary_file, "a", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")

    print(
        f"Smart CI Summary generated for workflow '{workflow_name}' "
        f"({total_jobs} total jobs, warnings scan complete)."
    )

if __name__ == "__main__":
    main()

