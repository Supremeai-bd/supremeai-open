#!/usr/bin/env python3
import base64
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY")
BRANCH = os.environ.get("GITHUB_REF_NAME")
CURRENT_RUN_ID = int(os.environ.get("GITHUB_RUN_ID", "0"))
WORKFLOW_NAME = os.environ.get("GITHUB_WORKFLOW")
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")

if not REPO or not BRANCH or not TOKEN or not WORKFLOW_NAME or not CURRENT_RUN_ID:
    print("Missing required GitHub environment variables.")
    sys.exit(1)

HEADERS = {
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}",
    "X-GitHub-Api-Version": "2022-11-28",
}

PACKAGE_MAP = {
    "backend": [
        "Backend (Test)",
        "Backend Tests",
        "Deploy Backend (Render)",
        "Deploy Backend (Cloud Run)",
        "Canary Deploy Backend (Cloud Run)",
    ],
    "frontend": [
        "Frontend Monorepo (Turbo)",
        "Deploy Admin Portal (Firebase)",
        "Deploy Frontend",
    ],
    "infra": ["Build Base Image", "Edge", "Infra", "Infrastructure"],
    "scraper": ["Scraper", "Crawl", "Crawler"],
    "dependencies": [],
    # Gate failure memory: ensure gates that failed in the prior run are NOT skipped
    "advanced_checks": [
        "Advanced Pre-Merge Checks",
        "Advanced Repository, Security & Contract Checks",
        "advanced-checks",
    ],
    "security": [
        "Zero-Cost Security Gate",
        "Security Gate",
    ],
    "dry_gate": ["DRY Gate"],
    "qa_contract": ["QA Contract"],
    # Issue #470: per-group failure memory. The backend-test-planner job
    # forces a group back into the matrix when its most recent prior run
    # failed/cancelled, so a flaky group is retried even when nothing in it
    # changed. Patterns must stay distinct from each other (match_job does
    # substring matching both ways).
    "backend_group_fast": ["Backend Tests (fast)"],
    "backend_group_core_unit": ["Backend Tests (core-unit)"],
    "backend_group_core_support": ["Backend Tests (core-support)"],
    "backend_group_services": ["Backend Tests (services)"],
}

FAILED_CONCLUSIONS = {"failure", "cancelled", "timed_out"}
SUCCESS_CONCLUSIONS = {"success"}
SKIPPED_CONCLUSIONS = {"skipped", "neutral"}


def _build_ssl_context() -> ssl.SSLContext:
    # বাংলা মন্তব্য (fix 23834c8): আগে এখানে verify_mode=ssl.CERT_NONE দিয়ে TLS
    # verification পুরোপুরি বন্ধ করে দেওয়া হয়েছিল — সম্ভবত runner-এ কোনো cert
    # error সমাধান করতেই, কিন্তু এটা man-in-the-middle risk তৈরি করে এবং কোনো
    # script কপি করলে ছড়িয়ে পড়তে পারে। সঠিক fix: system CA bundle দিয়ে
    # default verified context ব্যবহার করা, আর সেটা fail করলে (কিছু runner-এ
    # bundled CA store পুরনো/অনুপস্থিত থাকতে পারে) certifi-র bundle দিয়ে
    # verified fallback — কখনোই verification বন্ধ করা হয় না।
    try:
        return ssl.create_default_context()
    except ssl.SSLError:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())


def api_get(path: str, params: dict | None = None) -> dict:
    url = f"https://api.github.com/repos/{REPO}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS, method="GET")

    ctx = _build_ssl_context()

    # বাংলা মন্তব্য (PERF/ROBUSTNESS FIX): 429 (secondary rate limit)-এ GitHub
    # Retry-After হেডার দেয়। আগে retry না থাকায় আটকে যাওয়া sequential
    # call-গুলোতে 429 পড়লে পুরো স্টেপ ভেঙে যেত/ধীরে যেত — এখন max 3 বার
    # honored sleep দিয়ে retry হয়, ফলে short burst-এ স্থিতিশীল।
    _5XX_RETRYABLE = {500, 502, 503, 504}
    body = ""
    status = 0
    for _attempt in range(4):
        try:
            with urllib.request.urlopen(req, context=ctx) as resp:
                body = resp.read().decode("utf-8")
                status = resp.status
                break
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            status = e.code
            if status == 429 and e.headers:
                retry_after = e.headers.get("Retry-After")
                if retry_after:
                    try:
                        time.sleep(max(0, int(retry_after)))
                    except ValueError:
                        time.sleep(2)
                    continue
                time.sleep(2)
                continue
            if status == 429:
                time.sleep(2)
                continue
            if status in _5XX_RETRYABLE:
                backoff = 2 ** (_attempt + 1)
                print(
                    f"GitHub API transient {status} on attempt {_attempt + 1}/4 — "
                    f"retrying in {backoff}s: {path}",
                    file=sys.stderr,
                )
                time.sleep(backoff)
                continue
            break
    if status in _5XX_RETRYABLE:
        print(
            f"WARNING: GitHub API {status} persisted after 4 attempts on {path}. "
            "Returning empty safe default — CI change-detection will be conservative.",
            file=sys.stderr,
        )
        return {}
    if status >= 400:
        raise SystemExit(f"GitHub API request failed: {status} {body}")
    return json.loads(body)


