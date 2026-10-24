"""
core/models/shared_workspace.py
================================
SupremeAI 2.0 — Shared Workspace & Collaboration Models

বাংলা মন্তব্য: মাল্টি-টেন্যান্ট শেয়ার্ড ওয়ার্কস্পেস মডেল যা
টিম কলাবোরেশন, রিয়েল-টাইম এডিটিং, এবং ভার্সন কন্ট্রোল সমর্থন করে।

Features:
- Tenant-scoped workspace isolation
- Role-based access (owner, editor, viewer)
- Real-time cursor tracking
- Version snapshots
- Activity audit trail
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkspaceRole(StrEnum):
    """RBAC roles within a workspace."""

    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"
    COMMENTER = "commenter"


class WorkspaceStatus(StrEnum):
    """Lifecycle status of a workspace."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    FROZEN = "frozen"
    PENDING_DELETION = "pending_deletion"


class Permission(StrEnum):
    """Granular permissions for workspace resources."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SHARE = "share"
    ADMIN = "admin"
    EXECUTE = "execute"


# Role → Permissions mapping
ROLE_PERMISSIONS: dict[WorkspaceRole, list[Permission]] = {
    WorkspaceRole.OWNER: [
        Permission.READ,
        Permission.WRITE,
        Permission.DELETE,
        Permission.SHARE,
        Permission.ADMIN,
        Permission.EXECUTE,
    ],
    WorkspaceRole.ADMIN: [
        Permission.READ,
        Permission.WRITE,
        Permission.DELETE,
        Permission.SHARE,
        Permission.ADMIN,
    ],
    WorkspaceRole.EDITOR: [Permission.READ, Permission.WRITE, Permission.SHARE],
    WorkspaceRole.VIEWER: [Permission.READ],
    WorkspaceRole.COMMENTER: [Permission.READ, Permission.WRITE],  # Can add comments
}


class WorkspaceMember(BaseModel):
    """A member of a workspace with their role."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="Unique user identifier")
    email: str = Field(..., description="User email address")
    role: WorkspaceRole = Field(default=WorkspaceRole.VIEWER)
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    added_by: str | None = Field(default=None, description="User ID of the inviter")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email format")
        return v.lower()


class WorkspaceResource(BaseModel):
    """A resource (file, document, agent config) within a workspace."""

    model_config = ConfigDict(frozen=False)

    resource_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=255)
    resource_type: str = Field(
        ..., description="e.g., 'document', 'code', 'agent_config', 'dataset'"
    )
    content: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = Field(default=1)
    is_locked: bool = Field(default=False)
    locked_by: str | None = Field(default=None)

    def bump_version(self) -> None:
        """Increment version on update."""
        self.version += 1
        self.updated_at = datetime.now(UTC)


