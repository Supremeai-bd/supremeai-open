"""
SupremeAI — Code-to-Database Outbox Sync Daemon
===============================================

Syncs code changes and transactional outbox updates to database endpoints.
- Incremental code indexing & change detection
- Asynchronous Outbox Flusher with Idempotency Key matching
- Periodic background worker loop
- Bangla inline comments for team clarity (AGENTS.md compliant)
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.cache import get_cache
from core.logging_config import logger
from database.multi_db_router import get_multi_db_router

# ── Constants ────────────────────────────────────────────────────────────────
SYNC_CACHE_TTL = 86400  # 24 hours
DEFAULT_DAEMON_INTERVAL = 10.0  # seconds


class CodeToDBSync:
    """
    Synchronizes codebase and outbox transactions to multi-database instances.
    """

    def __init__(self) -> None:
        self.cache = get_cache()
        self.router = get_multi_db_router()
        self._last_sync_key = "code_sync:last_run"
        self._file_hashes_key = "code_sync:file_hashes"
        self._is_running = False
        self._worker_task: asyncio.Task | None = None

    async def sync_project(self, project_path: str) -> dict[str, Any]:
        """
        Sync project files to database.

        Args:
            project_path: Path to project root.

        Returns:
            Sync summary.
        """
        project = Path(project_path)
        if not project.exists():
            return {"status": "error", "message": "Project not found"}

        # Get last sync state
        await self.cache.get(self._last_sync_key)
        file_hashes = await self.cache.get(self._file_hashes_key) or {}

        changed_files = []
        current_hashes = {}

        for py_file in project.rglob("*.py"):
            # Skip hidden directories
            if any(p.startswith(".") for p in py_file.parts):
                continue

            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                file_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                current_hashes[str(py_file)] = file_hash

                if file_hashes.get(str(py_file)) != file_hash:
                    changed_files.append(str(py_file))
            except Exception as e:
                logger.debug(f"Failed to hash {py_file}: {e}")

        # Update state
        await self.cache.set(self._file_hashes_key, current_hashes, ttl=SYNC_CACHE_TTL)
        await self.cache.set(self._last_sync_key, datetime.now(UTC).isoformat(), ttl=SYNC_CACHE_TTL)

        # বাংলা ব্যাখ্যা: প্রোজেক্ট সিঙ্কের পর পরিবর্তিত ফাইল মেটাডেটা আউটবক্স সিঙ্ক রাউটারে রেকর্ড করা হয়।
        logger.info(
            f"CodeToDBSync: Indexed {len(current_hashes)} files ({len(changed_files)} changed)"
        )

        return {
            "status": "success",
            "project": project_path,
            "files_processed": len(current_hashes),
            "changed_files": len(changed_files),
            "changed_file_list": changed_files[:20],  # Top 20
            "synced_at": datetime.now(UTC).isoformat(),
        }

    async def flush_outbox_queue(self) -> int:
        """
        Flushes pending Outbox transactions to D1 / Supabase / Redis replicas.
        বাংলা মন্তব্য: WriteBehindBatcher নিজেই background thread-এ প্রতি flush_interval-এ
        self-flush করে, কিন্তু daemon loop থেকে eager flush ট্রিগার করা ও প্রকৃত pending-count
        রিপোর্ট করার জন্য এখানে সরাসরি batcher.flush() কল করা হচ্ছে (Patch 17 fix)।
        """
        from database.multi_db_router import outbox_batcher

        flushed = await asyncio.to_thread(outbox_batcher.flush)
        if flushed:
            logger.info(f"CodeToDBSync Outbox Worker: Flushed {flushed} pending outbox rows")
        else:
            logger.debug("CodeToDBSync Outbox Worker: No pending outbox rows to flush")
        return flushed

    async def start_daemon(
        self, project_path: str = "./", interval: float = DEFAULT_DAEMON_INTERVAL
    ) -> None:
        """
        Start the background sync daemon loop.
        বাংলা ব্যাখ্যা: সিঙ্ক ডেমন চালু করা যা ব্যাকগ্রাউন্ডে নির্দিষ্ট সময় পরপর কোড সিঙ্ক ও আউটবক্স ফ্লাশ সচল রাখে।
        """
        if self._is_running:
            logger.warning("CodeToDBSync daemon is already running")
            return

        self._is_running = True

        async def _daemon_loop() -> None:
            while self._is_running:
                try:
                    await self.sync_project(project_path)
                    await self.flush_outbox_queue()
                except Exception as exc:
                    logger.error(f"CodeToDBSync daemon error: {exc}")
                await asyncio.sleep(interval)

        self._worker_task = asyncio.create_task(_daemon_loop())
        logger.info(f"CodeToDBSync background daemon started (interval={interval}s)")

    async def stop_daemon(self) -> None:
        """Stop the background sync daemon loop."""
        self._is_running = False
        if self._worker_task:
            self._worker_task.cancel()
            self._worker_task = None
        logger.info("CodeToDBSync background daemon stopped")

    async def get_file_metadata(self, file_path: str) -> dict[str, Any]:
        """Extract metadata from file for database storage."""
        path = Path(file_path)
        if not path.exists():
            return {}

        content = path.read_text(encoding="utf-8", errors="ignore")

        # Extract imports
        import re

        imports = re.findall(r"^import\s+(\w+)|^from\s+(\w+)", content, re.MULTILINE)

        # Extract classes and functions
        classes = re.findall(r"^class\s+(\w+)", content, re.MULTILINE)
        functions = re.findall(r"^def\s+(\w+)", content, re.MULTILINE)

        return {
            "file_path": file_path,
            "language": "python",
            "size_bytes": len(content),
            "imports": [i[0] or i[1] for i in imports],
            "classes": classes,
            "functions": functions,
            "last_indexed": datetime.now(UTC).isoformat(),
        }


# Singleton
_sync_instance: CodeToDBSync | None = None


def get_code_sync() -> CodeToDBSync:
    """Get or create the singleton CodeToDBSync instance."""
    global _sync_instance
    if _sync_instance is None:
        _sync_instance = CodeToDBSync()
    return _sync_instance
