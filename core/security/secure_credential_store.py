from __future__ import annotations

import base64
import hashlib
import os
from abc import ABC, abstractmethod

from core.logging_config import logger

try:
    from cryptography.fernet import Fernet, InvalidToken

    CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    CRYPTO_AVAILABLE = False


def generate_key() -> str:
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography package is required for key generation")
    return Fernet.generate_key().decode()


class CredentialEncryptionUnavailableError(RuntimeError):
    """ISSUE-1570: raised when credential encryption is unavailable or fails.

    Fail-Closed policy — callers must NEVER fall back to plaintext persistence;
    abort the operation instead so no secret ever lands on disk unencrypted.
    """

    pass


def _resolve_fail_closed(fail_closed: bool | None) -> bool:
    """Resolve the fail-closed toggle (default TRUE per issue #1570).

    Opt-out (legacy fail-open behaviour) requires an explicit
    ``BROWSER_CREDENTIALS_FAIL_CLOSED=false`` / ``0`` environment variable.
    """
    if fail_closed is not None:
        return bool(fail_closed)
    return os.getenv("BROWSER_CREDENTIALS_FAIL_CLOSED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
    }


class RotatingFernet:
    """
    বাংলা মন্তব্য: P0 Fix — Fernet key rotation with multiple-key decryption support.

    Encrypts always with the primary (latest) key.
    Decrypts by trying the primary key first; if that fails with InvalidToken
    it falls back to each previously known key in insertion order.

    All tokens are generated with a 24-hour TTL (86400 seconds).
    Expired tokens raise InvalidToken at decrypt time.
    """

    def __init__(self, keys: list[str]) -> None:
        if not keys:
            raise ValueError("At least one key is required")
        self._fernets = []
        for k in keys:
            raw_key = k.encode() if isinstance(k, str) else k
            try:
                self._fernets.append(Fernet(raw_key))
            except ValueError:
                logger.warning(
                    "⚠️ Non-Base64 encryption key detected in current context. Natively deriving valid Fernet key layout."
                )
                hashed = hashlib.sha256(raw_key).digest()
                safe_b64_key = base64.urlsafe_b64encode(hashed)
                self._fernets.append(Fernet(safe_b64_key))

    @property
    def primary(self) -> Fernet:
        return self._fernets[0]

    def encrypt(self, data: bytes) -> bytes:
        return self.primary.encrypt(data)

    def encrypt_at_time(self, data: bytes, current_time: int) -> bytes:
        return self.primary.encrypt_at_time(data, current_time)

    def decrypt(self, token: bytes, ttl: int | None = 86400) -> bytes:
        for fernet in self._fernets:
            try:
                return fernet.decrypt(token, ttl=ttl)
            except InvalidToken:
                continue
        raise InvalidToken("No valid key could decrypt token")

    def decrypt_at_time(self, token: bytes, ttl: int, current_time: int) -> bytes:
        last_exc: Exception | None = None
        for fernet in self._fernets:
            try:
                return fernet.decrypt_at_time(token, ttl, current_time)
            except InvalidToken as e:
                last_exc = e
                continue
        raise last_exc or InvalidToken("No valid key could decrypt token")


class EncryptionProvider(ABC):
    @abstractmethod
    def encrypt(self, plaintext: str) -> tuple[str, str | None]:
        """Returns (ciphertext, key_ref)"""
        pass

    @abstractmethod
    def decrypt(self, ciphertext: str, key_ref: str | None) -> str:
        """Returns plaintext"""
        pass


