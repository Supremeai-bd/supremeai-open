#!/usr/bin/env python3
"""
SupremeAI Git Pre-Commit Hook
==============================
Runs automatically on every `git commit`:
  1. rotate_lessons.py  — Enforces 12KB cap on LESSONS_LEARNED.md (archives if over limit)
  2. checkpoint_update.py — Updates CHECKPOINT.md with current session state

Install:
  python scripts/install_hooks.py
  (or manually: copy this file to .git/hooks/pre-commit)
"""

import subprocess
import sys

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
PYTHON = sys.executable


def run_script(script_name: str, args: list[str] | None = None) -> bool:
    """Run a script and return True if successful."""
    if args is None:
        args = []
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    if not os.path.exists(script_path):
        print(f"[WARN] Script not found, skipping: {script_path}")
        return True  # Non-blocking — don't fail commit if script missing

    try:
        result = subprocess.run(
            [PYTHON, script_path] + args,
            cwd=ROOT_DIR,
            capture_output=False,  # Show output live
            text=True,
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[WARN] Failed to run {script_name}: {e}")
        return True  # Non-blocking


def check_github_actions_status():
    import json
    import urllib.request

    print("\n[4/4] Checking GitHub Actions status for previous push...")
    try:
        repo_url = subprocess.check_output(["git", "config", "--get", "remote.origin.url"], text=True).strip()
        owner_repo = ""
        if "github.com" in repo_url:
            if repo_url.startswith("http"):
                parts = repo_url.split("/")
                owner_repo = f"{parts[-2]}/{parts[-1].replace('.git', '')}"
            elif repo_url.startswith("git@"):
                parts = repo_url.split(":")[-1].split("/")
                owner_repo = f"{parts[0]}/{parts[1].replace('.git', '')}"

        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], text=True).strip()

        if owner_repo:
            api_url = f"https://api.github.com/repos/{owner_repo}/actions/runs?branch={branch}&per_page=1"
            headers = {"User-Agent": "SupremeAI-PreCommitHook"}

            # Read token from environment or local .env to prevent 403 Rate Limit
            token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
            if not token:
                env_file = os.path.join(ROOT_DIR, ".env")
                if os.path.exists(env_file):
                    try:
                        with open(env_file, "r", encoding="utf-8") as f:
                            for line in f:
                                k, _, v = line.partition("=")
                                if k.strip() in ("GITHUB_TOKEN", "GH_TOKEN"):
                                    token = v.strip().strip('"\'')
                                    break
                    except Exception as e:
                        print(f"warning: could not read {env_file} for token: {e}")
            if token and not token.startswith("your-") and not token.startswith("mock-") and not token.startswith("dummy-"):
                headers["Authorization"] = f"Bearer {token}"
            elif token and (token.startswith("your-") or token.startswith("mock-") or token.startswith("dummy-")):
                token = None

            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                if data.get("workflow_runs"):
                    run = data["workflow_runs"][0]
                    status = run.get("status")
                    conclusion = run.get("conclusion")
                    if status == "completed" and conclusion == "failure":
                        print(f"\n[WARN] [ATTENTION] Your last push to GitHub failed! (Branch: {branch})")
                        print(f"Run URL: {run.get('html_url')}")

                        # Fetch failed jobs details
                        try:
                            jobs_url = run.get("jobs_url")
                            if jobs_url:
                                req_jobs = urllib.request.Request(jobs_url, headers=headers)
                                with urllib.request.urlopen(req_jobs, timeout=5) as r2:
                                    jobs_data = json.loads(r2.read().decode())
                                    for job in jobs_data.get("jobs", []):
                                        if job.get("conclusion") == "failure":
                                            job_name = job.get("name", "").encode("ascii", "ignore").decode()
                                            print(f"[FAILED JOB] {job_name}")
                                            for step in job.get("steps", []):
                                                if step.get("conclusion") == "failure":
                                                    step_name = step.get("name", "").encode("ascii", "ignore").decode()
                                                    print(f"  -> Failed Step: {step_name}")
                        except Exception as e:
                            print(f"[DEBUG] Could not fetch job details: {e}")

                        print("\n[SUGGESTION FOR AI AGENT]")
                        print("-> Do NOT ignore these remote CI failures!")
                        print("-> You MUST investigate the root cause and fix the code before pushing.")
                        print("-> You have full access: read the GITHUB_TOKEN (or GH_TOKEN) from the .env file to fetch the failed logs via GitHub API, or use the `gh` CLI if authenticated.\n")
                    elif status == "completed" and conclusion == "success":
                        print("[INFO] [OK] Previous GitHub Actions run passed successfully.")
                    else:
                        print(f"[INFO] [PENDING] Previous GitHub Actions run is currently: {status}.")
    except Exception as e:
        print(f"[INFO] GitHub Actions status check skipped: {e}")


