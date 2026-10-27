"""Legacy Firebase Auth Stub (Zero-Firebase Architecture).

Firebase Admin SDK has been deprecated and replaced by SupremeAI Native Auth (Supabase + JWT).
This stub returns None safely without throwing errors or requiring firebase-admin imports.
"""

from __future__ import annotations

from core.logging_config import logger

auth = None


def get_firebase_auth():
    """Deprecated: Returns None as Firebase is decommissioned in favor of Native Auth."""
    global auth
    return None

