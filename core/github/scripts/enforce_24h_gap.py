#!/usr/bin/env python3
# বাংলা মন্তব্য: এই স্ক্রিপ্টটি শিডিউলড রানের ক্ষেত্রে ২৪ ঘণ্টার গ্যাপ চেক করে।
# পুরনো ফোর্স ক্যানসেল লজিক (sys.exit(1) / gh run cancel) সরিয়ে
# গ্রেসফুল স্কিপিং লজিক বসানো হয়েছে — should_run আউটপুটের মাধ্যমে gatekeeper জবকে সিগন্যাল দেওয়া হয়।
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone


def set_output(name, value):
    """গিটহাব অ্যাকশনস-এ আউটপুট সেট করার হেল্পার ফাংশন"""
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"{name}={value}\n")

def main():
    if os.environ.get("GITHUB_EVENT_NAME") != "schedule":
        print("Not a scheduled run. Proceeding normally.")
        set_output("should_run", "true")
        return 0

    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN")
    workflow_name = os.environ.get("GITHUB_WORKFLOW")
    current_run_id = os.environ.get("GITHUB_RUN_ID")

    if not all([repo, token, workflow_name, current_run_id]):
        print("Missing required GitHub environment variables.")
        set_output("should_run", "true")
        return 0

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SupremeAI-Workflow",
    } # বাংলা মন্তব্য: এপিআই রিকোয়েস্টের জন্য হেডার্স ডিকশনারি ডিফাইন করা হলো

    url = f"https://api.github.com/repos/{repo}/actions/runs"
    query = urllib.parse.urlencode({"per_page": 20})
    full_url = f"{url}?{query}"
    req = urllib.request.Request(full_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            status = resp.status
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        status = e.code

    if not (200 <= status < 300):
        print(f"Failed to fetch runs: {body}")
        set_output("should_run", "true")
        return 0

    runs = json.loads(body).get("workflow_runs", [])
    now = datetime.now(timezone.utc)

    for run in runs:
        if str(run["id"]) == current_run_id:
            continue

        if run["name"] != workflow_name:
            continue

        conclusion = run.get("conclusion")
        if conclusion in ["cancelled", "skipped"]:
            continue

        if conclusion == "failure":
            print(f"Previous run ({run['id']}) failed. Allowing this scheduled run as a retry.")
            set_output("should_run", "true")
            return 0

        created_at_str = run["created_at"]
        created_at = datetime.strptime(created_at_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

        diff = now - created_at

        if diff < timedelta(hours=24):
            print(f"Previous run ({run['id']}) started at {created_at_str}, which is {diff} ago.")
            print("Gracefully skipping this scheduled run to save free minutes.")
            set_output("should_run", "false")  # বাংলা মন্তব্য: গিটহাবকে সিগন্যাল দিচ্ছে স্কিপ করার জন্য
            return 0

    print("No valid previous runs found. Minimum 24-hour gap met. Proceeding.")
    set_output("should_run", "true")
    return 0

if __name__ == "__main__":
    sys.exit(main())
