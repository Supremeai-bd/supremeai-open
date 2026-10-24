# Encryption and GCP Service Account Manager
# বাংলা মন্তব্য: GCP ক্রেডেনশিয়াল ম্যানেজমেন্ট ও সেফ-স্টোরেজ এনক্রিপশন ডিক্রিপশন মডিউল।

import base64
import hashlib
import json
import os

from cryptography.fernet import Fernet
from google.oauth2 import service_account

from core.logging_config import logger

# Global encryption key management
# বাংলা মন্তব্য: Fernet এনক্রিপশনের জন্য ৩২ বাইটের কী জেনারেট বা লোড করা হচ্ছে।
# Zero Breakage নীতি: প্রাথমিকভাবে ENCRYPTION_KEY, না থাকলে legacy alias SUPREMEAI_CREDENTIAL_ENC_KEY
# (backend/api/routes/keys.py এর সাথে সামঞ্জস্যপূর্ণ)।
_KEY = os.getenv("ENCRYPTION_KEY") or os.getenv("SUPREMEAI_CREDENTIAL_ENC_KEY")
if not _KEY:
    logger.warning(
        "⚠️ ENCRYPTION_KEY not set in environment. Deriving temporary test/dev key for module initialization."
    )
    _KEY = "DEV_TEST_SUPREMEAI_FALLBACK_ENCRYPTION_KEY_32BYTES="

try:
    cipher = Fernet(_KEY.encode())
except ValueError:
    logger.warning(
        "⚠️ Non-Base64 encryption key detected in current context. Natively deriving valid Fernet key layout."
    )
    hashed = hashlib.sha256(_KEY.encode()).digest()
    safe_b64_key = base64.urlsafe_b64encode(hashed)
    cipher = Fernet(safe_b64_key)


class CloudStatus:
    def __init__(self, connected: bool = False, provider: str = "gcp", region: str | None = None):
        self.connected = connected
        self.provider = provider
        self.region = region


class CloudResource:
    def __init__(self, res_id: str, res_type: str, name: str, status: str):
        self.id = res_id
        self.type = res_type
        self.name = name
        self.status = status


class GCPCredentialManager:
    """
    Encrypts, decrypts, and validates Google Cloud Service Account JSON credentials.
    """

    @staticmethod
    def encrypt_credentials(sa_dict: dict) -> bytes:
        # বাংলা মন্তব্য: সার্ভিস অ্যাকাউন্ট ডিকশনারি এনক্রিপ্ট করে সিকিউরড বাইটসে কনভার্ট করা হচ্ছে
        data_str = json.dumps(sa_dict)
        return cipher.encrypt(data_str.encode())

    @staticmethod
    def decrypt_credentials(encrypted_data: bytes) -> dict:
        # বাংলা মন্তব্য: এনক্রিপ্ট করা বাইটস থেকে পুনরায় ডিক্রিপ্ট করা হচ্ছে
        decrypted_str = cipher.decrypt(encrypted_data).decode()
        return json.loads(decrypted_str)

    @staticmethod
    def validate_service_account(sa_dict: dict) -> bool:
        # বাংলা মন্তব্য: সার্ভিস অ্যাকাউন্ট কী সঠিক কিনা তা পরীক্ষা করা হচ্ছে
        required = {"type", "project_id", "private_key"}
        if not sa_dict or not required.issubset(sa_dict.keys()):
            return False
        try:
            service_account.Credentials.from_service_account_info(sa_dict)
            return True
        except Exception as e:
            logger.error(f"GCP Service Account validation failed: {e}")
            return False


async def ping() -> CloudStatus:
    # Default ping fallback behavior
    return CloudStatus(connected=False, provider="gcp")


async def list_resources() -> list[CloudResource]:
    return []