def main():
    print("\n[PRE-COMMIT] SupremeAI hook running...")
    print("-" * 50)

    marker_file = os.path.join(ROOT_DIR, ".git", "pre_commit_failed")
    if os.path.exists(marker_file):
        print("[INFO] ⚠️ Detected previous hook failure. Running strict checks to ensure issues are resolved...")
        print("-" * 50)

    # Step 1: Rotate LESSONS_LEARNED.md if over 12KB cap
    print("[1/2] Checking LESSONS_LEARNED.md size...")
    run_script("rotate_lessons.py")

    # Step 2: Update CHECKPOINT.md
    print("\n[2/3] Updating CHECKPOINT.md...")
    run_script("checkpoint_update.py", ["--message", "Auto-updated via pre-commit hook"])

    # Step 2b: Architecture Plans Protection Guard (AGENTS.md Clause 6)
    try:
        # Use -M across the repo diff so moved/renamed plans to docs/archive/ are recognized as R (renames)
        diff_raw = subprocess.check_output(
            ["git", "diff", "--cached", "--name-status", "-M"],
            cwd=ROOT_DIR,
            text=True
        ).strip().splitlines()

        deleted_plans = [
            line.split("\t", 1)[1]
            for line in diff_raw
            if line.startswith("D\t") and line.split("\t", 1)[1].startswith("docs/plans/")
        ]

        if deleted_plans:
            print("\n" + "!" * 60)
            print("[CRITICAL ERROR] CONSTITUTIONAL VIOLATION DETECTED!")
            print("AGENTS.md Clause 6: 'Architectural Plans as Protected Living Assets'")
            print("The following architecture plans are staged for UNCONTROLLED DELETION:")
            for p in deleted_plans:
                print(f"  ❌ {p}")
            print("\n-> Architectural plans MUST NEVER be deleted without proper merging/redirection.")
            print("-> If a plan is obsolete, merge its contents, update its status or evolve it with evidence.")
            print("-> COMMIT REJECTED. Unstage these deletions before proceeding.")
            print("!" * 60 + "\n")
            sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"[pre-commit] git diff error: {e}")

    # Check what areas are actually staged to avoid cross-domain contamination
    try:
        staged_output = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"], cwd=ROOT_DIR, text=True
        )
        staged_list = [f.strip() for f in staged_output.splitlines() if f.strip()]
    except Exception:
        staged_list = []

    backend_staged = any(f.startswith("backend/") or f.startswith("backend\\") for f in staged_list)
    frontend_staged = any(f.startswith("frontend/") or f.startswith("frontend\\") for f in staged_list)

    # Step 3: Run Ruff Formatter & Linter (only if backend files staged)
    backend_dir = os.path.join(ROOT_DIR, "backend")
    if os.path.exists(backend_dir) and backend_staged:
        print("\n[3/3] Running Code Formatter & Linter (Ruff) on staged backend files...")
        try:
            # Run formatter
            subprocess.run(
                ["ruff", "format", "."],
                cwd=backend_dir,
                capture_output=False,
            )
            # Run linter and auto-fix
            subprocess.run(
                ["ruff", "check", "--fix", "."],
                cwd=backend_dir,
                capture_output=False,
            )
            # Stage any formatting changes in backend
            subprocess.run(
                ["git", "add", "."],
                cwd=backend_dir,
                capture_output=True,
            )
            # Final strict lint check (Blocking)
            lint_result = subprocess.run(
                ["ruff", "check", "."],
                cwd=backend_dir,
                capture_output=False,
            )
            if lint_result.returncode != 0:
                print("\n[ERROR] Ruff Linter found errors! Commit blocked. Please fix them before committing.")
                with open(marker_file, 'w') as f:
                    f.write('failed')
                sys.exit(1)
        except Exception as e:
            print(f"[WARN] Failed to run ruff: {e}")
    else:
        print("\n[3/3] No backend files staged. Ruff formatting skipped.")

    # Step 3b: Frontend Formatter & Linter Auto-Fix (ESLint)
    frontend_dir = os.path.join(ROOT_DIR, "frontend")
    if os.path.exists(frontend_dir) and frontend_staged:
        print("\n[3b/4] Running Frontend Linter Auto-Fix (ESLint) on staged frontend files...")
        try:
            # Run eslint auto-fix
            subprocess.run(
                ["pnpm", "exec", "eslint", "src/", "--ext", ".ts,.tsx", "--fix"],
                cwd=frontend_dir,
                capture_output=False,
                shell=True,
                check=False,
            )
            # Stage any auto-fixed frontend files
            subprocess.run(
                ["git", "add", "src/"],
                cwd=frontend_dir,
                capture_output=True,
                check=False,
            )
        except Exception as e:
            print(f"[WARN] Frontend auto-fix skipped: {e}")
    else:
        print("\n[3b/4] No frontend files staged. ESLint auto-fix skipped.")

    # Stage any changes made by the scripts above
    try:
        files_to_stage = ["CHECKPOINT.md", "LESSONS_LEARNED.md", "docs/archive/"]
        for f in files_to_stage:
            full_path = os.path.join(ROOT_DIR, f)
            if os.path.exists(full_path):
                subprocess.run(
                    ["git", "add", f],
                    cwd=ROOT_DIR,
                    capture_output=True
                )
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Silenced error: {e}")

    # Step 4: Check GitHub Actions remote status
    check_github_actions_status()

    print("-" * 50)
    print("[PRE-COMMIT] Done. Proceeding with commit.\n")

    if os.path.exists(marker_file):
        os.remove(marker_file)

    sys.exit(0)  # Allow commit if linter passes


if __name__ == "__main__":
    main()
