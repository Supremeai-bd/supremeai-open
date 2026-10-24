"""Role-Based Access Control (RBAC) system.

বাংলা: রোল-ভিত্তিক অ্যাক্সেস কন্ট্রোল (RBAC) সিস্টেম।

Defines roles, permissions, and authorization logic for the entire platform.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from core.logging_config import logger


# বাংলা মন্তব্য: UP042 ফিক্স — Role এর জন্য StrEnum ব্যবহার করা হয়েছে
class Role(StrEnum):
    """Valid system roles with hierarchical permissions."""

    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

    @classmethod
    def has_value(cls, value: str) -> bool:
        return any(value == r.value for r in cls)


# বাংলা মন্তব্য: UP042 ফিক্স — Permission এর জন্য StrEnum ব্যবহার করা হয়েছে
class Permission(StrEnum):
    """Valid action permissions in the system."""

    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    AUDIT = "audit"
    MANAGE_USERS = "manage_users"
    MANAGE_BILLING = "manage_billing"
    DEPLOY = "deploy"
    MANAGE_API_KEYS = "manage_api_keys"


# ── Role-to-Permission Mapping ────────────────────────────────────────────────
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(
        {
            Permission.READ,
            Permission.WRITE,
            Permission.ADMIN,
            Permission.AUDIT,
            Permission.MANAGE_USERS,
            Permission.MANAGE_BILLING,
            Permission.DEPLOY,
            Permission.MANAGE_API_KEYS,
        }
    ),
    Role.ADMIN: frozenset(
        {
            Permission.READ,
            Permission.WRITE,
            Permission.ADMIN,
            Permission.AUDIT,
            Permission.MANAGE_API_KEYS,
        }
    ),
    Role.OPERATOR: frozenset(
        {
            Permission.READ,
            Permission.WRITE,
            Permission.DEPLOY,
        }
    ),
    Role.VIEWER: frozenset(
        {
            Permission.READ,
        }
    ),
}


@dataclass(frozen=True)
class RBACEntry:
    """An RBAC entry linking a role to its permitted actions.

    Attributes:
        role: The role identifier.
        permissions: Set of permissions granted to this role.
    """

    role: Role
    permissions: frozenset[Permission] = field(compare=False)


def get_role_permissions(role: str | Role) -> frozenset[Permission] | frozenset[str]:
    """Get all permissions for a given role.

    বাংলা: নির্দিষ্ট রোলের জন্য সব পারমিশন রিটার্ন করে। প্রথমে config চেক করে, তারপর default।
    """
    role_str = role.value if isinstance(role, Role) else role.lower()

    # বাংলা মন্তব্য (ROOT-CAUSE FIX): module-level `from core.config import settings`
    # একবারই bind করত — টেস্ট suite-এ core.config মডিউল `sys.modules` থেকে মুছে
    # re-import হলে (tests/conftest.py delete pattern) *নতুন* Settings() তৈরি হতো,
    # rbac পুরনো instance-এই আটকে থাকত, আর monkeypatch কার্যকর হতো না (stale
    # `rbac_role_definitions={'admin': ['*'], ...}` → admin সবসময় authorize)।
    # এখন প্রতি কল-এ current settings পড়া হয়, ফলে re-import/rebind যাই ঘটুক,
    # rbac সবসময় সর্বশেষ instance দেখে।
    from core.config import settings

    # Check config-driven roles first
    custom_roles = getattr(settings, "rbac_role_definitions", {}) or {}
    if isinstance(custom_roles, dict) and role_str in custom_roles:
        configured_permissions = custom_roles[role_str]
        if isinstance(configured_permissions, dict):
            configured_permissions = configured_permissions.get("permissions", ())
        return frozenset(configured_permissions)

    # Fallback to hardcoded roles
    try:
        role_enum = Role(role_str)
        return ROLE_PERMISSIONS.get(role_enum, frozenset())
    except ValueError:
        return frozenset()


def has_permission(role: str | Role, required_permission: str | Permission) -> bool:
    """Check if a role has a specific permission.

    বাংলা: একটি রোলের নির্দিষ্ট পারমিশন আছে কিনা চেক করে।
    """
    try:
        req_perm_str = (
            required_permission.value
            if isinstance(required_permission, Permission)
            else required_permission.lower()
        )
        role_perms = get_role_permissions(role)

        # Normalize configured permissions so wildcard and string-based roles
        # behave the same as the built-in enum-backed roles.
        normalized_perms = {
            permission.value if isinstance(permission, Permission) else str(permission).lower()
            for permission in role_perms
        }

        # wildcard support
        if "*" in normalized_perms:
            return True

        # check both enum-based and string-based perms
        if req_perm_str in normalized_perms:
            return True

        if isinstance(required_permission, str):
            try:
                perm_enum = Permission(required_permission.lower())
                if perm_enum in role_perms:
                    return True
            except ValueError as ve:
                logger.debug(f"Permission string conversion fallback: {ve}")

        return False
    except Exception as exc:
        logger.warning(
            f"Invalid role or permission check: role={role}, permission={required_permission}, error={exc}"
        )
        return False


def authorize(
    user_role: str | Role,
    required_permission: str | Permission,
    context: dict[str, Any] | None = None,
) -> bool:
    """Authorize a user action based on their role.

    বাংলা: ইউজারের রোলের ভিত্তিকে অ্যাকশন অথরাইজ করে।

    Args:
        user_role: The role of the user requesting the action.
        required_permission: The permission required for the action.
        context: Optional context for more granular authorization logic.

    Returns:
        True if authorized, False otherwise.
    """
    return has_permission(user_role, required_permission)


class PermissionDeniedError(PermissionError):
    """Raised when a user attempts an action without sufficient permissions."""

    def __init__(self, role: str, action: str) -> None:
        self.role = role
        self.action = action
        super().__init__(f"Role '{role}' lacks permission for '{action}'")


# বাংলা মন্তব্য: ইউজার কনটেক্সট ক্লাস যা ইউজারের আইডি, রোল, মেয়াদ এবং স্কোপ ধারণ করে।
@dataclass
class UserContext:
    user_id: str
    role: str = "viewer"
    roles: list[str] = field(default_factory=list)
    expires_at: str | None = None
    scopes: tuple[str, ...] | None = None
    email: str | None = None

    def __post_init__(self) -> None:
        # বাংলা মন্তব্য: যদি roles প্রোভাইড করা থাকে কিন্তু role ডিফল্ট থাকে, তবে প্রথম role কে মূল role হিসেবে সেট করা হবে।
        if self.roles and self.role == "viewer":
            object.__setattr__(self, "role", self.roles[0])
        elif self.role and not self.roles:
            object.__setattr__(self, "roles", [self.role])


# বাংলা মন্তব্য: ক্লাসের মাধ্যমে রোলের পারমিশন চেক করার জন্য RoleBasedAccessControl ক্লাস যোগ করা হলো।
class RoleBasedAccessControl:
    def __init__(self, role_matrix: dict[str, Any] | None = None) -> None:
        self.role_matrix = role_matrix

    def has_permission(self, role: str | Role, action: str | Permission) -> bool:
        if self.role_matrix:
            # বাংলা মন্তব্য: কাস্টম রোল ম্যাট্রিক্স থাকলে সেটি চেক করা হচ্ছে।
            if isinstance(role, Role):
                role = role.value
            if role in self.role_matrix:
                entry = self.role_matrix[role]
                perms = getattr(entry, "permissions", ())
                if isinstance(action, Permission):
                    action = action.value
                if isinstance(entry, dict):
                    perms = entry.get("permissions", ())
                return action in perms
            return False
        # বাংলা মন্তব্য: গ্লোবাল রোল পারমিশন চেক করা হচ্ছে।
        return has_permission(role, action)

    def check(self, context: UserContext, action: str | Permission) -> bool:
        # বাংলা মন্তব্য: কনটেক্সট মেয়াদোত্তীর্ণ হয়েছে কিনা তা চেক করা হচ্ছে।
        if context.expires_at:
            try:
                import datetime

                from core.utils.time_utils import ensure_aware, utc_now

                expires = datetime.datetime.fromisoformat(context.expires_at)
                expires = ensure_aware(expires)

                if utc_now() > expires:
                    return False
            except (ValueError, TypeError):
                return False
        # বাংলা মন্তব্য: স্কোপ চেক করা হচ্ছে।
        if context.scopes is not None:
            act_str = action.value if isinstance(action, Permission) else action
            if act_str not in context.scopes:
                return False
        return self.has_permission(context.role, action)

    def require(self, context: UserContext, action: str | Permission) -> dict[str, Any]:
        """Raises PermissionDeniedError on failure — callers cannot accidentally ignore a denial."""
        if not self.check(context, action):
            raise PermissionDeniedError(
                role=context.role,
                action=action.value if isinstance(action, Permission) else action,
            )
        return {
            "allowed": True,
            "role": context.role,
            "action": action.value if isinstance(action, Permission) else action,
        }


# ── FastAPI Dependency Injection Helpers ───────────────────────────────────────
def get_current_user_token(request: Any = None) -> dict[str, Any]:
    """Extract current user token payload from request context or test environment.

    Test fallback mirrors the canonical ``api/dependencies.get_current_user_token``
    gate (AUDIT-SEC-9, issue #1662): it now requires BOTH the test-environment
    signature (``utils.environment.is_test_environment``) AND the explicit
    ``ALLOW_TEST_AUTH_BYPASS=true`` opt-in (``settings.is_bypass_allowed``,
    hardcoded ``False`` in production). A stray ``pytest`` import inside a
    production process can therefore no longer grant ``role=admin`` here.
    """
    if request is not None:
        user = getattr(getattr(request, "state", None), "user", None)
        if user:
            return user
    try:
        # বাংলা মন্তব্য (issue #1662 root-cause parity fix): আগে শুধু
        # `"pytest" in sys.modules` দেখে এখানে role=admin ফেরত দেওয়া হতো —
        # production প্রসেসে ভুল করে pytest লোড হলেই পুরো admin API খুলে যেত।
        # এখন canonical dependency-র মতোই explicit bypass opt-in লাগবে।
        from core.config import settings
        from utils.environment import is_test_environment

        if is_test_environment() and settings.is_bypass_allowed:
            admin_email = os.getenv("ADMIN_EMAIL", "test_admin@supremeai.com")
            logger.warning(
                "RBAC test-auth bypass ACTIVE for %s (ALLOW_TEST_AUTH_BYPASS=true) — "
                "never enable outside test/CI environments",
                admin_email,
            )
            return {"sub": admin_email, "role": "admin"}
    except Exception as e:
        logger.debug(f"RBAC environment check error: {e}")
    from fastapi import HTTPException

    raise HTTPException(status_code=401, detail="Unauthorized")


def get_current_admin(request: Any = None) -> dict[str, Any]:
    """Enforce admin role for admin-facing endpoints.

    AUD-2.6 fix: this dependency previously delegated to `get_current_user_token`
    without verifying the role, which let ANY authenticated user reach
    admin-registered routers (e.g. tools_registry, internal). It now fails
    closed unless the caller carries the `admin` role.
    """
    user = get_current_user_token(request)
    if str(user.get("role", "")).lower() != "admin":
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user
