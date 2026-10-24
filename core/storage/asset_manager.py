import os

from firebase_admin import storage as firebase_storage

from core.config import settings
from core.logging_config import logger


class AssetManager:
    """
    Manages large assets (models, docs, datasets) via object storage.
    Uses Firebase as primary, Supabase as backup.
    """

    def __init__(self, bucket: str = "supremeai-assets"):
        self.bucket = bucket
        self._supabase_client = None
        self._firebase_bucket = None

        # Initialize Firebase
        try:
            # Assumes firebase_admin.initialize_app() is called in app.py
            firebase_bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET")
            if firebase_bucket_name:
                self._firebase_bucket = firebase_storage.bucket(firebase_bucket_name)
        except Exception as exc:
            logger.warning(f"Firebase storage unavailable: {exc}")

    def _get_supabase(self):
        if self._supabase_client is None:
            try:
                from supabase import create_client

                url = settings.supabase_url
                key = os.getenv("SUPABASE_KEY")
                if url and key:
                    self._supabase_client = create_client(url, key)
            except Exception as exc:
                logger.warning(f"Supabase client unavailable: {exc}")
        return self._supabase_client

    def get_asset_url(self, path: str, expires_in: int = 3600) -> str | None:
        # Try Firebase first
        if self._firebase_bucket:
            try:
                blob = self._firebase_bucket.blob(path)
                # Generate signed URL
                return blob.generate_signed_url(version="v4", expiration=expires_in)
            except Exception as exc:
                logger.error(f"Failed to generate Firebase URL: {exc}")

        # Fallback to Supabase
        supabase = self._get_supabase()
        if supabase:
            try:
                res = supabase.storage.from_(self.bucket).get_public_url(path)
                return res
            except Exception as exc:
                logger.error(f"Failed to get Supabase public URL: {exc}")
        return None

    def upload_asset(
        self,
        local_path: str,
        remote_path: str,
        content_type: str = "application/octet-stream",
    ) -> bool:
        success = False

        # Primary: Firebase
        if self._firebase_bucket:
            try:
                blob = self._firebase_bucket.blob(remote_path)
                blob.upload_from_filename(local_path, content_type=content_type)
                logger.info(f"Uploaded to Firebase: {remote_path}")
                success = True
            except Exception as exc:
                logger.error(f"Firebase upload failed: {exc}")

        # Backup: Supabase
        supabase = self._get_supabase()
        if supabase:
            try:
                with open(local_path, "rb") as f:
                    supabase.storage.from_(self.bucket).upload(
                        remote_path, f, {"content-type": content_type}
                    )
                logger.info(f"Uploaded to Supabase: {remote_path}")
                success = True
            except Exception as exc:
                # If Supabase fails but Firebase succeeded, we still consider it a success
                logger.error(f"Supabase upload failed: {exc}")

        return success

    def download_asset(self, remote_path: str, local_path: str) -> bool:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        # Try Firebase first
        if self._firebase_bucket:
            try:
                blob = self._firebase_bucket.blob(remote_path)
                if blob.exists():
                    blob.download_to_filename(local_path)
                    return True
            except Exception as exc:
                logger.error(f"Firebase download failed: {exc}")

        # Fallback to Supabase
        supabase = self._get_supabase()
        if supabase:
            try:
                data = supabase.storage.from_(self.bucket).download(remote_path)
                with open(local_path, "wb") as f:
                    f.write(data)
                return True
            except Exception as exc:
                logger.error(f"Supabase download failed: {exc}")

        return False

    def delete_asset(self, remote_path: str) -> bool:
        success = False

        # Delete from Firebase
        if self._firebase_bucket:
            try:
                blob = self._firebase_bucket.blob(remote_path)
                if blob.exists():
                    blob.delete()
                    success = True
            except Exception as exc:
                logger.error(f"Firebase delete failed: {exc}")

        # Delete from Supabase
        supabase = self._get_supabase()
        if supabase:
            try:
                supabase.storage.from_(self.bucket).remove([remote_path])
                success = True
            except Exception as exc:
                logger.error(f"Supabase delete failed: {exc}")

        return success
