"""Central tenant-scoped registry for zero-friction capability connections."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from pydantic import BaseModel, Field, HttpUrl

from adaptive_engine._store import get_conn, jdump, jload
from core.mcp_audit import MCPAuditEntry, get_audit_logger
from core.plugins.mcp_security import MCPSecurityGuard


class ConnectionRecord(BaseModel):
    id: str
    tenant_id: str
    actor_id: str
    url: HttpUrl
    name: str
    connection_type: str = "mcp"
    permission_level: str = "user"
    status: str = "active"
    capabilities: list[dict[str, Any]] = Field(default_factory=list)
    tool_permissions: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class ConnectionRegistry:
    """Single source of truth for tenant-owned external capabilities."""

    TABLE = "supremeai_connections"

    def __init__(self) -> None:
        with get_conn() as conn:
            conn.execute(
                f"""CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    connection_type TEXT NOT NULL,
                    permission_level TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL,
                    capabilities TEXT NOT NULL DEFAULT '{{}}',
                    tool_permissions TEXT NOT NULL DEFAULT '{{}}',
                    metadata TEXT NOT NULL DEFAULT '{{}}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(tenant_id, url)
                )"""
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_tenant ON {self.TABLE}(tenant_id)"
            )
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({self.TABLE})")}
            if "tool_permissions" not in columns:
                conn.execute(
                    f"ALTER TABLE {self.TABLE} ADD COLUMN tool_permissions TEXT NOT NULL DEFAULT '{{}}'"
                )
            conn.commit()

    @staticmethod
    def _identity(user: dict[str, Any]) -> tuple[str, str, str]:
        tenant_value = user.get("tenant_id") or user.get("organization_id")
        if not tenant_value:
            raise PermissionError("Authenticated tenant context is required")
        tenant_id = str(tenant_value)
        actor_value = user.get("user_id") or user.get("id")
        if not actor_value:
            raise PermissionError("Authenticated actor context is required")
        actor_id = str(actor_value)
        role = str(user.get("role") or user.get("user_role") or "user").lower()
        if tenant_id in {"None", "unknown"}:
            raise PermissionError("Authenticated tenant context is required")
        return tenant_id, actor_id, role

    def register(
        self,
        *,
        user: dict[str, Any],
        url: str,
        capabilities: list[dict[str, Any]],
        name: str | None = None,
        permission_level: str = "user",
        tool_permissions: dict[str, str] | None = None,
    ) -> ConnectionRecord:
        tenant_id, actor_id, _ = self._identity(user)
        if not MCPSecurityGuard.is_safe_url(url, enforce_https=False):
            raise ValueError("URL blocked by SSRF / security policy")
        if permission_level not in {"user", "admin", "system"}:
            raise ValueError("permission_level must be user, admin, or system")
        if permission_level != "user":
            raise PermissionError(
                "Connections start with user authority; use the permission endpoint for escalation"
            )

        now = datetime.now(UTC).isoformat()
        record = ConnectionRecord(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            actor_id=actor_id,
            url=url,
            name=name or urlparse(url).hostname or "mcp-server",
            permission_level=permission_level,
            capabilities=capabilities,
            tool_permissions=tool_permissions or {},
            created_at=now,
            updated_at=now,
        )
        with get_conn() as conn:
            conn.execute(
                f"""INSERT INTO {self.TABLE}
                (id, tenant_id, actor_id, url, name, connection_type,
                 permission_level, status, capabilities, tool_permissions, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tenant_id, url) DO UPDATE SET
                 capabilities=excluded.capabilities, name=excluded.name,
                 updated_at=excluded.updated_at, status='active'""",
                (
                    record.id,
                    record.tenant_id,
                    record.actor_id,
                    str(record.url),
                    record.name,
                    record.connection_type,
                    record.permission_level,
                    record.status,
                    jdump(record.capabilities),
                    jdump(record.tool_permissions),
                    jdump(record.metadata),
                    record.created_at,
                    record.updated_at,
                ),
            )
            conn.commit()
            stored_row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE tenant_id = ? AND url = ?",
                (record.tenant_id, str(record.url)),
            ).fetchone()
        if stored_row is None:
            raise RuntimeError("Connection registration could not be verified")
        stored_record = self._from_row(stored_row)
        get_audit_logger().log(
            MCPAuditEntry(
                tool_name="mcp.connection.register",
                decision="allow",
                risk_level="medium",
                tenant_id=tenant_id,
            )
        )
        return stored_record

    def set_permission(
        self,
        *,
        user: dict[str, Any],
        connection_id: str,
        permission_level: str,
    ) -> ConnectionRecord:
        tenant_id, _, role = self._identity(user)
        if role not in {"admin", "owner", "system"}:
            raise PermissionError("Only tenant administrators can change connection authority")
        if permission_level not in {"user", "admin", "system"}:
            raise ValueError("permission_level must be user, admin, or system")
        if permission_level == "system":
            raise PermissionError("System authority requires a separate governance approval")
        with get_conn() as conn:
            previous = conn.execute(
                f"SELECT permission_level FROM {self.TABLE} WHERE id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
            conn.execute(
                f"UPDATE {self.TABLE} SET permission_level = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (permission_level, datetime.now(UTC).isoformat(), connection_id, tenant_id),
            )

            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
            conn.commit()
        if row is None:
            raise LookupError("Connection not found")
        get_audit_logger().log(
            MCPAuditEntry(
                tool_name="mcp.connection.permission",
                decision="allow",
                risk_level="high" if permission_level == "system" else "medium",
                tenant_id=tenant_id,
                error=None if previous is None else f"changed_from={previous['permission_level']}",
            )
        )
        return self._from_row(row)

    def set_tool_permissions(
        self,
        *,
        user: dict[str, Any],
        connection_id: str,
        tool_permissions: dict[str, str],
    ) -> ConnectionRecord:
        tenant_id, _, role = self._identity(user)
        if role not in {"admin", "owner", "system"}:
            raise PermissionError("Only tenant administrators can change tool permissions")
        if any(
            level not in {"deny", "read", "execute", "write"} for level in tool_permissions.values()
        ):
            raise ValueError("Tool permission must be deny, read, execute, or write")
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
            if row is None:
                raise LookupError("Connection not found")
            conn.execute(
                f"UPDATE {self.TABLE} SET tool_permissions = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (jdump(tool_permissions), datetime.now(UTC).isoformat(), connection_id, tenant_id),
            )
            updated = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
            conn.commit()
        get_audit_logger().log(
            MCPAuditEntry(
                tool_name="mcp.connection.tool_permissions",
                decision="allow",
                risk_level="high",
                tenant_id=tenant_id,
            )
        )
        return self._from_row(updated)

    def reactivate(self, *, user: dict[str, Any], connection_id: str) -> ConnectionRecord:
        tenant_id, _, role = self._identity(user)
        if role not in {"admin", "owner", "system"}:
            raise PermissionError("Only tenant administrators can reactivate connections")
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
            if row is None:
                raise LookupError("Connection not found")
            if not MCPSecurityGuard.is_safe_url(row["url"], enforce_https=False):
                raise ValueError("Connection URL no longer satisfies security policy")
            conn.execute(
                f"UPDATE {self.TABLE} SET status = 'active', updated_at = ? WHERE id = ? AND tenant_id = ?",
                (datetime.now(UTC).isoformat(), connection_id, tenant_id),
            )
            updated = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
            conn.commit()
        get_audit_logger().log(
            MCPAuditEntry(
                tool_name="mcp.connection.reactivate",
                decision="allow",
                risk_level="medium",
                tenant_id=tenant_id,
            )
        )
        return self._from_row(updated)

    async def health(self, *, user: dict[str, Any], connection_id: str) -> ConnectionRecord:
        tenant_id, _, _ = self._identity(user)
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
        if row is None:
            raise LookupError("Connection not found")
        if row["status"] != "active":
            return self._from_row(row)

        started = time.perf_counter()
        status = "healthy"
        error: str | None = None
        if not MCPSecurityGuard.is_safe_url(row["url"], enforce_https=False):
            status = "degraded"
            error = "URL blocked by SSRF / security policy"
        else:
            try:
                request = UrlRequest(row["url"], method="HEAD")
                await asyncio.to_thread(urlopen, request, timeout=3)
            except Exception as exc:  # noqa: BLE001 - health probes must degrade safely
                status = "degraded"
                error = type(exc).__name__

        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        now = datetime.now(UTC).isoformat()
        metadata = jload(row["metadata"], {})
        metadata.update(
            {
                "health_status": status,
                "health_latency_ms": latency_ms,
                "health_checked_at": now,
                "health_error": error,
            }
        )
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET status = ?, metadata = ?, updated_at = ? WHERE id = ? AND tenant_id = ?",
                (status, jdump(metadata), now, connection_id, tenant_id),
            )
            conn.commit()
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
        return self._from_row(row)

    def revoke(self, *, user: dict[str, Any], connection_id: str) -> ConnectionRecord:
        tenant_id, _, role = self._identity(user)
        if role not in {"admin", "owner", "system"}:
            raise PermissionError("Only tenant administrators can revoke connections")
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET status = 'revoked', updated_at = ? WHERE id = ? AND tenant_id = ?",
                (datetime.now(UTC).isoformat(), connection_id, tenant_id),
            )
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE id = ? AND tenant_id = ?",
                (connection_id, tenant_id),
            ).fetchone()
            conn.commit()
        if row is None:
            raise LookupError("Connection not found")
        get_audit_logger().log(
            MCPAuditEntry(
                tool_name="mcp.connection.revoke",
                decision="allow",
                risk_level="high",
                tenant_id=tenant_id,
            )
        )
        return self._from_row(row)

    def list_for_tenant(self, user: dict[str, Any]) -> list[ConnectionRecord]:
        tenant_id, _, _ = self._identity(user)
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE tenant_id = ? ORDER BY created_at DESC",
                (tenant_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    @staticmethod
    def _from_row(row: Any) -> ConnectionRecord:
        return ConnectionRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            actor_id=row["actor_id"],
            url=row["url"],
            name=row["name"],
            connection_type=row["connection_type"],
            permission_level=row["permission_level"],
            status=row["status"],
            capabilities=jload(row["capabilities"], []),
            tool_permissions=jload(row["tool_permissions"], {}),
            metadata=jload(row["metadata"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


connection_registry = ConnectionRegistry()

__all__ = ["ConnectionRecord", "ConnectionRegistry", "connection_registry"]