class LocalFernetProvider(EncryptionProvider):
    def __init__(self, encryption_key: str | None = None, fail_closed: bool | None = None) -> None:
        self.enabled = False
        self.rotating_fernet: RotatingFernet | None = None
        # ISSUE-1570: default fail-closed — encryption unavailable হলে plaintext
        # fallback নিষিদ্ধ; পুরোনো fail-open আচরণ পেতে env flag দিয়ে opt-out।
        self.fail_closed = _resolve_fail_closed(fail_closed)
        if CRYPTO_AVAILABLE:
            raw_key = (
                encryption_key
                or os.getenv("BROWSER_CREDENTIALS_ENCRYPTION_KEY", "")
                or os.getenv("SUPREMEAI_CREDENTIAL_ENC_KEY", "")
                or os.getenv("ENCRYPTION_KEY", "")
            )
            if raw_key:
                try:
                    # Split by comma to support multiple keys (for rotation)
                    keys = [k.strip() for k in raw_key.split(",") if k.strip()]
                    self.rotating_fernet = RotatingFernet(keys)
                    self.enabled = True
                except Exception as exc:
                    logger.error(f"Failed to initialize Fernet: {exc}")

    def _guard(self, action: str) -> None:
        if self.fail_closed and (not self.enabled or not self.rotating_fernet):
            raise CredentialEncryptionUnavailableError(
                f"Credential encryption is unavailable ({action}) — failing closed; "
                "plaintext fallback is forbidden (issue #1570)."
            )

    def encrypt(self, plaintext: str) -> tuple[str, str | None]:
        self._guard("encrypt")
        if not self.enabled or not self.rotating_fernet:
            # fail-open legacy mode (explicit opt-out only)
            return plaintext, None
        try:
            token = self.rotating_fernet.encrypt(plaintext.encode())
            ciphertext = base64.urlsafe_b64encode(token).decode()
            return ciphertext, None
        except Exception as exc:
            if self.fail_closed:
                raise CredentialEncryptionUnavailableError(
                    f"Fernet encryption failed: {exc} — refusing plaintext fallback."
                ) from exc
            logger.error(f"Encryption failed: {exc}")
            return plaintext, None

    def decrypt(self, ciphertext: str, key_ref: str | None = None, ttl: int | None = None) -> str:
        self._guard("decrypt")
        if not self.enabled or not self.rotating_fernet:
            # fail-open legacy mode (explicit opt-out only)
            return ciphertext
        try:
            token = base64.urlsafe_b64decode(ciphertext.encode())
            plaintext = self.rotating_fernet.decrypt(token, ttl=ttl)
            return plaintext.decode()
        except InvalidToken:
            if self.fail_closed:
                raise CredentialEncryptionUnavailableError(
                    "Token expired or invalid — decryption failed (fail-closed)."
                )
            logger.warning("Token expired or invalid — decryption failed")
            return ciphertext
        except Exception as exc:
            if self.fail_closed:
                raise CredentialEncryptionUnavailableError(
                    f"Decryption failed: {exc} — refusing to return ciphertext as plaintext."
                ) from exc
            logger.error(f"Decryption failed: {exc}")
            return ciphertext


class CloudKMSProvider(EncryptionProvider):
    def __init__(self, fail_closed: bool | None = None) -> None:
        self.kms_client = None
        self.key_name = os.getenv("KMS_KEY_NAME", "")
        # ISSUE-1570: KMS-unavailable অবস্থাতেও plaintext fallback নিষিদ্ধ।
        self.fail_closed = _resolve_fail_closed(fail_closed)
        self._init_kms()

    def _guard(self, action: str) -> None:
        if self.fail_closed and (not self.kms_client or not self.key_name):
            raise CredentialEncryptionUnavailableError(
                f"Cloud KMS is unavailable ({action}) — failing closed; "
                "plaintext fallback is forbidden (issue #1570)."
            )

    def _init_kms(self) -> None:
        if not self.key_name:
            return
        try:
            from google.cloud import kms

            self.kms_client = kms.KeyManagementServiceClient()
            logger.info("Cloud KMS initialized successfully.")
        except ImportError:
            logger.warning("google-cloud-kms not installed; Cloud KMS unavailable.")
        except Exception as exc:
            logger.error(f"Failed to initialize Cloud KMS: {exc}")

    def encrypt(self, plaintext: str) -> tuple[str, str | None]:
        self._guard("encrypt")
        if not self.kms_client or not self.key_name:
            logger.warning("KMS not configured; returning plaintext.")
            return plaintext, None
        try:
            response = self.kms_client.encrypt(
                request={"name": self.key_name, "plaintext": plaintext.encode()}
            )
            ciphertext = base64.b64encode(response.ciphertext).decode()
            return ciphertext, self.key_name
        except Exception as exc:
            if self.fail_closed:
                raise CredentialEncryptionUnavailableError(
                    f"KMS encrypt failed: {exc} — refusing plaintext fallback."
                ) from exc
            logger.error(f"KMS encrypt failed: {exc}")
            return plaintext, None

    def decrypt(self, ciphertext: str, key_ref: str | None) -> str:
        self._guard("decrypt")
        if not self.kms_client or not (key_ref or self.key_name):
            logger.warning("KMS not configured or missing key_ref; returning ciphertext as-is.")
            return ciphertext
        try:
            response = self.kms_client.decrypt(
                request={
                    "name": key_ref or self.key_name,
                    "ciphertext": base64.b64decode(ciphertext.encode()),
                }
            )
            return response.plaintext.decode()
        except Exception as exc:
            if self.fail_closed:
                raise CredentialEncryptionUnavailableError(
                    f"KMS decrypt failed: {exc} — failing closed."
                ) from exc
            logger.error(f"KMS decrypt failed: {exc}")
            return ciphertext


