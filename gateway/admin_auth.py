"""SupremeAI Native Admin Authentication Module (Zero-Firebase).

Re-exports from gateway.service.admin_auth for backward compatibility with root gateway consumers.
"""

from __future__ import annotations

try:
    from gateway.service.admin_auth import *
    from gateway.service.admin_auth import (
        router,
        issue_admin_jwt,
        verify_admin_jwt,
        check_totp,
        generate_totp_secret,
        build_provisioning_uri,
        DEFAULT_ADMIN_EMAIL,
        PRIMARY_OWNER_EMAIL,
        DEFAULT_ADMIN_UID,
    )
except ImportError:
    from service.admin_auth import *
    from service.admin_auth import (
        router,
        issue_admin_jwt,
        verify_admin_jwt,
        check_totp,
        generate_totp_secret,
        build_provisioning_uri,
        DEFAULT_ADMIN_EMAIL,
        PRIMARY_OWNER_EMAIL,
        DEFAULT_ADMIN_UID,
    )
