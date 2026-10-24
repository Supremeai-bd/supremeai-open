"""Provides a secure mechanism for the SupremeAI system to apply runtime code updates and multi-file patches.

বাংলা: সিস্টেমের স্বয়ংক্রিয় আপডেট, মাল্টি-ফাইল প্যাচিং এবং সেলফ-হিলিং রোলব্যাক ইঞ্জিন।
"""

import shutil
from pathlib import Path

from core.logging_config import logger

_ALLOWED_BASE_DIR = Path(__file__).resolve().parent.parent.parent


class SelfUpdater:
    """Self-Updater module for SupremeAI 2.0.

    Applies patches, updates code modules, and manages multi-file evolution.
    """

    def __init__(self, authorized: bool = False):
        self.authorized = authorized

    def _validate_path(self, file_path: str) -> Path:
        target = Path(file_path).resolve()
        if not str(target).startswith(str(_ALLOWED_BASE_DIR)):
            raise ValueError(f"Hotfix target '{file_path}' is outside allowed project directory.")
        return target

    def apply_hotfix(self, file_path: str, new_content: str) -> bool:
        """Applies a hotpatch directly to an active file."""
        logger.info(f"Applying self-evolution hotfix to {file_path}")
        try:
            target = self._validate_path(file_path)
            if not target.exists():
                logger.error(f"Target file does not exist: {file_path}")
                return False
        except (ValueError, OSError) as e:
            logger.error(f"Hotfix path validation failed: {e}")
            return False

        if not self.authorized:
            logger.error("Hotfix rejected: updater is not authorized.")
            return False

        try:
            # Backup original
            backup_path = target.with_suffix(target.suffix + ".bak")
            original = target.read_text(encoding="utf-8")
            backup_path.write_text(original, encoding="utf-8")

            # Write new version
            target.write_text(new_content, encoding="utf-8")

            logger.info("Hotfix successfully applied.")
            return True
        except (OSError, PermissionError, UnicodeDecodeError) as e:
            logger.error(f"Failed to apply hotpatch: {e}")
            return False

    def apply_multi_file_patch(
        self,
        patches: dict[str, str],
        proposal_id: str | None = None,
    ) -> tuple[bool, list[str]]:
        """Applies multi-file patches with automatic rollbacks on failure.

        বাংলা: একাধিক ফাইল একসাথে আপডেট করে; কোনো সমস্যা হলে স্বয়ংক্রিয় রোলব্যাক করে।
        """
        if not self.authorized:
            logger.error("Multi-file patch rejected: updater is not authorized.")
            return False, ["Unauthorized"]

        applied_backups: list[tuple[Path, Path]] = []
        applied_files: list[str] = []

        try:
            for file_path, content in patches.items():
                target = self._validate_path(file_path)
                backup_path = target.with_suffix(target.suffix + ".evobak")

                if target.exists():
                    shutil.copy2(target, backup_path)
                    applied_backups.append((target, backup_path))

                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
                applied_files.append(str(target))

            logger.info(
                f"Multi-file patch {proposal_id or ''} applied to {len(applied_files)} files."
            )
            return True, applied_files

        except Exception as exc:
            logger.error(f"Multi-file patch failed, initiating rollback: {exc}")
            # Rollback changed files
            for target, backup_path in applied_backups:
                if backup_path.exists():
                    shutil.copy2(backup_path, target)
                    backup_path.unlink()
            return False, [str(exc)]


# AUD-6.1: the module-level singleton previously instantiated SelfUpdater with
# authorized=True, exposing an uncalled-but-armed path that could write any
# file under backend/ directly. Self-mutation is only permitted inside the
# governed evolution pipeline (ChangeProposalManager + GovernancePolicy), so
# the standalone updater now defaults to UNAUTHORIZED.
self_updater = SelfUpdater(authorized=False)
