#!/usr/bin/env python3
"""
AI Model Version Manager
Model versioning and rollback management for AI/ML models.
Priority: 🟡 Medium
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from core.config import settings
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ModelStatus(Enum):
    """Model deployment status."""
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"


class RollbackReason(Enum):
    """Reasons for model rollback."""
    PERFORMANCE_DEGRADATION = "performance_degradation"
    ACCURACY_DROP = "accuracy_drop"
    BIAS_DETECTED = "bias_detected"
    SECURITY_VULNERABILITY = "security_vulnerability"
    DATA_DRIFT = "data_drift"


@dataclass
class ModelVersion:
    """Model version metadata."""
    version_id: str
    model_name: str
    version_number: str
    status: ModelStatus
    created_at: datetime
    artifacts_path: str
    metrics: dict[str, float]
    parent_version: str | None = None
    tags: list[str] = field(default_factory=list)
    checksum: str | None = None


class ModelVersionManager:
    """
    Manages AI model versions including deployment, rollback, and state management.
    """

    def __init__(self, storage_path: str = "model_versions", db_path: str = "model_registry.db"):
        self.storage_path = Path(storage_path)
        self.db_path = db_path
        self.storage_path.mkdir(exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database for model registry."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS model_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id TEXT UNIQUE NOT NULL,
                model_name TEXT NOT NULL,
                version_number TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                artifacts_path TEXT,
                metrics TEXT,
                parent_version TEXT,
                tags TEXT,
                checksum TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rollback_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_version TEXT NOT NULL,
                to_version TEXT NOT NULL,
                reason TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                details TEXT
            )
        ''')
        conn.commit()
        conn.close()

    def _compute_checksum(self, directory: Path) -> str:
        """Compute checksum for model artifacts."""
        hasher = hashlib.sha256()
        for file_path in sorted(directory.rglob('*')):
            if file_path.is_file():
                with open(file_path, 'rb') as f:
                    hasher.update(f.read())
        return hasher.hexdigest()

    def create_version(
        self,
        model_name: str,
        version_number: str,
        artifacts_path: str,
        metrics: dict[str, float] | None = None,
        parent_version: str | None = None,
        tags: list[str] | None = None
    ) -> ModelVersion:
        """Create a new model version entry."""
        version_id = f"{model_name}_v{version_number}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Compute checksum
        artifacts_dir = Path(artifacts_path)
        checksum = self._compute_checksum(artifacts_dir) if artifacts_dir.exists() else None

        version = ModelVersion(
            version_id=version_id,
            model_name=model_name,
            version_number=version_number,
            status=ModelStatus.STAGING,
            created_at=datetime.now(),
            artifacts_path=str(artifacts_dir),
            metrics=metrics or {},
            parent_version=parent_version,
            tags=tags or [],
            checksum=checksum
        )

        self._save_version(version)
        logger.info(f"Created model version: {version_id}")

        return version

    def _sync_to_supabase(self, version: ModelVersion):
        """Sync version metadata to Supabase ModelVersion table if env variables are available."""
        import os
        url = settings.supabase_url
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
        if not url or not key:
            return
        try:
            from supabase import create_client
            client = create_client(url, key)
            data = {
                "version_id": version.version_id,
                "model_name": version.model_name,
                "version_number": version.version_number,
                "status": version.status.value,
                "created_at": version.created_at.isoformat(),
                "artifacts_path": version.artifacts_path,
                "metrics": version.metrics,
                "parent_version": version.parent_version,
                "tags": version.tags,
                "checksum": version.checksum,
            }
            client.table("ModelVersion").upsert(data).execute()
            logger.info(f"Synced version {version.version_id} to Supabase ModelVersion table.")
        except Exception as e:
            logger.warning(f"Supabase sync failed (non-blocking): {e}")

    def _sync_to_hf_hub(self, version: ModelVersion, repo_id: str | None = None):
        """Sync version metadata to HuggingFace Hub repository if token is available."""
        import os
        token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
        if not token or not repo_id:
            return
        try:
            from huggingface_hub import HfApi
            api = HfApi(token=token)
            api.create_repo(repo_id=repo_id, exist_ok=True)
            meta_json = json.dumps({
                "version_id": version.version_id,
                "model_name": version.model_name,
                "version_number": version.version_number,
                "status": version.status.value,
                "metrics": version.metrics,
                "checksum": version.checksum,
            }, indent=2)
            api.upload_file(
                path_or_fileobj=meta_json.encode("utf-8"),
                path_in_repo=f"versions/{version.version_id}.json",
                repo_id=repo_id,
            )
            logger.info(f"Uploaded model version {version.version_id} metadata to HF Hub repo {repo_id}.")
        except Exception as e:
            logger.warning(f"HF Hub sync failed (non-blocking): {e}")

    def _save_version(self, version: ModelVersion):
        """Save version to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO model_versions
            (version_id, model_name, version_number, status, created_at, artifacts_path,
             metrics, parent_version, tags, checksum)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            version.version_id,
            version.model_name,
            version.version_number,
            version.status.value,
            version.created_at.isoformat(),
            version.artifacts_path,
            json.dumps(version.metrics),
            version.parent_version,
            json.dumps(version.tags),
            version.checksum
        ))
        conn.commit()
        conn.close()

        self._sync_to_supabase(version)

    def get_current_production_version(self, model_name: str) -> ModelVersion | None:
        """Get the current production version of a model."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT version_id, model_name, version_number, status, created_at, artifacts_path,
                   metrics, parent_version, tags, checksum
            FROM model_versions
            WHERE model_name = ? AND status = ?
            ORDER BY created_at DESC LIMIT 1
        ''', (model_name, ModelStatus.PRODUCTION.value))

        row = cursor.fetchone()
        conn.close()

        if row:
            return ModelVersion(
                version_id=row[0],
                model_name=row[1],
                version_number=row[2],
                status=ModelStatus(row[3]),
                created_at=datetime.fromisoformat(row[4]),
                artifacts_path=row[5],
                metrics=json.loads(row[6]),
                parent_version=row[7],
                tags=json.loads(row[8]),
                checksum=row[9]
            )
        return None

    def get_version(self, version_id: str) -> ModelVersion | None:
        """Get a specific version by ID."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT version_id, model_name, version_number, status, created_at, artifacts_path,
                   metrics, parent_version, tags, checksum
            FROM model_versions WHERE version_id = ?
        ''', (version_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return ModelVersion(
                version_id=row[0],
                model_name=row[1],
                version_number=row[2],
                status=ModelStatus(row[3]),
                created_at=datetime.fromisoformat(row[4]),
                artifacts_path=row[5],
                metrics=json.loads(row[6]),
                parent_version=row[7],
                tags=json.loads(row[8]),
                checksum=row[9]
            )
        return None

    def promote_to_production(self, version_id: str) -> bool:
        """Promote a staging version to production."""
        version = self.get_version(version_id)
        if not version:
            logger.error(f"Version not found: {version_id}")
            return False

        # Archive current production version
        current = self.get_current_production_version(version.model_name)
        if current:
            self._update_status(current.version_id, ModelStatus.ARCHIVED)
            logger.info(f"Archived current production version: {current.version_id}")

        # Promote new version
        self._update_status(version_id, ModelStatus.PRODUCTION)
        logger.info(f"Promoted to production: {version_id}")

        return True

    def _update_status(self, version_id: str, status: ModelStatus):
        """Update version status in database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE model_versions SET status = ? WHERE version_id = ?
        ''', (status.value, version_id))
        conn.commit()
        conn.close()

    def rollback(
        self,
        model_name: str,
        reason: RollbackReason,
        details: str | None = None
    ) -> str | None:
        """Rollback to previous known good version."""
        # Find the most recent archived version (previous production)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT version_id, model_name, version_number, status, created_at, artifacts_path,
                   metrics, parent_version, tags, checksum
            FROM model_versions
            WHERE model_name = ? AND status = ?
            ORDER BY created_at DESC LIMIT 1
        ''', (model_name, ModelStatus.ARCHIVED.value))

        row = cursor.fetchone()
        conn.close()

        if not row:
            logger.error(f"No archived version found for rollback: {model_name}")
            return None

        rollback_version = ModelVersion(
            version_id=row[0],
            model_name=row[1],
            version_number=row[2],
            status=ModelStatus(row[3]),
            created_at=datetime.fromisoformat(row[4]),
            artifacts_path=row[5],
            metrics=json.loads(row[6]),
            parent_version=row[7],
            tags=json.loads(row[8]),
            checksum=row[9]
        )

        # Log rollback
        self._log_rollback(model_name, rollback_version.version_id, reason, details)

        # Promote archived version to production
        self.promote_to_production(rollback_version.version_id)

        logger.warning(f"Rollback completed: {model_name} -> {rollback_version.version_id}")
        return rollback_version.version_id

    def _log_rollback(
        self,
        model_name: str,
        to_version: str,
        reason: RollbackReason,
        details: str | None
    ):
        """Log rollback to history table."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO rollback_history (from_version, to_version, reason, timestamp, details)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            model_name,
            to_version,
            reason.value,
            datetime.now().isoformat(),
            details
        ))
        conn.commit()
        conn.close()

    def compare_versions(
        self,
        version1_id: str,
        version2_id: str
    ) -> dict[str, Any]:
        """Compare two model versions."""
        v1 = self.get_version(version1_id)
        v2 = self.get_version(version2_id)

        if not v1 or not v2:
            return {"error": "One or both versions not found"}

        metrics_comparison = {}
        all_metrics = set(v1.metrics.keys()) | set(v2.metrics.keys())

        for metric in all_metrics:
            v1_val = v1.metrics.get(metric, 0)
            v2_val = v2.metrics.get(metric, 0)
            diff = v2_val - v1_val
            metrics_comparison[metric] = {
                'version1': v1_val,
                'version2': v2_val,
                'difference': diff,
                'improved': diff > 0
            }

        return {
            'version1': version1_id,
            'version2': version2_id,
            'metrics_comparison': metrics_comparison,
            'recommended': version1_id if all(m['improved'] for m in metrics_comparison.values()) else version2_id
        }

    def list_versions(self, model_name: str) -> list[ModelVersion]:
        """List all versions of a model."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT version_id, model_name, version_number, status, created_at, artifacts_path,
                   metrics, parent_version, tags, checksum
            FROM model_versions
            WHERE model_name = ?
            ORDER BY created_at DESC
        ''', (model_name,))

        rows = cursor.fetchall()
        conn.close()

        return [
            ModelVersion(
                version_id=row[0],
                model_name=row[1],
                version_number=row[2],
                status=ModelStatus(row[3]),
                created_at=datetime.fromisoformat(row[4]),
                artifacts_path=row[5],
                metrics=json.loads(row[6]),
                parent_version=row[7],
                tags=json.loads(row[8]),
                checksum=row[9]
            )
            for row in rows
        ]

    def get_rollback_history(self, model_name: str) -> list[dict[str, Any]]:
        """Get rollback history for a model."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT from_version, to_version, reason, timestamp, details
            FROM rollback_history
            WHERE from_version = ? OR to_version = ?
            ORDER BY timestamp DESC
        ''', (model_name, model_name))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                'from_version': row[0],
                'to_version': row[1],
                'reason': row[2],
                'timestamp': row[3],
                'details': row[4]
            }
            for row in rows
        ]


def main():
    """Main entry point for model version management."""
    import argparse

    parser = argparse.ArgumentParser(description="Manage AI model versions")
    parser.add_argument('--model-name', required=True, help='Model name')
    parser.add_argument('--action', choices=['create', 'promote', 'rollback', 'list', 'compare'],
                       default='list', help='Action to perform')
    parser.add_argument('--version', help='Version number or ID')
    parser.add_argument('--artifacts-path', help='Path to model artifacts')
    parser.add_argument('--reason', choices=['performance_degradation', 'accuracy_drop',
                                           'bias_detected', 'security_vulnerability', 'data_drift'],
                       help='Rollback reason')

    args = parser.parse_args()

    manager = ModelVersionManager()

    if args.action == 'create':
        if not args.version or not args.artifacts_path:
            print("Error: --version and --artifacts-path required for create")
            return

        version = manager.create_version(
            model_name=args.model_name,
            version_number=args.version,
            artifacts_path=args.artifacts_path,
            metrics={'accuracy': 0.92, 'latency_ms': 45}
        )
        print(f"Created version: {version.version_id}")

    elif args.action == 'promote':
        if not args.version:
            print("Error: --version required for promote")
            return

        success = manager.promote_to_production(args.version)
        print(f"Promote {'successful' if success else 'failed'}")

    elif args.action == 'rollback':
        if not args.reason:
            print("Error: --reason required for rollback")
            return

        result = manager.rollback(args.model_name, RollbackReason(args.reason))
        print(f"Rollback result: {result or 'No version to rollback to'}")

    elif args.action == 'list':
        versions = manager.list_versions(args.model_name)
        print(f"\nVersions for {args.model_name}:")
        for v in versions:
            print(f"  {v.version_id} [{v.status.value}] - v{v.version_number}")

    elif args.action == 'compare':
        # Example comparison
        current = manager.get_current_production_version(args.model_name)
        if current:
            print(f"Current production: {current.version_id}")
            print(f"Metrics: {current.metrics}")


if __name__ == "__main__":
    main()
