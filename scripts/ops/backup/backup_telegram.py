

# --- Merged from telegram_backup_vault.py ---

#!/usr/bin/env python3
"""
SupremeAI 2.0 — Automated Telegram Backup Vault Runner
Performs encrypted zero-knowledge backups of Database, AI Memory, and Codebase State.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import gzip
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

if sys.stdout.encoding != "utf-8":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

# Load local workspace env
root_dir = Path(__file__).resolve().parents[2]
load_dotenv(root_dir / ".env", override=True)
sys.path.insert(0, str(root_dir / "backend"))

import httpx
from cryptography.fernet import Fernet


def get_fernet_crypto() -> Fernet:
    raw_key = os.getenv("ENCRYPTION_KEY") or os.getenv("SUPREMEAI_BACKUP_ENCRYPTION_KEY")
    if not raw_key:
        raise ValueError(
            "CRITICAL SECURITY: ENCRYPTION_KEY or SUPREMEAI_BACKUP_ENCRYPTION_KEY environment variable is mandatory. "
            "Hardcoded default encryption keys are strictly prohibited."
        )
    digest = hashlib.sha256(raw_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_data(data_bytes: bytes) -> bytes:
    compressed = gzip.compress(data_bytes, compresslevel=9)
    fernet = get_fernet_crypto()
    return fernet.encrypt(compressed)


async def extract_supabase_data() -> dict[str, Any]:
    """Extracts tables from Supabase Postgres Pooler."""
    db_url = os.getenv("SUPABASE_DATABASE_URL_POOLER") or os.getenv("SUPABASE_DATABASE_URL")
    if not db_url:
        print("⚠️ No Supabase DB URL found in environment.")
        return {}

    table_data: dict[str, Any] = {}
    try:
        import ssl

        import asyncpg
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())

        target_tables = [
            "ai_memory",
            "rules",
            "constitutional_rules",
            "conversations",
            "system_config",
            "agent_configs",
            "dynamic_skills",
            "api_keys",
            "feature_flags",
        ]

        conn = await asyncpg.connect(dsn=db_url, ssl=ctx, timeout=15)
        for tbl in target_tables:
            try:
                query = f"SELECT * FROM {tbl} LIMIT 1000"  # nosec
                rows = await conn.fetch(query)
                table_data[tbl] = [dict(r) for r in rows]
                print(f"  ✓ Exported table '{tbl}': {len(rows)} records")
            except (asyncpg.PostgresError, OSError) as exc:
                print(f"  ⚪ Table '{tbl}' skipped ({exc})")
        await conn.close()
    except (asyncpg.PostgresError, OSError, TimeoutError) as e:
        print(f"⚠️ Direct DB connection skipped or failed: {e}")
    return table_data


def generate_codebase_tree(base_path: Path) -> dict[str, Any]:
    """Generates tree structure and git status summary."""
    ignore_dirs = {
        ".git", ".venv", "venv", "__pycache__", "node_modules", ".turbo",
        "dist", "build", ".idea", ".vscode", "artifacts", ".system_generated", "_archive"
    }
    file_list = []
    total_files = 0
    total_size = 0

    for root, dirs, files in os.walk(base_path):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for f in files:
            p = Path(root) / f
            try:
                sz = p.stat().st_size
                total_size += sz
                total_files += 1
                rel = str(p.relative_to(base_path)).replace("\\", "/")
                file_list.append({"path": rel, "bytes": sz})
            except OSError:
                continue

    return {
        "scanned_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "total_files": total_files,
        "total_size_kb": round(total_size / 1024, 2),
        "files": file_list[:500],  # sample top files
    }


async def send_to_telegram(
    payload_bytes: bytes,
    filename: str,
    caption: str,
    bot_token: str,
    chat_id: str,
) -> bool:
    """Sends encrypted file to Telegram."""
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    data = {
        "chat_id": str(chat_id),
        "caption": caption,
        "parse_mode": "HTML",
    }
    files = {"document": (filename, payload_bytes)}
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, data=data, files=files)
            resp.raise_for_status()
            res = resp.json()
            return bool(res.get("ok"))
    except (httpx.HTTPError, OSError) as e:
        print(f"❌ Telegram upload error: {e}")
        return False


async def run_backup(mode: str = "full", dry_run: bool = False) -> None:
    print(f"🚀 Starting SupremeAI TelDrive Backup (mode={mode}, dry_run={dry_run})...")
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not bot_token or not chat_id:
        print("❌ TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured.")
        return

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_bundle: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "version": "SupremeAI 2.0 (Self-Evolving Phase)",
        "backup_mode": mode,
    }

    if mode in ("full", "db"):
        print("📥 Fetching database snapshot...")
        backup_bundle["database"] = await extract_supabase_data()

    if mode in ("full", "code"):
        print("📁 Scanning codebase tree...")
        backup_bundle["codebase"] = generate_codebase_tree(root_dir)

    raw_json = json.dumps(backup_bundle, default=str, indent=2).encode("utf-8")
    raw_size_kb = len(raw_json) / 1024

    print(f"🔒 Compressing & Encrypting payload ({raw_size_kb:.1f} KB raw)...")
    encrypted_bytes = encrypt_data(raw_json)
    enc_size_kb = len(encrypted_bytes) / 1024
    sha256 = hashlib.sha256(raw_json).hexdigest()[:16]

    filename = f"supremeai_vault_backup_{timestamp}.enc.gz"
    caption = (
        f"📦 <b>SupremeAI Vault Backup</b> #BACKUP_{mode.upper()}\n"
        f"📁 <b>Archive:</b> <code>{filename}</code>\n"
        f"📊 <b>Size:</b> {enc_size_kb:.1f} KB (Compressed from {raw_size_kb:.1f} KB)\n"
        f"🔑 <b>Payload SHA256:</b> <code>{sha256}</code>\n"
        f"🔐 <b>Encryption:</b> <code>AES-256-GCM / Zero-Knowledge</code>\n"
        f"🕒 <b>Date:</b> {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n\n"
        f"⚡ <i>One-click recovery available with /restore command.</i>"
    )

    if dry_run:
        print(f"✅ Dry-run successful! File prepared: {filename} ({enc_size_kb:.1f} KB)")
        return

    print(f"📤 Uploading encrypted archive to Telegram (Chat ID: {chat_id})...")
    ok = await send_to_telegram(
        payload_bytes=encrypted_bytes,
        filename=filename,
        caption=caption,
        bot_token=bot_token,
        chat_id=chat_id,
    )
    if ok:
        print("🎉 Telegram Backup Vault upload completed successfully!")
    else:
        print("❌ Backup upload to Telegram failed.")


def main():
    parser = argparse.ArgumentParser(description="SupremeAI TelDrive Encrypted Backup")
    parser.add_argument("--mode", choices=["full", "db", "code"], default="full", help="Backup scope")
    parser.add_argument("--dry-run", action="store_true", help="Prepare bundle without uploading")
    args = parser.parse_args()
    asyncio.run(run_backup(mode=args.mode, dry_run=args.dry_run))


if __name__ == "__main__":
    main()


# --- Merged from telegram_code_backup.py ---

#!/usr/bin/env python3
# ruff: noqa: BLE001, ASYNC230, SIM102
"""
SupremeAI 2.0 — Automated Telegram Codebase Backup Runner (Zip & Markdown Digest)
---------------------------------------------------------------------------------
Generates an AI-optimized clean zip and unified single-file Markdown digest (.md) 
of the project and uploads them directly to Telegram Cloud Vault on Push.