def get_recent_workflow_runs() -> list[dict]:
    # Do not force event=push here. Pull-request workflows also need the
    # previous run for the same branch; filtering to pushes makes the failure
    # memory silently empty for PR-only branches.
    # বাংলা মন্তব্য (PERF FIX): আগে per_page=100 নেওয়া হতো, আর নিচের
    # determine_force_flags() প্রতিটা run (≤100) এর jobs আলাদা sequentially
    # fetch করত — মোট 101টা API call → secondary rate limit + 3+ মিনিট।
    # এখন (ক) লেজি fetch + early-exit (নিচে দেখুন), আর (খ) 30টা run-ই শালীন
    # "recent failure memory" — 100টা না। বাস্তবে 1-2টা run-এর jobs-ই লাগে।
    params = {"branch": BRANCH, "per_page": 30}
    runs_data = api_get("/actions/runs", params=params)
    runs = runs_data.get("workflow_runs", [])
    return sorted(
        (
            run
            for run in runs
            if run.get("name") == WORKFLOW_NAME
            and str(run.get("id")) != str(CURRENT_RUN_ID)
            and run.get("head_branch") == BRANCH
        ),
        key=lambda run: run.get("created_at") or "",
        reverse=True,
    )


def terminal_conclusion(job: dict) -> str:
    return str(job.get("conclusion") or "").lower()


def is_retry_failure(conclusion: str) -> bool:
    return conclusion in FAILED_CONCLUSIONS


def is_success(conclusion: str) -> bool:
    return conclusion in SUCCESS_CONCLUSIONS


def get_job_statuses(run_id: int) -> list[dict]:
    jobs_data = api_get(f"/actions/runs/{run_id}/jobs", params={"per_page": 100})
    return jobs_data.get("jobs", [])


def match_job(job_name: str, patterns: list[str]) -> bool:
    lower_name = job_name.lower()
    for pattern in patterns:
        if pattern.lower() in lower_name or lower_name in pattern.lower():
            return True
    return False