class SecureCredentialStore:
    def __init__(
        self,
        provider: EncryptionProvider | None = None,
        fail_closed: bool | None = None,
    ) -> None:
        self.fail_closed = _resolve_fail_closed(fail_closed)
        self.provider: EncryptionProvider = provider or (
            CloudKMSProvider(fail_closed=self.fail_closed)
            if os.getenv("KMS_KEY_NAME")
            else LocalFernetProvider(fail_closed=self.fail_closed)
        )

    @property
    def encryption_available(self) -> bool:
        """ISSUE-1570: browser context setup gates on this before persisting secrets."""
        provider = self.provider
        if isinstance(provider, LocalFernetProvider):
            return provider.enabled and provider.rotating_fernet is not None
        if isinstance(provider, CloudKMSProvider):
            return provider.kms_client is not None and bool(provider.key_name)
        return bool(getattr(provider, "enabled", True))

    def encrypt(self, plaintext: str) -> tuple[str, str | None]:
        return self.provider.encrypt(plaintext)

    def decrypt(self, ciphertext: str, key_ref: str | None = None, ttl: int | None = None) -> str:
        if isinstance(self.provider, LocalFernetProvider):
            return self.provider.decrypt(ciphertext, key_ref, ttl=ttl)
        return self.provider.decrypt(ciphertext, key_ref)

    @staticmethod
    def mask(value: str, visible_chars: int = 4) -> str:
        if len(value) <= visible_chars:
            return "****"
        return value[:visible_chars] + "*" * (len(value) - visible_chars)


# ══════════════════════════════════════════════════════════════════════════
# Security Vault (folded from core/security/security_vault.py — Wave 3.9,
# issue #1265): Fernet token encryption with fail-fast key validation.
#
# বাংলা: সিকিউরিটি ভল্ট — STRICT_ENCRYPTION_CHECK=true মোডে encryption key
# শুধুই raw environment থেকে নেয়া হবে। core.security.security_vault এখন এই
# মডিউলের re-export shim — ৩ importer (agent_action, integrations,
# github_agent) অক্ষত কাজ করবে।
# ══════════════════════════════════════════════════════════════════════════

import os as _os
import sys as _sys

from cryptography.fernet import Fernet as _Fernet

from core.config import settings as _settings
from core.errors.error_bus import with_error_bus
from core.logging_config import logger
from core.messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

# Fail-fast policy:
# STRICT_ENCRYPTION_CHECK=true হলে encryption key শুধুই raw environment থেকে নেয়া হবে।
# (settings singleton/test computed secret এ stale value থাকতে পারে)
strict_enabled = _os.environ.get("STRICT_ENCRYPTION_CHECK") == "true"

