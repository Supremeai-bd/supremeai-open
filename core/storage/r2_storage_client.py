import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from core.logging_config import logger


class StorageNotConfiguredError(RuntimeError):
    """Raised when object storage is used without credentials (fail-closed).

    বাংলা মন্তব্য: আগে ক্রেডেনশিয়াল না থাকলে ভুয়া presigned URL
    (https://mock-r2-*.local/...) রিটার্ন হতো — আপলোড "সফল" দেখিয়ে ডেটা নীরবে
    কোথাও যেত না (audit B-01, 2026-09-17)। এখন সৎ ব্যর্থতা: caller 503 পাবে।
    """


class R2StorageClient:
    def __init__(self):
        # বাংলা মন্তব্য: ক্লাউডফ্লেয়ার R2 এর ক্রেডেনশিয়াল এনভায়রনমেন্ট থেকে পড়া হচ্ছে।
        self.account_id = os.getenv("R2_ACCOUNT_ID")
        self.access_key = os.getenv("R2_ACCESS_KEY")
        self.secret_key = os.getenv("R2_SECRET_KEY")
        self.bucket_name = os.getenv("R2_BUCKET_NAME", "supremeai-assets")

        # বাংলা মন্তব্য: ক্রেডেনশিয়াল মিসিং থাকলে আর dry-run মক মোড নেই — প্রথম
        # ব্যবহারে StorageNotConfiguredError (fail-closed, audit B-01)।
        self.dry_run = not (self.account_id and self.access_key and self.secret_key)

        if self.dry_run:
            logger.warning(
                "Cloudflare R2 credentials missing — R2StorageClient is UNCONFIGURED; "
                "storage operations will fail with StorageNotConfiguredError instead of "
                "returning fake URLs."
            )
            self.s3_client = None
        else:
            # Cloudflare R2 Endpoint
            endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name="auto",  # R2 uses 'auto'
                config=Config(signature_version="s3v4"),
            )

    def _ensure_configured(self) -> None:
        if self.dry_run or self.s3_client is None:
            raise StorageNotConfiguredError(
                "Cloudflare R2 is not configured — set R2_ACCOUNT_ID, R2_ACCESS_KEY and "
                "R2_SECRET_KEY. Refusing to fabricate presigned URLs (audit B-01 fix)."
            )

    def generate_presigned_upload_url(self, object_name: str, file_type: str, expiration=3600):
        self._ensure_configured()

        try:
            response = self.s3_client.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": object_name,
                    "ContentType": file_type,
                },
                ExpiresIn=expiration,
            )
            return response
        except ClientError as e:
            logger.error(f"Error generating presigned URL: {e}")
            return None

    def generate_presigned_download_url(self, object_name: str, expiration=3600):
        self._ensure_configured()

        try:
            response = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": object_name},
                ExpiresIn=expiration,
            )
            return response
        except ClientError as e:
            logger.error(f"Error generating download URL: {e}")
            return None
