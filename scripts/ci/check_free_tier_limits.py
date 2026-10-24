#!/usr/bin/env python
"""
check_free_tier_limits.py
=========================
বাংলা মন্তব্য: pre-commit hook এবং Nightly CI guard হিসেবে কাজ করে।
প্রতিটি commit-এর আগে বিভিন্ন free-tier পরিবেশের সাইজ লিমিট
চেক করে এবং সীমা অতিক্রম করতে চাইলে সতর্ক করে বা block করে।

Free-tier limits tracked:
  - Render (Free):      ~500MB backend deploy context
  - GitHub Actions:     8GB cache (our soft cap, hard limit 10GB)
  - Vercel (Hobby):     100MB per serverless function bundle
  - Firebase Hosting:   1GB total storage
  - Git Repo:           200MB recommended max (GitHub warning at 5GB)

Usage:
    python scripts/ci/check_free_tier_limits.py
    python scripts/ci/check_free_tier_limits.py --auto-fix          # Intelligent cleanup
    python scripts/ci/check_free_tier_limits.py --auto-fix --dry-run # Preview only

Auto-Fix Tiers:
  WARNING (80%+) → Safe cleanup: __pycache__, .mypy_cache, .ruff_cache,
                                  .pytest_cache, htmlcov/, *.pyc
  CRITICAL (95%+) → Aggressive:  All of WARNING + git gc --prune=now
                                  + stale frontend/dist artifacts
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

# বাংলা মন্তব্য: Windows-এ emoji print করতে UTF-8 encoding force করা হচ্ছে
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Project root ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent

# ══════════════════════════════════════════════════════════════════════════════
# Free-tier limit definitions
# ══════════════════════════════════════════════════════════════════════════════

MB = 1024 * 1024
GB = 1024 * MB

class SizeLimit(NamedTuple):
    label: str           # Human readable env name
    path: str            # Relative path from root to measure
    warn_bytes: int      # Warn at this size (80%)
    block_bytes: int     # Block commit at this size (95%)
    tip: str             # What to do if exceeded


FREE_TIER_LIMITS: list[SizeLimit] = [
    SizeLimit(
        label="🟠 Render Free (backend deploy context)",
        path="backend",
        warn_bytes=int(400 * MB),    # 400MB → warn (80% of 500MB)
        block_bytes=int(475 * MB),   # 475MB → block (95% of 500MB)
        tip=(
            "Render free tier ~500MB RAM. Remove unused packages from "
            "pyproject.toml, delete large model files, or use .dockerignore "
            "to exclude test/dev assets from the build context."
        ),
    ),
    SizeLimit(
        label="🟡 GitHub Actions cache (CI cache quota)",
        path=".git",
        warn_bytes=int(6 * GB),      # 6GB → warn
        block_bytes=int(8 * GB),     # 8GB → block (our soft cap)
        tip=(
            "GitHub cache approaches our 8GB soft cap. Run "
            "'git gc --aggressive --prune=now' to shrink .git, "
            "or remove large binary/model files from history with git-filter-repo."
        ),
    ),
    SizeLimit(
        label="🔵 Vercel Hobby (frontend bundle per function)",
        path="frontend/dist",
        warn_bytes=int(80 * MB),     # 80MB → warn (80% of 100MB)
        block_bytes=int(95 * MB),    # 95MB → block (95% of 100MB)
        tip=(
            "Vercel hobby limit is 100MB per function. Run 'pnpm build' "
            "and check bundle analyzer output. Use dynamic imports, "
            "tree-shaking, or move large deps to CDN."
        ),
    ),
    SizeLimit(
        label="🟢 Firebase Hosting (static assets)",
        path="frontend/dist",
        warn_bytes=int(800 * MB),    # 800MB → warn (80% of 1GB)
        block_bytes=int(950 * MB),   # 950MB → block (95% of 1GB)
        tip=(
            "Firebase Hosting free tier allows 1GB storage. "
            "Compress images, use WebP format, and remove unused static assets."
        ),
    ),
    SizeLimit(
        label="📦 Git repo size (tracked files, excl. .git)",
        path=".",
        warn_bytes=int(800 * MB),    # 800MB → warn (GitHub সাধারণত 2GB সীমার নিচে থাকা ভালো)
        block_bytes=int(2 * GB),     # 2GB → block
        tip=(
            "Repo working tree is large. Avoid committing binary files, model weights, "
            "or node_modules. Use Git LFS for large assets. "
            "Run: git ls-files | xargs ls -la | sort -k5 -rn | head -20"
        ),
    ),
]

# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

EXCLUDED_DIRS = {
    "node_modules", "__pycache__", ".venv", "venv",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "htmlcov",
    ".git",  # বাংলা: .git আলাদাভাবে check হয়, repo size থেকে বাদ
    ".worktrees", "dist", "build", "target",
}


def get_dir_size(path: Path) -> int:
    """বাংলা মন্তব্য: একটি ডিরেক্টরির মোট সাইজ বাইটে গণনা করে।"""
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size

    for dirpath, dirnames, filenames in os.walk(path):
        # বাংলা মন্তব্য: ভার্চুয়াল এনভায়রনমেন্ট ও cache বাদ দেওয়া হচ্ছে
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for filename in filenames:
            try:
                fp = Path(dirpath) / filename
                total += fp.stat().st_size
            except Exception as e:
                import logging
                logging.getLogger(__name__).exception(f"Silenced error: {e}")
    return total


def human_size(size_bytes: int) -> str:
    """বাংলা মন্তব্য: বাইট সংখ্যাকে মানুষের পড়ার যোগ্য ফরম্যাটে রূপান্তর।"""
    if size_bytes >= GB:
        return f"{size_bytes / GB:.2f} GB"
    if size_bytes >= MB:
        return f"{size_bytes / MB:.1f} MB"
    return f"{size_bytes / 1024:.1f} KB"


def progress_bar(current: int, total: int, width: int = 30) -> str:
    """বাংলা মন্তব্য: ASCII progress bar তৈরি করে।"""
    filled = int(width * current / total) if total > 0 else 0
    filled = min(filled, width)
    bar = "█" * filled + "░" * (width - filled)
    pct = min(100.0, 100.0 * current / total) if total > 0 else 0.0
    return f"[{bar}] {pct:.1f}%"


# ══════════════════════════════════════════════════════════════════════════════
# Main scan
# ══════════════════════════════════════════════════════════════════════════════

def run_checks() -> bool:
    """
    বাংলা মন্তব্য: সব free-tier limit চেক করে।
    Returns True if commit should be BLOCKED, False if safe to proceed.
    """
    print("\n📏 SupremeAI Free-Tier Size Guard — Pre-commit Check")
    print("=" * 60)

    any_warn = False
    any_block = False

    for limit in FREE_TIER_LIMITS:
        target = ROOT / limit.path
        if not target.exists():
            # বাংলা মন্তব্য: path না থাকলে skip করা হয় (e.g. dist/ not built yet)
            print(f"\n{limit.label}")
            print(f"  ⏭  Path not found: {limit.path!r} — skipping")
            continue

        size = get_dir_size(target)
        bar = progress_bar(size, limit.block_bytes)

        print(f"\n{limit.label}")
        print(f"  Path : {limit.path}")
        print(f"  Size : {human_size(size)} / {human_size(limit.block_bytes)} limit")
        print(f"  {bar}")

        if size >= limit.block_bytes:
            print(f"  🔴 CRITICAL: Size exceeds {int(100 * limit.block_bytes / limit.block_bytes)}% of free-tier limit!")
            print(f"  💡 Fix: {limit.tip}")
            any_block = True

        elif size >= limit.warn_bytes:
            pct = int(100 * limit.warn_bytes / limit.block_bytes)
            print(f"  🟠 WARNING: Approaching limit ({pct}% threshold reached)")
            print(f"  💡 Tip: {limit.tip}")
            any_warn = True

        else:
            print("  ✅ OK — well within free-tier limit")

    print("\n" + "=" * 60)

    if any_block:
        print("🚫 COMMIT BLOCKED: One or more free-tier size limits exceeded.")
        print("   Fix the issues above before committing.")
        print("   Use --no-verify to bypass (NOT recommended for production).")
        return True  # block

    if any_warn:
        print("⚠️  WARNINGS: Some paths are approaching free-tier limits.")
        print("   Monitor closely — no action required yet.")

    if not any_warn and not any_block:
        print("✅ All free-tier size checks passed!")

    print()
    return False  # allow commit


# ══════════════════════════════════════════════════════════════════════════════
# Runtime Memory Guard
# ══════════════════════════════════════════════════════════════════════════════

# Heavy packages that must NOT be in default (non-optional) dependencies
HEAVY_PACKAGES = [
    "torch",
    "torchvision",
    "torchaudio",
    "sentence-transformers",
    "sentence_transformers",
    "transformers",
    "tensorflow",
    "keras",
]

# pyproject.toml sections that are ALLOWED to contain heavy packages (optional groups)
ALLOWED_HEAVY_SECTIONS = [
    "[tool.poetry.group.ml",
    "[tool.poetry.group.gpu",
    "[tool.poetry.group.dev",
]


def check_runtime_memory_guard() -> bool:
    """
    বাংলা মন্তব্য: Runtime memory safety checks for 512MB free-tier.
    Verifies that:
      1. LOW_MEMORY_MODE is not explicitly set to 'false' in .env files
      2. UVICORN_WORKERS is not set > 1 in .env files
      3. Heavy ML packages are not in core (non-optional) dependencies
    Returns True if BLOCKED, False if safe.
    """
    print("\n🧠 Runtime Memory Guard — 512MB Free-Tier Safety Check")
    print("=" * 60)

    any_block = False

    # ── 1. Check pyproject.toml for heavy packages in core deps ──────────────
    pyproject_path = ROOT / "backend" / "pyproject.toml"
    if pyproject_path.exists():
        print("\n📦 Checking pyproject.toml for heavy ML packages in core deps...")
        content = pyproject_path.read_text(encoding="utf-8")
        lines = content.splitlines()

        # Parse sections to find where we are
        current_section = ""
        in_core_deps = False
        violations: list[str] = []

        for lineno, line in enumerate(lines, start=1):
            stripped = line.strip()

            # Track section headers
            if stripped.startswith("["):
                current_section = stripped
                # Core dependencies section = main poetry deps
                in_core_deps = (
                    stripped == "[tool.poetry.dependencies]"
                    or stripped == "[tool.poetry.dev-dependencies]"
                )
                # If it's an optional group, we're safe
                if any(allowed in stripped for allowed in ALLOWED_HEAVY_SECTIONS):
                    in_core_deps = False

            # Check for heavy packages only in core deps
            if in_core_deps:
                for pkg in HEAVY_PACKAGES:
                    # Match "package-name = " or "package_name = " style
                    pkg_normalized = pkg.replace("-", "[-_]")
                    import re
                    if re.match(rf"^\s*{pkg_normalized}\s*[=<>{{]", line, re.IGNORECASE):
                        violations.append(
                            f"  Line {lineno}: '{stripped}' in section '{current_section}'"
                        )

        if violations:
            print("  🔴 BLOCKED: Heavy ML packages found in core dependencies!")
            print("  These packages consume 200-800MB RAM and will OOM on Render free-tier.")
            print("  Move them to [tool.poetry.group.ml.dependencies] (optional=true):")
            for v in violations:
                print(v)
            print("  💡 Fix: Add 'optional = true' group and move the package there.")
            any_block = True
        else:
            print("  ✅ OK — no heavy ML packages in core dependencies")
    else:
        print("  ⏭  pyproject.toml not found — skipping package check")

    # ── 2. Check .env files for LOW_MEMORY_MODE=false ────────────────────────
    print("\n🔧 Checking .env files for LOW_MEMORY_MODE setting...")
    env_files = list(ROOT.glob("**/.env")) + list(ROOT.glob("**/.env.*"))
    env_files = [f for f in env_files if ".git" not in str(f) and "node_modules" not in str(f)]

    low_memory_violations: list[str] = []
    for env_file in env_files:
        try:
            for lineno, line in enumerate(env_file.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                stripped = line.strip()
                if stripped.upper().startswith("LOW_MEMORY_MODE") and "FALSE" in stripped.upper():
                    low_memory_violations.append(f"  {env_file.relative_to(ROOT)}:{lineno} → {stripped}")
        except Exception as e:
            print(f"  ⚠️ Warning: Could not read {env_file}: {e}")

    if low_memory_violations:
        print("  🔴 BLOCKED: LOW_MEMORY_MODE=false found in .env file(s)!")
        print("  This re-enables SentenceTransformer and will OOM on Render free-tier.")
        for v in low_memory_violations:
            print(v)
        print("  💡 Fix: Set LOW_MEMORY_MODE=true (or remove the line — default is true).")
        any_block = True
    else:
        print("  ✅ OK — LOW_MEMORY_MODE not explicitly disabled")

    # ── 3. Check .env files for UVICORN_WORKERS > 1 ──────────────────────────
    print("\n⚙️  Checking .env files for UVICORN_WORKERS setting...")
    worker_violations: list[str] = []
    for env_file in env_files:
        try:
            for lineno, line in enumerate(env_file.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                stripped = line.strip()
                if stripped.upper().startswith("UVICORN_WORKERS"):
                    import re
                    match = re.search(r"UVICORN_WORKERS\s*=\s*(\d+)", stripped, re.IGNORECASE)
                    if match and int(match.group(1)) > 1:
                        worker_violations.append(
                            f"  {env_file.relative_to(ROOT)}:{lineno} → {stripped}"
                        )
        except Exception as e:
            print(f"  ⚠️ Warning: Could not read {env_file}: {e}")

    if worker_violations:
        print("  🔴 BLOCKED: UVICORN_WORKERS > 1 found in .env file(s)!")
        print("  Multiple workers split the 512MB budget — guaranteed OOM on Render free-tier.")
        for v in worker_violations:
            print(v)
        print("  💡 Fix: Set UVICORN_WORKERS=1 (or remove the line — default is 1).")
        any_block = True
    else:
        print("  ✅ OK — UVICORN_WORKERS is not set above 1")

    print("\n" + "=" * 60)
    if any_block:
        print("🚫 RUNTIME MEMORY GUARD: One or more checks FAILED.")
        return True
    print("✅ All runtime memory guard checks passed!")
    print()
    return False


# ══════════════════════════════════════════════════════════════════════════════
# Intelligent Auto-Fix Cleanup
# ══════════════════════════════════════════════════════════════════════════════

# Safe-to-delete directory names (always regenerable)
_SAFE_CACHE_DIRS = {
    "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache",
    ".pytype", ".dmypy", ".hypothesis", "htmlcov",
}

# File patterns safe to delete
_SAFE_FILE_GLOBS = ["**/*.pyc", "**/*.pyo", "**/.DS_Store"]

# Dirs safe to wipe only in CRITICAL zone (100% rebuild possible)
_CRITICAL_EXTRA_DIRS = {"frontend/dist", "frontend/.next", "frontend/build"}


def _bytes_freed_label(freed: int) -> str:
    if freed >= GB:
        return f"{freed / GB:.2f} GB"
    if freed >= MB:
        return f"{freed / MB:.1f} MB"
    return f"{freed / 1024:.1f} KB"


def auto_fix_cleanup(dry_run: bool = False) -> int:
    """
    বাংলা মন্তব্য: Intelligent tiered cleanup.
    WARNING zone → safe caches only.
    CRITICAL zone → aggressive cleanup + git gc.
    Returns total bytes freed.
    """
    print()
    print("🧹 Intelligent Auto-Fix Cleanup")
    print("=" * 60)
    if dry_run:
        print("  ⚠️  DRY-RUN MODE — nothing will actually be deleted")
    print()

    total_freed = 0
    actions: list[tuple[str, Path]] = []  # (label, path)

    # ── Determine cleanup tier from current state ─────────────────────────────
    warn_triggered = False
    critical_triggered = False
    for limit in FREE_TIER_LIMITS:
        target = ROOT / limit.path
        if not target.exists():
            continue
        size = get_dir_size(target)
        if size >= limit.block_bytes:
            critical_triggered = True
            break
        elif size >= limit.warn_bytes:
            warn_triggered = True

    if not warn_triggered and not critical_triggered:
        print("  ✅ All sizes within safe limits — no cleanup needed.")
        return 0

    tier = "CRITICAL" if critical_triggered else "WARNING"
    print(f"  📊 Cleanup tier: {tier}")
    print()

    # ── Collect targets ───────────────────────────────────────────────────────
    # 1. Safe cache dirs (WARNING+)
    print("  🔍 Scanning for safe cache directories...")
    for dirpath, dirnames, _ in os.walk(ROOT):
        dp = Path(dirpath)
        # Skip .git itself
        if ".git" in dp.parts:
            continue
        for d in list(dirnames):
            if d in _SAFE_CACHE_DIRS:
                full = dp / d
                sz = get_dir_size(full)
                if sz > 0:
                    actions.append((f"  🗑  [CACHE DIR] {full.relative_to(ROOT)} ({_bytes_freed_label(sz)})", full))
                    total_freed += sz
                dirnames.remove(d)  # Don't recurse into it

    # 2. Safe file globs (WARNING+)
    for pattern in _SAFE_FILE_GLOBS:
        for f in ROOT.glob(pattern):
            if ".git" in f.parts:
                continue
            sz = f.stat().st_size
            actions.append((f"  🗑  [FILE] {f.relative_to(ROOT)} ({_bytes_freed_label(sz)})", f))
            total_freed += sz

    # 3. CRITICAL-only targets
    if critical_triggered:
        for rel_path in _CRITICAL_EXTRA_DIRS:
            target = ROOT / rel_path
            if target.exists():
                sz = get_dir_size(target)
                if sz > 0:
                    actions.append((f"  🗑  [BUILD ARTIFACT] {rel_path} ({_bytes_freed_label(sz)})", target))
                    total_freed += sz

    # ── Preview ───────────────────────────────────────────────────────────────
    if not actions and not critical_triggered:
        print("  ✅ No safe cleanup targets found.")
        return 0

    print(f"  Found {len(actions)} item(s) to clean — estimated savings: {_bytes_freed_label(total_freed)}")
    print()
    for label, _ in actions:
        print(label)

    if critical_triggered:
        print(f"  🗑  [GIT GC] Will run: git gc --auto --prune=now (in .git/)")

    print()

    if dry_run:
        print("  ℹ️  Dry-run complete. Run without --dry-run to apply changes.")
        return total_freed

    # ── Execute ───────────────────────────────────────────────────────────────
    print("  ⚡ Executing cleanup...")
    actually_freed = 0
    for label, path in actions:
        try:
            if path.is_dir():
                sz = get_dir_size(path)
                shutil.rmtree(path)
                actually_freed += sz
            elif path.is_file():
                sz = path.stat().st_size
                path.unlink()
                actually_freed += sz
            print(f"  ✅ Removed: {label.strip()}")
        except Exception as e:
            print(f"  ⚠️  Could not remove {path}: {e}")

    # git gc for CRITICAL
    if critical_triggered:
        print("  ⚡ Running git gc --auto --prune=now ...")
        try:
            result = subprocess.run(
                ["git", "gc", "--auto", "--prune=now"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0:
                print("  ✅ git gc completed successfully")
            else:
                print(f"  ⚠️  git gc exited {result.returncode}: {result.stderr.strip()[:200]}")
        except Exception as e:
            print(f"  ⚠️  git gc failed: {e}")

    print()
    print(f"  🎉 Cleanup complete! Freed ~{_bytes_freed_label(actually_freed)}")
    print()

    # ── Re-check after cleanup ────────────────────────────────────────────────
    print("  📏 Re-checking sizes after cleanup...")
    for limit in FREE_TIER_LIMITS:
        target = ROOT / limit.path
        if not target.exists():
            continue
        size = get_dir_size(target)
        bar = progress_bar(size, limit.block_bytes)
        status = "✅" if size < limit.warn_bytes else ("🟠" if size < limit.block_bytes else "🔴")
        print(f"  {status} {limit.label}: {human_size(size)} / {human_size(limit.block_bytes)}  {bar}")

    return actually_freed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SupremeAI Free-Tier Size & Runtime Memory Guard"
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Intelligently clean caches/artifacts when WARNING or CRITICAL limits are hit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what --auto-fix would delete without actually deleting anything",
    )
    args = parser.parse_args()

    size_blocked = run_checks()
    memory_blocked = check_runtime_memory_guard()

    if args.auto_fix or args.dry_run:
        auto_fix_cleanup(dry_run=args.dry_run)
        if not args.dry_run and (size_blocked or memory_blocked):
            # Re-run checks after cleanup to see if we're now in the clear
            print()
            print("🔄 Re-running checks after auto-fix...")
            print("=" * 60)
            size_blocked = run_checks()
            memory_blocked = check_runtime_memory_guard()

    sys.exit(1 if (size_blocked or memory_blocked) else 0)
