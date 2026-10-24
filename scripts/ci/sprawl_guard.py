#!/usr/bin/env python3
"""Script Sprawl Guard (Loop 1 of Continuous Governance).

বাংলা মন্তব্য:
এই স্ক্রিপ্টটি নিশ্চিত করে যে ভবিষ্যতে কেউ যেন `scripts/` ডিরেক্টরির রুটে বিচ্ছিন্ন
বা এলোমেলো কোনো নতুন স্ক্রিপ্ট ফাইল (.py, .sh, .js ইত্যাদি) যুক্ত করতে না পারে।
সকল নতুন স্ক্রিপ্ট বা ইউটিলিটি অবশ্যই অনুমোদিত সাব-ডিরেক্টরি (যেমন: `scripts/supremeai_toolkit/`,
`scripts/ci/`, `scripts/agents/`) ইত্যাদিতে সুশৃঙ্খলভাবে সাজিয়ে রাখতে হবে।
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Set, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# বাংলা মন্তব্য: legacy রুট স্ক্রিপ্টগুলোর বেইজলাইন তালিকা — যাতে বিদ্যমান কোড হঠাৎ ভেঙে না যায়
# তবে এই তালিকায় নতুন কোনো ফাইল যুক্ত করা যাবে না; ধীরে ধীরে ছাঁটাই করে এগুলোকে toolkit-এ নিয়ে আসা হবে।
BASELINE_ROOT_SCRIPTS: Set[str] = {
    "_INDEX.md",
    "__init__.py",
    "architecture_baseline.json",
    "audit_env_usage.py",
    "audit_isolated_components.py",
    "audit_isolated_modules_and_capabilities.py",
    "audit_module_wiring.py",
    "audit_observability.py",
    "audit_run_backend_suites.sh",
    "audit_underutilized_capabilities.py",
    "auto_marketing_skill_forge.py",
    "check_app_boots.sh",
    "check_no_requests_in_backend.sh",
    "checkpoint_update.py",
    "ci-full-audit.sh",
    "cloudflare_worker.test.mjs",
    "codegraph_integration.py",
    "deploy_all_services.py",
    "detect_silent_errors.py",
    "duplicate_audit.txt",
    "feature_parity_baseline.json",
    "feature_parity_sentinel.py",
    "find_stub_data.py",
    "free-tier-health-check.sh",
    "generate_api_health_report.py",
    "generate_doc_inventory.py",
    "generate_openapi.py",
    "generate_script_index.py",
    "generate_types.py",
    "keepalive.js",
    "merge_and_consolidate_docs.py",
    "multi_model_validator.py",
    "observability_baseline.json",
    "pre_commit_hook.py",
    "pre_deploy_check.sh",
    "pre_merge_guard.py",
    "pre_push_hook.py",
    "prune_cache.sh",
    "render_build_backend.sh",
    "render_build_frontend.sh",
    "rotate_lessons.py",
    # বাংলা মন্তব্য (#2642/#2645 ফ্লিট-আনব্লক): ruff.toml স্ক্রিপ্ট নয় — lint কনফিগ।
    # ruff-এর config-discovery চুক্তি অনুযায়ী lint-কৃত ডিরেক্টরির রুটেই থাকতে হয়,
    # তাই scripts/ রুটে থাকা বাধ্যতামূলক; স্প্রল-গার্ডের উদ্দেশ্য (অপ্রয়োজনীয়
    # স্ক্রিপ্ট-বিক্ষেপ) এতে লঙ্ঘিত হয় না।
    "ruff.toml",
    "safety_guard.py",
    "setup-git-hooks.sh",
    "setup_kms.sh",
    "silent_errors_baseline.json",
    "supreme_ops.py",
    "supremeai_performance_benchmark.py",
    "sync_modules_list.py",
    "test_mcp_servers.py",
    "update_cors_hosts.py",
    "verify_capabilities.py",
    "verify_infisical_env.py",
    "verify_render_env.py",
}

APPROVED_DOMAINS: Set[str] = {
    "agents",
    "ai",
    "benchmarks",
    "ci",
    "db",
    "dev",
    "docker",
    "git",
    "lib",
    "maintenance",
    "monitoring",
    "quality",
    "release",
    "security",
    "supremeai_toolkit",
    "tests",
}


def is_root_sprawl_path(filepath: str) -> bool:
    """
    বাংলা মন্তব্য: ফাইলটি কি scripts/ এর সরাসরি রুটে অবস্থিত?
    e.g. 'scripts/new_script.py' -> True
         'scripts/ci/sprawl_guard.py' -> False
    """
    clean = filepath.replace("\\", "/").strip().lstrip("./")
    parts = clean.split("/")
    return len(parts) == 2 and parts[0] == "scripts"


def check_changed_files(files: List[dict]) -> Tuple[bool, List[str]]:
    """
    বাংলা মন্তব্য: নতুন যোগ হওয়া (added) ফাইলগুলোর মধ্যে কোনো স্ক্রিপ্ট স্প্রল আছে কি না পরীক্ষা করা।
    'files' হল [{'filename': '...', 'status': 'added'|'modified'|...}]
    """
    offenders: List[str] = []

    for item in files:
        filename = item.get("filename", "")
        status = item.get("status", "")

        # শুধু নতুন ফাইল অথবা আনট্র্যাকড ফাইল ভ্যালিডেট করা হয়
        if status in ("added", "untracked", "copied", "A", "??"):
            if is_root_sprawl_path(filename):
                base_name = Path(filename).name
                if base_name not in BASELINE_ROOT_SCRIPTS:
                    offenders.append(filename)

    if offenders:
        return False, offenders
    return True, []


def get_pr_files(pr_number: int) -> List[dict]:
    """বাংলা মন্তব্য: gh CLI দিয়ে পিআরে পরিবর্তিত ফাইল ও তাদের স্ট্যাটাস ফেচ করা।"""
    try:
        res = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "files"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if res.returncode != 0:
            print(f"::warning::gh pr view #{pr_number} ব্যর্থ: {res.stderr.strip()}")
            return []
        data = json.loads(res.stdout or "{}")
        # GitHub CLI 'files' ফরম্যাট: [{'path': '...', 'additions': ...}]
        out = []
        for f in data.get("files", []):
            path = f.get("path", "")
            # স্ট্যাটাস নির্ধারণ (gh pr view তে path থাকে)
            out.append({"filename": path, "status": "added"})
        return out
    except Exception as e:
        print(f"::warning::Error fetching PR files: {e}")
        return []


def get_git_tracked_files() -> Set[str]:
    """বাংলা মন্তব্য: গিট ট্র্যাকিংয়ে থাকা সমস্ত scripts/ ফাইলের তালিকা ফেচ করা।"""
    res = subprocess.run(
        ["git", "ls-files", "scripts/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if res.returncode == 0 and res.stdout.strip():
        return set(res.stdout.splitlines())
    return set()


def get_git_diff_files(base_ref: str = "origin/main") -> List[dict]:
    """বাংলা মন্তব্য: লোকাল git diff থেকে পরিবর্তিত ও যোগ হওয়া ফাইলের তালিকা পাওয়া।"""
    out: List[dict] = []
    try:
        # ১. কমিট হওয়া diff (base_ref এর সাপেক্ষে)
        res = subprocess.run(
            ["git", "diff", "--name-status", f"{base_ref}...HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().splitlines():
                parts = line.split(maxsplit=1)
                if len(parts) == 2:
                    status_code, path = parts[0], parts[1]
                    status = "added" if status_code.startswith("A") else "modified"
                    out.append({"filename": path, "status": status})

        # ২. আনকমিটেড বা আনট্র্যাকড ফাইল
        st_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if st_res.returncode == 0 and st_res.stdout.strip():
            for line in st_res.stdout.strip().splitlines():
                if len(line) >= 4:
                    status_code = line[:2].strip()
                    path = line[3:].strip()
                    if status_code in ("A", "??"):
                        out.append({"filename": path, "status": "added"})
    except Exception as e:
        print(f"::warning::Error checking git diff: {e}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Script Sprawl Guard (Loop 1 of Continuous Maintenance)")
    parser.add_argument("--pr", type=int, default=0, help="PR number to inspect")
    parser.add_argument("--base", default="origin/main", help="Base ref for git diff comparison")
    parser.add_argument("--check-all", action="store_true", help="Scan existing repository for unapproved root scripts")
    args = parser.parse_args()

    print("🛡️ [Loop 1: Script Sprawl Guard] Checking for unauthorized scripts root additions...")

    if args.check_all:
        tracked_files = get_git_tracked_files()
        offenders = []
        for path_str in sorted(tracked_files):
            clean = path_str.replace("\\", "/").strip()
            parts = clean.split("/")
            if len(parts) == 2 and parts[0] == "scripts":
                filename = parts[1]
                if filename not in BASELINE_ROOT_SCRIPTS and not filename.startswith("."):
                    offenders.append(clean)
        if offenders:
            print(f"::error::[SCRIPT SPRAWL] {len(offenders)} unapproved root script(s) found in repository:")
            for o in offenders:
                print(f"  ❌ {o}")
            return 1
        print("✅ [Loop 1: Script Sprawl Guard] All git-tracked root scripts match constitutional baseline.")
        return 0

    if args.pr > 0:
        files = get_pr_files(args.pr)
    else:
        files = get_git_diff_files(base_ref=args.base)

    if not files:
        print("✅ No changed files to inspect for script sprawl.")
        return 0

    ok, offenders = check_changed_files(files)
    if not ok:
        print(f"::error::[SCRIPT SPRAWL BLOCKED] {len(offenders)} unapproved script(s) added to 'scripts/' root:")
        for off in offenders:
            print(f"  ❌ {off}")
        print("\n💡 সমাধান (Remediation Rule):")
        print("  ১. 'scripts/' রুটে সরাসরি কোনো নতুন .py, .sh বা স্ক্রিপ্ট ফাইল রাখা নিষিদ্ধ।")
        print("  ২. ফাইলটি ডোমেন সাব-ডিরেক্টরি (যেমন: 'scripts/supremeai_toolkit/' বা 'scripts/ci/')-তে স্থানান্তর করুন।")
        print("  ৩. পুনঃপরীক্ষা করুন: 'python scripts/ci/sprawl_guard.py'")
        return 1

    print("✅ [Loop 1: Script Sprawl Guard] PASS: No unauthorized root script additions detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
