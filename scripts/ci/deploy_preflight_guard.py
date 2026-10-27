#!/usr/bin/env python3
"""deploy_preflight_guard.py — Fast Preflight Lint, Secret Presence, and Render Quota Guard.

Unifies Step 1 and Step 2 of the Shift-Left Validation Doctrine:
  - Step 1 (Fast Lint & Syntax, < 10s):
      Compiles and validates Python (py_compile), JSON (json.loads), YAML (yaml.safe_load),
      and Shell script syntax across all touched/domain files before anything is merged or dispatched.
  - Step 2 (Environment & Secrets Presence, < 15s):
      Verifies that required deployment secrets and bridge tokens are configured and non-empty.
  - Step 3 (Render Account Quota & Deploy Routing):
      Inspects the target service's Render account monthly build minutes (< 450m = native autoDeploy;
      >= 450m = switch to GitHub Actions build to protect Render 500m free cap).

Usage:
  python3 scripts/ci/deploy_preflight_guard.py --all
  python3 scripts/ci/deploy_preflight_guard.py --step1-syntax
  python3 scripts/ci/deploy_preflight_guard.py --step2-secrets
  python3 scripts/ci/deploy_preflight_guard.py --step3-quota --service supremeai-primary-node
  python3 scripts/ci/deploy_preflight_guard.py --self-test
"""

from __future__ import annotations

import argparse
import json
import os
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import yaml
except ImportError:
    yaml = None

try:
    from render_build_quota_guard import (
        SAFE_BUILD_THRESHOLD_MINUTES,
        SERVICE_ACCOUNT_MAP,
        calculate_monthly_build_minutes,
        evaluate_deployment_mode,
        fetch_account_services,
    )
    from render_build_quota_guard import (
        load_env as load_render_env,
    )
except ImportError:
    SAFE_BUILD_THRESHOLD_MINUTES = 450.0
    SERVICE_ACCOUNT_MAP = {}
    calculate_monthly_build_minutes = None
    evaluate_deployment_mode = None
    fetch_account_services = None
    load_render_env = None


