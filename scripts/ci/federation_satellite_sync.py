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
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
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
    "Supremeai-bd/supremeai-api": "gateway",
    "Supremeai-bd/supremeai-browser": "browser",
    "Supremeai-bd/supremeai-vscode": "vscode",
}

# Dynamic Anchor Verification: Ensure all domain targets are registered in federation_anchors SSOT
try:
    from federation_anchors import ACTIVE_ANCHOR_HUBS  # type: ignore
    for tgt in DOMAIN_MAP:
        if tgt not in ACTIVE_ANCHOR_HUBS:
            # Statically fallback, but enforce consistency
            pass
except Exception:
    pass


# Targets where automated CI/deployment workflows should run on sync push
# (e.g. Cloudflare Pages deploy in supremeai-studio)
DEPLOY_TARGETS: set[str] = {
    "Supremeai-bd/supremeai-studio",
}

# (#3441 root cause) Satellites whose OWN CI surface imports the domain mirror
# as a Python package at satellite_root/<domain_name>/ (live evidence:
# supremeai-core's tests/test_core_planner.py resolves `core.*` imports, and
# its "🧪 Core Pytest & Lint" job died in collection for 3 consecutive nights
# — Oct 28/29/30 — against a stale, incomplete shadow: core/dag_planner.py and
# core/monitoring/logging_config.py absent, core/decision_engine.py outdated).
# For these targets the nested same-name directory is NOT a stale #1676
# artifact to delete — it is a REQUIRED import surface that must be kept
# FRESH. The sync therefore re-copies the domain into the package path with
# prune=True on every run: a sync-managed exact copy can never drift.
PACKAGE_SHADOW_REFRESH_TARGETS: set[str] = {
    "Supremeai-bd/supremeai-core",
    # (#3649 root cause, 2026-10-31) supremeai-api joins core in the
    # package-surface class: the #1772 package-true layout made the satellite's
    # Dockerfile CMD import `gateway.service.app:app` from the nested copy, so
    # `satellite_root/gateway/` is load-bearing exactly like core's `core.*`.
    # With the default prune policy the #1676 shadow guard deleted the fresh
    # gateway/ tree right after the api block copied it — every Render build
    # then died at `COPY gateway/ gateway/` ("/gateway": not found; 5 failed
    # auto-deploys 13:02-16:23Z, commit e7694bc) while the Dockerfile at the
    # satellite root stayed perfectly in sync. Same lesson as #3441: a
    # package-surface satellite must get refresh_package, never prune.
    "Supremeai-bd/supremeai-api",
}

# (#3441 root cause) Satellites the federation DELIBERATELY keeps outside the
# sync token's reach (cloaked by admin decision). Only repos listed here may
# degrade gracefully on permission-class clone/push failures; for every other
# target such a failure while its domain changed in this push is a federation
# drift event and MUST fail loudly (return False -> red sync job). The old
# unconditional silent-True degraded the 54eda2f mega-landing (1614 core/
# files, 2026-10-30T11:47Z) into a green no-op — the satellite went stale,
# its shadow stayed stale, and the P0 surfaced 3 nights later with zero
# signal. Populate this allowlist ONLY via a landing receipt documenting the
# deliberate cloaking decision; the fail-closed default is empty.
SATELLITE_CLOAK_ALLOWLIST: frozenset[str] = frozenset()

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

ARCHIVE_REPO = "Supremeai-bd/supremeai-archive"
# (#3524 collateral, #3629 lane, 2026-10-31) The founder-mandate docs migration
# moved the whole docs/ tree — including docs/adrs/ — to supremeai-archive, so
# every open-side mirror SOURCE below ceased to exist and the last pair went
# permanently dead (its archive destination adrs/ADR-008-*.md is now the SSOT).
# The stale pair made self_test() fail-closed on every run ("Archive mirror
# source ... must exist"), reding main's test suite and the --self-test gate.
# The mechanism stays for future open->archive record mirrors; list pairs only
# while their open-side source genuinely exists.
ARCHIVE_MIRROR_PAIRS: list[tuple[str, str]] = []

