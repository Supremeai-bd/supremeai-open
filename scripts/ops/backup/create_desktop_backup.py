"""
SupremeAI 2.0 — Local Desktop Project Backup & AI Ingestion Master
-------------------------------------------------------------------
Creates an ultra-clean, noise-free project archive and Single-File AI Digest (.md)
alongside Git Diff Patches directly to Desktop for AI ingestion (Claude, ChatGPT, Gemini).

Formats Supported:
1. Full AI-Ready Zip Archive (.zip)
2. Unified Single-File Markdown AI Digest (.md) [Direct LLM Drop]
3. Commit Diff Markdown Patch (.md) [Incremental Code Review]
4. Changed-Files-Only Zip Package (.zip) [Feather-light differential update]
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force UTF-8 on Windows stdout/stderr
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Silenced error: {e}")

DEFAULT_PROJECT_DIR = Path(__file__).resolve().parents[2]
DESKTOP_DIR = Path.home() / "Desktop"

# File extensions to strip from archives & AI digests
IGNORED_EXTENSIONS = {
    # Images & Media
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff",
    # Datasets & DBs
    ".jsonl", ".parquet", ".arrow", ".h5", ".sqlite", ".db", ".csv",
    # Archives & Build binaries
    ".zip", ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".wasm", ".map", ".tmp"
}

# Directories to completely ignore (legacy/log bloat)
IGNORED_DIRECTORY_PREFIXES = (
    "_archive/",
    "reports/",
    "backend/docs/autogen/",
    "backend/reports/",
)

EXT_TO_LANG = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".json": "json",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown",
    ".toml": "toml",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".sh": "bash",
    ".bash": "bash",
    ".ps1": "powershell",
    ".dockerfile": "dockerfile",
    ".env.example": "ini",
    ".txt": "text",
    ".xml": "xml",
}

def slugify(text: str) -> str:
    """Helper to convert commit message to clean filename slug."""
    cleaned = re.sub(r"[^\w\s-]", "", text.strip())
    slug = re.sub(r"[-\s]+", "_", cleaned).strip("_")
    return slug[:40] if slug else "commit"

def is_knowledge_base_doc(rel_path_posix: str) -> bool:
    """Check if file is part of essential knowledge base documentation."""
    return rel_path_posix.startswith("docs/knowledge-base/") and rel_path_posix.endswith(".md")

def is_excluded_for_ai(rel_path_posix: str) -> bool:
    """Determine if a file should be excluded from the AI-optimized zip."""
    ext = Path(rel_path_posix).suffix.lower()
    filename = Path(rel_path_posix).name.lower()

    if ext in IGNORED_EXTENSIONS:
        return True

    for prefix in IGNORED_DIRECTORY_PREFIXES:
        if rel_path_posix.startswith(prefix) or rel_path_posix == prefix.rstrip("/"):
            return True

    if "failure_logs" in filename or "failed_job_log" in filename or filename.endswith(".log"):
        return True

    if rel_path_posix == "docs" or rel_path_posix.startswith("docs/"):
        if not is_knowledge_base_doc(rel_path_posix):
            return True

    return bool(rel_path_posix == ".git" or rel_path_posix.startswith(".git/"))

def get_git_filtered_files(project_dir: Path) -> list[Path]:
    """Uses git to list all tracked and untracked files that are NOT ignored by .gitignore."""
    try:
        cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
        result = subprocess.run(
            cmd,
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True
        )
        file_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        files = [project_dir / rel_path for rel_path in file_lines]

        env_example = project_dir / ".env.example"
        if env_example.exists() and env_example not in files:
            files.append(env_example)

        return files
    except Exception as e:
        print(f"[!] Warning: Git command failed ({e}). Falling back to manual scanner...")
        return fallback_file_scanner(project_dir)

def fallback_file_scanner(project_dir: Path) -> list[Path]:
    """Fallback scanner if git is unavailable."""
    ignored = {
        ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
        ".pytest_cache", ".ruff_cache", ".mypy_cache", ".coverage", "*.pyc", "*.pyo",
        ".next", ".nuxt", "coverage", ".turbo", "_archive"
    }
    selected = []
    for root, dirs, files in os.walk(project_dir):
        root_p = Path(root)
        try:
            root_p.relative_to(project_dir)
        except ValueError:
            continue
        dirs[:] = [d for d in dirs if d not in ignored and d != ".git"]
        for f in files:
            selected.append(root_p / f)
    return selected

def get_git_commit_info(project_dir: Path) -> dict[str, str]:
    """Retrieves commit metadata."""
    info = {"commit": "N/A", "message": "Manual Desktop Backup", "author": "Local User", "branch": "main"}
    try:
        commit = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=project_dir, text=True).strip()
        branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=project_dir, text=True).strip()
        msg = subprocess.check_output(["git", "log", "-1", "--pretty=%B"], cwd=project_dir, text=True).strip()
        author = subprocess.check_output(["git", "log", "-1", "--pretty=%an"], cwd=project_dir, text=True).strip()
        info.update({"commit": commit, "branch": branch, "message": msg.splitlines()[0] if msg else "N/A", "author": author})
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Silenced error: {e}")
    return info

def get_git_diff_info(project_dir: Path) -> dict[str, Any]:
    """Extracts git diff patch and changed files list for the latest commit/push."""
    diff_data: dict[str, Any] = {
        "has_diff": False,
        "stat": "No diff available",
        "raw_diff": "",
        "changed_files": [],
        "files_changed_count": 0,
    }
    try:
        subprocess.check_call(["git", "rev-parse", "HEAD~1"], cwd=project_dir, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        diff_target = "HEAD~1"
    except Exception:
        diff_target = None

    try:
        if diff_target:
            stat_cmd = ["git", "diff", "HEAD~1", "HEAD", "--stat"]
            diff_cmd = ["git", "diff", "HEAD~1", "HEAD"]
            files_cmd = ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"]
        else:
            stat_cmd = ["git", "show", "--stat", "--oneline", "HEAD"]
            diff_cmd = ["git", "show", "--pretty=format:", "HEAD"]
            files_cmd = ["git", "show", "--pretty=format:", "--name-only", "HEAD"]

        stat_out = subprocess.check_output(stat_cmd, cwd=project_dir, encoding="utf-8", errors="replace").strip()
        raw_diff_out = subprocess.check_output(diff_cmd, cwd=project_dir, encoding="utf-8", errors="replace").strip()
        files_out = subprocess.check_output(files_cmd, cwd=project_dir, encoding="utf-8", errors="replace").strip()

        changed = [f.strip() for f in files_out.splitlines() if f.strip()]
        diff_data["has_diff"] = bool(changed)
        diff_data["stat"] = stat_out
        diff_data["raw_diff"] = raw_diff_out
        diff_data["changed_files"] = changed
        diff_data["files_changed_count"] = len(changed)
    except Exception as e:
        print(f"[!] Warning: Git diff extraction: {e}")

    return diff_data

def create_full_zip(project_dir: Path, output_zip_path: Path) -> tuple[int, int, int]:
    """Generates clean, full AI-optimized project zip."""
    all_files = get_git_filtered_files(project_dir)
    filtered_files: list[tuple[Path, str]] = []

    for file_path in all_files:
        if not file_path.exists() or file_path.is_dir():
            continue
        try:
            rel_path = file_path.relative_to(project_dir).as_posix()
        except ValueError:
            continue

        if not is_excluded_for_ai(rel_path):
            filtered_files.append((file_path, rel_path))

    output_zip_path.parent.mkdir(parents=True, exist_ok=True)
    total_uncompressed = 0

    with zipfile.ZipFile(output_zip_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file_path, rel_path in filtered_files:
            try:
                sz = file_path.stat().st_size
                total_uncompressed += sz
                zf.write(file_path, arcname=rel_path)
            except Exception as e:
                print(f"[!] Skip {rel_path}: {e}")

    final_size = output_zip_path.stat().st_size
    return len(filtered_files), total_uncompressed, final_size

def create_ai_markdown_digest(project_dir: Path, output_md_path: Path, git_info: dict[str, str]) -> tuple[int, int]:
    """Generates single-file markdown digest of all project source code."""
    all_files = get_git_filtered_files(project_dir)
    filtered_files: list[tuple[Path, str]] = []

    for file_path in all_files:
        if not file_path.exists() or file_path.is_dir():
            continue
        try:
            rel_path = file_path.relative_to(project_dir).as_posix()
        except ValueError:
            continue

        if not is_excluded_for_ai(rel_path):
            filtered_files.append((file_path, rel_path))

    filtered_files.sort(key=lambda x: x[1])
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    md_lines: list[str] = [
        "# 🔱 SupremeAI 2.0 Codebase Snapshot Digest\n",
        f"- **Branch:** `{git_info['branch']}`",
        f"- **Commit:** `{git_info['commit']}`",
        f"- **Message:** {git_info['message']}",
        f"- **Author:** {git_info['author']}",
        f"- **Timestamp:** `{timestamp_str}`",
        f"- **Total Active Files:** {len(filtered_files):,}\n",
        "## 📑 Table of Contents\n",
    ]

    for _, rel_path in filtered_files:
        md_lines.append(f"- [`{rel_path}`](#{rel_path.replace('/', '-').replace('.', '-')})")

    md_lines.append("\n---\n\n## 📂 Codebase File Contents\n")

    for file_path, rel_path in filtered_files:
        ext = file_path.suffix.lower()
        lang = EXT_TO_LANG.get(ext, "text")
        if file_path.name.lower() == "dockerfile":
            lang = "dockerfile"
        elif file_path.name.lower() == ".env.example":
            lang = "ini"

        try:
            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = file_path.read_text(encoding="latin-1", errors="replace")

            fence = "````" if "```" in content else "```"
            anchor = rel_path.replace('/', '-').replace('.', '-')
            md_lines.append(f"<a id=\"{anchor}\"></a>\n### 📄 `{rel_path}`\n")
            md_lines.append(f"{fence}{lang}\n{content}\n{fence}\n")
        except Exception as e:
            md_lines.append(f"### 📄 `{rel_path}`\n*(Error reading file: {e})*\n")

    full_md_text = "\n".join(md_lines)
    output_md_path.write_text(full_md_text, encoding="utf-8", errors="replace")
    final_size = output_md_path.stat().st_size

    return len(filtered_files), final_size

def create_commit_diff_markdown(
    output_md_path: Path,
    git_info: dict[str, str],
    diff_info: dict[str, Any]
) -> tuple[int, int]:
    """Generates markdown diff patch with syntax-highlighted git diff."""
    output_md_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    md_lines: list[str] = [
        "# 🔀 SupremeAI Commit Diff & Patch Digest\n",
        f"- **Commit:** `{git_info['commit']}`",
        f"- **Branch:** `{git_info['branch']}`",
        f"- **Message:** **{git_info['message']}**",
        f"- **Author:** `{git_info['author']}`",
        f"- **Timestamp:** `{timestamp_str}`",
        f"- **Files Modified:** `{diff_info['files_changed_count']}`\n",
        "## 📊 Diff Stat Summary\n",
        "```text",
        diff_info.get("stat", "N/A"),
        "```\n",
        "## 📝 Changed Files List\n",
    ]

    for cf in diff_info.get("changed_files", []):
        md_lines.append(f"- `{cf}`")

    md_lines.append("\n---\n\n## 🔍 Unified Code Diff Patch\n")
    md_lines.append("```diff")
    md_lines.append(diff_info.get("raw_diff", "# No changes detected."))
    md_lines.append("```\n")

    full_md = "\n".join(md_lines)
    output_md_path.write_text(full_md, encoding="utf-8", errors="replace")
    final_size = output_md_path.stat().st_size

    return diff_info.get("files_changed_count", 0), final_size

def create_changed_files_zip(
    project_dir: Path,
    output_zip_path: Path,
    changed_files: list[str]
) -> tuple[int, int, int]:
    """Creates a lightweight zip containing ONLY modified files from latest commit."""
    output_zip_path.parent.mkdir(parents=True, exist_ok=True)
    total_uncompressed = 0
    valid_files: list[tuple[Path, str]] = []

    for rel_str in changed_files:
        fp = project_dir / rel_str
        if fp.exists() and fp.is_file() and not is_excluded_for_ai(rel_str):
            valid_files.append((fp, rel_str))

    with zipfile.ZipFile(output_zip_path, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for fp, rel_str in valid_files:
            try:
                sz = fp.stat().st_size
                total_uncompressed += sz
                zf.write(fp, arcname=rel_str)
            except Exception as e:
                print(f"[!] Skip diff file {rel_str}: {e}")

    final_size = output_zip_path.stat().st_size if output_zip_path.exists() else 0
    return len(valid_files), total_uncompressed, final_size

def main():
    parser = argparse.ArgumentParser(description="SupremeAI Desktop Project Backup & AI Ingestion Master")
    parser.add_argument("project_path", nargs="?", default=str(DEFAULT_PROJECT_DIR), help="Project directory path")
    parser.add_argument("--out-dir", type=str, default=str(DESKTOP_DIR), help="Output directory (default: Desktop)")
    parser.add_argument(
        "--format",
        choices=["all", "full-zip", "full-md", "diff-md", "diff-zip", "full-only", "diff-only"],
        default="all",
        help="Backup format selection"
    )
    args = parser.parse_args()

    project_dir = Path(args.project_path)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not project_dir.exists():
        print(f"[X] Error: Project directory not found: {project_dir}")
        sys.exit(1)

    git_info = get_git_commit_info(project_dir)
    diff_info = get_git_diff_info(project_dir)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    msg_slug = slugify(git_info["message"])

    print("=" * 75)
    print(" 🔱 SupremeAI 2.0 — Local Desktop AI Archival Master")
    print("=" * 75)
    print(f" [*] Source Repo  : {project_dir}")
    print(f" [*] Destination  : {out_dir}")
    print(f" [*] Git Branch   : {git_info['branch']} ({git_info['commit']})")
    print(f" [*] Last Commit  : {git_info['message']}")
    print("-" * 75)

    # 1. Full ZIP Archive
    if args.format in ("all", "full-only", "full-zip"):
        zip_path = out_dir / f"supremeai_full_backup_{git_info['commit']}_{timestamp}.zip"
        t0 = time.time()
        fc, _unc, cmp_sz = create_full_zip(project_dir, zip_path)
        t_el = time.time() - t0
        print(f" [1] Full Zip Archive Created ({t_el:.2f}s):")
        print(f"     -> {zip_path.name} ({cmp_sz / (1024*1024):.2f} MB, {fc:,} files)")

    # 2. Full Markdown AI Digest
    if args.format in ("all", "full-only", "full-md"):
        md_path = out_dir / f"supremeai_full_digest_{git_info['commit']}_{timestamp}.md"
        t0 = time.time()
        mfc, m_sz = create_ai_markdown_digest(project_dir, md_path, git_info)
        t_el = time.time() - t0
        print(f" [2] Single-File Markdown Digest Created ({t_el:.2f}s):")
        print(f"     -> {md_path.name} ({m_sz / (1024*1024):.2f} MB, {mfc:,} files)")

    # 3. Commit Diff Markdown Patch
    if args.format in ("all", "diff-only", "diff-md") and diff_info["has_diff"]:
        diff_md_path = out_dir / f"supremeai_diff_{git_info['commit']}_{msg_slug}.md"
        t0 = time.time()
        dfc, d_sz = create_commit_diff_markdown(diff_md_path, git_info, diff_info)
        t_el = time.time() - t0
        print(f" [3] Commit Diff Patch (.md) Created ({t_el:.2f}s):")
        print(f"     -> {diff_md_path.name} ({d_sz / 1024:.1f} KB, {dfc} modified files)")

    # 4. Changed Files Only ZIP
    if args.format in ("all", "diff-only", "diff-zip") and diff_info["has_diff"]:
        diff_zip_path = out_dir / f"supremeai_diff_files_{git_info['commit']}_{msg_slug}.zip"
        t0 = time.time()
        cfz, _, cz_sz = create_changed_files_zip(project_dir, diff_zip_path, diff_info["changed_files"])
        t_el = time.time() - t0
        print(f" [4] Incremental Changed-Files Zip Created ({t_el:.2f}s):")
        print(f"     -> {diff_zip_path.name} ({cz_sz / 1024:.1f} KB, {cfz} files)")

    print("-" * 75)
    print(" [OK] All requested backup formats are ready directly on Desktop!")
    print("=" * 75)

if __name__ == "__main__":
    main()
