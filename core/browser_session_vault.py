"""Browser Session Vault — encrypted cookie/localStorage persistence (issue #943, MESH-5).

বাংলা সারসংক্ষেপ:
------------------
Bolt.new-জাতীয় ব্রাউজার-সেশনের cookies + localStorage **Fernet-এনক্রিপ্টেড**
ভল্টে জমা/লোড — Cloudflare-পার করা persistent login-এর ভিত্তি।

নাম-নোট: issue-তে `browser_session_manager.py` বলা হয়েছিল, কিন্তু সেই নামে
আগে থেকেই একটি ভিন্ন-উদ্দেশ্যের মডিউল আছে (bounded playwright context manager)।
তাই vault-টি `browser_session_vault.py` — একই চুক্তি, দ্বন্দ্বমুক্ত নাম।

চুক্তি (#943 spec):
- save_session(service, cookies, local_storage)  → vault_path/<service>.json.enc
- load_session(service)                          → (cookies, local_storage)
- is_session_valid(service)                      → last_login ≤ ৭ দিন (heuristic)
- load_state(service)                            → playwright storage_state dict

নিরাপত্তা:
- কী: `BROWSER_VAULT_KEY` (Fernet base64) বা constructor injection — কোনোটাই
  না থাকলে **fail-closed** RuntimeError (প্লেইনটেক্সট ভল্ট কখনো নয়)।
- ফাইল পারমিশন 0600; tamper/corrupt → SessionVaultError (নীরব [] ফেরত নেই)।
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from core.logging_config import logger

# সেশন-বৈধতা heuristic (#943): শেষ লগইন ৭ দিনের বেশি পুরোনো হলে অবৈধ।
DEFAULT_SESSION_TTL_SECONDS = 7 * 24 * 3600


class SessionVaultError(RuntimeError):
    """ভল্ট অপারেশন ব্যর্থ — corrupt, tampered, বা key অনুপস্থিত (fail-closed)।"""


class BrowserSessionVault:
    """এনক্রিপ্টেড সেশন ভল্ট — প্রতি service একটি .json.enc ফাইল।"""

    def __init__(self, vault_path: Path | str, encryption_key: bytes | None = None) -> None:
        self.vault_path = Path(vault_path)
        key = encryption_key or self._key_from_env()
        if not key:
            raise SessionVaultError(
                "BrowserSessionVault requires encryption_key or BROWSER_VAULT_KEY "
                "(Fernet base64) — refusing to build a plaintext vault (fail-closed)"
            )
        try:
            self._fernet = Fernet(key)
        except (ValueError, TypeError) as exc:
            raise SessionVaultError(f"invalid Fernet key: {exc}") from exc
        self.vault_path.mkdir(parents=True, exist_ok=True)
        os.chmod(self.vault_path, 0o700)

    @staticmethod
    def _key_from_env() -> bytes | None:
        raw = os.getenv("BROWSER_VAULT_KEY", "").strip()
        if not raw:
            return None
        # ডেভ-সুবিধা: raw passphrase → deterministic কী (prod এ Fernet key দেবে)।
        try:
            base64.urlsafe_b64decode(raw)
            return raw.encode()
        except Exception:
            digest = base64.urlsafe_b64encode(__import__("hashlib").sha256(raw.encode()).digest())
            return digest

    def _service_file(self, service: str) -> Path:
        if not service or "/" in service or ".." in service or service.startswith("."):
            raise SessionVaultError(f"invalid service name: {service!r}")
        return self.vault_path / f"{service}.json.enc"

    # ── Save ─────────────────────────────────────────────────────────────────
    def save_session(self, service: str, cookies: list, local_storage: dict) -> Path:
        """সেশন + last_login টাইমস্ট্যাম্প এনক্রিপ্ট করে জমা — ফাইল পাথ রিটার্ন।"""
        record = {
            "service": service,
            "cookies": cookies,
            "local_storage": local_storage,
            "last_login": time.time(),
            "saved_at": time.time(),
        }
        blob = self._fernet.encrypt(json.dumps(record, ensure_ascii=False).encode("utf-8"))
        target = self._service_file(service)
        target.write_bytes(blob)
        os.chmod(target, 0o600)
        logger.info(f"[SessionVault] saved session for {service!r} ({len(cookies)} cookies)")
        return target

    # ── Load ─────────────────────────────────────────────────────────────────
    def load_session(self, service: str) -> tuple[list, dict]:
        """ডিক্রিপ্ট → (cookies, local_storage); corrupt/tamper → SessionVaultError।"""
        path = self._service_file(service)
        if not path.exists():
            raise SessionVaultError(f"no saved session for {service!r}")
        try:
            record = json.loads(self._fernet.decrypt(path.read_bytes()).decode("utf-8"))
        except InvalidToken as exc:
            raise SessionVaultError(f"session vault tampered or wrong key for {service!r}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SessionVaultError(f"session vault corrupt for {service!r}: {exc}") from exc
        return record.get("cookies", []), record.get("local_storage", {})

    def load_state(self, service: str) -> dict[str, Any]:
        """playwright `storage_state` আকৃতি: {cookies, origins:[{origin, localStorage}]}।"""
        cookies, local_storage = self.load_session(service)
        origins = [
            {"origin": origin, "localStorage": [{"name": k, "value": v} for k, v in items.items()]}
            for origin, items in (local_storage or {}).items()
            if isinstance(items, dict)
        ]
        return {"cookies": cookies, "origins": origins}

    # ── Validity heuristic (#943) ────────────────────────────────────────────
    def is_session_valid(
        self, service: str, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS
    ) -> bool:
        """last_login ≤ ttl হলে বৈধ; ফাইল/রেকর্ড না পড়া গেলে অবৈধ (ভান নেই)।"""
        path = self._service_file(service)
        if not path.exists():
            return False
        try:
            record = json.loads(self._fernet.decrypt(path.read_bytes()).decode("utf-8"))
        except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError):
            return False
        last_login = record.get("last_login", 0)
        return bool(last_login) and (time.time() - float(last_login)) < ttl_seconds

    def forget(self, service: str) -> bool:
        """সেশন মুছে দাও (logout/rotate) — মুছেছিল কিনা রিটার্ন।"""
        path = self._service_file(service)
        if path.exists():
            path.unlink()
            return True
        return False


def generate_vault_key() -> str:
    """নতুন Fernet কী (base64) — admin একবার জেনারেট করে BROWSER_VAULT_KEY-তে রাখবে।"""
    return Fernet.generate_key().decode()


__all__ = ["BrowserSessionVault", "SessionVaultError", "generate_vault_key"]