if strict_enabled:
    # Zero Breakage নীতি: ENCRYPTION_KEY প্রাথমিক, SUPREMEAI_CREDENTIAL_ENC_KEY legacy alias
    # (backend/api/routes/keys.py:22 এর canonical প্যাটার্নের সামঞ্জস্যপূর্ণ)।
    ENCRYPTION_KEY = _os.environ.get("ENCRYPTION_KEY") or _os.environ.get(
        "SUPREMEAI_CREDENTIAL_ENC_KEY"
    )
    if not ENCRYPTION_KEY:
        error_event_bus.emit(
            ErrorEvent(
                module="security_vault",
                error_type="MISSING_ENCRYPTION_KEY",
                message="ENCRYPTION_KEY environment variable is missing",
                severity="CRITICAL",
                structured_context=ErrorContext(module="auto_fixed"),
            )
        )
        raise ValueError(
            "CRITICAL: ENCRYPTION_KEY environment variable is not set. Halting application for security reasons. Fail-Fast!"
        )
else:
    # Normal mode: settings.encryption_key থেকে আসে (computed field via secret_vault)
    ENCRYPTION_KEY = (
        _settings.encryption_key.get_secret_value()
        if _settings.encryption_key
        else _os.environ.get("ENCRYPTION_KEY")
    )

    if not ENCRYPTION_KEY:
        # বাংলা মন্তব্য: টেস্ট ও সিআই পরিবেশে ক্র্যাশ এড়াতে একটি ডামি/এফেমেরাল কী জেনারেট করা হচ্ছে।
        if (
            _os.environ.get("ENV") in {"test", "testing", "ci"}
            or _os.environ.get("CI") == "true"
            or _os.environ.get("GITHUB_ACTIONS") == "true"
            or "pytest" in _sys.modules
        ):
            ENCRYPTION_KEY = _Fernet.generate_key().decode("utf-8")
        else:
            error_event_bus.emit(
                ErrorEvent(
                    module="security_vault",
                    error_type="MISSING_ENCRYPTION_KEY",
                    message="ENCRYPTION_KEY environment variable is missing",
                    severity="CRITICAL",
                    structured_context=ErrorContext(module="auto_fixed"),
                )
            )
            raise ValueError(
                "CRITICAL: ENCRYPTION_KEY environment variable is not set. Halting application for security reasons. Fail-Fast!"
            )


# Encryption key rotation support.
_raw_keys = [
    k
    for k in _os.environ.get(
        "ENCRYPTION_KEYS",
        _os.environ.get("SUPREMEAI_CREDENTIAL_ENC_KEY", ENCRYPTION_KEY or ""),
    ).split(",")
    if k.strip()
]

if not _raw_keys:
    raise ValueError("CRITICAL: No encryption keys configured (ENCRYPTION_KEYS). Fail-Fast!")

_vault = RotatingFernet(_raw_keys)


@with_error_bus("encrypt_token")
def encrypt_token(plain_text: str) -> str:
    """Encrypts a token using Fernet via central RotatingFernet."""

    if not plain_text:
        return ""

    try:
        return _vault.encrypt(plain_text.encode("utf-8")).decode("utf-8")
    except Exception as e:
        logger.error(f"Error encrypting token: {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="security_vault",
                error_type="ENCRYPTION_FAILED",
                message=str(e)[:200],
                severity="ERROR",
                structured_context=ErrorContext(module="auto_fixed"),
            )
        )
        raise RuntimeError("Token encryption failed.") from e


@with_error_bus("decrypt_token")
def decrypt_token(cipher_text: str, ttl: int | None = None) -> str:
    """Decrypts a token using Fernet via central RotatingFernet."""

    if not cipher_text:
        return ""

    # ttl=None keeps the RotatingFernet default behavior.
    try:
        return _vault.decrypt(cipher_text.encode("utf-8"), ttl=ttl).decode("utf-8")
    except Exception as e:
        logger.error(f"Error decrypting token: {e}")
        error_event_bus.emit(
            ErrorEvent(
                module="security_vault",
                error_type="DECRYPTION_FAILED",
                message=str(e)[:200],
                severity="CRITICAL",
                structured_context=ErrorContext(module="auto_fixed"),
            )
        )
        raise ValueError("Decryption failed: Invalid or corrupted token.") from e
