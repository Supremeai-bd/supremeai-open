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
import hashlib
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

    #4471 second layer (--check-committed): the workspace file can be mutated
    before this gate runs — pipeline.yml's regen-first step regenerates the
    runner copy, so a workspace read always sees a fresh index and a PR
    carrying a stale committed index passes (the #3418 ordering regression
    family). The committed-blob check reads git HEAD instead — in CI HEAD is
    exactly the tree under test — and fails closed when the committed index
    is stale, killing the ordering class regardless of workflow ordering.
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
    # #4471 layer 2: committed-blob check — immune to regen-first CI mutation.
    try:
        result = subprocess.run(
            [sys.executable, str(gen), "--check-committed"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            errors.append(
                "scripts/ops/_INDEX.md at HEAD is STALE (committed-blob check, "
                "immune to regen-first CI mutation) — regenerate AND commit the index"
            )
            for line in (result.stdout + result.stderr).strip().splitlines()[:3]:
                errors.append(f"  index@HEAD: {line}")
    except subprocess.TimeoutExpired:
        errors.append("scripts/ops/generate_script_index.py --check-committed timed out (60s)")
    return errors


def _provenance_digest(receipts_dir: Path | None = None) -> list[str]:
    """#1674 minimal provenance lane: verify bridge patch digest receipts.

    Bridge-submitted agent patches are the federation's autonomous supply
    chain, and trust today is narrative (agentIdentity prose), not
    cryptographic. Minimal lane (EXTRACT_PATTERNS_ONLY — sigstore is NOT
    vendored): a submission that wants tamper-evidence ships a
    machine-readable receipt at docs/provenance/bridge-<taskId>.json listing
    per-file sha256 digests of the full_file contents AS SUBMITTED. This
    sub-check recomputes the digests on the checked-out branch and fails
    closed on mismatch: any post-receipt edit of a listed file breaks the
    match, detecting post-review mutation of agent patches.

    Honest limitation (mirrors the issue): the receipt travels with the
    patch over the same automated channel, so the bar rises from narrative
    trust to tamper-evidence — a compromised submitter is not eliminated,
    and attestation proves provenance, not code correctness. The full lane
    (actions/attest-build-provenance under .github/) is admin-owned and out
    of scope for this guard.

    Only invoked in full-repo mode (targets=None); the offline self-test
    path passes explicit targets and stays deterministic/fast. An absent or
    empty receipts dir is a no-op (additive; zero false positives for
    layouts without receipts). ``receipts_dir`` is injectable so offline
    tests can exercise the verifier without touching tracked files; target
    paths always resolve against REPO_ROOT (the checked-out branch).
    """
    root = receipts_dir if receipts_dir is not None else REPO_ROOT / "docs" / "provenance"
    errors: list[str] = []
    if not root.is_dir():
        return errors
    repo_resolved = str(REPO_ROOT.resolve())
    for receipt_path in sorted(root.glob("*.json")):
        try:
            rel = receipt_path.relative_to(REPO_ROOT)
        except ValueError:
            # Injected out-of-repo receipts dir (offline tests): label by path.
            rel = receipt_path
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            errors.append(f"{rel}: unreadable/malformed provenance receipt: {e}")
            continue
        if not isinstance(receipt, dict):
            errors.append(f"{rel}: receipt must be a JSON object")
            continue
        algorithm = receipt.get("algorithm")
        if algorithm != "sha256":
            errors.append(
                f"{rel}: unsupported algorithm {algorithm!r} (only sha256 verifiable)"
            )
            continue
        entries = receipt.get("files")
        if not isinstance(entries, list) or not entries:
            errors.append(f"{rel}: receipt 'files' must be a non-empty list")
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append(f"{rel}: file entry must be an object: {entry!r}")
                continue
            path_str = entry.get("path")
            claimed = entry.get("sha256")
            if not isinstance(path_str, str) or not path_str:
                errors.append(f"{rel}: file entry missing 'path'")
                continue
            if (
                not isinstance(claimed, str)
                or len(claimed) != 64
                or any(c not in "0123456789abcdef" for c in claimed.lower())
            ):
                errors.append(f"{rel}: entry '{path_str}' has an invalid sha256 digest")
                continue
            target = (REPO_ROOT / path_str).resolve()
            if not str(target).startswith(repo_resolved + os.sep):
                errors.append(
                    f"{rel}: entry '{path_str}' escapes the repo (path traversal rejected)"
                )
                continue
            if not target.is_file():
                errors.append(f"{rel}: listed file missing on branch: {path_str}")
                continue
            actual = hashlib.sha256(target.read_bytes()).hexdigest()
            if actual != claimed.lower():
                errors.append(
                    f"{rel}: PROVENANCE MISMATCH for {path_str} — receipt "
                    f"{claimed.lower()} vs branch {actual} "
                    "(post-receipt mutation of an agent patch?)"
                )
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
    # #1674: provenance digest receipts verify on the same full-repo-only path.
    if targets is None:
        errors.extend(_script_index_freshness())
        errors.extend(_provenance_digest())

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


def run_step4_migrations() -> tuple[bool, list[str]]:
    versions_dir = REPO_ROOT / "core" / "alembic_migrations" / "versions"
    errors = []
    if not versions_dir.is_dir():
        print("[Step 4: Migration Guard] Skipped: versions dir not found.")
        return True, []
    files = sorted(f for f in versions_dir.glob("*.py") if not f.name.startswith("__"))
    revisions = {}
    down_revisions = {}
    import ast
    for f in files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append("compile error in %s: %s" % (f.name, e))
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, OSError) as e:
            errors.append("parse error in %s: %s" % (f.name, e))
            continue
        rev = None
        down = None
        for node in ast.walk(tree):
            targets = []
            value = None
            if isinstance(node, ast.Assign):
                targets = node.targets
                value = node.value
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
                value = node.value
            for t in targets:
                if isinstance(t, ast.Name) and t.id == "revision":
                    if isinstance(value, ast.Constant):
                        rev = value.value
                if isinstance(t, ast.Name) and t.id == "down_revision":
                    if isinstance(value, ast.Constant):
                        down = value.value
                    elif isinstance(value, ast.Tuple):
                        down = tuple((e.value if isinstance(e, ast.Constant) else None) for e in value.elts)
        if rev is None:
            errors.append("%s: missing revision assignment" % f.name)
            continue
        if rev in revisions:
            errors.append("duplicate revision id %r" % rev)
        revisions[rev] = f
        down_revisions[rev] = down
    for rev, down in down_revisions.items():
        if down is None:
            continue
        if isinstance(down, tuple):
            for d in down:
                if d is not None and d not in revisions:
                    errors.append("revision %r references unknown down_revision %r" % (rev, d))
        else:
            if down not in revisions:
                errors.append("revision %r references unknown down_revision %r" % (rev, down))
    if errors:
        for e in errors:
            print("[Step 4: Migration Guard] %s" % e)
        return False, errors
    print("[Step 4: Migration Guard] OK: %d migration files, %d revisions, chain consistent" % (len(files), len(revisions)))
    return True, []


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
        "--step4-migrations",
        action="store_true",
        help="Run Step 4 (DB migration chain check, #1691)",
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

    # Step 4: Migrations
    if run_all or args.step4_migrations:
        s4_pass, s4_errs = run_step4_migrations()
        results["step4_migrations"] = {"passed": s4_pass, "errors": s4_errs}
        if not s4_pass:
            overall_pass = False

    if args.json:
        print(json.dumps(results, indent=2))

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
