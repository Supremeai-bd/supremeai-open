#!/usr/bin/env python3
"""Federation Documentation Archival Engine.

Moves historical, audit, workorder, and non-essential documentation out of
active federation repositories into Supremeai-bd/supremeai-archive while
preserving strict 'MUST-HAVE' operational contracts in the active 7 repositories.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys

FEDERATION_ROOT = pathlib.Path(__file__).resolve().parents[2].parent
ARCHIVE_REPO = FEDERATION_ROOT / "supremeai-archive"

ACTIVE_REPOS = [
    "supremeai",
    "supremeai-open",
    "supremeai-studio",
    "supremeai-api",
    "supremeai-core",
    "supremeai-vscode",
    "supremeai-browser",
]

ARCHIVE_BASE_URL = "https://github.com/Supremeai-bd/supremeai-archive/blob/main"

# Directories whose contents should be completely archived
ARCHIVE_DIRECTORIES = [
    "docs/reports",
    "docs/bridge",
    "docs/workorders",
    "docs/audit_reports",
    "docs/adrs",
    "docs/ci-templates",
    "docs/ops",
    "docs/provenance",
    "docs/pr_archive",
    "docs/jules",
    "docs/devcontainer",
    "docs/security",
    "archive",
]

# Specific loose files under docs/ to archive
ARCHIVE_DOCS_LOOSE_PREFIXES = (
    "AUDIT_",
    "EVAL_",
    "SCOUT_RADAR_",
    "SKILLS_AGENT_SCAN_",
    "SEQ",
    "PROJECT_",
    "supremeai-audit-report-",
    "KAGGLE_",
    "INFINITY_",
    "RENDER_512MB_",
    "VOICE_",
    "STUDIO_FRONTEND_MASTER_PLAN",
    "SUPREMEAI_PROVIDER_AGNOSTIC_",
    "ZIP_USE_LIST",
    "FEDERATION_SATELLITE_GAP_",
    "CROWN_JEWELS_",
    "CROSS_PLATFORM_",
    "COMMAND_SEED_",
    "CI_PIPELINES_AUDIT_",
    "AI_TRIO_",
    "GHOST_TOWER_",
    "WEBHOOK_PRIMARY_",
    "SUPREMEAI_API_KEY_",
)


def is_must_keep(rel_path: str) -> bool:
    """Check if relative path matches any must-keep pattern."""
    if rel_path in {"README.md", "AGENTS.md", "CONTRIBUTING.md", "LICENSE", "SECURITY.md"}:
        return True
    if rel_path.lower() in {"readme.md", "agents.md", "license", "security.md"}:
        return True
        
    if rel_path in {"docs/AGENT_OPERATING_SYSTEM.md", "docs/AGENT_LOOP_SPEC.md", "docs/ARCHITECTURE.md", "docs/SCOUT_RADAR_INDEX.md"}:
        return True

    if rel_path.startswith("docs/specs/") or rel_path.startswith("docs/runbooks/"):
        return True

    if rel_path.startswith(".agents/skills/") or rel_path.startswith("skills/"):
        return True

    if rel_path.startswith("infrastructure/mcp-control-plane/docs/"):
        return True

    return False


def collect_archivable_files(repo_path: pathlib.Path) -> list[pathlib.Path]:
    """Find all markdown and archive files eligible to move to supremeai-archive."""
    archivable: list[pathlib.Path] = []
    
    docs_dir = repo_path / "docs"
    if docs_dir.is_dir():
        for root, dirs, files in os.walk(docs_dir):
            for file in files:
                full_path = pathlib.Path(root) / file
                rel_path = full_path.relative_to(repo_path).as_posix()
                
                if is_must_keep(rel_path):
                    continue
                
                in_archive_dir = any(rel_path.startswith(f"{ad}/") or rel_path == ad for ad in ARCHIVE_DIRECTORIES)
                
                if not in_archive_dir and full_path.parent == docs_dir:
                    fname = full_path.name
                    if any(fname.startswith(prefix) for prefix in ARCHIVE_DOCS_LOOSE_PREFIXES) or "BN" in fname or "bn" in fname:
                        archivable.append(full_path)
                    elif fname.endswith(".json") and fname != "audit-process.json":
                        archivable.append(full_path)
                    elif fname not in {"AGENT_OPERATING_SYSTEM.md", "AGENT_LOOP_SPEC.md", "ARCHITECTURE.md"}:
                        archivable.append(full_path)
                elif in_archive_dir:
                    archivable.append(full_path)

    sat_archive = repo_path / "archive"
    if sat_archive.is_dir():
        for root, dirs, files in os.walk(sat_archive):
            for file in files:
                archivable.append(pathlib.Path(root) / file)

    return archivable


def update_markdown_links(repo_dir: pathlib.Path, archivable_rels: set[str]) -> None:
    """Update markdown links in retained files that pointed to archived files."""
    retained_files = [repo_dir / "README.md", repo_dir / "AGENTS.md"] + [
        p for p in repo_dir.glob("docs/**/*.md") if p.relative_to(repo_dir).as_posix() not in archivable_rels
    ]
    
    for file_path in retained_files:
        if not file_path.exists():
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
            
        modified = False
        
        # 1. Special case: CONTRIBUTING.md in docs -> ../CONTRIBUTING.md
        if file_path == repo_dir / "docs" / "AGENT_OPERATING_SYSTEM.md":
            if "[CONTRIBUTING.md](CONTRIBUTING.md)" in content:
                content = content.replace("[CONTRIBUTING.md](CONTRIBUTING.md)", "[CONTRIBUTING.md](../CONTRIBUTING.md)")
                modified = True

        # 2. Update links pointing to archived docs
        for arch_rel in archivable_rels:
            doc_rel = arch_rel.replace("docs/", "")
            archive_url = f"{ARCHIVE_BASE_URL}/{arch_rel}"

            patterns = [
                f"./{arch_rel}",
                arch_rel,
            ]
            if file_path.parent == repo_dir / "docs":
                patterns.append(doc_rel)
                patterns.append(f"./{doc_rel}")

            for pat in patterns:
                link_pat = f"]({pat})"
                if link_pat in content:
                    content = content.replace(link_pat, f"]({archive_url})")
                    modified = True

        if modified:
            file_path.write_text(content, encoding="utf-8")
            print(f"  [links] Updated links in {file_path.relative_to(repo_dir).as_posix()}")


def clean_empty_directories(base_dir: pathlib.Path) -> None:
    """Remove empty directories recursively under base_dir."""
    for root, dirs, files in os.walk(base_dir, topdown=False):
        for d in dirs:
            dir_path = pathlib.Path(root) / d
            try:
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
            except OSError:
                pass


def migrate(dry_run: bool = True) -> int:
    """Migrate archivable documents across all active repos to supremeai-archive."""
    if not ARCHIVE_REPO.is_dir():
        print(f"ERROR: Archive repo not found at {ARCHIVE_REPO}", file=sys.stderr)
        return 1

    print(f"=== SupremeAI Documentation Archival Engine {'(DRY-RUN)' if dry_run else '(LIVE)'} ===")
    print(f"Destination: {ARCHIVE_REPO}\n")

    total_moved = 0

    for repo_name in ACTIVE_REPOS:
        repo_dir = FEDERATION_ROOT / repo_name
        if not repo_dir.is_dir():
            print(f"[-] Skipping {repo_name} (directory does not exist)")
            continue

        files = collect_archivable_files(repo_dir)
        archivable_rels = {f.relative_to(repo_dir).as_posix() for f in files}
        print(f"[{repo_name}] Found {len(files)} archivable documents")

        for f in files:
            rel_to_repo = f.relative_to(repo_dir)
            
            if repo_name in ("supremeai", "supremeai-open"):
                dest_file = ARCHIVE_REPO / rel_to_repo
            else:
                dest_file = ARCHIVE_REPO / "docs" / "satellites" / repo_name / rel_to_repo

            if dry_run:
                total_moved += 1
            else:
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest_file)
                f.unlink()
                total_moved += 1

        if not dry_run:
            for req_dir_name in ["docs/reports", "docs/bridge", "docs/workorders"]:
                req_dir = repo_dir / req_dir_name
                req_dir.mkdir(parents=True, exist_ok=True)
                gitkeep = req_dir / ".gitkeep"
                if not gitkeep.exists():
                    gitkeep.write_text("# evidence plane stub\n", encoding="utf-8")

            update_markdown_links(repo_dir, archivable_rels)

            docs_dir = repo_dir / "docs"
            if docs_dir.is_dir():
                clean_empty_directories(docs_dir)

    print(f"\nTotal documents {'identified' if dry_run else 'migrated'}: {total_moved}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Migrate non-essential docs to supremeai-archive")
    parser.add_argument("--execute", action="store_true", help="Perform live migration and deletion")
    args = parser.parse_args()

    return migrate(dry_run=not args.execute)


if __name__ == "__main__":
    sys.exit(main())
