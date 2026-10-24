#!/usr/bin/env python3
"""
Service Topology Checker
─────────────────────────
docs/architecture/service_topology.yml পড়ে, .github/workflows/supreme-core-ci.yml
এর ভেতরে প্রতিটা deploy job-এর VITE_API_URL/VITE_API_BASE env var manifest-এর
সাথে মিলছে কিনা যাচাই করে। উদ্দেশ্য: admin/user (বা staging/prod) portal ভুলে
একই backend-এ point করে ফেললে CI-তেই ধরে ফেলা — deploy হওয়ার আগে।

ব্যবহার:
    python3 scripts/ci/check_service_topology.py

Exit code 1 = mismatch পাওয়া গেছে (blocking)
Exit code 0 = সব ঠিক আছে (known_exceptions warning-only)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("❌ pyyaml দরকার: pip install pyyaml --break-system-packages")
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "docs" / "architecture" / "service_topology.yml"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def load_manifest() -> dict:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_job_env_var(workflow_text: str, job_name: str) -> str | None:
    """workflow ফাইলের raw টেক্সট থেকে নির্দিষ্ট job-এর VITE_API_URL assignment খুঁজে বের করে।"""
    # job block বের করা: job_name: থেকে পরের top-level job (২ স্পেস ইন্ডেন্ট key) পর্যন্ত
    pattern = rf"(?m)^  {re.escape(job_name)}:\n(?:.*\n)*?(?=^  [a-zA-Z_-]+:\n|\Z)"
    match = re.search(pattern, workflow_text)
    if not match:
        return None
    block = match.group(0)
    var_match = re.search(r"VITE_API_URL:\s*(.+)", block)
    return var_match.group(1).strip() if var_match else None


def main() -> None:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    manifest = load_manifest()
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")

    blocking_errors: list[str] = []
    warnings: list[str] = []

    # ১. প্রতিটা target-এর env_var আসলে workflow-তে সেই job-এ ব্যবহার হচ্ছে কিনা
    seen_env_vars: dict[str, str] = {}  # env_var -> job_name (duplicate ধরার জন্য)
    for target in manifest["targets"]:
        job = target["workflow_job"]
        expected_var = target["env_var"]
        actual_line = find_job_env_var(workflow_text, job)

        if actual_line is None:
            warnings.append(f"[{job}] VITE_API_URL খুঁজে পাওয়া যায়নি — job renamed/removed হয়েছে কি?")
            continue

        if expected_var not in actual_line:
            blocking_errors.append(
                f"[{job}] manifest বলছে '{expected_var}' ব্যবহার হওয়া উচিত, "
                f"কিন্তু workflow-তে পাওয়া গেছে: {actual_line}"
            )

        if expected_var in seen_env_vars:
            other_job = seen_env_vars[expected_var]
            blocking_errors.append(
                f"env var '{expected_var}' দুইটা ভিন্ন job-এ ব্যবহার হচ্ছে: "
                f"'{job}' এবং '{other_job}' — এটাই সেই bug-class যেটা আগে ঘটেছিল।"
            )
        seen_env_vars[expected_var] = job

    # ২. rules সেকশন — env_var আর default backend সব target-এ ইউনিক কিনা
    env_vars = [t["env_var"] for t in manifest["targets"]]
    if len(env_vars) != len(set(env_vars)):
        blocking_errors.append("দুই বা তার বেশি target একই env_var শেয়ার করছে — manifest নিজেই invalid।")

    defaults = [t["expected_backend_default"] for t in manifest["targets"]]
    if len(defaults) != len(set(defaults)):
        blocking_errors.append("দুই বা তার বেশি target একই default backend URL শেয়ার করছে — manifest নিজেই invalid।")

    # ৩. known_exceptions শুধু warning
    for exc in manifest.get("known_exceptions", []):
        warnings.append(f"[{exc['workflow_job']}] জানা exception: {exc['reason'].strip()}")

    print("=" * 60)
    print("Service Topology Check")
    print("=" * 60)

    if warnings:
        print(f"\n⚠️  {len(warnings)}টা non-blocking warning:")
        for w in warnings:
            print(f"  - {w}")

    if blocking_errors:
        print(f"\n❌ {len(blocking_errors)}টা BLOCKING mismatch:")
        for e in blocking_errors:
            print(f"  - {e}")
        print("\nCI FAILED — service topology mismatch পাওয়া গেছে।")
        sys.exit(1)

    print("\n✅ সব target manifest অনুযায়ী সঠিক backend-এ point করছে।")
    sys.exit(0)


if __name__ == "__main__":
    main()
