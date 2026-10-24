"""This module provides a robust, asynchronous cloud object storage manager for the SupremeAI project, primarily leveraging Supabase Storage. It enables direct uploading of assets to a designated cloud bucket, bypassing local file system operations, which is essential for maintaining data persistence and integrity in serverless or distributed environments. It ensures that all AI-generated or processed assets are securely and reliably stored in the cloud.

Key Components:
- `CloudStorageManager`: Manages asynchronous interactions with the configured cloud object storage (e.g., Supabase), handling file uploads and public URL generation.
- `cloud_storage`: A global singleton instance of `CloudStorageManager` for convenient access throughout the application.

Dependencies:
- `httpx`: For performing asynchronous HTTP requests to the cloud storage API.
- `fastapi`: For raising standardized HTTP exceptions and status codes in case of storage failures.
- `core.config`: To retrieve application-wide settings, including cloud storage credentials.
- `core.logging_config`: For structured logging of storage operations, successes, and errors."""

# বাংলা কমেন্ট: সুপ্রিম-এআই এর ক্লাউড অবজেক্ট স্টোরেজ ম্যানেজার।
# সার্ভারলেস এনভায়রনমেন্টে ডেটা লস রুখতে এটি লোকাল ফাইল রাইটের বদলে সরাসরি ক্লাউড বাকেটে ফাইল আপলোড ও রিড করে।

import httpx
from fastapi import HTTPException, status

from core.config import settings
from core.logging_config import logger
from utils.http_client import DEFAULT_TIMEOUT, create_async_client


class CloudStorageManager:
    def __init__(self):
        # বাংলা কমেন্ট: Supabase বা ক্লাউড স্টোরেজের ক্রেডেনশিয়াল লোড করা হচ্ছে।
        self.supabase_url = getattr(settings, "supabase_url", None)
        self.supabase_key = getattr(settings, "supabase_key", None)
        self.bucket_name = "supremeai-assets"

    async def upload_file_async(
        self,
        file_path_in_bucket: str,
        file_bytes: bytes,
        content_type: str = "application/json",
    ) -> str:
        """
        লোকাল এফএস বাইপাস করে সরাসরি ক্লাউড স্টোরেজে অবজেক্ট পুশ করে এবং পাবলিক ইউআরএল রিটার্ন করে।
        """
        if not self.supabase_url or not self.supabase_key:
            logger.critical("🔥 Storage Failure: Cloud Storage credentials missing!")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Cloud storage infrastructure is unconfigured.",
            )

        # সুপাবেস স্টোরেজ এপিআই এন্ডপয়েন্ট ইউআরএল বিল্ড
        url = f"{self.supabase_url}/storage/v1/object/{self.bucket_name}/{file_path_in_bucket}"
        headers = {
            "Authorization": f"Bearer {self.supabase_key}",
            "API-Key": self.supabase_key,
            "Content-Type": content_type,
        }

        try:
            # বাংলা কমেন্ট: শেয়ার্ড ক্লায়েন্ট পুল ব্যবহার করে রিকোয়েস্ট পাঠানো হচ্ছে।
            async with create_async_client(timeout=10.0) as client:
                response = await client.post(url, content=file_bytes, headers=headers)

            if response.status_code != 200:
                logger.error(f"❌ Cloud Upload Rejected: {response.text}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cloud storage engine rejected the asset package.",
                )

            public_url = f"{self.supabase_url}/storage/v1/object/public/{self.bucket_name}/{file_path_in_bucket}"
            logger.success(f"✅ Asset securely synced to cloud storage -> {public_url}")
            return public_url

        except httpx.HTTPError as http_err:
            logger.critical(f"🔥 Network Failure during cloud file streaming: {http_err!s}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Storage cluster network timeout.",
            ) from http_err


# গ্লোবাল সিঙ্গেলটন ইনস্ট্যান্স জেনারেশন
cloud_storage = CloudStorageManager()