def determine_force_flags() -> dict[str, str]:
    runs = get_recent_workflow_runs()
    force_flags = {pkg: "false" for pkg in PACKAGE_MAP}

    # বাংলা মন্তব্য (PERF FIX): আগে প্রতিটা run (≤100) এর jobs আগে থেকেই eagerly
    # fetch করা হতো — ≤100টা sequential GitHub API call → 3+ মিনিট এবং secondary
    # rate limit-এর কারণ। এখন লেজি: closest run থেকে শুরু করে প্রতি-run jobs শুধু
    # তখনই fetch হয় যখন অন্তত একটা প্যাকেজ এখনো unresolved, আর সব প্যাকেজের
    # conclusive (failure/success) ফলাফল পেয়ে গেলেই লুপ break — বাস্তবে 1-2টা
    # run-এর jobs-ই লাগে। শব্দার্থ আগেরটাই: dependabot বাদ, প্রতি-প্যাকেজ
    # newest→oldest walk, skipped/neutral/in_progress হলে পুরনো run-এ এগোনো।
    # নোট: empty-patterns প্যাকেজ (যেমন "dependencies": []) কখনো match করতে
    # পারে না, তাই সেগুলো unresolved-এ রাখা হয় না — নইলে early-exit কখনোই
    # ট্রিগার হবে না এবং অপটিমাইজেশন কার্যকর হবে না।
    unresolved = {pkg for pkg, patterns in PACKAGE_MAP.items() if patterns}
    fetched_any = False
    for run in runs:
        run_id = run.get("id")
        if not run_id:
            continue
        # Skip dependabot runs so they don't reset failure history
        actor_login = run.get("actor", {}).get("login", "").lower()
        if "dependabot" in actor_login or "[bot]" in actor_login:
            continue
        # BUGFIX (2026-09-20 audit): cancelled রানের প্রতিটি job নিজেও 'cancelled'
        # হয় — আগে সেটাকে failure ধরা হতো (FAILED_CONCLUSIONS-এ cancelled আছে),
        # ফলে একটি মাত্র cancelled রান (concurrency cancel-in-progress) failure-
        # memory পয়জন করত → পরের রান সব গ্রুপ force-rerun করত। প্রমাণ: ৯ রানের
        # মধ্যে ৫টি cancelled → প্রায় প্রতি push-এ পূর্ণ ম্যাট্রিক্স। সমাধান:
        # সম্পূর্ণ cancelled রান স্কিপ — সত্যিক failure (failure/timed_out) আগের
        # non-cancelled রান থেকেই resolve হবে।
        if str(run.get("conclusion") or "").lower() == "cancelled":
            continue
        jobs = get_job_statuses(run_id)
        fetched_any = True
        for pkg in list(unresolved):
            patterns = PACKAGE_MAP[pkg]
            matching_jobs = [
                job for job in jobs if match_job(job.get("name", ""), patterns)
            ]
            if not matching_jobs:
                continue
            # BUGFIX (2026-09-20 audit): আগে শুধু matching_jobs[0] দেখা হতো —
            # একই প্যাকেজের (যেমন "Backend Tests") একাধিক shard-এর মধ্যে প্রথমটি
            # সফল হলে পরের কোনো shard-এর ব্যর্থতা অদৃশ্য হয়ে যেত (job order-
            # নির্ভর বাগ)। এখন: যেকোনো matching job ব্যর্থ হলে force, নাহলে
            # অন্তত একটি সফল হলে clear।
            conclusions = [terminal_conclusion(job) for job in matching_jobs]
            if any(is_retry_failure(c) for c in conclusions):
                force_flags[pkg] = "true"
                unresolved.discard(pkg)
            elif any(is_success(c) for c in conclusions):
                force_flags[pkg] = "false"
                unresolved.discard(pkg)
            # skipped/neutral/in_progress → পরের (পুরনো) run-এ চালিয়ে যাও
        if not unresolved:
            break

    if not fetched_any:
        print("No processable previous workflow runs found.")
        return force_flags

    for pkg in PACKAGE_MAP:
        if force_flags[pkg] == "true":
            print(f"{pkg}: A recent failure was detected. Forcing retry.")
        else:
            print(f"{pkg}: no recent failures found.")

    return force_flags


def main() -> int:
    force_flags = determine_force_flags()
    json_str = json.dumps(force_flags)
    encoded = base64.b64encode(json_str.encode("utf-8")).decode("utf-8")
    print(f"force_flags (encoded)={encoded}")
    # Write to GITHUB_OUTPUT file instead of using deprecated ::set-output
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"force_flags_b64={encoded}\n")
            # Expose stable per-area outputs for the changes job. The prior
            # implementation only emitted a base64 aggregate that no caller
            # decoded, so failed/cancelled jobs never affected path filtering.
            output_map = {
                "backend": force_flags.get("backend", "false"),
                "frontend": force_flags.get("frontend", "false"),
                "infra": force_flags.get(
                    "infra", force_flags.get("docker_build", "false")
                ),
                "scraper": force_flags.get("scraper", "false"),
                # Gate failure memory
                "advanced_checks": force_flags.get("advanced_checks", "false"),
                "security": force_flags.get("security", "false"),
                "dry_gate": force_flags.get("dry_gate", "false"),
                "qa_contract": force_flags.get("qa_contract", "false"),
                # Issue #470: per-group failure memory for the planner.
                "backend_group_fast": force_flags.get("backend_group_fast", "false"),
                "backend_group_core_unit": force_flags.get(
                    "backend_group_core_unit", "false"
                ),
                "backend_group_core_support": force_flags.get(
                    "backend_group_core_support", "false"
                ),
                "backend_group_services": force_flags.get(
                    "backend_group_services", "false"
                ),
            }
            f.writelines(f"{key}={value}\n" for key, value in output_map.items())
    return 0


if __name__ == "__main__":
    sys.exit(main())
