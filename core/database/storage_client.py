import os
from typing import Any

import boto3
from supabase import Client, create_client

from core.config import settings
from core.logging_config import logger


class StorageClient:
    """
    Manages object storage for large assets (Model weights, Docs, Fixtures).
    Uses Supabase Storage or AWS S3 based on configuration.
    """

    def __init__(self, provider: str = "supabase"):
        self.provider = provider
        self.bucket_name = os.getenv("STORAGE_BUCKET", "supremeai-assets")
        self.supabase_client: Client | None = None
        self.s3_client = None

        if self.provider == "supabase":
            url = settings.supabase_url
            key = os.getenv("SUPABASE_KEY")
            if url and key:
                self.supabase_client = create_client(url, key)
                logger.info("Initialized Supabase Storage Client")
        elif self.provider == "s3":
            self.s3_client = boto3.client("s3")
            logger.info("Initialized AWS S3 Client")

    def upload_file(self, local_path: str, remote_path: str) -> dict[str, Any]:
        """Uploads a file to object storage."""
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"File {local_path} not found.")

        logger.info(f"Uploading {local_path} to {self.provider}://{self.bucket_name}/{remote_path}")

        try:
            if self.provider == "supabase" and self.supabase_client:
                with open(local_path, "rb") as f:
                    self.supabase_client.storage.from_(self.bucket_name).upload(remote_path, f)
                return {
                    "status": "success",
                    "provider": "supabase",
                    "path": remote_path,
                }
            elif self.provider == "s3" and self.s3_client:
                self.s3_client.upload_file(local_path, self.bucket_name, remote_path)
                return {"status": "success", "provider": "s3", "path": remote_path}
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return {"status": "error", "error": str(e)}

        return {"status": "error", "error": "Provider not configured properly."}

    def get_public_url(self, remote_path: str) -> str:
        """Returns the public CDN URL for a file."""
        if self.provider == "supabase" and self.supabase_client:
            return self.supabase_client.storage.from_(self.bucket_name).get_public_url(remote_path)
        elif self.provider == "s3":
            # Very basic S3 URL format
            region = os.getenv("AWS_REGION", "us-east-1")
            return f"https://{self.bucket_name}.s3.{region}.amazonaws.com/{remote_path}"

        return f"https://cdn.supremeai.example/{remote_path}"


storage = StorageClient()