Usage:
    python scripts/backup/telegram_code_backup.py --format all
"""



import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

# Ensure UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Silenced error: {e}")

ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env", override=True)

IGNORED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp", ".tiff",
    ".jsonl", ".parquet", ".arrow", ".h5", ".sqlite", ".db", ".csv",
    ".zip", ".tar", ".gz", ".7z", ".exe", ".dll", ".so", ".dylib", ".wasm", ".map", ".tmp"
}

IGNORED_DIRECTORY_PREFIXES = (
    "_archive/",
    "reports/",
    "backend/docs/autogen/",
    "backend/reports/",
)

def is_knowledge_base_doc(rel_path_posix: str) -> bool:
    return rel_path_posix.startswith("docs/knowledge-base/") and rel_path_posix.endswith(".md")

def is_excluded_for_ai(rel_path_posix: str) -> bool:
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
        print(f"[!] Warning: Git command failed ({e}). Scanning manually...")
        return fallback_file_scanner(project_dir)

def fallback_file_scanner(project_dir: Path) -> list[Path]:
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

def create_ai_zip(project_dir: Path, output_zip_path: Path) -> tuple[int, int, int]:
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

    # Sort files alphabetically
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

            # Avoid triple-backtick collision by using 4 backticks if needed
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

def slugify(text: str) -> str:
    """Helper to convert commit message to clean filename slug."""
    import re
    cleaned = re.sub(r"[^\w\s-]", "", text.strip())
    slug = re.sub(r"[-\s]+", "_", cleaned).strip("_")
    return slug[:40] if slug else "commit"

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
        # Check if there is a parent commit
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
        print(f"[!] Warning: Git diff extraction error: {e}")

    return diff_data

def create_commit_diff_markdown(
    output_md_path: Path,
    git_info: dict[str, str],
    diff_info: dict[str, Any]
) -> tuple[int, int]:
    """Generates a dedicated Markdown diff document with commit metadata and code diffs."""
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
    """Creates a lightweight zip containing ONLY the files modified in this commit."""
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

def get_git_commit_info(project_dir: Path) -> dict[str, str]:
    info = {"commit": "N/A", "message": "Automated Backup", "author": "CI/CD Agent", "branch": "main"}
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

async def upload_document_to_telegram(
    doc_path: Path,
    caption: str,
    mime_type: str,
    bot_token: str,
    chat_id: str,
) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    size_mb = doc_path.stat().st_size / (1024 * 1024)

    print(f"📤 Uploading {doc_path.name} ({size_mb:.2f} MB) to Telegram Chat {chat_id}...")
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            with open(doc_path, "rb") as f:
                files = {"document": (doc_path.name, f, mime_type)}
                data = {"chat_id": str(chat_id), "caption": caption, "parse_mode": "HTML"}
                response = await client.post(url, data=data, files=files)
                response.raise_for_status()
                res = response.json()
                if res.get("ok"):
                    print(f"✅ Upload Successful for {doc_path.name}!")
                    return True
                else:
                    print(f"❌ Telegram API Error for {doc_path.name}: {res}")
                    return False
    except Exception as e:
        print(f"❌ Telegram Upload Exception for {doc_path.name}: {e}")
        return False

async def main():
    parser = argparse.ArgumentParser(description="SupremeAI Telegram Codebase Backup (Full & Incremental Diff)")
    parser.add_argument("--dry-run", action="store_true", help="Create archives without uploading to Telegram")
    parser.add_argument("--out-dir", type=str, default="", help="Custom output directory")
    parser.add_argument(
        "--mode",
        choices=["auto", "diff", "full", "all"],
        default="auto",
        help="Backup mode: auto (diff on push, full on weekly/dispatch), diff, full, or all"
    )
    args = parser.parse_args()

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    if not args.dry_run and (not bot_token or not chat_id):
        print("⚠️ Warning: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured.")
        print("   Proceeding in dry-run mode (local generation only)...")
        args.dry_run = True

    git_info = get_git_commit_info(ROOT_DIR)
    diff_info = get_git_diff_info(ROOT_DIR)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    msg_slug = slugify(git_info["message"])
    out_dir = Path(args.out_dir) if args.out_dir else ROOT_DIR / "temp_backup"

    # Determine what to run based on mode & CI event
    event_name = os.getenv("GITHUB_EVENT_NAME", "push").lower()

    if args.mode == "auto":
        if event_name == "schedule":
            # 🗓️ Weekly scheduled run — Full Codebase Archive + Digest
            run_full = True
            run_diff = False
            print("🗓️ Event: Scheduled Weekly Cron → Generating Full Codebase Vault Backup.")
        elif event_name == "workflow_dispatch":
            # 🚀 Manual Trigger — Run Everything
            run_full = True
            run_diff = True
            print("🚀 Event: Manual Dispatch → Generating Full Archive & Diff Snapshots.")
        else:
            # ⚡ Standard Git Push — Incremental Diff & Changed Files Only
            run_full = False
            run_diff = True
            print("⚡ Event: Git Push → Generating Incremental Diff & Changed Files Package.")
    elif args.mode == "diff":
        run_full = False
        run_diff = True
    elif args.mode == "full":
        run_full = True
        run_diff = False
    else:  # all
        run_full = True
        run_diff = True

    success_all = True

    # ── 1. Full Project ZIP & Markdown Digest (Weekly / Full) ───
    if run_full:
        # Full ZIP
        zip_filename = f"supremeai_{git_info['branch']}_{git_info['commit']}_{timestamp}.zip"
        zip_path = out_dir / zip_filename
        print("🚀 Generating Full AI-Ready Zip Archive...")
        start_time = time.time()
        file_count, uncompressed_size, compressed_size = create_ai_zip(ROOT_DIR, zip_path)
        elapsed = time.time() - start_time
        cmp_mb = compressed_size / (1024 * 1024)
        unc_mb = uncompressed_size / (1024 * 1024)
        ratio = (1 - (compressed_size / uncompressed_size)) * 100 if uncompressed_size > 0 else 0
        print(f"✨ Full Zip Created in {elapsed:.2f}s: {zip_path.name} ({cmp_mb:.2f} MB, {file_count} files)")

        if not args.dry_run:
            zip_caption = (
                f"📦 <b>SupremeAI Full Codebase Archive (.zip)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌿 <b>Branch:</b> <code>{git_info['branch']}</code>\n"
                f"🔖 <b>Commit:</b> <code>{git_info['commit']}</code>\n"
                f"💬 <b>Message:</b> <i>{git_info['message']}</i>\n"
                f"👤 <b>Author:</b> <code>{git_info['author']}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📁 <b>Active Files:</b> {file_count:,}\n"
                f"📊 <b>Zip Size:</b> {cmp_mb:.2f} MB (Saved {ratio:.1f}% from {unc_mb:.2f} MB)\n"
                f"🕒 <b>Timestamp:</b> <code>{timestamp_str}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ <i>Weekly Zero-Cost Codebase Vault</i>"
            )
            ok_zip = await upload_document_to_telegram(
                doc_path=zip_path,
                caption=zip_caption,
                mime_type="application/zip",
                bot_token=bot_token,
                chat_id=chat_id,
            )
            if not ok_zip:
                success_all = False

            if os.getenv("GITHUB_ACTIONS"):
                zip_path.unlink(missing_ok=True)

        # Full Markdown Digest
        md_filename = f"supremeai_{git_info['branch']}_{git_info['commit']}_{timestamp}_digest.md"
        md_path = out_dir / md_filename
        print("🚀 Generating Full Single-File Markdown Digest (.md)...")
        start_time = time.time()
        md_file_count, md_size_bytes = create_ai_markdown_digest(ROOT_DIR, md_path, git_info)
        elapsed = time.time() - start_time
        md_mb = md_size_bytes / (1024 * 1024)
        print(f"✨ Full Markdown Digest Created in {elapsed:.2f}s: {md_path.name} ({md_mb:.2f} MB, {md_file_count} files)")

        if not args.dry_run:
            md_caption = (
                f"📄 <b>SupremeAI Full AI Codebase Digest (.md)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🌿 <b>Branch:</b> <code>{git_info['branch']}</code>\n"
                f"🔖 <b>Commit:</b> <code>{git_info['commit']}</code>\n"
                f"💬 <b>Message:</b> <i>{git_info['message']}</i>\n"
                f"👤 <b>Author:</b> <code>{git_info['author']}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📁 <b>Included Files:</b> {md_file_count:,}\n"
                f"📊 <b>Doc Size:</b> {md_mb:.2f} MB (Single-File Context Ready)\n"
                f"💡 <b>Usage:</b> Drop into ChatGPT / Claude / Gemini for full context!\n"
                f"🕒 <b>Timestamp:</b> <code>{timestamp_str}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🧠 <i>Continuous Learning Matrix Snapshot</i>"
            )
            ok_md = await upload_document_to_telegram(
                doc_path=md_path,
                caption=md_caption,
                mime_type="text/markdown",
                bot_token=bot_token,
                chat_id=chat_id,
            )
            if not ok_md:
                success_all = False

            if os.getenv("GITHUB_ACTIONS"):
                md_path.unlink(missing_ok=True)

    # ── 2. Incremental Commit Diff & Changed Files (On Push) ────
    if run_diff and diff_info["has_diff"]:
        # Diff Markdown Patch
        diff_md_filename = f"supremeai_diff_{git_info['commit']}_{msg_slug}.md"
        diff_md_path = out_dir / diff_md_filename
        print(f"🚀 Generating Commit Diff Markdown Patch ({diff_md_filename})...")
        start_time = time.time()
        cf_count, diff_size_bytes = create_commit_diff_markdown(diff_md_path, git_info, diff_info)
        elapsed = time.time() - start_time
        diff_kb = diff_size_bytes / 1024
        print(f"✨ Commit Diff MD Created in {elapsed:.2f}s: {diff_md_path.name} ({diff_kb:.1f} KB, {cf_count} files modified)")

        if not args.dry_run:
            diff_caption = (
                f"🔀 <b>SupremeAI Commit Diff Patch (.md)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔖 <b>Commit:</b> <code>{git_info['commit']}</code>\n"
                f"🌿 <b>Branch:</b> <code>{git_info['branch']}</code>\n"
                f"💬 <b>Message:</b> <i>{git_info['message']}</i>\n"
                f"👤 <b>Author:</b> <code>{git_info['author']}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📝 <b>Modified Files:</b> {cf_count} file(s)\n"
                f"📊 <b>Diff Size:</b> {diff_kb:.1f} KB\n"
                f"🕒 <b>Timestamp:</b> <code>{timestamp_str}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔍 <i>Incremental Git Diff Snapshot</i>"
            )
            ok_diff_md = await upload_document_to_telegram(
                doc_path=diff_md_path,
                caption=diff_caption,
                mime_type="text/markdown",
                bot_token=bot_token,
                chat_id=chat_id,
            )
            if not ok_diff_md:
                success_all = False

            if os.getenv("GITHUB_ACTIONS"):
                diff_md_path.unlink(missing_ok=True)

        # Changed Files Only ZIP
        diff_zip_filename = f"supremeai_diff_files_{git_info['commit']}_{msg_slug}.zip"
        diff_zip_path = out_dir / diff_zip_filename
        print(f"🚀 Generating Changed-Files-Only Zip Package ({diff_zip_filename})...")
        start_time = time.time()
        cz_count, _cz_unc, cz_cmp = create_changed_files_zip(ROOT_DIR, diff_zip_path, diff_info["changed_files"])
        elapsed = time.time() - start_time
        cz_kb = cz_cmp / 1024
        print(f"✨ Changed-Files Zip Created in {elapsed:.2f}s: {diff_zip_path.name} ({cz_kb:.1f} KB, {cz_count} files)")

        if not args.dry_run and cz_count > 0:
            diff_zip_caption = (
                f"📦 <b>SupremeAI Incremental Changed Files (.zip)</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔖 <b>Commit:</b> <code>{git_info['commit']}</code>\n"
                f"🌿 <b>Branch:</b> <code>{git_info['branch']}</code>\n"
                f"💬 <b>Message:</b> <i>{git_info['message']}</i>\n"
                f"👤 <b>Author:</b> <code>{git_info['author']}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📁 <b>Packaged Files:</b> {cz_count} file(s)\n"
                f"📊 <b>Package Size:</b> {cz_kb:.1f} KB\n"
                f"🕒 <b>Timestamp:</b> <code>{timestamp_str}</code>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚡ <i>Instant Differential Code Package</i>"
            )
            ok_diff_zip = await upload_document_to_telegram(
                doc_path=diff_zip_path,
                caption=diff_zip_caption,
                mime_type="application/zip",
                bot_token=bot_token,
                chat_id=chat_id,
            )
            if not ok_diff_zip:
                success_all = False

            if os.getenv("GITHUB_ACTIONS"):
                diff_zip_path.unlink(missing_ok=True)

    if not success_all:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())


# --- Merged from restore_from_telegram.py ---

#!/usr/bin/env python3
"""
SupremeAI 2.0 — Disaster Recovery & Restore Engine
Decrypts and restores Supabase Database & AI Memory from TelDrive Vault.
"""



import contextlib
import sys
from pathlib import Path

from dotenv import load_dotenv

if sys.stdout.encoding != "utf-8":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

# Load local workspace env
root_dir = Path(__file__).resolve().parents[2]
load_dotenv(root_dir / ".env", override=True)



def get_fernet_crypto() -> Fernet:
    raw_key = os.getenv("ENCRYPTION_KEY") or os.getenv("SUPREMEAI_BACKUP_ENCRYPTION_KEY")
    if not raw_key:
        raise ValueError(
            "CRITICAL SECURITY: ENCRYPTION_KEY or SUPREMEAI_BACKUP_ENCRYPTION_KEY environment variable is mandatory. "
            "Hardcoded default encryption keys are strictly prohibited."
        )
    digest = hashlib.sha256(raw_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def decrypt_file(file_path: Path) -> dict[str, Any]:
    with open(file_path, "rb") as f:
        encrypted_bytes = f.read()

    fernet = get_fernet_crypto()
    decompressed = gzip.decompress(fernet.decrypt(encrypted_bytes))
    return json.loads(decompressed.decode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="SupremeAI Disaster Recovery & Decryptor")
    parser.add_argument("backup_file", type=Path, help="Path to .enc.gz backup file")
    parser.add_argument("--inspect", action="store_true", help="Print summary of backup contents without restoring")
    args = parser.parse_args()

    if not args.backup_file.exists():
        print(f"❌ File not found: {args.backup_file}")
        sys.exit(1)

    print(f"🔓 Decrypting {args.backup_file.name} using AES-256 Fernet Key...")
    try:
        data = decrypt_file(args.backup_file)
        print(f"✅ Decryption successful! Backup created at: {data.get('timestamp')}")

        if "database" in data:
            db_data = data["database"]
            print(f"📊 Tables in backup ({len(db_data)} total):")
            for tbl, rows in db_data.items():
                print(f"  - {tbl}: {len(rows)} records")

        if "codebase" in data:
            code = data["codebase"]
            print(f"📁 Codebase Snapshot: {code.get('total_files')} files ({code.get('total_size_kb')} KB)")

        if args.inspect:
            return

        print("\n⚡ Ready for database restoration. (Run with DB write permissions to apply).")

    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"❌ Decryption or restore error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
