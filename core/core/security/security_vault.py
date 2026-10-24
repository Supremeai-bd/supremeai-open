"""Security Vault — DEPRECATION SHIM (Wave 3.9, issue #1265).

Folded into :mod:`core.security.secure_credential_store` (single credential-
encryption module). This file remains as a pure re-export shim per the
no-file-delete doctrine (WAVE_MASTER_PLAN §10 rule 4) — its 3 importers
(``core/agents/agent_action.py``, ``api/routes/integrations.py``,
``tools/devops/github_agent.py``) keep working unchanged.

New code should import from ``core.security.secure_credential_store`` directly.
"""

from __future__ import annotations

from core.security.secure_credential_store import (  # noqa: F401  (re-export)
    ENCRYPTION_KEY,
    decrypt_token,
    encrypt_token,
)

__all__ = ["ENCRYPTION_KEY", "decrypt_token", "encrypt_token"]
