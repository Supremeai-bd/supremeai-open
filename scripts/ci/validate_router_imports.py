#!/usr/bin/env python3
"""
validate_router_imports.py
==========================
High-Speed Router Import Smoke-Test — pre-CI & pre-commit gate script.

বাংলা মন্তব্য: এই স্ক্রিপ্টটি অতিদ্রুত ইন-প্রসেস লুপের মাধ্যমে সকল registered router-কে import করে।
পূর্বে Subprocess চালানোর কারণে যে ৭০-১৪০ সেকেন্ড সময় লাগত, তা এখন ১ সেকেন্ডেরও কমে সমাধান হবে।

Usage:
    cd backend
    python ../scripts/ci/validate_router_imports.py
    python ../scripts/ci/validate_router_imports.py --strict  # core routers must all pass
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import traceback
from pathlib import Path

# বাংলা মন্তব্য: Windows cp1252 টার্মিনালে UnicodeEncodeError ঠেকাতে stdout UTF-8 এ রিকনফিগার করা হচ্ছে
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# বাংলা মন্তব্য: PRE_COMMIT=1 এবং TESTING=1 সেট করা হচ্ছে যাতে Infisical vault
# network call skip হয় এবং secret_vault দ্রুত env fallback ব্যবহার করে।
# এটি না করলে pre-commit hook hang হয়ে যায়।
os.environ.setdefault("PRE_COMMIT", "1")
os.environ.setdefault("TESTING", "1")
os.environ.setdefault("ENV", "test")

# Ensure backend root and repo root are in python path
backend_dir = str(Path(__file__).parent.parent.parent / "backend")
repo_root = str(Path(__file__).parent.parent.parent)

# বাংলা মন্তব্য: backend_dir-কে sys.path-এর প্রথমে (index 0) রাখা অত্যন্ত জরুরী,
# যাতে repo_root/tools (VS Code extension/firebase functions) এর আগে backend/tools
# সঠিকভাবে প্যাকেজ হিসেবে ইমপোর্ট হতে পারে এবং ModuleNotFoundError না ঘটে।
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Ensure encryption key exists for testing
if "ENCRYPTION_KEY" not in os.environ and "ENCRYPTION_KEY" not in os.environ:
    os.environ["ENCRYPTION_KEY"] = "TEST_ONLY_SUPREMEAI_ENCRYPTION_KEY_DO_NOT_USE_IN_PROD="

# ── Router lists (mirrors backend/api/routers.py) ─────────────────────────────
CORE_ROUTERS = [
    "api.routes.memory",
    "api.routes.task",
    "api.routes.markdown",
    "api.routes.simulator",
    "api.routes.site_actions",
    "api.routes.browser",
    "api.routes.stream",
    "api.routes.media",
    "api.routes.graph",
    "api.routes.marketplace_endpoints",
    "api.routes.auth",
    "api.routes.onboarding",
    "api.routes.evolution",
    "api.routes.meta_ai",
    "api.routes.localization",
    "api.routes.analytics",
    "api.routes.admin_dashboard",
    "api.routes.email",
    "api.routes.github",
    "api.routes.internal",
    "api.routes.config_routes",
    "api.routes.repos",
    "api.routes.tools_ops",
    "api.routes.agents",
    "api.routes.agent",
    "api.routes.admin",
    "api.routes.tools_registry",
    "api.routes.preferences",
    "api.routes.usage_metrics",
    "api.routes.sso",
    "api.routes.health",
    "api.routes.api_keys",
    "api.routes.ci_webhooks",
    "api.routes.task_workspace",
    "api.routes.websocket_agent",
    "api.routes.agent_workspace",
    "api.routes.integrations",
    "api.routes.public_config",
    "api.routes.traffic_monitor",
    "api.routes.agent_action",
    "api.routes.websocket_hitl",
    "api.routes.syncguard",
    "api.routes.admin_librarian",
    "api.routes.realtime_dashboard",
]

OPTIONAL_ROUTERS = [
    "api.routes.llm_gateway",
    "api.routes.swarm",
    "api.routes.knowledge",
    "api.routes.dock_actions",
    "api.routes.websocket_voice",
    "tools.collaborative_editor",
    "tools.image_to_code",
    "tools.style_learner",
    "api.routes.codeflow",
    "api.routes.feedback",
    "tools.media.multilingual_tts",
    "api.routes.voice",
    "tools.comment_thread_ai",
    "api.routes.tenant_admin",
    "api.routes.mobile_bff",
    "api.routes.billing_api",
    "api.routes.metrics",
    "api.routes.cloud_mesh",
    "api.routes.events",
    "api.routes.payments",
    "api.routes.maintenance",
    "api.routes.sandbox_api",
    "api.routes.pr_review_api",
    "api.v1.telemetry",
    "api.routes.byoc_api",
]

# ANSI colors for readable terminal output
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


import threading
import time

# বাংলা মন্তব্য: সর্বোচ্চ 90 সেকেন্ড — timeout হলে স্বয়ংক্রিয়ভাবে exit করবে।
# এটি pre-commit hang প্রতিরোধ করে।
_MAX_TOTAL_SECONDS = 90

def _watchdog_timer(timeout: int) -> None:
    """Kill the process if it hangs beyond timeout seconds."""
    time.sleep(timeout)
    print(f"\n[TIMEOUT] Router smoke-test exceeded {timeout}s — killing to prevent pre-commit hang.")
    os._exit(1)

# Start watchdog in daemon thread
_wd = threading.Thread(target=_watchdog_timer, args=(_MAX_TOTAL_SECONDS,), daemon=True)
_wd.start()


def try_import_fast(module_path: str) -> tuple[bool, str | None]:
    """
    In-process fast import check.

    বাংলা মন্তব্য: ইন-প্রসেস লুপ ব্যবহার করা হচ্ছে যা ১ সেকেন্ডের মধ্যে পুরো টেস্ট শেষ করে।
    """
    try:
        mod = importlib.import_module(module_path)
        if not hasattr(mod, "router"):
            return False, f"No 'router' attribute in {module_path}"
        return True, None
    except Exception:
        exc_type, exc_val, _tb = sys.exc_info()
        last_line = traceback.format_exception_only(exc_type, exc_val)[-1].strip()
        return False, last_line


def run_validation(strict: bool = False) -> int:
    """
    Run high-speed import validation for all routers.
    """
    print(f"\n{BOLD}{CYAN}High-Speed Router Import Smoke-Test{RESET}")
    print(f"{'=' * 60}")

    core_failures: list[tuple[str, str]] = []
    optional_failures: list[tuple[str, str]] = []

    # Test core routers
    print(f"\n{BOLD}Core Routers ({len(CORE_ROUTERS)} total){RESET}")
    for module in CORE_ROUTERS:
        ok, err = try_import_fast(module)
        if ok:
            print(f"  {GREEN}[OK]{RESET} {module}")
        else:
            print(f"  {RED}[FAIL]{RESET} {module}")
            print(f"     {RED}+-- {err}{RESET}")
            core_failures.append((module, err or "unknown error"))

    # Test optional routers
    print(f"\n{BOLD}Optional Routers ({len(OPTIONAL_ROUTERS)} total){RESET}")
    for module in OPTIONAL_ROUTERS:
        ok, err = try_import_fast(module)
        if ok:
            print(f"  {GREEN}[OK]{RESET} {module}")
        else:
            print(f"  {YELLOW}[WARN]{RESET} {module} (optional -- will warn, not fail)")
            print(f"     {YELLOW}+-- {err}{RESET}")
            optional_failures.append((module, err or "unknown error"))

    # Summary
    print(f"\n{'=' * 60}")
    print(f"{BOLD}Summary{RESET}")
    total = len(CORE_ROUTERS) + len(OPTIONAL_ROUTERS)
    failed = len(core_failures) + len(optional_failures)
    passed = total - failed
    print(f"  Total routers checked : {total}")
    print(f"  {GREEN}Passed               : {passed}{RESET}")
    if core_failures:
        print(f"  {RED}Core failures        : {len(core_failures)} <- BLOCKS CI{RESET}")
        for mod, err in core_failures:
            print(f"    {RED}* {mod}{RESET}")
            print(f"      {err[:120]}")
    if optional_failures:
        print(f"  {YELLOW}Optional failures    : {len(optional_failures)} (non-blocking){RESET}")
        for mod, err in optional_failures:
            print(f"    {YELLOW}* {mod}{RESET}")

    if core_failures:
        print(f"\n{RED}{BOLD}[FAIL] GATE FAILED — {len(core_failures)} core router(s) cannot be imported.{RESET}\n")
        return 1

    if optional_failures and strict:
        print(f"\n{RED}{BOLD}[FAIL] STRICT GATE FAILED — {len(optional_failures)} optional router(s) cannot be imported.{RESET}\n")
        return 1

    if optional_failures:
        print(f"\n{YELLOW}{BOLD}[WARN] PASSED WITH WARNINGS — {len(optional_failures)} optional router(s) unavailable.{RESET}\n")
    else:
        print(f"\n{GREEN}{BOLD}[OK] ALL ROUTERS OK — high-speed smoke-test passed.{RESET}\n")

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fast in-process validation that all registered API routers can be imported without errors."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also fail on optional router import errors",
    )
    args = parser.parse_args()
    sys.exit(run_validation(strict=args.strict))


if __name__ == "__main__":
    main()
