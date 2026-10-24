from datetime import datetime
from typing import BinaryIO

import httpx

from core.config import settings
from core.logging_config import logger
from core.storage.interfaces import StorageProvider
from core.storage.models import StorageFile, StorageResult


class AppwriteStorageAdapter:
    """An Appwrite implementation of StorageProvider."""

    def __init__(self):
        self.endpoint = settings.appwrite_endpoint
        self.project_id = settings.appwrite_project_id

        # Load API key securely from settings
        # The actual property might be Appwrite_api_key or appwrite_api_key
        # depending on config_secrets.py, let's use getattr to be safe.
        self.api_key = None
        if hasattr(settings, "appwrite_api_key"):
            key_val = settings.appwrite_api_key
            if hasattr(key_val, "get_secret_value"):
                self.api_key = key_val.get_secret_value()
            else:
                self.api_key = key_val

        if not self.endpoint or not self.project_id or not self.api_key:
            logger.error("AppwriteStorageAdapter initialized but missing credentials.")

        self.headers = {
            "X-Appwrite-Project": self.project_id,
            "X-Appwrite-Key": self.api_key or "",
        }

    async def put(
        self, bucket: str, key: str, file: BinaryIO, content_type: str = "application/octet-stream"
    ) -> StorageResult:
        """Upload a file to Appwrite storage."""
        if not self.endpoint or not self.api_key:
            return StorageResult(
                success=False, bucket=bucket, key=key, error="Appwrite credentials not configured"
            )

        url = f"{self.endpoint}/storage/buckets/{bucket}/files"

        try:
            # We must use file parameter as required by Appwrite API
            # Since key is a path, Appwrite expects a unique ID (max 36 chars) or 'unique()'
            # Here we can pass the key as the file ID if it's alphanumeric,
            # otherwise we just generate unique() and store it.
            # For simplicity, we use 'unique()' and rely on Appwrite's generated ID as the new 'key'
            # Alternatively, we could sanitize the key.
            file_id = "unique()"

            content = file.read()
            files = {"file": (key.split("/")[-1], content, content_type)}
            data = {"fileId": file_id}

            async with httpx.AsyncClient(timeout=30.0) as client:  # AUD-5.5: bounded timeout
                response = await client.post(url, headers=self.headers, data=data, files=files)

            if response.status_code in (200, 201):
                resp_data = response.json()
                new_key = resp_data.get("$id", key)
                return StorageResult(
                    success=True,
                    bucket=bucket,
                    key=new_key,  # Return the Appwrite-assigned fileId
                    url=await self.get_url(bucket, new_key),
                    size_bytes=resp_data.get("sizeOriginal", len(content)),
                    content_type=resp_data.get("mimeType", content_type),
                )
            else:
                logger.error(f"Appwrite storage put error: {response.text}")
                return StorageResult(success=False, bucket=bucket, key=key, error=response.text)

        except Exception as e:
            logger.error(f"Appwrite storage put exception: {e}")
            return StorageResult(success=False, bucket=bucket, key=key, error=str(e))

    async def get(self, bucket: str, key: str) -> StorageFile | None:
        """Retrieve a file from Appwrite storage (downloads content to memory)."""
        if not self.endpoint or not self.api_key:
            return None

        url = f"{self.endpoint}/storage/buckets/{bucket}/files/{key}/download"
        info_url = f"{self.endpoint}/storage/buckets/{bucket}/files/{key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:  # AUD-5.5: bounded timeout
                # Need metadata to construct StorageFile properly
                info_resp = await client.get(info_url, headers=self.headers)
                if info_resp.status_code != 200:
                    return None

                file_info = info_resp.json()

                # Now download content
                download_resp = await client.get(url, headers=self.headers)
                if download_resp.status_code != 200:
                    return None

                import io

                content_io = io.BytesIO(download_resp.content)

                return StorageFile(
                    bucket=bucket,
                    key=key,
                    content=content_io,
                    content_type=file_info.get("mimeType", "application/octet-stream"),
                    size_bytes=file_info.get("sizeOriginal", len(download_resp.content)),
                    last_modified=datetime.fromisoformat(
                        file_info.get("$updatedAt").replace("Z", "+00:00")
                    )
                    if file_info.get("$updatedAt")
                    else None,
                )

        except Exception as e:
            logger.error(f"Appwrite storage get exception: {e}")
            return None

    async def delete(self, bucket: str, key: str) -> bool:
        """Delete a file from Appwrite storage."""
        if not self.endpoint or not self.api_key:
            return False

        url = f"{self.endpoint}/storage/buckets/{bucket}/files/{key}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:  # AUD-5.5: bounded timeout
                response = await client.delete(url, headers=self.headers)
                return response.status_code == 204
        except Exception as e:
            logger.error(f"Appwrite storage delete exception: {e}")
            return False

    async def get_url(self, bucket: str, key: str) -> str:
        """Get a view/download URL for the file."""
        if not self.endpoint:
            return ""

        # Standard Appwrite view URL format
        return (
            f"{self.endpoint}/storage/buckets/{bucket}/files/{key}/view?project={self.project_id}"
        )
