#!/usr/bin/env python3
"""
Feature Store Sync
Synchronizes features between different stores and data sources.
Priority: 🟢 Low
"""

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent / "backend"))
from core.config import settings
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SyncStatus(Enum):
    """Synchronization status."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Feature:
    """Feature definition."""
    feature_id: str
    name: str
    description: str
    data_type: str
    source: str
    version: str
    last_updated: datetime
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncResult:
    """Result of feature synchronization."""
    source: str
    destination: str
    feature_id: str
    status: SyncStatus
    timestamp: datetime
    record_count: int
    size_bytes: int
    error_message: str | None = None


class FeatureStoreSync:
    """
    Synchronizes features between different stores and data sources.
    """

    def __init__(
        self,
        source_config: dict[str, Any] | None = None,
        destination_config: dict[str, Any] | None = None
    ):
        self.source_config = source_config or {}
        self.destination_config = destination_config or {}
        self.sync_history: list[SyncResult] = []

    def _compute_checksum(self, data: Any) -> str:
        """Compute checksum for data integrity."""
        data_str = json.dumps(data, sort_keys=True, default=str)
        return hashlib.md5(data_str.encode()).hexdigest()

    def _get_feature_schema(self, feature: Feature) -> dict[str, Any]:
        """Extract feature schema for validation."""
        return {
            'name': feature.name,
            'data_type': feature.data_type,
            'source': feature.source,
            'version': feature.version,
            'fields': feature.metadata.get('fields', [])
        }

    async def fetch_from_source(
        self,
        query: str | None = None,
        feature_ids: list[str] | None = None
    ) -> list[Feature]:
        """Fetch features from source store."""
        features = []

        # Simulate fetching from different source types
        if self.source_config.get('type') == 'redis':
            features = await self._fetch_from_redis(query, feature_ids)
        elif self.source_config.get('type') == 'bigquery':
            features = await self._fetch_from_bigquery(query, feature_ids)
        elif self.source_config.get('type') == 's3':
            features = await self._fetch_from_s3(query, feature_ids)
        else:
            # Default: simulate local store
            features = await self._fetch_from_local(feature_ids)

        logger.info(f"Fetched {len(features)} features from source")
        return features

    async def _fetch_from_redis(
        self,
        query: str | None = None,
        feature_ids: list[str] | None = None
    ) -> list[Feature]:
        """Fetch features from Redis."""
        try:
            import redis.asyncio as redis
            client = redis.Redis(
                host=self.source_config.get('host', 'localhost'),
                port=self.source_config.get('port', 6379),
                db=self.source_config.get('db', 0)
            )
            # Implementation would connect and fetch features
            features = []
            for fid in feature_ids or []:
                data = await client.hgetall(f"feature:{fid}")
                if data:
                    features.append(Feature(
                        feature_id=fid,
                        name=data.get(b'name', fid.encode()).decode(),
                        description=data.get(b'description', b'').decode(),
                        data_type=data.get(b'data_type', b'unknown').decode(),
                        source='redis',
                        version=data.get(b'version', b'1.0').decode(),
                        last_updated=datetime.now(),
                        checksum=data.get(b'checksum', b'').decode()
                    ))
            return features
        except ImportError:
            logger.warning("Redis not available, using simulated data")
            return []

    async def _fetch_from_bigquery(
        self,
        query: str | None = None,
        feature_ids: list[str] | None = None
    ) -> list[Feature]:
        """Fetch features from BigQuery."""
        # Implementation would use google-cloud-bigquery
        logger.warning("BigQuery fetch requires google-cloud-bigquery package")
        return []

    async def _fetch_from_s3(
        self,
        query: str | None = None,
        feature_ids: list[str] | None = None
    ) -> list[Feature]:
        """Fetch features from S3."""
        # Implementation would use boto3
        logger.warning("S3 fetch requires boto3 package")
        return []

    async def _fetch_from_local(
        self,
        feature_ids: list[str] | None = None
    ) -> list[Feature]:
        """Fetch features from local storage (simulation)."""
        # Generate simulated features
        features = []
        for i in range(5):
            fid = f"feature_{i}" if not feature_ids else (feature_ids[i] if i < len(feature_ids) else f"feature_{i}")
            features.append(Feature(
                feature_id=fid,
                name=f"Feature {i}",
                description=f"Simulated feature {i}",
                data_type="float",
                source="local",
                version="1.0",
                last_updated=datetime.now(),
                checksum=self._compute_checksum({"data": list(range(100))})
            ))
        return features

    async def push_to_destination(
        self,
        features: list[Feature],
        destination_type: str | None = None
    ) -> list[SyncResult]:
        """Push features to destination store."""
        results = []
        dest_type = destination_type or self.destination_config.get('type', 'local')

        for feature in features:
            try:
                if dest_type == 'redis':
                    result = await self._push_to_redis(feature)
                elif dest_type == 'bigquery':
                    result = await self._push_to_bigquery(feature)
                elif dest_type == 's3':
                    result = await self._push_to_s3(feature)
                else:
                    result = await self._push_to_local(feature)

                results.append(result)
            except Exception as e:
                results.append(SyncResult(
                    source=feature.source,
                    destination=dest_type,
                    feature_id=feature.feature_id,
                    status=SyncStatus.FAILED,
                    timestamp=datetime.now(),
                    record_count=0,
                    size_bytes=0,
                    error_message=str(e)
                ))

        return results

    async def _push_to_redis(self, feature: Feature) -> SyncResult:
        """Push feature to Redis."""
        try:
            import redis.asyncio as redis
            client = redis.Redis(
                host=self.destination_config.get('host', 'localhost'),
                port=self.destination_config.get('port', 6379),
                db=self.destination_config.get('db', 0)
            )
            await client.hset(f"feature:{feature.feature_id}", mapping={
                'name': feature.name,
                'description': feature.description,
                'data_type': feature.data_type,
                'source': feature.source,
                'version': feature.version,
                'checksum': feature.checksum or ''
            })
            return SyncResult(
                source=feature.source,
                destination='redis',
                feature_id=feature.feature_id,
                status=SyncStatus.COMPLETED,
                timestamp=datetime.now(),
                record_count=1,
                size_bytes=len(str(feature.metadata))
            )
        except Exception as e:
            return SyncResult(
                source=feature.source,
                destination='redis',
                feature_id=feature.feature_id,
                status=SyncStatus.FAILED,
                timestamp=datetime.now(),
                record_count=0,
                size_bytes=0,
                error_message=str(e)
            )

    async def _push_to_bigquery(self, feature: Feature) -> SyncResult:
        """Push feature to BigQuery."""
        logger.warning("BigQuery push requires google-cloud-bigquery package")
        return SyncResult(
            source=feature.source,
            destination='bigquery',
            feature_id=feature.feature_id,
            status=SyncStatus.SKIPPED,
            timestamp=datetime.now(),
            record_count=0,
            size_bytes=0,
            error_message="BigQuery client not configured"
        )

    async def _push_to_s3(self, feature: Feature) -> SyncResult:
        """Push feature to S3."""
        logger.warning("S3 push requires boto3 package")
        return SyncResult(
            source=feature.source,
            destination='s3',
            feature_id=feature.feature_id,
            status=SyncStatus.SKIPPED,
            timestamp=datetime.now(),
            record_count=0,
            size_bytes=0,
            error_message="S3 client not configured"
        )

    async def _push_to_local(self, feature: Feature) -> SyncResult:
        """Push feature to local storage."""
        output_dir = Path(self.destination_config.get('path', 'synced_features'))
        output_dir.mkdir(exist_ok=True)

        feature_path = output_dir / f"{feature.feature_id}.json"
        with open(feature_path, 'w') as f:
            json.dump({
                'feature_id': feature.feature_id,
                'name': feature.name,
                'description': feature.description,
                'data_type': feature.data_type,
                'source': feature.source,
                'version': feature.version,
                'last_updated': feature.last_updated.isoformat(),
                'checksum': feature.checksum
            }, f, indent=2)

        return SyncResult(
            source=feature.source,
            destination='local',
            feature_id=feature.feature_id,
            status=SyncStatus.COMPLETED,
            timestamp=datetime.now(),
            record_count=1,
            size_bytes=feature_path.stat().st_size
        )

    async def run_sync(
        self,
        feature_ids: list[str] | None = None,
        query: str | None = None
    ) -> tuple[list[Feature], list[SyncResult]]:
        """Run full synchronization pipeline."""
        # Fetch features
        features = await self.fetch_from_source(query=query, feature_ids=feature_ids)

        # Push to destination
        results = await self.push_to_destination(features)

        self.sync_history.extend(results)
        return features, results

    def get_sync_summary(self) -> dict[str, Any]:
        """Get summary of sync results."""
        if not self.sync_history:
            return {"status": "no_sync_performed"}

        status_counts = {s.value: 0 for s in SyncStatus}
        for result in self.sync_history:
            status_counts[result.status.value] += 1

        total_bytes = sum(r.size_bytes for r in self.sync_history)

        return {
            'total_features': len(self.sync_history),
            'status_distribution': status_counts,
            'total_bytes_synced': total_bytes,
            'success_rate': status_counts.get('completed', 0) / len(self.sync_history),
            'failed_syncs': status_counts.get('failed', 0),
            'skipped_syncs': status_counts.get('skipped', 0)
        }

    def save_sync_report(self, output_path: str | None = None) -> str:
        """Save synchronization report."""
        output = Path(output_path or 'sync_reports')
        output.mkdir(exist_ok=True)

        report_path = output / f"sync_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': self.get_sync_summary(),
            'details': [
                {
                    'source': r.source,
                    'destination': r.destination,
                    'feature_id': r.feature_id,
                    'status': r.status.value,
                    'record_count': r.record_count,
                    'size_bytes': r.size_bytes,
                    'error_message': r.error_message
                }
                for r in self.sync_history
            ]
        }

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Sync report saved to: {report_path}")
        return str(report_path)


async def sync_feature_stores(
    source_config: dict[str, Any] | None = None,
    destination_config: dict[str, Any] | None = None,
    feature_ids: list[str] | None = None
) -> dict[str, Any]:
    """Convenience function to run feature store synchronization."""
    sync = FeatureStoreSync(source_config, destination_config)
    _features, _results = await sync.run_sync(feature_ids)
    sync.save_sync_report()
    return sync.get_sync_summary()


def main():
    """Main entry point for feature store synchronization."""
    import argparse

    parser = argparse.ArgumentParser(description="Synchronize feature stores")
    parser.add_argument('--source-type', choices=['redis', 'bigquery', 's3', 'local'],
                       default='local', help='Source store type')
    parser.add_argument('--dest-type', choices=['redis', 'bigquery', 's3', 'local'],
                       default='local', help='Destination store type')
    parser.add_argument('--features', nargs='*', help='Specific feature IDs to sync')
    parser.add_argument('--output-dir', default='sync_reports', help='Output directory for reports')

    args = parser.parse_args()

    source_config = {'type': args.source_type}
    dest_config = {'type': args.dest_type, 'path': args.output_dir}

    summary = asyncio.run(sync_feature_stores(source_config, dest_config, args.features))

    print("\nFeature Store Sync Summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
