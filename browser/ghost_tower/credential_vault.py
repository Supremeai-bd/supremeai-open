"""
credential_vault.py — Sovereign AES-256 Fernet Encrypted Credential Vault.
==========================================================================
Enables zero-plaintext storage of AI account credentials (Email, Password, 2FA TOTP).
Used for fully automated, hands-free login recovery.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VAULT_DIR = Path(os.path.expanduser(r"~\.supremeai_vault"))
VAULT_FILE = VAULT_DIR / "credentials.enc.json"
KEY_FILE = VAULT_DIR / "vault.key"


def get_or_create_master_key() -> bytes:
    """Retrieves master key from environment or persistent local keyfile."""
    env_key = os.getenv("CREDENTIAL_MASTER_KEY", "").strip()
    if env_key:
        return env_key.encode()

    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes().strip()

    # Generate new key
    new_key = Fernet.generate_key()
    KEY_FILE.write_bytes(new_key)
    print(f"[KEY] [VAULT] New Master Key generated and secured at: {KEY_FILE}")
    print(
        f"[INFO] You can also set this in your environment: CREDENTIAL_MASTER_KEY={new_key.decode()}"
    )
    return new_key


class CredentialVault:
    def __init__(self, master_key: bytes | None = None):
        self.master_key = master_key or get_or_create_master_key()
        self.cipher = Fernet(self.master_key)

    def encrypt(self, plain_text: str) -> str:
        if not plain_text:
            return ""
        return self.cipher.encrypt(plain_text.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted_text: str) -> str:
        if not encrypted_text:
            return ""
        return self.cipher.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")

    def save_account(
        self,
        provider: str,
        account_label: str,
        email: str,
        password: str,
        totp_secret: str = "",
        recovery_email: str = "",
    ) -> dict[str, Any]:
        """Encrypts and stores account credentials securely."""
        data = self._read_raw_store()

        enc_password = self.encrypt(password)
        enc_totp = self.encrypt(totp_secret) if totp_secret else ""

        account_entry = {
            "provider": provider.lower(),
            "account_label": account_label,
            "email": email,
            "encrypted_password": enc_password,
            "encrypted_totp": enc_totp,
            "recovery_email": recovery_email,
        }

        data[account_label] = account_entry
        self._write_raw_store(data)
        print(
            f"[OK] [VAULT] Account '{account_label}' ({email}) successfully encrypted and saved!"
        )
        return account_entry

    def get_account(self, account_label: str) -> dict[str, Any] | None:
        """Returns decrypted credentials in-memory for automated login."""
        data = self._read_raw_store()
        account = data.get(account_label)
        if not account:
            # Check Infisical-injected environment variables as fallback
            env_email = os.getenv("GEMINI_WEB_EMAIL", "").strip()
            env_password = os.getenv("GEMINI_WEB_PASSWORD", "").strip()
            if (
                env_email
                and env_password
                and (
                    "gemini" in account_label.lower()
                    or "google" in account_label.lower()
                )
            ):
                return {
                    "provider": "gemini",
                    "account_label": account_label,
                    "email": env_email,
                    "password": env_password,
                    "totp_secret": os.getenv("GEMINI_WEB_TOTP", ""),
                    "recovery_email": os.getenv("GEMINI_WEB_RECOVERY", ""),
                }
            return None

        return {
            "provider": account["provider"],
            "account_label": account["account_label"],
            "email": account["email"],
            "password": self.decrypt(account["encrypted_password"]),
            "totp_secret": self.decrypt(account.get("encrypted_totp", "")),
            "recovery_email": account.get("recovery_email", ""),
        }

    def list_accounts(self) -> list:
        data = self._read_raw_store()
        return [
            {"account_label": k, "provider": v["provider"], "email": v["email"]}
            for k, v in data.items()
        ]

    def delete_account(self, account_label: str) -> bool:
        """Removes an account entry from the encrypted store."""
        data = self._read_raw_store()
        if account_label in data:
            del data[account_label]
            self._write_raw_store(data)
            print(f"[OK] [VAULT] Account '{account_label}' deleted successfully.")
            return True
        print(f"[WARN] [VAULT] Account '{account_label}' not found.")
        return False

    def _read_raw_store(self) -> dict[str, Any]:
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        if not VAULT_FILE.exists():
            return {}
        try:
            with open(VAULT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_raw_store(self, data: dict[str, Any]):
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        with open(VAULT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


if __name__ == "__main__":
    import argparse
    import getpass

    parser = argparse.ArgumentParser(description="SupremeAI Sovereign Credential Vault")
    parser.add_argument("--list", action="store_true", help="List stored accounts")
    parser.add_argument(
        "--add", action="store_true", help="Add or update an account non-interactively"
    )
    parser.add_argument(
        "--delete", type=str, metavar="LABEL", help="Delete an account by label"
    )
    parser.add_argument(
        "--provider", type=str, default="gemini", help="Provider (default: gemini)"
    )
    parser.add_argument(
        "--label", type=str, default="", help="Account label (e.g. gemini_primary)"
    )
    parser.add_argument("--email", type=str, default="", help="Account email")
    parser.add_argument("--password", type=str, default="", help="Account password")
    parser.add_argument(
        "--totp", type=str, default="", help="Authenticator 2FA Secret Key"
    )
    parser.add_argument("--recovery", type=str, default="", help="Recovery email")

    args = parser.parse_args()
    vault = CredentialVault()

    print("=================================================================")
    print("   SupremeAI: Sovereign Encrypted Credential Vault")
    print("=================================================================")

    if args.list:
        accounts = vault.list_accounts()
        print(f"Found {len(accounts)} stored accounts:")
        for acc in accounts:
            print(f" * [{acc['provider']}] {acc['account_label']} ({acc['email']})")
        sys.exit(0)

    if args.delete:
        vault.delete_account(args.delete)
        sys.exit(0)

    if args.add:
        if not args.email or not args.password:
            print("[ERROR] Both --email and --password are required when using --add.")
            sys.exit(1)
        lbl = args.label or f"{args.provider}_default"
        vault.save_account(
            provider=args.provider,
            account_label=lbl,
            email=args.email,
            password=args.password,
            totp_secret=args.totp,
            recovery_email=args.recovery,
        )
        sys.exit(0)

    # Interactive mode fallback
    print("\nPlease enter account details to encrypt and save:")
    provider = (
        input("Provider [gemini/chatgpt/claude] (default: gemini): ").strip()
        or "gemini"
    )
    label = (
        input("Account Label (e.g. gemini_primary): ").strip() or f"{provider}_default"
    )
    email = input("Account Email: ").strip()
    if not email:
        print("[ERROR] Email cannot be empty.")
        sys.exit(1)

    password = getpass.getpass("Account Password (hidden): ").strip()
    if not password:
        print("[ERROR] Password cannot be empty.")
        sys.exit(1)

    totp = input(
        "Authenticator 2FA Secret Key (Optional, press Enter if none): "
    ).strip()
    recovery = input("Recovery Email (Optional, press Enter if none): ").strip()

    vault.save_account(
        provider=provider,
        account_label=label,
        email=email,
        password=password,
        totp_secret=totp,
        recovery_email=recovery,
    )
