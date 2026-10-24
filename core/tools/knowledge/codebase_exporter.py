import asyncio
import os
import shutil
import subprocess
import tempfile

from core.logging_config import logger

IGNORE_DIRS: set[str] = {
    ".git",
    "node_modules",
    "venv",
    "env",
    "__pycache__",
    "dist",
    "build",
    ".next",
    ".vscode",
    ".idea",
    "coverage",
    ".github",
    ".venv",
}

IGNORE_EXTS: set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".webp",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".mp4",
    ".mp3",
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".exe",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".log",
}

IGNORE_FILES: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "service-account.json",
}


def get_language(file_name: str) -> str:
    ext = os.path.splitext(file_name)[1].lower()
    mapping = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "jsx",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".json": "json",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".md": "markdown",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".sh": "bash",
        "Dockerfile": "dockerfile",
    }
    return mapping.get(ext, "text")


def _collect_files(root_dir: str, changed_files: set[str] | None = None) -> list[str]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root_dir, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for file in filenames:
            if file in IGNORE_FILES or file.startswith("."):
                continue
            ext = os.path.splitext(file)[1].lower()
            if ext in IGNORE_EXTS:
                continue
            full_path = os.path.join(dirpath, file)
            rel_path = os.path.relpath(full_path, root_dir).replace("\\", "/")

            # If we only want files changed in a specific git time range
            if changed_files is not None and rel_path not in changed_files:
                continue

            if rel_path == "supremeai_full_codebase.md" or file == "code_to_md.py":
                continue
            files.append(full_path)
    return files


def _chunk_lines(content: str, chunk_size: int = 200000) -> list[str]:
    if len(content) <= chunk_size:
        return [content]
    chunks = []
    start = 0
    while start < len(content):
        end = start + chunk_size
        chunk = content[start:end]
        if end < len(content):
            nl = chunk.rfind("\n")
            if nl != -1:
                end = start + nl + 1
                chunk = content[start:end]
        chunks.append(chunk)
        start = end
    return [c for c in chunks if c.strip()]


async def export_file_async(file_path: str, root_dir: str) -> str:
    rel = os.path.relpath(file_path, root_dir).replace("\\", "/")
    language = get_language(os.path.basename(file_path))
    try:
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(None, _read_file, file_path)
    except Exception as exc:
        return f"### File: `{rel}` (read error: {exc})\n\n"
    parts = [f"### File: `{rel}`\n\n```{language}\n"]
    for idx, chunk in enumerate(_chunk_lines(content)):
        if idx > 0:
            parts.append(f"\n...[truncated chunk {idx + 1}]\n")
        parts.append(chunk)
        if not chunk.endswith("\n"):
            parts.append("\n")
    parts.append("```\n\n")
    return "".join(parts)


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def _get_git_changed_files(
    root_dir: str, since: str | None = None, until: str | None = None
) -> set[str] | None:
    """Gets the list of files changed in Git within the specified time range."""
    if not os.path.exists(os.path.join(root_dir, ".git")):
        return None

    cmd = ["git", "log", "--name-only", "--pretty=format:"]
    if since:
        cmd.append(f"--since={since}")
    if until:
        cmd.append(f"--until={until}")

    try:
        output = subprocess.check_output(cmd, cwd=root_dir, stderr=subprocess.DEVNULL).decode(
            "utf-8", errors="ignore"
        )
        files = {line.strip().replace("\\", "/") for line in output.split("\n") if line.strip()}
        return files
    except Exception as e:
        logger.warning(f"Failed to fetch git changed files: {e}")
        return None


def _get_git_diff_summary(root_dir: str, since: str | None = None, until: str | None = None) -> str:
    """Generates a summary of changes from Git logs."""
    if not os.path.exists(os.path.join(root_dir, ".git")):
        return "No Git repository detected."

    cmd = ["git", "log", "--oneline"]
    if since:
        cmd.append(f"--since={since}")
    if until:
        cmd.append(f"--until={until}")

    try:
        output = subprocess.check_output(cmd, cwd=root_dir, stderr=subprocess.DEVNULL).decode(
            "utf-8", errors="ignore"
        )
        if not output.strip():
            return "No changes recorded in this time range."
        commits = output.strip().split("\n")
        summary = f"Total commits: {len(commits)}\n\n"
        summary += "\n".join(f"- {commit}" for commit in commits[:20])
        if len(commits) > 20:
            summary += f"\n- ... and {len(commits) - 20} more commits."
        return summary
    except Exception as e:
        return f"Failed to retrieve git changes: {e}"


async def export_codebase_to_markdown(
    root_dir: str = ".",
    max_concurrency: int = 8,
    time_since: str | None = None,
    time_until: str | None = None,
    git_diff_only: bool = False,
    clone_url: str | None = None,
) -> str:
    """Exports a codebase to a single Markdown file with optional Git diff filtering and cloning."""
    temp_dir = None

    try:
        # Step 1: Clone public repo if specified
        if clone_url:
            logger.info(f"Cloning public repository: {clone_url}")
            temp_dir = tempfile.mkdtemp()
            # Run git clone depth 1 for speed
            process = await asyncio.create_subprocess_exec(
                "git",
                "clone",
                "--depth",
                "1",
                clone_url,
                temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            _stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(f"Git clone failed: {stderr.decode('utf-8', errors='ignore')}")
            export_dir = temp_dir
        else:
            export_dir = os.path.abspath(root_dir)

        # Step 2: Determine file list and Git history summary
        changed_files = None
        git_summary = ""

        if time_since or time_until or git_diff_only:
            changed_files = _get_git_changed_files(export_dir, time_since, time_until)
            git_summary = _get_git_diff_summary(export_dir, time_since, time_until)

        files = _collect_files(export_dir, changed_files if git_diff_only else None)

        # Step 3: Run concurrent file reads and assembly
        semaphore = asyncio.Semaphore(max_concurrency)

        async def bounded(path):
            async with semaphore:
                return await export_file_async(path, export_dir)

        chunks = await asyncio.gather(*(bounded(p) for p in files))

        # Build headers
        header = "# 📄 SupremeAI 2.0 Codebase Export\n"
        if clone_url:
            header += f"- **Source URL**: {clone_url}\n"
        else:
            header += "- **Source**: Local Workspace\n"
        if time_since or time_until:
            header += (
                f"- **Time Range**: {time_since or 'Beginning'} to {time_until or 'Present'}\n"
            )
        if git_summary:
            header += f"\n## 📈 Git Changes Summary\n```text\n{git_summary}\n```\n"

        header += "\n## 🗂️ File Content Snapshot\n\n"

        return header + "".join(chunks)

    finally:
        # Cleanup temp directory if created
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp dir {temp_dir}: {e}")
