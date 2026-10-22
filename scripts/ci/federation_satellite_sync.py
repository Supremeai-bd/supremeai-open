#!/usr/bin/env python3
"""
federation_satellite_sync.py — Direct Federation Satellite & Monorepo Synchronizer.

Mission:
  When a commit or PR lands on `supremeai-open:main`, this script directly,
  deterministically, and immediately pushes the scoped domain files into the
  respective target satellite repository's `main` branch (and the central monorepo).

Guarantees:
  - Zero-middleman: No waiting for asynchronous dispatch receivers or external bridge bots.
  - Idempotent: If the target repo is already up to date, it clean-skips (no-op).
  - Fail-closed: If token is missing or push fails, exits with non-zero code.
  - Ephemeral patch auto-pruning: Any lingering patch files in patches/ are cleanly pruned.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# Mapping of target repository to its source directory in supremeai-open
# (slug -> relative source path in supremeai-open)
DOMAIN_MAP: dict[str, str] = {
    "Supremeai-bd/supremeai-studio": "studio",
    "Supremeai-bd/supremeai-core": "core",
    "Supremeai-bd/supremeai-command": "command",
    "Supremeai-bd/supremeai-api": "gateway",
    "Supremeai-bd/supremeai-agents": "agents",
    "Supremeai-bd/supremeai-skills": "skills",
    "Supremeai-bd/supremeai-browser": "browser",
    "Supremeai-bd/supremeai-vscode": "vscode",
    "Supremeai-bd/supremeai-infrastructure": "infra",
    "Supremeai-bd/supremeai-mcp-control-plane": "infrastructure/mcp-control-plane",
    "Supremeai-bd/supremeai-sdk": "sdk",
}

# Mirrored contract files mapped from supremeai-open root to specific satellite destination paths:
# (source_rel_in_open, target_repo, target_rel_in_satellite)
CONTRACT_MIRROR_PAIRS: list[tuple[str, str, str]] = [
    (
        "examples/gateway_client.py",
        "Supremeai-bd/supremeai-api",
        "scripts/clients/gateway_client.py",
    ),
    (
        "api-schemas/gateway.openapi.yaml",
        "Supremeai-bd/supremeai-api",
        "contracts/openapi.yaml",
    ),
]

# Monorepo sync ignores: files in supremeai-open that should not overwrite monorepo root configs
MONOREPO_EXCLUDES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    ".DS_Store",
}


def get_auth_token(token_arg: str | None = None) -> str:
    """Resolve GitHub token with write access to target repositories."""
    if token_arg and token_arg.strip():
        return token_arg.strip()
    for env_var in ("BRIDGE_PUSH_TOKEN", "SAT_SYNC_PAT", "GITHUB_TOKEN", "GH_TOKEN"):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val
    # Fallback to local gh CLI if available
    try:
        out = subprocess.check_output(
            ["gh", "auth", "token"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        if out:
            return out
    except Exception:
        pass
    raise RuntimeError(
        "No GitHub authentication token found (checked BRIDGE_PUSH_TOKEN, SAT_SYNC_PAT, GH_TOKEN)."
    )


def copy_tree_contents(src: Path, dst: Path) -> None:
    """Recursively copy files from src to dst, skipping caches and git metadata."""
    if not src.exists():
        return
    for root, dirs, files in os.walk(src):
        # Exclude hidden git/cache dirs
        dirs[:] = [
            d
            for d in dirs
            if d not in (".git", "__pycache__", ".pytest_cache", "node_modules")
        ]
        rel = Path(root).relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                continue
            s_file = Path(root) / f
            d_file = target_dir / f
            shutil.copy2(s_file, d_file)


def sync_satellite(
    target_repo: str,
    source_dir: str,
    repo_root: Path,
    token: str,
    commit_msg: str,
) -> bool:
    """Clone target satellite, copy files, commit and push if diff exists."""
    slug = target_repo.split("/")[-1]
    src_path = repo_root / source_dir
    if not src_path.exists():
        print(
            f"⏩ [SKIP] Source directory '{source_dir}' does not exist for {target_repo}."
        )
        return True

    clone_url = f"https://x-access-token:{token}@github.com/{target_repo}.git"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_repo = Path(tmp_dir) / slug
        print(f"📥 Cloning {target_repo}:main into temporary workspace...")
        r = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(tmp_repo)],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            print(f"❌ Failed to clone {target_repo}: {r.stderr.strip()}")
            return False

        # Copy domain files into the satellite root
        copy_tree_contents(src_path, tmp_repo)

        # Copy contract mirror pairs specific to this satellite
        for open_rel, sat_repo, sat_rel in CONTRACT_MIRROR_PAIRS:
            if sat_repo == target_repo:
                src_file = repo_root / open_rel
                dst_file = tmp_repo / sat_rel
                if src_file.exists():
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)

        # For consolidated unified API engine (supremeai-api per ARCHITECTURE_PLAN):
        if target_repo == "Supremeai-bd/supremeai-api":
            for sub in ("command", "skills", "agents", "gateway"):
                sub_src = repo_root / sub
                if sub_src.exists():
                    copy_tree_contents(sub_src, tmp_repo / sub)
                    print(
                        f"📋 Mirrored contract file '{open_rel}' -> '{sat_rel}' in {target_repo}"
                    )

        # Check for diff
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(tmp_repo),
            text=True,
        ).strip()

        if not status:
            print(
                f"✅ [NO-OP] {target_repo} is already in perfect sync with '{source_dir}'."
            )
            return True

        print(f"📝 Diff detected in {target_repo}:\n{status}")

        # Commit and push
        subprocess.check_call(
            ["git", "config", "user.name", "github-actions[bot]"],
            cwd=str(tmp_repo),
        )
        subprocess.check_call(
            [
                "git",
                "config",
                "user.email",
                "github-actions[bot]@users.noreply.github.com",
            ],
            cwd=str(tmp_repo),
        )
        subprocess.check_call(["git", "add", "-A"], cwd=str(tmp_repo))
        msg = f"sync(open->{slug}): {commit_msg} [skip ci]"
        subprocess.check_call(["git", "commit", "-m", msg], cwd=str(tmp_repo))

        # Avoid non-fast-forward rejection on concurrent landings (#416).
        subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            check=False,
        )

        print(f"🚀 Pushing changes to {target_repo}:main...")
        push_res = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if push_res.returncode == 0:
            print(f"🎉 [SUCCESS] Successfully synced and pushed to {target_repo}:main")
            return True
        else:
            print(f"❌ Failed to push to {target_repo}: {push_res.stderr.strip()}")
            return False


def sync_monorepo(
    repo_root: Path,
    token: str,
    commit_msg: str,
) -> bool:
    """Sync full umbrella monorepo Supremeai-bd/supremeai."""
    target_repo = "Supremeai-bd/supremeai"
    clone_url = f"https://x-access-token:{token}@github.com/{target_repo}.git"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_repo = Path(tmp_dir) / "supremeai"
        print(f"📥 Cloning {target_repo}:main for umbrella sync...")
        r = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, str(tmp_repo)],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            print(f"❌ Failed to clone {target_repo}: {r.stderr.strip()}")
            return False

        # Copy non-excluded root dirs and files
        for item in repo_root.iterdir():
            if item.name in MONOREPO_EXCLUDES or item.name.startswith(".git"):
                continue
            dst_item = tmp_repo / item.name
            if item.is_dir():
                copy_tree_contents(item, dst_item)
            else:
                shutil.copy2(item, dst_item)

        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(tmp_repo),
            text=True,
        ).strip()

        if not status:
            print(f"✅ [NO-OP] {target_repo} is already in perfect sync.")
            return True

        print(f"📝 Diff detected in {target_repo}:\n{status}")

        subprocess.check_call(
            ["git", "config", "user.name", "github-actions[bot]"],
            cwd=str(tmp_repo),
        )
        subprocess.check_call(
            [
                "git",
                "config",
                "user.email",
                "github-actions[bot]@users.noreply.github.com",
            ],
            cwd=str(tmp_repo),
        )
        subprocess.check_call(["git", "add", "-A"], cwd=str(tmp_repo))
        msg = f"sync(open->monorepo): {commit_msg} [skip ci]"
        subprocess.check_call(["git", "commit", "-m", msg], cwd=str(tmp_repo))

        # Avoid non-fast-forward rejection on concurrent landings (#416).
        subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            check=False,
        )

        print(f"🚀 Pushing umbrella changes to {target_repo}:main...")
        push_res = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if push_res.returncode == 0:
            print(
                f"🎉 [SUCCESS] Successfully synced umbrella monorepo {target_repo}:main"
            )
            return True
        else:
            print(f"❌ Failed to push to {target_repo}: {push_res.stderr.strip()}")
            return False


def prune_ephemeral_patches(repo_root: Path) -> None:
    """Remove lingering .patch files from patches/ directory (Rule #416)."""
    patches_dir = repo_root / "patches"
    if not patches_dir.exists():
        return
    patch_files = list(patches_dir.glob("*.patch"))
    if not patch_files:
        return
    print(f"🧹 Pruning {len(patch_files)} ephemeral patch file(s) from patches/...")
    for pf in patch_files:
        try:
            pf.unlink()
            print(f"  - Removed: {pf.name}")
        except Exception as e:
            print(f"  ⚠️ Could not remove {pf.name}: {e}")


def self_test() -> bool:
    """Self-test verifying contract and mappings."""
    assert len(DOMAIN_MAP) == 11, (
        f"Expected 11 satellites in DOMAIN_MAP, got {len(DOMAIN_MAP)}"
    )
    assert "Supremeai-bd/supremeai-studio" in DOMAIN_MAP
    assert "Supremeai-bd/supremeai-core" in DOMAIN_MAP
    assert "Supremeai-bd/supremeai-api" in DOMAIN_MAP
    assert len(CONTRACT_MIRROR_PAIRS) >= 2, (
        "Expected at least 2 mirrored contract pairs"
    )
    for open_rel, sat_repo, sat_rel in CONTRACT_MIRROR_PAIRS:
        assert sat_repo in DOMAIN_MAP, (
            f"Target repo {sat_repo} must exist in DOMAIN_MAP"
        )
        assert open_rel and sat_rel, "Mirror paths must be non-empty"
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synchronize supremeai-open changes directly to satellites."
    )
    parser.add_argument(
        "--targets",
        nargs="*",
        help="Specific target repositories to sync (default: all mapped)",
    )
    parser.add_argument(
        "--all", action="store_true", help="Sync all 11 satellites and central monorepo"
    )
    parser.add_argument("--token", help="GitHub Personal Access Token or App Token")
    parser.add_argument(
        "--commit-msg",
        default="synchronize federation transit surface",
        help="Commit message",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run contract verification self-test"
    )
    parser.add_argument(
        "--prune-patches",
        action="store_true",
        help="Auto-prune ephemeral patches in patches/",
    )

    args = parser.parse_args()

    if args.self_test:
        print("[self-test] Validating satellite sync contract...")
        if self_test():
            print("✅ [self-test] All satellite sync contract checks passed!")
            return 0
        return 1

    repo_root = Path(__file__).resolve().parent.parent.parent

    if args.prune_patches:
        prune_ephemeral_patches(repo_root)

    try:
        token = get_auth_token(args.token)
    except Exception as e:
        print(f"❌ Authentication Error: {e}")
        return 2

    # Determine targets
    targets_to_sync: list[str] = []
    sync_umbrella = False

    if args.all:
        targets_to_sync = list(DOMAIN_MAP.keys())
        sync_umbrella = True
    elif args.targets:
        for t in args.targets:
            t = t.strip()
            if t == "Supremeai-bd/supremeai":
                sync_umbrella = True
            elif t in DOMAIN_MAP:
                targets_to_sync.append(t)
            else:
                print(f"⚠️ Unrecognized target repository '{t}'. Skipping.")
    else:
        # Default: sync all mapped satellites
        targets_to_sync = list(DOMAIN_MAP.keys())
        sync_umbrella = True

    print(
        f"🎯 Target Repositories to Sync: {targets_to_sync} (Umbrella: {sync_umbrella})"
    )

    success = True
    for target in targets_to_sync:
        src_dir = DOMAIN_MAP[target]
        ok = sync_satellite(target, src_dir, repo_root, token, args.commit_msg)
        if not ok:
            success = False

    if sync_umbrella:
        ok = sync_monorepo(repo_root, token, args.commit_msg)
        if not ok:
            success = False

    if not success:
        print("❌ One or more repository sync operations failed.")
        return 1

    print("🎉 All federation target repositories synchronized successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