class WorkspaceSnapshot(BaseModel):
    """Point-in-time snapshot of workspace state."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(...)
    description: str | None = Field(default=None)
    resource_states: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class WorkspaceActivity(BaseModel):
    """Audit log entry for workspace activity."""

    model_config = ConfigDict(frozen=True)

    activity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workspace_id: str = Field(...)
    user_id: str = Field(...)
    action: str = Field(..., description="e.g., 'created', 'updated', 'deleted', 'shared'")
    resource_id: str | None = Field(default=None)
    details: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ip_address: str | None = Field(default=None)


class SharedWorkspace(BaseModel):
    """
    Core workspace model for multi-tenant collaboration.

    বাংলা মন্তব্য: প্রতিটি ওয়ার্কস্পেস একটি টেন্যান্টের মধ্যে আইসোলেটেড।
    সমস্ত রিসোর্স, মেম্বার, এবং অ্যাক্টিভিটি এই মডেলের অধীনে।
    """

    model_config = ConfigDict(frozen=False)

    workspace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = Field(..., description="Tenant/organization identifier")
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1024)
    status: WorkspaceStatus = Field(default=WorkspaceStatus.ACTIVE)

    # Members
    members: list[WorkspaceMember] = Field(default_factory=list)
    pending_invites: list[str] = Field(default_factory=list)  # Emails pending invitation

    # Resources
    resources: dict[str, WorkspaceResource] = Field(default_factory=dict)

    # Versioning
    snapshots: list[WorkspaceSnapshot] = Field(default_factory=list)
    current_snapshot_id: str | None = Field(default=None)

    # Activity
    activity_log: list[WorkspaceActivity] = Field(default_factory=list)

    # Metadata
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str = Field(...)
    tags: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)

    # Quotas
    max_members: int = Field(default=50)
    max_resources: int = Field(default=1000)
    max_storage_mb: int = Field(default=1024)  # 1GB default

    def add_member(self, member: WorkspaceMember) -> None:
        """Add a member to the workspace."""
        if len(self.members) >= self.max_members:
            raise ValueError(f"Workspace member limit ({self.max_members}) reached")
        # Check if already member
        if any(m.user_id == member.user_id for m in self.members):
            raise ValueError(f"User {member.user_id} is already a member")
        self.members.append(member)
        self.updated_at = datetime.now(UTC)

    def remove_member(self, user_id: str, removed_by: str) -> None:
        """Remove a member from the workspace."""
        if user_id == self.created_by:
            raise ValueError("Cannot remove workspace owner")
        self.members = [m for m in self.members if m.user_id != user_id]
        self.updated_at = datetime.now(UTC)
        self._log_activity(removed_by, "member_removed", details={"removed_user": user_id})

    def update_member_role(self, user_id: str, new_role: WorkspaceRole, updated_by: str) -> None:
        """Update a member's role."""
        for member in self.members:
            if member.user_id == user_id:
                # Create new member with updated role (immutable model)
                updated = WorkspaceMember(
                    user_id=member.user_id,
                    email=member.email,
                    role=new_role,
                    joined_at=member.joined_at,
                    added_by=member.added_by,
                )
                self.members = [m for m in self.members if m.user_id != user_id] + [updated]
                self.updated_at = datetime.now(UTC)
                self._log_activity(
                    updated_by,
                    "role_updated",
                    details={
                        "target_user": user_id,
                        "new_role": new_role.value,
                    },
                )
                return
        raise ValueError(f"Member {user_id} not found")

    def add_resource(self, resource: WorkspaceResource) -> None:
        """Add a resource to the workspace."""
        if len(self.resources) >= self.max_resources:
            raise ValueError(f"Workspace resource limit ({self.max_resources}) reached")
        self.resources[resource.resource_id] = resource
        self.updated_at = datetime.now(UTC)

    def get_member_permissions(self, user_id: str) -> list[Permission]:
        """Get effective permissions for a user."""
        for member in self.members:
            if member.user_id == user_id:
                return ROLE_PERMISSIONS.get(member.role, [Permission.READ])
        return []  # No permissions for non-members

    def can(self, user_id: str, permission: Permission) -> bool:
        """Check if a user has a specific permission."""
        return permission in self.get_member_permissions(user_id)

    def create_snapshot(self, user_id: str, description: str | None = None) -> WorkspaceSnapshot:
        """Create a point-in-time snapshot."""
        snapshot = WorkspaceSnapshot(
            workspace_id=self.workspace_id,
            created_by=user_id,
            description=description,
            resource_states={
                rid: {
                    "version": r.version,
                    "name": r.name,
                    "type": r.resource_type,
                }
                for rid, r in self.resources.items()
            },
            tags=list(self.tags),
        )
        self.snapshots.append(snapshot)
        self.current_snapshot_id = snapshot.snapshot_id
        self._log_activity(
            user_id, "snapshot_created", details={"snapshot_id": snapshot.snapshot_id}
        )
        return snapshot

    def restore_snapshot(self, snapshot_id: str, user_id: str) -> None:
        """Restore workspace to a snapshot state."""
        snapshot = next((s for s in self.snapshots if s.snapshot_id == snapshot_id), None)
        if not snapshot:
            raise ValueError(f"Snapshot {snapshot_id} not found")
        # In production, this would restore actual resource contents
        self.current_snapshot_id = snapshot_id
        self.updated_at = datetime.now(UTC)
        self._log_activity(user_id, "snapshot_restored", details={"snapshot_id": snapshot_id})

    def _log_activity(
        self,
        user_id: str,
        action: str,
        resource_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        """Internal method to log workspace activity."""
        activity = WorkspaceActivity(
            workspace_id=self.workspace_id,
            user_id=user_id,
            action=action,
            resource_id=resource_id,
            details=details or {},
        )
        self.activity_log.append(activity)
        # Trim activity log if too long
        if len(self.activity_log) > 10000:
            self.activity_log = self.activity_log[-5000:]

    def get_stats(self) -> dict[str, Any]:
        """Get workspace statistics."""
        total_storage = sum(len(r.content or "") for r in self.resources.values()) / (
            1024 * 1024
        )  # MB

        return {
            "workspace_id": self.workspace_id,
            "tenant_id": self.tenant_id,
            "member_count": len(self.members),
            "resource_count": len(self.resources),
            "snapshot_count": len(self.snapshots),
            "activity_count": len(self.activity_log),
            "storage_used_mb": round(total_storage, 2),
            "storage_limit_mb": self.max_storage_mb,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# Firestore serialization helpers
def workspace_to_firestore(workspace: SharedWorkspace) -> dict[str, Any]:
    """Convert workspace to Firestore-compatible dict."""
    return {
        "workspace_id": workspace.workspace_id,
        "tenant_id": workspace.tenant_id,
        "name": workspace.name,
        "description": workspace.description,
        "status": workspace.status.value,
        "members": [m.model_dump() for m in workspace.members],
        "pending_invites": workspace.pending_invites,
        "resources": {k: v.model_dump() for k, v in workspace.resources.items()},
        "snapshots": [s.model_dump() for s in workspace.snapshots],
        "current_snapshot_id": workspace.current_snapshot_id,
        "activity_log": [a.model_dump() for a in workspace.activity_log[-100:]],  # Last 100 only
        "created_at": workspace.created_at.isoformat(),
        "updated_at": workspace.updated_at.isoformat(),
        "created_by": workspace.created_by,
        "tags": workspace.tags,
        "settings": workspace.settings,
        "max_members": workspace.max_members,
        "max_resources": workspace.max_resources,
        "max_storage_mb": workspace.max_storage_mb,
    }


def workspace_from_firestore(data: dict[str, Any]) -> SharedWorkspace:
    """Reconstruct workspace from Firestore document."""
    ws = SharedWorkspace(
        workspace_id=data.get("workspace_id", str(uuid.uuid4())),
        tenant_id=data["tenant_id"],
        name=data["name"],
        description=data.get("description"),
        status=WorkspaceStatus(data.get("status", "active")),
        created_by=data["created_by"],
    )

    # Restore members
    for m_data in data.get("members", []):
        ws.members.append(WorkspaceMember(**m_data))

    # Restore resources
    for r_id, r_data in data.get("resources", {}).items():
        ws.resources[r_id] = WorkspaceResource(**r_data)

    # Restore snapshots
    for s_data in data.get("snapshots", []):
        ws.snapshots.append(WorkspaceSnapshot(**s_data))

    ws.current_snapshot_id = data.get("current_snapshot_id")
    ws.tags = data.get("tags", [])
    ws.settings = data.get("settings", {})
    ws.max_members = data.get("max_members", 50)
    ws.max_resources = data.get("max_resources", 1000)
    ws.max_storage_mb = data.get("max_storage_mb", 1024)

    return ws