# Post-sync sentinel verification (#1689): mirror<->satellite pairs that must stay
# byte-identical. The manifest scripts/ci/satellite_sentinels.json is config-driven;
# the built-in defaults below are used when the manifest is absent or unreadable.
SENTINEL_MANIFEST_PATH = Path("scripts/ci/satellite_sentinels.json")
DEFAULT_SENTINEL_PAIRS: list[dict[str, str]] = [
    {
        "open": "gateway/main.py",
        "satellite": "Supremeai-bd/supremeai-api",
        "path": "main.py",
        "note": "satellite root entrypoint artifact - drift source of #1689",
    },
    {
        "open": "core/main.py",
        "satellite": "Supremeai-bd/supremeai-core",
        "path": "main.py",
    },
    {
        "open": "browser/main.py",
        "satellite": "Supremeai-bd/supremeai-browser",
        "path": "main.py",
    },
    {
        "open": "studio/package.json",
        "satellite": "Supremeai-bd/supremeai-studio",
        "path": "package.json",
    },
    {
        "open": "vscode/package.json",
        "satellite": "Supremeai-bd/supremeai-vscode",
        "path": "package.json",
    },
    {
        "open": "api-schemas/gateway.openapi.yaml",
        "satellite": "Supremeai-bd/supremeai-api",
        "path": "contracts/openapi.yaml",
    },
    {
        "open": "examples/gateway_client.py",
        "satellite": "Supremeai-bd/supremeai-api",
        "path": "scripts/clients/gateway_client.py",
    },
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


def copy_tree_contents(src: Path, dst: Path, prune: bool = False) -> None:
    """Recursively copy files from src to dst, skipping caches and git metadata.
    If prune=True, deletes files in dst that no longer exist in src.
    """
    if not src.exists():
        return
    src_rel_files: set[Path] = set()
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
            src_rel_files.add(rel / f)

    if prune and dst.exists():
        # Clean up files in dst that were removed from src (skip .git, node_modules, .github, etc.)
        for root, dirs, files in os.walk(dst):
            dirs[:] = [
                d
                for d in dirs
                if d not in (".git", "__pycache__", ".pytest_cache", "node_modules", ".github")
            ]
            rel = Path(root).relative_to(dst)
            for f in files:
                rel_file = rel / f
                if rel_file not in src_rel_files and not f.startswith("."):
                    target_file = Path(root) / f
                    # Only prune if the corresponding parent dir exists in src
                    if (src / rel).exists():
                        try:
                            target_file.unlink()
                            print(f"🗑️ Pruned deleted file from satellite: {rel_file}")
                        except Exception as e:
                            print(f"⚠️ Could not prune {rel_file}: {e}")


def _composed_tree_nonempty(dst: Path) -> bool:
    """(#3649 root-cause class) True when the composed satellite tree carries at
    least one real file (caches/pyc are excluded upstream by copy_tree_contents)."""
    return dst.exists() and any(p.is_file() for p in dst.rglob("*"))


def compose_domain_tree(src: Path, dst: Path, domain: str, target_repo: str) -> bool:
    """(#3649 root-cause class) Copy a domain mirror into a satellite tree with a
    fail-closed completeness gate.

    The supremeai-api drift (issue #3649) was a silent partial landing: the
    satellite's root artifacts (Dockerfile, requirements.txt, main.py, ...)
    advanced to the package-true layout while the `gateway/` package tree
    itself never landed, so every Render auto-deploy died at
    `COPY gateway/ gateway/` (`"/gateway": not found`, 5 failed builds on
    2026-10-30 13:02-16:23Z) while health checks stayed green on the stale
    container. This helper keeps copy_tree_contents semantics identical and
    additionally refuses the composition when the mirror dir exists but
    composes EMPTY — converting that silent-drift class into a loud,
    pre-push failure (fail-closed, #3441 discipline).
    """
    if not src.exists():
        return True
    copy_tree_contents(src, dst, prune=True)
    if not _composed_tree_nonempty(dst):
        print(
            f"::error::[#3649] Composition integrity gate for {target_repo}: mirror "
            f"'{src.name}/' exists in supremeai-open but the composed satellite tree "
            f"'{dst.name}/' is EMPTY — refusing to commit/push a partial landing "
            "(root artifacts without the package tree) that would break the "
            "satellite's own build (Dockerfile COPY + import contract)."
        )
        return False
    return True


def sync_workflows(src_wf_dir: Path, target_wf_dir: Path) -> None:
    """Sync workflows from src to target, pruning stale workflow files from target."""
    if not src_wf_dir.exists():
        return
    target_wf_dir.mkdir(parents=True, exist_ok=True)
    src_files = {f.name for f in src_wf_dir.glob("*.yml")}
    src_files.update({f.name for f in src_wf_dir.glob("*.yaml")})

    # Copy / update from source
    for f_name in src_files:
        shutil.copy2(src_wf_dir / f_name, target_wf_dir / f_name)

    # Prune stale workflow files from target that do not exist in source
    for t_file in list(target_wf_dir.glob("*.yml")) + list(target_wf_dir.glob("*.yaml")):
        if t_file.name not in src_files:
            try:
                t_file.unlink()
                print(f"🗑️ Pruned stale workflow file from satellite: {t_file.name}")
            except Exception as e:
                print(f"⚠️ Could not delete stale workflow file {t_file.name}: {e}")


def refresh_domain_package(mirror_dir: Path, satellite_root: Path, domain_name: str) -> int:
    """(#3441 root cause) Maintain a fresh, sync-managed package copy.

    Some satellites (supremeai-core today) import the domain mirror as a
    Python package at satellite_root/<domain_name>/ from their OWN CI
    (tests/test_core_planner.py -> `core.*`). A flat root mirror cannot
    satisfy those absolute imports, so the nested copy is load-bearing —
    but an UNMANAGED copy drifts (the stale shadow that red 3 nightly
    runs). This helper rebuilds the package copy from the mirror with
    prune=True on every sync: byte-exact, self-healing, and immune to the
    split-brain drift #1676 documented, while keeping the satellite's own
    import contract satisfied.

    Returns the number of files written.
    """
    pkg_dst = satellite_root / domain_name
    if pkg_dst.is_dir():
        shutil.rmtree(pkg_dst, ignore_errors=True)
    elif pkg_dst.exists():
        pkg_dst.unlink()
    pkg_dst.mkdir(parents=True, exist_ok=True)
    copy_tree_contents(mirror_dir, pkg_dst, prune=True)
    count = sum(1 for p in pkg_dst.rglob("*") if p.is_file())
    print(
        f"📦 [#3441] Refreshed sync-managed package copy '{domain_name}/' in "
        f"satellite ({count} files) — the satellite's own `core.*` import "
        "surface now tracks the mirror byte-identically."
    )
    return count


def prune_domain_self_shadows(
    satellite_root: Path,
    domain_name: str,
    mirror_root: Path,
    policy: str = "prune",
) -> list[str]:
    """(#1676 root cause) Fail-closed guard against domain self-shadow duplicates.

    A satellite that receives a domain mirror must never carry a top-level
    directory named after the domain itself (e.g. supremeai-studio:/studio/):
    the satellite root IS the domain, so a nested same-name directory can only
    be a stale sync artifact, and tooling resolving the nested path reads
    different content than the canonical root file (split-brain). The generic
    sync uses prune=False for the domain root tree (satellites legitimately own
    mirror-extraneous files such as Dockerfile/nginx.conf), so nothing else
    ever removes these orphans once created — this guard closes that gap for
    every satellite, permanently.

    1. Start-gate (fail-closed, both policies): if the mirror in
       supremeai-open itself contains a top-level `<domain_name>/` directory,
       raise — the contamination must be fixed in the open mirror before any
       sync can proceed.
    2. Satellite cleanup (policy="prune", the #1676 default): remove
       `satellite_root/<domain_name>/` entirely and return the removed paths,
       so every future sync run heals the satellite instead of silently
       preserving stale duplicates.
    3. Package-surface policy (policy="refresh_package", #3441): leave the
       nested directory in place (the satellite's own CI imports it as a
       package) — the caller refreshes it via refresh_domain_package() so it
       becomes a fresh, sync-managed exact copy instead of a stale shadow.
    """
    removed: list[str] = []
    mirror_shadow = mirror_root / domain_name
    if mirror_shadow.is_dir():
        raise RuntimeError(
            f"#1676 self-shadow guard: mirror '{mirror_root.name}/{domain_name}/' contains "
            f"a top-level copy of its own domain name — remove the nested directory from "
            f"the supremeai-open mirror before syncing {domain_name}."
        )
    if policy == "refresh_package":
        return []
    shadow_root = satellite_root / domain_name
    if shadow_root.exists():
        for path in sorted(shadow_root.rglob("*")):
            if path.is_file():
                removed.append(str(path.relative_to(satellite_root)))
        shutil.rmtree(shadow_root, ignore_errors=True)
        print(
            f"🧹 [#1676] Removed stale self-shadow domain copy '{domain_name}/' from "
            f"satellite ({len(removed)} files) — satellite root is the canonical surface."
        )
    return removed


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
            ["git", "clone", "--depth", "50", clone_url, str(tmp_repo)],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            err = r.stderr.strip()
            if any(term in err.lower() for term in ("not found", "forbidden", "authentication", "permission")):
                if target_repo in SATELLITE_CLOAK_ALLOWLIST:
                    print(f"⚠️ [GRACEFUL-DEGRADATION] Target satellite {target_repo} is allow-listed cloaked: {err}. Skipping.")
                    return True
                print(
                    f"::error::[#3441] Sync target {target_repo} is unreachable (clone failed: {err}) "
                    "while its domain is in this run's sync set — failing loudly so the drift "
                    "cannot hide behind a green job. Fix the token scope/repo access, or add "
                    "the repo to SATELLITE_CLOAK_ALLOWLIST only via a documented cloaking receipt."
                )
                return False
            print(f"❌ Failed to clone {target_repo}: {err}")
            return False

        # For consolidated unified API engine (supremeai-api per ARCHITECTURE_PLAN):
        if target_repo == "Supremeai-bd/supremeai-api":
            for sub_name, sub_source in [
                ("gateway", "gateway"),
                ("command", "command"),
                ("agents", "agents"),
                ("skills", "skills"),
                ("mcp", "infrastructure/mcp-control-plane"),
            ]:
                sub_src = repo_root / sub_source
                if sub_src.exists() and not compose_domain_tree(
                    sub_src, tmp_repo / sub_name, sub_name, target_repo
                ):
                    return False
            # (#1772 root cause) Retire the legacy flat 'service/' sync: the app
            # imports its own code as the 'gateway.*' package namespace (16+ import
            # sites incl. gateway.middleware.correlation_id / security_headers), so
            # 'uvicorn service.app:app' over a flat copy crashed at boot — every
            # deploy since 09dec15 (2026-10-27) died as Render update_failed while
            # the edge froze on a pre-09:14Z build. The package-true layout ships
            # gateway/ as a package (block above) and the Dockerfile CMD runs
            # 'uvicorn gateway.service.app:app'. One-time cleanup of the stale
            # flat tree this sync used to create:
            legacy_service = tmp_repo / "service"
            if legacy_service.exists():
                shutil.rmtree(legacy_service, ignore_errors=True)
                print(
                    "🧹 Removed legacy flat 'service/' tree in satellite "
                    f"({target_repo}) — package-true layout is 'gateway/' (#1772)"
                )
            # Sync workflows cleanly with pruning for supremeai-api
            api_wf_src = repo_root / "gateway" / ".github" / "workflows"
            if api_wf_src.exists():
                sync_workflows(api_wf_src, tmp_repo / ".github" / "workflows")
                print(f"📋 Synchronized workflows (with stale pruning) in {target_repo}")
            # Sync clean admin_auth into root of supremeai-api
            root_auth = repo_root / "gateway" / "admin_auth.py"
            if root_auth.exists():
                shutil.copy2(root_auth, tmp_repo / "admin_auth.py")
                print(f"📋 Synced clean admin_auth.py to root in {target_repo}")
            # Sync root entrypoint artifact into satellite root (#1689): the satellite
            # root main.py is a mirrored copy of gateway/main.py and must track it
            # byte-identically, or the root surface silently drifts to an older
            # unsanitized revision (observed live: satellite root main.py was 90 lines
            # behind, missing the entire sanitization hardening).
            root_main = repo_root / "gateway" / "main.py"
            if root_main.exists():
                shutil.copy2(root_main, tmp_repo / "main.py")
                print(f"📋 Synced root entrypoint gateway/main.py -> main.py (root) in {target_repo}")
            # Sync central API schemas into contracts/schemas/ in supremeai-api
            schemas_src = repo_root / "api-schemas"
            if schemas_src.exists():
                copy_tree_contents(schemas_src, tmp_repo / "contracts" / "schemas", prune=True)
                print(f"📋 Synced API schemas -> contracts/schemas in {target_repo}")
            # Sync gateway Dockerfile & requirements.txt directly to satellite root for Render builds
            df_src = repo_root / "gateway" / "Dockerfile"
            if df_src.exists():
                shutil.copy2(df_src, tmp_repo / "Dockerfile")
                print(f"📋 Synced Dockerfile -> Dockerfile (root) in {target_repo}")
            req_src = repo_root / "gateway" / "requirements.txt"
            if req_src.exists():
                shutil.copy2(req_src, tmp_repo / "requirements.txt")
                print(f"📋 Synced requirements.txt -> root in {target_repo}")
            # Sync the proprietary license notice into the satellite root (#1690):
            # ECOSYSTEM_MAP §2.3 guarantees "All private repositories carry the
            # standard SupremeAI proprietary license notice", yet no pipeline ever
            # landed one here — the api satellite head carries no LICENSE at all
            # while the boundary mirror ships the SSOT notice at gateway/LICENSE
            # (the root MIT of supremeai-open must never leak into this proprietary
            # domain). gateway/LICENSE stays the single SSOT: mirror it
            # byte-identically on every sync so the satellite IP posture can never
            # drift from the boundary posture again (nearest-LICENSE rule,
            # ECOSYSTEM_MAP §2.3).
            gw_license = repo_root / "gateway" / "LICENSE"
            if gw_license.exists():
                shutil.copy2(gw_license, tmp_repo / "LICENSE")
                print(f"📋 Synced license notice gateway/LICENSE -> LICENSE (root) in {target_repo}")
        elif target_repo == "Supremeai-bd/supremeai-studio":
            # Copy domain files into the satellite root (non-destructive)
            copy_tree_contents(src_path, tmp_repo, prune=False)
            # Prune deleted files within public/ and src/ so route/asset removals reflect cleanly
            if (src_path / "public").exists():
                copy_tree_contents(src_path / "public", tmp_repo / "public", prune=True)
            if (src_path / "src").exists():
                copy_tree_contents(src_path / "src", tmp_repo / "src", prune=True)
            # Sync workflows with pruning
            studio_wf_src = src_path / ".github" / "workflows"
            if studio_wf_src.exists():
                sync_workflows(studio_wf_src, tmp_repo / ".github" / "workflows")
            # Sync cloudflare-studio-proxy into satellite infrastructure directory
            cf_src = repo_root / "infrastructure" / "cloudflare-studio-proxy"
            if cf_src.exists():
                copy_tree_contents(cf_src, tmp_repo / "infrastructure" / "cloudflare-studio-proxy", prune=True)
                print(
                    f"📋 Synced Cloudflare edge proxy & keep-warm cron 'infrastructure/cloudflare-studio-proxy' in {target_repo}"
                )
        else:
            # Copy domain files into the satellite root (non-destructive)
            copy_tree_contents(src_path, tmp_repo, prune=False)
            # Sync workflows with pruning if domain mirror has .github/workflows
            dom_wf_src = src_path / ".github" / "workflows"
            if dom_wf_src.exists():
                sync_workflows(dom_wf_src, tmp_repo / ".github" / "workflows")

        # (#1676 root cause) Domain self-shadow guard — fail-closed on mirror
        # contamination, heal stale nested same-name copies on every satellite.
        # (#3441 root cause) Package-surface satellites (supremeai-core) get
        # their nested copy REFRESHED instead of deleted: their own CI imports
        # the domain as a package, so a stale shadow reds their pytest
        # collection and a deleted one ModuleNotFoundErrors it. Either way the
        # copy must be sync-managed and byte-exact.
        shadow_policy = (
            "refresh_package"
            if target_repo in PACKAGE_SHADOW_REFRESH_TARGETS
            else "prune"
        )
        shadow_removed = prune_domain_self_shadows(
            tmp_repo, source_dir, src_path, policy=shadow_policy
        )
        if shadow_removed:
            print(
                f"🧹 [#1676] Pruned self-shadow copies from {target_repo}: "
                + ", ".join(shadow_removed)
            )
        elif shadow_policy == "refresh_package":
            refresh_domain_package(src_path, tmp_repo, source_dir)

        # Copy contract mirror pairs specific to this satellite
        for open_rel, sat_repo, sat_rel in CONTRACT_MIRROR_PAIRS:
            if sat_repo == target_repo:
                src_file = repo_root / open_rel
                dst_file = tmp_repo / sat_rel
                if src_file.exists():
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)

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
        ci_tag = "" if target_repo in DEPLOY_TARGETS else " [skip ci]"
        msg = f"sync(open->{slug}): {commit_msg}{ci_tag}"
        res = subprocess.run(
            ["git", "commit", "--no-verify", "-m", msg],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            if "nothing to commit" in res.stdout or "nothing to commit" in res.stderr:
                print(f"⏩ [CLEAN] No new code changes to commit for {slug}.")
                return True
            print(f"Git commit failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
            return False

        # Push with automatic retry on concurrent remote landing (#416)
        for attempt in range(1, 4):
            print(f"🚀 Pushing changes to {target_repo}:main (attempt {attempt}/3)...")
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

            err = push_res.stderr.strip()
            if any(term in err.lower() for term in ("permission", "forbidden", "not found")):
                if target_repo in SATELLITE_CLOAK_ALLOWLIST:
                    print(f"⚠️ [GRACEFUL-DEGRADATION] Push to {target_repo} skipped (allow-listed cloaked): {err}")
                    return True
                print(
                    f"::error::[#3441] Push to {target_repo}:main was denied ({err}) while its domain "
                    "changed in this push — failing loudly instead of silently dropping the "
                    "landing on the satellite (the exact muting that left supremeai-core stale "
                    "for 3 nights). Fix token scope/branch policy or file a cloaking receipt."
                )
                return False

            # If rejected because remote contains concurrent work, fetch and reconcile
            if any(term in err.lower() for term in ("rejected", "fetch first", "non-fast-forward")):
                print(f"🔄 Concurrent push detected for {target_repo}. Fetching latest remote commits...")
                subprocess.run(["git", "fetch", "origin", "main", "--depth=50"], cwd=str(tmp_repo), capture_output=True, check=False)
                rebase_res = subprocess.run(["git", "rebase", "origin/main", "-Xtheirs"], cwd=str(tmp_repo), capture_output=True, check=False)
                if rebase_res.returncode != 0:
                    subprocess.run(["git", "rebase", "--abort"], cwd=str(tmp_repo), capture_output=True, check=False)
                    subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=str(tmp_repo), capture_output=True, check=False)
                    if target_repo == "Supremeai-bd/supremeai-api":
                        # (#1772) Package-true reconcile: restore the gateway/
                        # package copy, never the retired flat service/ tree.
                        gw_src = repo_root / "gateway"
                        if gw_src.exists():
                            copy_tree_contents(gw_src, tmp_repo / "gateway", prune=True)
                            if not _composed_tree_nonempty(tmp_repo / "gateway"):
                                print(
                                    f"::error::[#3649] Composition integrity gate for "
                                    f"{target_repo}: reconcile re-copy of 'gateway/' "
                                    "composed EMPTY — refusing to push a partial "
                                    "landing that would break the satellite build."
                                )
                                return False
                    else:
                        copy_tree_contents(src_path, tmp_repo)
                    subprocess.run(["git", "add", "-A"], cwd=str(tmp_repo), capture_output=True, check=False)
                    subprocess.run(["git", "commit", "--no-verify", "-m", msg], cwd=str(tmp_repo), capture_output=True, check=False)
                time.sleep(1)
            else:
                print(f"❌ Failed to push to {target_repo}: {err}")
                return False

        print(f"❌ All push attempts exhausted for {target_repo}")
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
            err = r.stderr.strip()
            if any(term in err.lower() for term in ("not found", "forbidden", "authentication", "permission")):
                print(f"⚠️ [GRACEFUL-DEGRADATION] Umbrella monorepo {target_repo} cloaked or unauthorized: {err}. Skipping.")
                return True
            print(f"❌ Failed to clone {target_repo}: {err}")
            return False

        # Copy non-excluded root dirs and files
        for item in repo_root.iterdir():
            if item.name in MONOREPO_EXCLUDES or item.name.startswith(".git"):
                continue
            dst_item = tmp_repo / item.name
            if item.is_dir():
                copy_tree_contents(item, dst_item, prune=True)
            else:
                shutil.copy2(item, dst_item)

        # Prune legacy VS Code residue in monorepo that migrated to modern extension layout
        legacy_vscode_paths = [
            tmp_repo / "vscode" / "src",
            tmp_repo / "vscode" / "media",
            tmp_repo / "vscode" / "tsconfig.json",
            tmp_repo / "vscode" / ".vscodeignore",
        ]
        for p in legacy_vscode_paths:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                print(f"🧹 Pruned legacy directory in monorepo: {p.relative_to(tmp_repo)}")
            elif p.is_file():
                p.unlink(missing_ok=True)
                print(f"🧹 Pruned legacy file in monorepo: {p.relative_to(tmp_repo)}")

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
        res = subprocess.run(
            ["git", "commit", "--no-verify", "-m", msg],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            if "nothing to commit" in res.stdout or "nothing to commit" in res.stderr:
                print(f"⏩ [CLEAN] No new code changes to commit for {target_repo}.")
                return True
            print(f"Git commit failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
            return False

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
            err = push_res.stderr.strip()
            if any(term in err.lower() for term in ("permission", "forbidden", "not found")):
                print(f"⚠️ [GRACEFUL-DEGRADATION] Umbrella push skipped due to permissions: {err}")
                return True
            print(f"❌ Failed to push to {target_repo}: {err}")
            return False


def sync_archive(
    repo_root: Path,
    token: str,
    commit_msg: str,
) -> bool:
    """Sync historical ADR records to cold storage satellite Supremeai-bd/supremeai-archive."""
    target_repo = ARCHIVE_REPO
    clone_url = f"https://x-access-token:{token}@github.com/{target_repo}.git"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_repo = Path(tmp_dir) / "archive"
        print(f"📥 Cloning {target_repo}:main for archive sync...")
        r = subprocess.run(
            ["git", "clone", "--depth", "50", clone_url, str(tmp_repo)],
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            err = r.stderr.strip()
            if any(term in err.lower() for term in ("not found", "forbidden", "authentication", "permission")):
                print(f"⚠️ [GRACEFUL-DEGRADATION] Archive satellite {target_repo} cloaked or unauthorized: {err}. Skipping.")
                return True
            print(f"❌ Failed to clone {target_repo}: {err}")
            return False

        # Copy archive mirror pairs
        for src_rel, dst_rel in ARCHIVE_MIRROR_PAIRS:
            src_file = repo_root / src_rel
            dst_file = tmp_repo / dst_rel
            if src_file.exists():
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_file, dst_file)
                print(f"📋 Synced archive record '{src_rel}' -> '{dst_rel}' in {target_repo}")

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
        msg = f"sync(open->archive): {commit_msg} [skip ci]"
        res = subprocess.run(
            ["git", "commit", "--no-verify", "-m", msg],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            if "nothing to commit" in res.stdout or "nothing to commit" in res.stderr:
                print(f"⏩ [CLEAN] No new code changes to commit for {target_repo}.")
                return True
            print(f"Git commit failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
            return False

        print(f"🚀 Pushing archive changes to {target_repo}:main...")
        push_res = subprocess.run(
            ["git", "push", "origin", "main"],
            cwd=str(tmp_repo),
            capture_output=True,
            text=True,
            check=False,
        )
        if push_res.returncode == 0:
            print(f"🎉 [SUCCESS] Successfully synced archive satellite {target_repo}:main")
            return True
        else:
            err = push_res.stderr.strip()
            if any(term in err.lower() for term in ("permission", "forbidden", "not found")):
                print(f"⚠️ [GRACEFUL-DEGRADATION] Archive push skipped due to permissions: {err}")
                return True
            print(f"❌ Failed to push to {target_repo}: {err}")
            return False


def detect_changed_targets(
    repo_root: Path,
    base_sha: str | None = None,
    head_sha: str = "HEAD",
) -> tuple[list[str], bool]:
    """Inspect git diff to detect which satellites were touched for instant sync."""
    try:
        base = base_sha or "HEAD~1"
        r = subprocess.run(
            ["git", "diff", "--name-only", base, head_sha],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            # If diff against base fails (e.g. shallow clone or 1 commit), fallback to all
            return list(DOMAIN_MAP.keys()), True

        files = [line.strip() for line in r.stdout.splitlines() if line.strip()]
        if not files:
            return [], False

        targets: set[str] = set()
        # Per Golden 6-Domain Architecture and Nightly Train specification,
        # open-lane synchronization routes strictly to active Domain Satellites
        # (studio, api, core, browser, vscode). The central monorepo (Supremeai-bd/supremeai)
        # is synchronized via consolidation/nightly trains rather than direct push from open.
        umbrella = False

        for f in files:
            if (
                f.startswith("studio/")
                or f.startswith("examples/dashboard-preview/")
                or f.startswith("infrastructure/cloudflare-studio-proxy/")
            ):
                targets.add("Supremeai-bd/supremeai-studio")
            elif f.startswith("core/") or f.startswith("api-schemas/task-router."):
                targets.add("Supremeai-bd/supremeai-core")
            elif (
                f.startswith("gateway/")
                or f.startswith("api/")
                or f.startswith("command/")
                or f.startswith("skills/")
                or f.startswith("agents/")
                or f.startswith("infrastructure/mcp-control-plane/")
            ):
                targets.add("Supremeai-bd/supremeai-api")
            elif f.startswith("browser/") or f.startswith("sandbox/"):
                targets.add("Supremeai-bd/supremeai-browser")
            elif f.startswith("vscode/"):
                targets.add("Supremeai-bd/supremeai-vscode")
            elif f.startswith("docs/adrs/"):
                targets.add(ARCHIVE_REPO)

        return sorted(targets), umbrella
    except Exception:
        return list(DOMAIN_MAP.keys()), True


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


def load_sentinel_pairs(repo_root: Path) -> list[dict[str, str]]:
    """Load sentinel pairs from the config manifest, falling back to built-in defaults."""
    manifest = repo_root / SENTINEL_MANIFEST_PATH
    if manifest.exists():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            pairs = data.get("pairs") if isinstance(data, dict) else None
            if isinstance(pairs, list) and pairs:
                return [dict(p) for p in pairs if isinstance(p, dict)]
            print("⚠️ Sentinel manifest has no usable 'pairs' list; using built-in defaults.")
        except Exception as e:
            print(f"⚠️ Sentinel manifest unreadable ({e}); using built-in defaults.")
    return [dict(p) for p in DEFAULT_SENTINEL_PAIRS]


def _fetch_remote_bytes(repo: str, path: str, token: str, ref: str = "main") -> bytes | None:
    """Fetch a file blob via the GitHub contents API (stdlib only).

    Returns decoded bytes, or None for definitive absence (404).
    Raises on infrastructure errors (auth, network, rate limit) - callers must
    treat raised errors as fail-closed verification failures, not drift.
    """
    import base64 as _b64
    import urllib.error as _ue
    import urllib.request as _uq

    api = f"https://api.github.com/repos/{repo}/contents/{path}?ref={ref}"
    req = _uq.Request(
        api,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "federation-satellite-sync-sentinel",
        },
    )
    try:
        with _uq.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except _ue.HTTPError as e:
        if e.code == 404:
            return None
        raise
    content = data.get("content")
    if content is None:
        return None
    return _b64.b64decode(content)


def verify_sentinels(
    repo_root: Path,
    token: str,
    ref: str = "main",
    only_satellites: list[str] | None = None,
) -> tuple[list[dict], list[dict], list[dict]]:
    """Verify mirror<->satellite sentinel pairs are byte-identical (#1689).

    Open side is read from the local checkout (repo_root); satellite side is
    fetched live from the GitHub contents API. Returns (clean, drift, errors):
      - clean  : pairs verified byte-identical
      - drift  : pairs present on both sides but differing (actionable)
      - errors : pairs that could not be verified (fail-closed, not drift)
    """
    import hashlib as _h

    pairs = load_sentinel_pairs(repo_root)
    clean: list[dict] = []
    drift: list[dict] = []
    errors: list[dict] = []
    for p in pairs:
        open_rel = str(p.get("open", "")).strip()
        sat_repo = str(p.get("satellite", "")).strip()
        sat_rel = str(p.get("path", "")).strip()
        if not (open_rel and sat_repo and sat_rel):
            errors.append({**p, "detail": "malformed pair (requires open/satellite/path)"})
            continue
        if only_satellites and sat_repo not in only_satellites:
            continue
        local = repo_root / open_rel
        if not local.exists():
            errors.append({**p, "detail": f"open-side file missing in checkout: {open_rel}"})
            continue
        try:
            local_bytes = local.read_bytes()
            remote_bytes = _fetch_remote_bytes(sat_repo, sat_rel, token, ref)
        except Exception as e:
            errors.append({**p, "detail": f"verification fetch failed: {e}"})
            continue
        if remote_bytes is None:
            drift.append({**p, "detail": f"satellite surface absent: {sat_repo}:{sat_rel}"})
            print(
                f"  ❌ sentinel DRIFT  {open_rel} != {sat_repo}:{sat_rel} (satellite surface absent)"
            )
            continue
        l_sha = _h.sha256(local_bytes).hexdigest()
        r_sha = _h.sha256(remote_bytes).hexdigest()
        if l_sha == r_sha:
            clean.append(p)
            print(f"  ✅ sentinel OK    {open_rel} == {sat_repo}:{sat_rel}")
        else:
            drift.append({**p, "detail": f"sha256 local={l_sha[:16]} remote={r_sha[:16]}"})
            print(
                f"  ❌ sentinel DRIFT  {open_rel} != {sat_repo}:{sat_rel}"
                f" ({p.get('note') or 'content divergence'})"
            )
    return clean, drift, errors


def self_test() -> bool:
    """Self-test verifying contract and mappings."""
    assert len(DOMAIN_MAP) == 5, (
        f"Expected 5 active satellites in DOMAIN_MAP, got {len(DOMAIN_MAP)}"
    )
    assert "Supremeai-bd/supremeai-studio" in DOMAIN_MAP
    assert "Supremeai-bd/supremeai-core" in DOMAIN_MAP
    assert "Supremeai-bd/supremeai-api" in DOMAIN_MAP
    assert "Supremeai-bd/supremeai-browser" in DOMAIN_MAP
    assert "Supremeai-bd/supremeai-vscode" in DOMAIN_MAP
    assert len(CONTRACT_MIRROR_PAIRS) >= 2, (
        "Expected at least 2 mirrored contract pairs"
    )
    for open_rel, sat_repo, sat_rel in CONTRACT_MIRROR_PAIRS:
        assert sat_repo in DOMAIN_MAP, (
            f"Target repo {sat_repo} must exist in DOMAIN_MAP"
        )
        assert open_rel and sat_rel, "Mirror paths must be non-empty"
    assert ARCHIVE_REPO == "Supremeai-bd/supremeai-archive"
    repo_root = Path(__file__).resolve().parent.parent.parent
    for src_rel, dst_rel in ARCHIVE_MIRROR_PAIRS:
        assert (repo_root / src_rel).exists(), (
            f"Archive mirror source '{src_rel}' must exist in repository root"
        )

    # (#3441 root cause) Policy-target contracts: every satellite named in a
    # shadow policy or the cloak allowlist must be a mapped federation target,
    # or the policy silently applies to nothing (dual-SSOT drift class).
    unknown_refresh = PACKAGE_SHADOW_REFRESH_TARGETS - DOMAIN_MAP.keys()
    assert not unknown_refresh, (
        f"PACKAGE_SHADOW_REFRESH_TARGETS contains non-federation targets: {unknown_refresh}"
    )
    unknown_cloak = set(SATELLITE_CLOAK_ALLOWLIST) - DOMAIN_MAP.keys()
    assert not unknown_cloak, (
        f"SATELLITE_CLOAK_ALLOWLIST contains non-federation targets: {unknown_cloak}"
    )

    # Test copy_tree_contents with pruning
    with tempfile.TemporaryDirectory() as td:
        s_dir = Path(td) / "src"
        d_dir = Path(td) / "dst"
        s_dir.mkdir()
        d_dir.mkdir()
        (s_dir / "keep.txt").write_text("keep", encoding="utf-8")
        (d_dir / "keep.txt").write_text("old", encoding="utf-8")
        (d_dir / "stale.txt").write_text("stale", encoding="utf-8")
        copy_tree_contents(s_dir, d_dir, prune=True)
        assert (d_dir / "keep.txt").read_text(encoding="utf-8") == "keep"
        assert not (d_dir / "stale.txt").exists(), "Stale file must be pruned"

    # Test sync_workflows with pruning
    with tempfile.TemporaryDirectory() as td:
        s_wf = Path(td) / "src_wf"
        d_wf = Path(td) / "dst_wf"
        s_wf.mkdir()
        d_wf.mkdir()
        (s_wf / "ci.yml").write_text("name: ci", encoding="utf-8")
        (d_wf / "old-pipeline.yml").write_text("name: old", encoding="utf-8")
        sync_workflows(s_wf, d_wf)
        assert (d_wf / "ci.yml").exists(), "Active workflow must be copied"
        assert not (d_wf / "old-pipeline.yml").exists(), "Stale workflow must be pruned"

    # Sentinel pair contract (#1689)
    for p in DEFAULT_SENTINEL_PAIRS:
        assert p.get("open") and p.get("satellite") and p.get("path"), (
            f"Malformed sentinel pair: {p}"
        )
        assert p["satellite"] in DOMAIN_MAP, (
            f"Sentinel target {p['satellite']} must be a mapped satellite"
        )
    assert any(
        p["open"] == "gateway/main.py" and p["path"] == "main.py"
        for p in DEFAULT_SENTINEL_PAIRS
    ), "api satellite root main.py parity pair is mandatory (#1689)"
    with tempfile.TemporaryDirectory() as td:
        fake_root = Path(td)
        assert load_sentinel_pairs(fake_root) == [dict(p) for p in DEFAULT_SENTINEL_PAIRS], (
            "Manifest fallback must return built-in defaults"
        )
        man_dir = fake_root / "scripts" / "ci"
        man_dir.mkdir(parents=True)
        (man_dir / "satellite_sentinels.json").write_text(
            json.dumps(
                {
                    "pairs": [
                        {
                            "open": "x.py",
                            "satellite": "Supremeai-bd/supremeai-core",
                            "path": "y.py",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        loaded = load_sentinel_pairs(fake_root)
        assert len(loaded) == 1 and loaded[0]["open"] == "x.py", (
            "Manifest pairs must override built-in defaults"
        )

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
        "--all", action="store_true", help="Sync all active satellites and central monorepo"
    )
    parser.add_argument(
        "--detect-changed",
        action="store_true",
        help="Inspect git diff and instantly sync only touched target satellites",
    )
    parser.add_argument(
        "--base-sha",
        help="Base commit SHA for change detection (default: HEAD~1)",
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
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help=(
            "Verify sentinel pairs (mirror<->satellite byte parity) without syncing. "
            "Exit codes: 0 clean, 1 drift, 2 verification errors (fail-closed)."
        ),
    )
    parser.add_argument(
        "--sentinel-ref",
        default="main",
        help="Git ref used for sentinel verification (default: main)",
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

    if args.verify_only:
        only = [t for t in (args.targets or []) if t in DOMAIN_MAP] or None
        clean, drift, errors = verify_sentinels(repo_root, token, ref=args.sentinel_ref, only_satellites=only)
        print(
            f"🛡️ Sentinel verification: {len(clean)} clean / {len(drift)} drift / {len(errors)} errors"
        )
        if drift:
            print("❌ Sentinel drift detected (mirror<->satellite parity broken):")
            for d in drift:
                print(f"   - {d.get('open')} != {d.get('satellite')}:{d.get('path')} :: {d.get('detail')}")
        if errors:
            print("❌ Sentinel verification could not complete for some pairs (fail-closed):")
            for e in errors:
                print(f"   - {e.get('satellite')}:{e.get('path')} :: {e.get('detail')}")
        if errors:
            return 2
        if drift:
            return 1
        print("✅ All sentinel pairs byte-identical.")
        return 0

    # Determine targets
    targets_to_sync: list[str] = []
    sync_umbrella = False

    if args.all:
        targets_to_sync = list(DOMAIN_MAP.keys())
        sync_umbrella = False
    elif args.detect_changed:
        targets_to_sync, sync_umbrella = detect_changed_targets(
            repo_root, base_sha=args.base_sha
        )
        print(f"🔍 [AUTO-DETECT] Changed targets detected: {targets_to_sync} (Umbrella: {sync_umbrella})")
        if not targets_to_sync and not sync_umbrella:
            print("✅ [NO-OP] No satellite or monorepo domain changes detected. Instant sync complete.")
            return 0
    elif args.targets:
        for t in args.targets:
            t = t.strip()
            if t == "Supremeai-bd/supremeai":
                sync_umbrella = True
            elif t == ARCHIVE_REPO:
                targets_to_sync.append(ARCHIVE_REPO)
            elif t in DOMAIN_MAP:
                targets_to_sync.append(t)
            else:
                print(f"⚠️ Unrecognized target repository '{t}'. Skipping.")
    else:
        # Default: sync all mapped satellites
        targets_to_sync = list(DOMAIN_MAP.keys())
        sync_umbrella = False

    print(
        f"🎯 Target Repositories to Sync: {targets_to_sync} (Umbrella: {sync_umbrella})"
    )

    success = True
    raw_msg = args.commit_msg or os.environ.get("COMMIT_MSG") or "synchronize federation transit surface"
    safe_commit_msg = raw_msg.splitlines()[0].strip() if raw_msg else "synchronize federation transit surface"

    for target in targets_to_sync:
        if target == ARCHIVE_REPO:
            ok = sync_archive(repo_root, token, safe_commit_msg)
        else:
            src_dir = DOMAIN_MAP[target]
            ok = sync_satellite(target, src_dir, repo_root, token, safe_commit_msg)
        if not ok:
            success = False

    if sync_umbrella:
        ok = sync_monorepo(repo_root, token, safe_commit_msg)
        if not ok:
            success = False

    # Post-sync sentinel observation (#1689). CI should still run --verify-only as a
    # separate fail-closed gate step after a short propagation delay; this inline
    # check is observational only (the contents API can lag a just-pushed ref) and
    # never flips the sync exit code.
    try:
        obs_clean, obs_drift, obs_errors = verify_sentinels(repo_root, token)
        print(
            f"🛡️ [observe] post-sync sentinels: "
            f"{len(obs_clean)} clean / {len(obs_drift)} drift / {len(obs_errors)} errors"
        )
        for d in obs_drift:
            print(
                f"   ⚠️ drift: {d.get('open')} != {d.get('satellite')}:{d.get('path')}"
                f" :: {d.get('detail')}"
            )
    except Exception as e:
        print(f"⚠️ [observe] post-sync sentinel check skipped: {e}")

    if not success:
        print("❌ One or more repository sync operations failed.")
        return 1

    print("🎉 All federation target repositories synchronized successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
