"""
Load seed data from cloud storage (GCS/S3) at runtime.
Replaces static seed_data/ in git.
"""

import json
import os
from typing import Any

import boto3
from google.cloud import storage

from core.logging_config import logger


class SeedDataLoader:
    """
    Loads seed data from cloud storage buckets.
    Supports GCS, S3, or local fallback.
    """

    def __init__(self):
        self.provider = os.getenv("SEED_STORAGE_PROVIDER", "local")
        self.bucket = os.getenv("SEED_STORAGE_BUCKET", "supremeai-seed-data")
        self.local_path = "data/seed_data"

    def load_from_gcs(self, blob_name: str) -> dict[str, Any]:
        """Load seed data from Google Cloud Storage."""
        try:
            client = storage.Client()
            bucket = client.bucket(self.bucket)
            blob = bucket.blob(f"seed/{blob_name}.json")
            data = blob.download_as_string()
            return json.loads(data)
        except Exception as e:
            logger.error(f"GCS load failed: {e}")
            return self._local_fallback(blob_name)

    def load_from_s3(self, key: str) -> dict[str, Any]:
        """Load seed data from AWS S3."""
        try:
            s3 = boto3.client("s3")
            response = s3.get_object(Bucket=self.bucket, Key=f"seed/{key}.json")
            return json.loads(response["Body"].read())
        except Exception as e:
            logger.error(f"S3 load failed: {e}")
            return self._local_fallback(key)

    def _local_fallback(self, name: str) -> dict[str, Any]:
        """Fallback to local file."""
        path = f"{self.local_path}/{name}.json"
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
        logger.warning(f"Seed data not found: {name}")
        return {}

    def load_all(self) -> dict[str, Any]:
        """Load all seed data categories."""
        categories = [
            "ai_ml",
            "api_and_performance",
            "databases",
            "design_patterns",
            "devops",
            "errors",
            "frameworks",
            "helpers",
            "languages",
            "practices",
            "security",
            "system_design",
            "testing",
        ]

        result = {}
        for cat in categories:
            if self.provider == "gcs":
                result[cat] = self.load_from_gcs(cat)
            elif self.provider == "s3":
                result[cat] = self.load_from_s3(cat)
            else:
                result[cat] = self._local_fallback(cat)

        logger.info(f"Loaded {len(result)} seed data categories")
        return result


if __name__ == "__main__":
    loader = SeedDataLoader()
    data = loader.load_all()
    logger.debug(f"Loaded {len(data)} categories")