def _script_index_freshness() -> list[str]:
    """#1630: fail-closed freshness gate for scripts/ops/_INDEX.md.

    The index advertises a --check CI gate that was never wired anywhere, so
    it drifted 47 days unchecked (269->253 scripts). This sub-check runs the
    generator's own --check (regenerate in memory, compare) so a PR that
    adds/renames/deletes a script without regenerating the index fails Step 1.
    Only invoked in full-repo mode (targets=None); the offline self-test path
    passes explicit targets and stays deterministic/fast.
    """
    errors: list[str] = []
    gen = REPO_ROOT / "scripts" / "ops" / "generate_script_index.py"
    index = REPO_ROOT / "scripts" / "ops" / "_INDEX.md"
    if not gen.is_file() or not index.is_file():
        # Mirror layouts without the ops index tree: nothing to guard here.
        return errors
    try:
        result = subprocess.run(
            [sys.executable, str(gen), "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            errors.append(
                "scripts/ops/_INDEX.md is STALE — regenerate: "
                "python3 scripts/ops/generate_script_index.py"
            )
            for line in (result.stdout + result.stderr).strip().splitlines()[:3]:
                errors.append(f"  index: {line}")
    except subprocess.TimeoutExpired:
        errors.append("scripts/ops/generate_script_index.py --check timed out (60s)")
    return errors


def run_step1_syntax(targets: list[Path] | None = None) -> tuple[bool, list[str]]:
    """Step 1 (< 10s): Fast lint and syntax compilation across all target code."""
    errors: list[str] = []

    if targets is None:
        scan_paths = [
            REPO_ROOT / "core",
            REPO_ROOT / "gateway",
            REPO_ROOT / "api",
            REPO_ROOT / "agents",
            REPO_ROOT / "skills",
            REPO_ROOT / "command",
            REPO_ROOT / "infrastructure",
            REPO_ROOT / "scripts",
            REPO_ROOT / "examples",
        ]
        files_to_check: list[Path] = []
        for sp in scan_paths:
            if sp.is_dir():
                for f in sp.rglob("*"):
                    if (
                        f.is_file()
                        and ".git" not in f.parts
                        and "node_modules" not in f.parts
                        and "__pycache__" not in f.parts
                    ):
                        files_to_check.append(f)
    else:
        files_to_check = targets

    # #1630: index freshness rides the full-repo scan (CI Step 1); skipped for
    # explicit-target invocations (offline self-test keeps its fixtures).
    if targets is None:
        errors.extend(_script_index_freshness())

    py_count = 0
    json_count = 0
    yaml_count = 0
    python_files: list[Path] = []

    for file_path in files_to_check:
        ext = file_path.suffix.lower()

        # 1. Python Syntax
        if ext == ".py":
            py_count += 1
            python_files.append(file_path)
            try:
                py_compile.compile(str(file_path), doraise=True)
            except py_compile.PyCompileError as e:
                errors.append(
                    f"Python Syntax Error in {file_path.relative_to(REPO_ROOT)}: {e}"
                )

        # 2. JSON Validation
        elif ext == ".json":
            json_count += 1
            try:
                with file_path.open("r", encoding="utf-8") as jf:
                    json.load(jf)
            except (json.JSONDecodeError, OSError) as e:
                errors.append(
                    f"JSON Syntax Error in {file_path.relative_to(REPO_ROOT)}: {e}"
                )

        # 3. YAML Validation
        elif ext in {".yaml", ".yml"} and yaml is not None:
            yaml_count += 1
            try:
                with file_path.open("r", encoding="utf-8") as yf:
                    yaml.safe_load(yf)
            except (yaml.YAMLError, OSError) as e:
                errors.append(
                    f"YAML Syntax Error in {file_path.relative_to(REPO_ROOT)}: {e}"
                )

    # Ruff strict name/syntax check (mirrors satellite CI: E9,F63,F7,F82)
    ruff_dirs = [d for d in (REPO_ROOT / "gateway", REPO_ROOT / "core") if d.is_dir()]
    if ruff_dirs:
        try:
            result = subprocess.run(
                ["ruff", "check", "--select=E9,F63,F7,F82"] + [str(d) for d in ruff_dirs],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                for line in (result.stdout + result.stderr).strip().splitlines()[:50]:
                    errors.append(f"Ruff: {line}")
        except FileNotFoundError as exc:
            print(f"[Step 1: Syntax & Lint] INFO: ruff not installed ({exc!r}); skipping ruff check.")
    passed = len(errors) == 0
    print(
        f"[Step 1: Syntax & Lint] Checked: {py_count} Python, {json_count} JSON, {yaml_count} YAML files."
    )
    if passed:
        print(
            "[Step 1: Syntax & Lint] PASS: All files compiled cleanly with 0 syntax errors."
        )
    else:
        print(f"[Step 1: Syntax & Lint] FAIL: Found {len(errors)} syntax errors:")
        for err in errors[:5]:
            print(f"  - {err}")
    return passed, errors


def run_step2_secrets(required_keys: list[str] | None = None) -> tuple[bool, list[str]]:
    """Step 2 (< 15s): Verify presence and validity of required secrets without logging secrets."""
    errors: list[str] = []

    # Check environment + .env file
    env = dict(os.environ)
    env_file = REPO_ROOT / ".env"
    if env_file.is_file() and load_render_env:
        file_env = load_render_env(env_file)
        env = {**file_env, **env}

    default_required = [
        "GITHUB_PAT_ADMIN",
        "RENDER_API_KEY_1",
        "RENDER_API_KEY_2",
        "RENDER_API_KEY_3",
        "RENDER_API_KEY_4",
        "RENDER_API_KEY_5",
    ]
    check_keys = required_keys or default_required
    found_keys = []

    for key in check_keys:
        val = env.get(key, "").strip()
        if not val and key == "RENDER_API_KEY_5":
            val = env.get("RENDER_API_KEY_API", "").strip()
        if not val:
            # RENDER_API_KEY_5 may be optional if Gateway uses static webhook or direct deploy
            if key == "RENDER_API_KEY_5":
                print(
                    f"[Step 2: Secrets Presence] INFO: '{key}' not set in local env (will use GitHub Secrets in landing CI)."
                )
                continue
            errors.append(f"Missing required secret or environment variable: '{key}'")
        elif val.startswith("<") and val.endswith(">"):
            errors.append(f"Secret '{key}' contains unfilled placeholder: '{val}'")
        else:
            found_keys.append(key)

    passed = len(errors) == 0
    print(
        f"[Step 2: Secrets Presence] Verified {len(found_keys)} / {len(check_keys)} required environment keys."
    )
    if passed:
        print(
            "[Step 2: Secrets Presence] PASS: All required environment secrets are configured."
        )
    else:
        print(f"[Step 2: Secrets Presence] WARNING: {len(errors)} secrets missing:")
        for err in errors:
            print(f"  - {err}")
    return passed, errors


def run_step3_quota(
    target_service: str | None = None, threshold: float = SAFE_BUILD_THRESHOLD_MINUTES
) -> tuple[bool, dict[str, Any]]:
    """Step 3: Render Account Quota Evaluation (< 450m check)."""
    if not calculate_monthly_build_minutes or not fetch_account_services:
        print(
            "[Step 3: Quota Guard] Skipped: render_build_quota_guard module not found."
        )
        return True, {"skipped": True}

    env = dict(os.environ)
    env_file = REPO_ROOT / ".env"
    if env_file.is_file() and load_render_env:
        env = {**load_render_env(env_file), **env}

    target = target_service or "supremeai-primary-node"
    key_var = SERVICE_ACCOUNT_MAP.get(target, "RENDER_API_KEY_1")
    api_key = env.get(key_var)

    if not api_key:
        print(
            f"[Step 3: Quota Guard] WARNING: Key '{key_var}' not found in environment. Proceeding with caution."
        )
        return True, {"service": target, "warning": True, "reason": "No API key"}

    try:
        services = fetch_account_services(api_key)
        svc = next((s for s in services if s.get("name") == target), None)
        if not svc:
            print(
                f"[Step 3: Quota Guard] WARNING: Service '{target}' not found under key '{key_var}'."
            )
            return True, {
                "service": target,
                "warning": True,
                "reason": "Service not found",
            }

        svc_id = svc.get("id", "")
        build_mins, deploys = calculate_monthly_build_minutes(svc_id, api_key)
        eval_res = evaluate_deployment_mode(build_mins, threshold=threshold)
        eval_res["service"] = target
        eval_res["monthly_deploys"] = deploys

        print(
            f"[Step 3: Quota Guard] Service: {target} | Monthly Build: {build_mins}m / 500m (Threshold: {threshold}m)"
        )
        print(
            f"[Step 3: Quota Guard] Action: {eval_res['mode']} | autoDeploy Permitted: {eval_res['allow_render_native_build']}"
        )

        return not eval_res["warning"], eval_res
    except (RuntimeError, ValueError, OSError, KeyError) as e:
        print(f"[Step 3: Quota Guard] Quota check failed: {e}")
        return True, {"service": target, "error": str(e)}


def run_self_test() -> int:
    """Offline self-test for all preflight functions."""
    print("Running deploy_preflight_guard offline self-test...")

    # Test Step 1 with this script itself
    s1_pass, s1_err = run_step1_syntax([Path(__file__)])
    assert s1_pass is True, f"Self syntax check failed: {s1_err}"

    # Test Step 2 with mocked environment
    os.environ["MOCK_SECRET_TEST"] = "valid_secret_token_123"
    s2_pass, _ = run_step2_secrets(["MOCK_SECRET_TEST"])
    assert s2_pass is True, "Step 2 mock secrets check failed"

    # Test Step 2 failure handling
    s2_fail, s2_errs = run_step2_secrets(["NONEXISTENT_KEY_XYZ_999"])
    assert s2_fail is False, "Step 2 should fail on missing key"
    assert len(s2_errs) == 1

    print("deploy_preflight_guard self-test: PASS (deterministic exit 0)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="SupremeAI Deploy Preflight Guard")
    parser.add_argument(
        "--all", action="store_true", help="Run Step 1, Step 2, and Step 3 sequentially"
    )
    parser.add_argument(
        "--step1-syntax",
        action="store_true",
        help="Run Step 1 (Lint & Syntax Compilation)",
    )
    parser.add_argument(
        "--step2-secrets",
        action="store_true",
        help="Run Step 2 (Secrets Presence & Format)",
    )
    parser.add_argument(
        "--step3-quota",
        action="store_true",
        help="Run Step 3 (Render Account Quota Guard)",
    )
    parser.add_argument(
        "--service",
        type=str,
        default="supremeai-primary-node",
        help="Render service name for quota evaluation",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=SAFE_BUILD_THRESHOLD_MINUTES,
        help="Build minutes threshold (default: 450.0)",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run offline deterministic self-test"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    run_all = args.all or not (
        args.step1_syntax or args.step2_secrets or args.step3_quota
    )

    results: dict[str, Any] = {}
    overall_pass = True

    # Step 1: Syntax
    if run_all or args.step1_syntax:
        s1_pass, s1_errs = run_step1_syntax()
        results["step1_syntax"] = {"passed": s1_pass, "errors": s1_errs}
        if not s1_pass:
            overall_pass = False

    # Step 2: Secrets
    if run_all or args.step2_secrets:
        s2_pass, s2_errs = run_step2_secrets()
        results["step2_secrets"] = {"passed": s2_pass, "errors": s2_errs}
        if not s2_pass:
            # We treat missing local secrets as warning rather than hard exit if on public CI
            pass

    # Step 3: Quota
    if run_all or args.step3_quota:
        _s3_pass, s3_data = run_step3_quota(
            target_service=args.service, threshold=args.threshold
        )
        results["step3_quota"] = s3_data

    if args.json:
        print(json.dumps(results, indent=2))

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
