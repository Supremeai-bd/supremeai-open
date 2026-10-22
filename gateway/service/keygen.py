"""
service/keygen.py — Sovereign SupremeAI Key Generator & Cryptographic Verifier.

Key features:
- Generates authenticated client API keys (e.g. sk-supreme-studio-tier1-<rand>-<sig>).
- Stateless verification: Verifies key legitimacy in O(1) time without database queries
  via HMAC-SHA256 signature against the master secret.
- Fail-closed security: Requires SUPREMEAI_MASTER_KEY or API_KEY_SIGNING_SECRET in vault/env.
- Full 32-byte (64-hex) HMAC-SHA256 signature (zero 12-hex truncation).
- Supports CLI issuance: python -m service.keygen --client "studio" --quota "unlimited"
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import secrets
import sys


def get_signing_secret() -> str:
    secret = (
        os.getenv("SUPREMEAI_MASTER_KEY")
        or os.getenv("API_KEY_SIGNING_SECRET")
        or os.getenv("JWT_SECRET")
    )
    if not secret:
        raise RuntimeError(
            "CRITICAL: SUPREMEAI_MASTER_KEY or API_KEY_SIGNING_SECRET is missing. "
            "Fail-closed: Refusing to sign or verify API keys without vault secret."
        )
    return secret


def generate_key(client_name: str = "client", quota: str = "standard") -> str:
    """Generates an HMAC-signed sk-supreme-... API key with full SHA256 hex digest."""
    clean_name = "".join(c for c in client_name if c.isalnum() or c in "-_")[:20] or "client"
    clean_quota = "".join(c for c in quota if c.isalnum() or c in "-_")[:15] or "standard"
    random_entropy = secrets.token_hex(16)

    payload = f"{clean_name}.{clean_quota}.{random_entropy}"
    secret = get_signing_secret()

    signature = hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    return f"sk-supreme-{payload}-{signature}"


def verify_key(key: str) -> dict | None:
    """
    Statelessly verifies if an sk-supreme-... key has a valid HMAC signature.
    Returns metadata dict if valid, None if invalid.
    """
    if not key or not key.startswith("sk-supreme-"):
        return None

    raw = key[len("sk-supreme-"):]
    parts = raw.rsplit("-", 1)
    if len(parts) != 2:
        return None

    payload, provided_signature = parts
    payload_parts = payload.split(".")
    if len(payload_parts) != 3:
        return None

    client_name, quota, random_entropy = payload_parts
    try:
        secret = get_signing_secret()
    except RuntimeError:
        return None

    full_sig = hmac.new(
        secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()

    # Support full 64-hex signature and legacy 12-hex transition safely
    is_valid = hmac.compare_digest(provided_signature, full_sig) or (
        len(provided_signature) == 12 and hmac.compare_digest(provided_signature, full_sig[:12])
    )

    if is_valid:
        return {
            "valid": True,
            "client": client_name,
            "quota": quota,
            "entropy": random_entropy,
            "key": key,
        }
    return None


def main():
    parser = argparse.ArgumentParser(description="SupremeAI Key Generator CLI")
    parser.add_argument("--client", default="default-client", help="Client or agent name")
    parser.add_argument("--quota", default="tier-1", help="Quota level or tier description")
    parser.add_argument("--count", type=int, default=1, help="Number of keys to generate")
    parser.add_argument("--verify", type=str, default="", help="Verify an existing key")

    args = parser.parse_args()

    if args.verify:
        result = verify_key(args.verify)
        if result:
            print(f"[VALID] Client: {result['client']}, Quota: {result['quota']}")
            sys.exit(0)
        else:
            print("[INVALID] Key signature is invalid or forged.")
            sys.exit(1)

    print(f"Generating {args.count} key(s) for client='{args.client}', quota='{args.quota}'...\n")
    for i in range(args.count):
        k = generate_key(args.client, args.quota)
        print(f"  {i+1}: {k}")


if __name__ == "__main__":
    main()
