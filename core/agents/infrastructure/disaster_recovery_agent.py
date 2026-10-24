"""
Disaster Recovery Agent for SupremeAI 2.0
Handles automated backup and recovery procedures to ensure system resilience.
"""

import asyncio
import hashlib
import json
import os
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.cache.redis_manager import redis_manager
from core.config import settings
from core.llm.token_deductor import TokenDeductor
from core.logging_config import logger
from core.utils.background_tasks import track_task


@dataclass
class BackupResult:
    """Data class to hold backup operation results."""

    backup_id: str
    timestamp: datetime
    size_bytes: int
    location: str
    status: str  # success, failed, partial
    verification_hash: str
    components_backed_up: list[str]
    duration_seconds: float


@dataclass
class RecoveryResult:
    """Data class to hold recovery operation results."""

    recovery_id: str
    timestamp: datetime
    backup_id: str
    status: str  # success, failed, partial
    recovered_components: list[str]
    duration_seconds: float
    notes: str


class DisasterRecoveryAgent:
    """Agent that handles automated backup and recovery procedures."""

    def __init__(self):
        self.name = "Disaster Recovery Agent"
        self.token_deductor = TokenDeductor()
        self.backup_history_key = "disaster_recovery:backup_history"
        self.recovery_history_key = "disaster_recovery:recovery_history"
        self.recovery_plan_key = "disaster_recovery:recovery_plans"
        self.system_state_key = "disaster_recovery:system_state"

        # Define critical system components that need backup.
        # বাংলা: প্রতিটা component-এর paths env var দিয়ে override করা যায় (comma-separated)।
        # env var না থাকলে sensible defaults ব্যবহার হয়। এটি "zero-hardcoded" principle follow করে।
        self.critical_components = {
            "database": {
                "paths": self._env_paths(
                    "DR_DB_PATHS", [getattr(settings, "DATABASE_URL", ""), "/data/db.sqlite3"]
                ),
                "backup_method": "sql_dump",
                "restore_method": "sql_restore",
                "priority": "high",
            },
            "configuration": {
                "paths": self._env_paths("DR_CONFIG_PATHS", ["/config/", "./config/", "/etc/app/"]),
                "backup_method": "file_copy",
                "restore_method": "file_copy",
                "priority": "high",
            },
            "user_data": {
                "paths": self._env_paths(
                    "DR_USER_DATA_PATHS", ["/data/users/", "/storage/uploads/"]
                ),
                "backup_method": "archive",
                "restore_method": "extract",
                "priority": "high",
            },
            "skills": {
                "paths": self._env_paths("DR_SKILLS_PATHS", ["/skills/", "/backend/skills/"]),
                "backup_method": "archive",
                "restore_method": "extract",
                "priority": "medium",
            },
            "models": {
                "paths": self._env_paths("DR_MODELS_PATHS", ["/models/", "/backend/models/"]),
                "backup_method": "archive",
                "restore_method": "extract",
                "priority": "medium",
            },
            "logs": {
                "paths": self._env_paths("DR_LOGS_PATHS", ["/logs/", "/var/log/app/"]),
                "backup_method": "archive",
                "restore_method": "skip",
                "priority": "low",
            },
        }

        # Recovery priorities (order of restoration)
        self.recovery_priority_order = [
            "configuration",
            "database",
            "user_data",
            "skills",
            "models",
            "logs",
        ]

        # Initialize default recovery plans
        self.default_recovery_plans = {
            "minimal_service_restoration": {
                "name": "Minimal Service Restoration",
                "description": "Restore only essential services to resume basic operations",
                "components": ["configuration", "database"],
                "target_recovery_time": 300,  # 5 minutes
                "target_point_objective": 3600,  # 1 hour
            },
            "full_restoration": {
                "name": "Full System Restoration",
                "description": "Complete system restoration with all data and functionality",
                "components": list(self.critical_components.keys()),
                "target_recovery_time": 3600,  # 1 hour
                "target_point_objective": 900,  # 15 minutes
            },
            "user_data_restoration": {
                "name": "User Data Restoration",
                "description": "Restore only user data while keeping system operational",
                "components": ["user_data"],
                "target_recovery_time": 1800,  # 30 minutes
                "target_point_objective": 1800,  # 30 minutes
            },
        }

    @staticmethod
    def _env_paths(env_var: str, defaults: list[str]) -> list[str]:
        """
        env var থেকে comma-separated paths পড়ে। env var না থাকলে বা empty হলে
        defaults ফেরত দেয়। এটি "zero-hardcoded" principle মেনে চলে — deployment-এর
        সময় প্রতিটা component-এর paths env var দিয়ে override করা যায়।
        """
        val = os.environ.get(env_var, "").strip()
        if not val:
            return defaults
        return [p.strip() for p in val.split(",") if p.strip()]

    async def initialize_recovery_plans(self):
        """Initialize disaster recovery plans in Redis."""
        try:
            existing_plans = await redis_manager.get(self.recovery_plan_key)
            if not existing_plans:
                await redis_manager.set(
                    self.recovery_plan_key,
                    json.dumps(self.default_recovery_plans),
                    ex=2592000,  # 30 days
                )
                logger.info("Default disaster recovery plans initialized")
        except Exception as e:
            logger.error(f"Error initializing recovery plans: {e}")

    async def create_backup(
        self,
        backup_type: str = "full",
        components: list[str] | None = None,
        location_override: str | None = None,
    ) -> BackupResult:
        """
        Create a system backup.

        Args:
            backup_type: Type of backup ('full', 'incremental', 'config_only', etc.)
            components: Specific components to back up (if None, uses defaults)
            location_override: Specific location for backup storage

        Returns:
            BackupResult containing backup information
        """
        start_time = datetime.utcnow()

        try:
            backup_id = f"backup_{int(start_time.timestamp())}_{os.urandom(4).hex()}"

            # Determine which components to back up
            if components is None:
                if backup_type == "full":
                    components = list(self.critical_components.keys())
                elif backup_type == "config_only":
                    components = ["configuration"]
                elif backup_type == "data_only":
                    components = ["database", "user_data"]
                else:
                    components = list(self.critical_components.keys())

            # Filter to only valid components
            valid_components = [comp for comp in components if comp in self.critical_components]

            logger.info(f"Starting backup {backup_id} for components: {valid_components}")

            backup_location = location_override or getattr(settings, "BACKUP_LOCATION", "/backups/")
            backup_path = os.path.join(backup_location, f"{backup_id}.zip")

            # Create backup archive
            size_bytes = await self._create_backup_archive(backup_path, valid_components)

            # Generate verification hash
            verification_hash = await self._generate_file_hash(backup_path)

            # Record backup completion
            duration = (datetime.utcnow() - start_time).total_seconds()

            backup_result = BackupResult(
                backup_id=backup_id,
                timestamp=start_time,
                size_bytes=size_bytes,
                location=backup_path,
                status="success",
                verification_hash=verification_hash,
                components_backed_up=valid_components,
                duration_seconds=duration,
            )

            # Store backup result in history
            await self._store_backup_result(backup_result)

            # Update system state
            await self._update_system_state(
                {
                    "last_backup": start_time.isoformat(),
                    "backup_size": size_bytes,
                    "backup_location": backup_path,
                }
            )

            logger.info(f"Backup completed successfully: {backup_id}, size: {size_bytes} bytes")
            return backup_result

        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            duration = (datetime.utcnow() - start_time).total_seconds()

            backup_result = BackupResult(
                backup_id=f"backup_{int(start_time.timestamp())}_failed",
                timestamp=start_time,
                size_bytes=0,
                location="",
                status="failed",
                verification_hash="",
                components_backed_up=components or [],
                duration_seconds=duration,
            )

            await self._store_backup_result(backup_result)
            return backup_result

    async def restore_from_backup(
        self,
        backup_id: str,
        recovery_plan: str = "full_restoration",
        components: list[str] | None = None,
    ) -> RecoveryResult:
        """
        Restore system from a backup using a specific recovery plan.

        Args:
            backup_id: ID of the backup to restore from
            recovery_plan: Name of the recovery plan to use
            components: Specific components to restore (overrides plan if provided)

        Returns:
            RecoveryResult containing restoration information
        """
        start_time = datetime.utcnow()

        try:
            recovery_id = f"recovery_{int(start_time.timestamp())}_{os.urandom(4).hex()}"

            # Get backup information
            backup_info = await self._get_backup_info(backup_id)
            if not backup_info:
                raise ValueError(f"Backup {backup_id} not found")

            logger.info(f"Starting recovery {recovery_id} from backup {backup_id}")

            # Determine components to restore
            if components:
                restore_components = components
            else:
                plans = await self._get_recovery_plans()
                plan_info = plans.get(recovery_plan)
                if plan_info:
                    restore_components = plan_info["components"]
                else:
                    restore_components = list(self.critical_components.keys())

            # Validate components exist in backup
            available_components = backup_info.get("components_backed_up", [])
            valid_components = [comp for comp in restore_components if comp in available_components]

            # Restore components in priority order
            restored_components = []
            for component in self.recovery_priority_order:
                if component in valid_components:
                    success = await self._restore_component(component, backup_info["location"])
                    if success:
                        restored_components.append(component)

            # Record recovery completion
            duration = (datetime.utcnow() - start_time).total_seconds()

            recovery_result = RecoveryResult(
                recovery_id=recovery_id,
                timestamp=start_time,
                backup_id=backup_id,
                status="success"
                if len(restored_components) == len(valid_components)
                else "partial",
                recovered_components=restored_components,
                duration_seconds=duration,
                notes=f"Restored {len(restored_components)} of {len(valid_components)} components",
            )

            # Store recovery result in history
            await self._store_recovery_result(recovery_result)

            # Update system state
            await self._update_system_state(
                {
                    "last_recovery": start_time.isoformat(),
                    "recovery_id": recovery_id,
                    "recovered_components": restored_components,
                }
            )

            logger.info(
                f"Recovery completed: {recovery_id}, restored {len(restored_components)} components"
            )
            return recovery_result

        except Exception as e:
            logger.error(f"Error during recovery: {e}")
            duration = (datetime.utcnow() - start_time).total_seconds()

            recovery_result = RecoveryResult(
                recovery_id=f"recovery_{int(start_time.timestamp())}_failed",
                timestamp=start_time,
                backup_id=backup_id,
                status="failed",
                recovered_components=[],
                duration_seconds=duration,
                notes=f"Recovery failed: {e!s}",
            )

            await self._store_recovery_result(recovery_result)
            return recovery_result

    async def _create_backup_archive(self, archive_path: str, components: list[str]) -> int:
        """Create a backup archive for specified components."""
        try:
            os.makedirs(os.path.dirname(archive_path), exist_ok=True)

            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for component in components:
                    if component in self.critical_components:
                        comp_info = self.critical_components[component]
                        paths = comp_info["paths"]

                        for path_str in paths:
                            path = Path(path_str)
                            if path.exists():
                                if path.is_file():
                                    # Add single file
                                    zipf.write(str(path), f"{component}/{path.name}")
                                elif path.is_dir():
                                    # Add directory contents
                                    for file_path in path.rglob("*"):
                                        if file_path.is_file():
                                            arc_name = f"{component}/{file_path.relative_to(path)}"
                                            zipf.write(str(file_path), arc_name)

            # Return file size
            return os.path.getsize(archive_path)
        except Exception as e:
            logger.error(f"Error creating backup archive: {e}")
            raise

    async def _restore_component(self, component: str, backup_path: str) -> bool:
        """Restore a specific component from backup."""
        try:
            if component not in self.critical_components:
                logger.warning(f"Unknown component: {component}")
                return False

            comp_info = self.critical_components[component]
            restore_method = comp_info["restore_method"]

            if restore_method == "skip":
                logger.info(f"Skipping restoration of {component} (restore_method: skip)")
                return True

            # Extract component from backup
            with zipfile.ZipFile(backup_path, "r") as zipf:
                # Get all files for this component
                comp_files = [f for f in zipf.namelist() if f.startswith(f"{component}/")]

                if not comp_files:
                    logger.warning(f"No files found for component {component} in backup")
                    return False

                # Extract files to destination
                dest_path = comp_info["paths"][0]  # Use first path as destination
                os.makedirs(dest_path, exist_ok=True)

                for file_in_zip in comp_files:
                    zipf.extract(file_in_zip, dest_path)

            logger.info(f"Successfully restored component: {component}")
            return True

        except Exception as e:
            logger.error(f"Error restoring component {component}: {e}")
            return False

    async def _generate_file_hash(self, file_path: str) -> str:
        """Generate SHA-256 hash for file verification."""
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                # Read file in chunks to handle large files
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Error generating file hash: {e}")
            return ""

    async def _store_backup_result(self, result: BackupResult):
        """Store backup result in Redis."""
        try:
            result_data = {
                "backup_id": result.backup_id,
                "timestamp": result.timestamp.isoformat(),
                "size_bytes": result.size_bytes,
                "location": result.location,
                "status": result.status,
                "verification_hash": result.verification_hash,
                "components_backed_up": result.components_backed_up,
                "duration_seconds": result.duration_seconds,
            }

            # Get existing backups
            existing_backups = await redis_manager.get(self.backup_history_key)
            if existing_backups:
                backups_list = json.loads(existing_backups)
            else:
                backups_list = []

            # Add new backup
            backups_list.append(result_data)

            # Keep only the last N backups
            max_backups = 50
            if len(backups_list) > max_backups:
                backups_list = backups_list[-max_backups:]

            await redis_manager.set(
                self.backup_history_key,
                json.dumps(backups_list),
                ex=2592000,  # 30 days
            )
        except Exception as e:
            logger.error(f"Error storing backup result: {e}")

    async def _store_recovery_result(self, result: RecoveryResult):
        """Store recovery result in Redis."""
        try:
            result_data = {
                "recovery_id": result.recovery_id,
                "timestamp": result.timestamp.isoformat(),
                "backup_id": result.backup_id,
                "status": result.status,
                "recovered_components": result.recovered_components,
                "duration_seconds": result.duration_seconds,
                "notes": result.notes,
            }

            # Get existing recoveries
            existing_recoveries = await redis_manager.get(self.recovery_history_key)
            if existing_recoveries:
                recoveries_list = json.loads(existing_recoveries)
            else:
                recoveries_list = []

            # Add new recovery
            recoveries_list.append(result_data)

            # Keep only the last N recoveries
            max_recoveries = 50
            if len(recoveries_list) > max_recoveries:
                recoveries_list = recoveries_list[-max_recoveries:]

            await redis_manager.set(
                self.recovery_history_key,
                json.dumps(recoveries_list),
                ex=2592000,  # 30 days
            )
        except Exception as e:
            logger.error(f"Error storing recovery result: {e}")

    async def _get_backup_info(self, backup_id: str) -> dict[str, Any] | None:
        """Get information about a specific backup."""
        try:
            existing_backups = await redis_manager.get(self.backup_history_key)
            if not existing_backups:
                return None

            backups_list = json.loads(existing_backups)
            for backup in backups_list:
                if backup["backup_id"] == backup_id:
                    return backup

            return None
        except Exception as e:
            logger.error(f"Error getting backup info: {e}")
            return None

    async def _get_recovery_plans(self) -> dict[str, Any]:
        """Get current recovery plans."""
        try:
            plans_json = await redis_manager.get(self.recovery_plan_key)
            if plans_json:
                return json.loads(plans_json)
            else:
                return self.default_recovery_plans
        except Exception as e:
            logger.error(f"Error getting recovery plans: {e}")
            return self.default_recovery_plans

    async def _update_system_state(self, state_updates: dict[str, Any]):
        """Update system state with recovery-related information."""
        try:
            # Get current state
            current_state = await redis_manager.get(self.system_state_key)
            if current_state:
                state = json.loads(current_state)
            else:
                state = {}

            # Update with new information
            state.update(state_updates)
            state["last_updated"] = datetime.utcnow().isoformat()

            await redis_manager.set(
                self.system_state_key,
                json.dumps(state),
                ex=86400,  # 24 hours
            )
        except Exception as e:
            logger.error(f"Error updating system state: {e}")

    async def get_backup_schedule_recommendations(self) -> dict[str, Any]:
        """
        Generate recommendations for backup scheduling based on system usage.

        Returns:
            Dictionary with backup schedule recommendations
        """
        try:
            # Analyze system state and usage patterns to recommend backup schedule
            system_state = await redis_manager.get(self.system_state_key)
            if system_state:
                state = json.loads(system_state)
            else:
                state = {}

            # Default recommendations
            recommendations = {
                "full_backup_frequency": "daily",
                "incremental_backup_frequency": "hourly",
                "retention_period_days": 30,
                "offsite_replication": True,
                "backup_windows": ["02:00-04:00", "14:00-16:00"],  # Low usage times
                "critical_components_schedule": {
                    "configuration": "every_change",
                    "database": "hourly",
                    "user_data": "daily",
                },
            }

            # Adjust based on system characteristics
            if state.get("high_transaction_volume"):
                recommendations["incremental_backup_frequency"] = "every_15_minutes"

            if state.get("regulatory_requirements", {}).get("strict_data_retention"):
                recommendations["retention_period_days"] = 90

            return recommendations

        except Exception as e:
            logger.error(f"Error generating backup schedule recommendations: {e}")
            return {
                "full_backup_frequency": "daily",
                "incremental_backup_frequency": "hourly",
                "retention_period": 30,
                "offsite_replication": True,
            }

    async def verify_backup_integrity(self, backup_id: str) -> dict[str, Any]:
        """
        Verify the integrity of a backup.

        Args:
            backup_id: ID of the backup to verify

        Returns:
            Dictionary with verification results
        """
        try:
            backup_info = await self._get_backup_info(backup_id)
            if not backup_info:
                return {"status": "not_found", "message": f"Backup {backup_id} not found"}

            backup_path = backup_info["location"]
            stored_hash = backup_info["verification_hash"]

            # Recalculate hash
            current_hash = await self._generate_file_hash(backup_path)

            # Verify file structure
            try:
                with zipfile.ZipFile(backup_path, "r") as zipf:
                    file_list = zipf.namelist()
                    is_valid_structure = len(file_list) > 0
            except zipfile.BadZipFile:
                is_valid_structure = False

            verification_result = {
                "backup_id": backup_id,
                "status": "verified"
                if (stored_hash == current_hash and is_valid_structure)
                else "corrupted",
                "hash_match": stored_hash == current_hash,
                "structure_valid": is_valid_structure,
                "file_count": len(file_list) if is_valid_structure else 0,
                "size_match": os.path.getsize(backup_path) == backup_info["size_bytes"],
                "timestamp": datetime.utcnow().isoformat(),
            }

            return verification_result

        except Exception as e:
            logger.error(f"Error verifying backup integrity: {e}")
            return {
                "backup_id": backup_id,
                "status": "error",
                "message": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }


# Global instance
disaster_recovery_agent = DisasterRecoveryAgent()

# Initialize recovery plan on module load — শুধুমাত্র একটা event loop চলমান থাকলেই টাস্ক শিডিউল করা হয়;
# বাংলা: import-time-এ event loop না থাকলে RuntimeError এড়ানো হয়, আর টাস্কের রেফারেন্স ট্র্যাক করে
# রাখা হয় যাতে GC হয়ে মাঝপথে বাতিল না হয়ে যায় (RUF006)।
try:
    track_task(
        asyncio.get_running_loop().create_task(disaster_recovery_agent.initialize_recovery_plans())
    )
except RuntimeError:
    logger.debug(
        "No running event loop at import time; skipping eager recovery plan init "
        "(call initialize_recovery_plans() explicitly during app startup instead)."
    )
