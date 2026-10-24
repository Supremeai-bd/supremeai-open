"""Resource Registry + Provider Adapter base (ROADMAP §36–§38, §30–§34, §37).

বাংলা: ecosystem-এর সব external resource (Render, GitHub, Kaggle, Supabase,
Firebase, Redis, CI) একটি dynamic resource_id-র অধীনে registry-তে থাকে।
কোনো hard-coded `render-service-1` নেই। Provider-specific logic সব adapter-এর
ভেতরে থাকে; MCP/resource registry শুধু generic operation dispatch করে।

ROADMAP §46: MCP god-object এড়াতে → generic control operation → resource registry
→ provider adapter পথ অনুসরণ করা হয়।
"""

from __future__ import annotations

import abc
import enum
import importlib
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from adaptive_engine._store import get_conn, jdump, jload


class ProviderKind(enum.StrEnum):
    """ROADMAP §37 — supported provider families."""

    RENDER = "render"
    GITHUB = "github"
    KAGGLE = "kaggle"
    SUPABASE = "supabase"
    FIREBASE = "firebase"
    REDIS = "redis"
    CI = "ci"
    CUSTOM = "custom"


class ResourceState(enum.StrEnum):
    """ROADMAP §38 — resource lifecycle state."""

    REGISTERED = "REGISTERED"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"
    MAINTENANCE = "MAINTENANCE"
    OFFLINE = "OFFLINE"


class ResourceExistsError(KeyError):
    """Raised when registering a resource that already exists."""


class ResourceNotFoundError(KeyError):
    """Raised when a resource is not found."""


class AdapterNotRegisteredError(KeyError):
    """Raised when an adapter for a provider kind is not registered."""


class ResourceRecord(BaseModel):
    """A single registered resource (ROADMAP §38)."""

    resource_id: str = Field(default_factory=lambda: f"res-{uuid.uuid4().hex[:16]}")
    name: str
    provider: ProviderKind
    type: str = "web_service"  # web_service | worker | browser | scraper | db | cache | ci
    environment: str = "production"
    repository: str | None = None
    deployment_id: str | None = None
    region: str | None = None
    state: ResourceState = ResourceState.REGISTERED
    dependencies: list[str] = Field(default_factory=list)  # other resource_ids
    capabilities: list[str] = Field(default_factory=list)  # health, metrics, logs, deploy
    metadata: dict[str, Any] = Field(default_factory=dict)
    provider_config_ref: str | None = None  # secrets live in vault; only ref here
    owner: str = "system"
    tenant_id: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class BaseProviderAdapter(abc.ABC):
    """Common adapter contract (ROADMAP §37).

    বাংলা: প্রতিটি provider-এর জন্য একটি subclass দরকার যা এই generic operation-গুলো
    implement করবে। Provider-specific logic এই adapter-এর ভেতরে থাকবে, বাইরে নয়।
    """

    provider: ProviderKind = ProviderKind.CUSTOM

    def __init__(self, *, resource: ResourceRecord) -> None:
        self.resource = resource

    @abc.abstractmethod
    async def list_resources(self) -> list[dict[str, Any]]:
        """Return child resources (e.g. Render services under an account)."""

    @abc.abstractmethod
    async def get_resource(self) -> dict[str, Any]:
        """Return this resource's descriptor."""

    @abc.abstractmethod
    async def get_health(self) -> dict[str, Any]:
        """Return normalized health snapshot (see health_model)."""

    @abc.abstractmethod
    async def get_metrics(self) -> dict[str, Any]:
        """Return CPU / memory / latency / error-rate metrics."""

    @abc.abstractmethod
    async def get_logs(self, *, limit: int = 100, level: str | None = None) -> list[dict[str, Any]]:
        """Return recent log entries (lightweight metadata, ROADMAP §43)."""

    @abc.abstractmethod
    async def get_deployment(self) -> dict[str, Any] | None:
        """Return current deployment descriptor or None."""

    # Optional actions (default no-op so adapters opt-in).
    async def restart(self) -> dict[str, Any]:
        raise NotImplementedError(f"{self.provider} adapter does not implement restart")

    async def deploy(self, *, commit_sha: str | None = None) -> dict[str, Any]:
        raise NotImplementedError(f"{self.provider} adapter does not implement deploy")

    async def rollback(self, *, deployment_id: str) -> dict[str, Any]:
        raise NotImplementedError(f"{self.provider} adapter does not implement rollback")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class ResourceRegistry:
    """Central resource registry (ROADMAP §36, §38).

    Dynamic resource count — N nodes abstraction (ROADMAP §35). Admin never
    hard-codes `kaggle-account-1`; the registry sees capacity/quota/health.
    """

    TABLE = "ecosystem_resources"

    def __init__(self) -> None:
        self._ensure_schema()
        # provider → dotted adapter class path. Filled by register_adapter().
        self._adapter_classes: dict[ProviderKind, str] = {}

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    resource_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'web_service',
                    environment TEXT NOT NULL DEFAULT 'production',
                    repository TEXT,
                    deployment_id TEXT,
                    region TEXT,
                    state TEXT NOT NULL DEFAULT 'REGISTERED',
                    dependencies TEXT NOT NULL DEFAULT '[]',
                    capabilities TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT NOT NULL DEFAULT '{{}}',
                    provider_config_ref TEXT,
                    owner TEXT NOT NULL DEFAULT 'system',
                    tenant_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_provider ON {self.TABLE}(provider)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_state ON {self.TABLE}(state)"
            )
            conn.commit()

    # -- adapter registration ----------------------------------------------

    def register_adapter(self, provider: ProviderKind, adapter_class_path: str) -> None:
        """Bind a provider adapter implementation (dotted path, e.g. 'adapters.render.RenderAdapter')."""
        self._adapter_classes[provider] = adapter_class_path

    def resolve_adapter(self, resource: ResourceRecord) -> BaseProviderAdapter | None:
        """ROADMAP §37 — instantiate the registered adapter for this provider.

        বাংলা: adapter না থাকলে None রিটার্ন করে — caller তখন registry-only metadata
        দিয়ে কাজ চালাতে পারে (graceful degradation)।
        """
        path = self._adapter_classes.get(resource.provider)
        if not path:
            return None
        module_path, _, cls_name = path.rpartition(".")
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, cls_name)
        except (ImportError, AttributeError):
            return None
        return cls(resource=resource)

    # -- CRUD --------------------------------------------------------------

    def register(self, resource: ResourceRecord) -> ResourceRecord:
        with get_conn() as conn:
            conn.execute(
                self._insert_sql(),
                self._row(resource),
            )
            conn.commit()
        return resource

    def get(self, resource_id: str) -> ResourceRecord | None:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE resource_id = ?",
                (resource_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(
        self,
        *,
        provider: ProviderKind | None = None,
        environment: str | None = None,
        state: ResourceState | None = None,
        owner: str | None = None,
        tenant_id: str | None = None,
        limit: int = 200,
    ) -> list[ResourceRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if provider is not None:
            clauses.append("provider = ?")
            params.append(provider)
        if environment is not None:
            clauses.append("environment = ?")
            params.append(environment)
        if state is not None:
            clauses.append("state = ?")
            params.append(state)
        if owner is not None:
            clauses.append("owner = ?")
            params.append(owner)
        if tenant_id is not None:
            clauses.append("(tenant_id IS NULL OR tenant_id = ?)")
            params.append(tenant_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.TABLE} {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def update_state(self, resource_id: str, state: ResourceState) -> ResourceRecord | None:
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET state = ?, updated_at = ? WHERE resource_id = ?",
                (state, datetime.now(UTC).isoformat(), resource_id),
            )
            conn.commit()
        return self.get(resource_id)

    def link_deployment(self, resource_id: str, deployment_id: str) -> ResourceRecord | None:
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET deployment_id = ?, updated_at = ? WHERE resource_id = ?",
                (deployment_id, datetime.now(UTC).isoformat(), resource_id),
            )
            conn.commit()
        return self.get(resource_id)

    # -- generic control operation (ROADMAP §46) ----------------------------

    async def control(
        self,
        resource_id: str,
        operation: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generic control op → adapter. MCP uses this; it never grows per-provider."""
        resource = self.get(resource_id)
        if resource is None:
            return {"ok": False, "error": "resource_not_found", "resource_id": resource_id}
        adapter = self.resolve_adapter(resource)
        if adapter is None:
            return {
                "ok": False,
                "error": "adapter_not_registered",
                "provider": resource.provider,
            }
        payload = payload or {}
        handler = getattr(adapter, operation, None)
        if handler is None or not callable(handler):
            return {"ok": False, "error": "operation_not_supported", "operation": operation}
        try:
            result = await handler(**payload) if payload else await handler()
        except NotImplementedError as exc:
            return {"ok": False, "error": "not_implemented", "detail": str(exc)}
        except Exception as exc:  # noqa: BLE001 — adapters must never crash the registry
            return {"ok": False, "error": "adapter_error", "detail": str(exc)}
        return {"ok": True, "operation": operation, "result": result, "resource_id": resource_id}

    # -- internals ----------------------------------------------------------

    def _insert_sql(self) -> str:
        cols = (
            "resource_id, name, provider, type, environment, repository, "
            "deployment_id, region, state, dependencies, capabilities, metadata, "
            "provider_config_ref, owner, tenant_id, created_at, updated_at"
        )
        placeholders = ", ".join(["?"] * 17)
        return f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})"

    def _row(self, r: ResourceRecord) -> tuple[Any, ...]:
        return (
            r.resource_id,
            r.name,
            r.provider,
            r.type,
            r.environment,
            r.repository,
            r.deployment_id,
            r.region,
            r.state,
            jdump(r.dependencies),
            jdump(r.capabilities),
            jdump(r.metadata),
            r.provider_config_ref,
            r.owner,
            r.tenant_id,
            r.created_at,
            r.updated_at,
        )

    def _from_row(self, row: Any) -> ResourceRecord:
        return ResourceRecord(
            resource_id=row["resource_id"],
            name=row["name"],
            provider=ProviderKind(row["provider"]),
            type=row["type"],
            environment=row["environment"],
            repository=row["repository"],
            deployment_id=row["deployment_id"],
            region=row["region"],
            state=ResourceState(row["state"]),
            dependencies=jload(row["dependencies"], []),
            capabilities=jload(row["capabilities"], []),
            metadata=jload(row["metadata"], {}),
            provider_config_ref=row["provider_config_ref"],
            owner=row["owner"],
            tenant_id=row["tenant_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_registry: ResourceRegistry | None = None


def get_resource_registry() -> ResourceRegistry:
    global _registry
    if _registry is None:
        _registry = ResourceRegistry()
    return _registry


__all__ = [
    "ProviderKind",
    "ResourceState",
    "ResourceRecord",
    "BaseProviderAdapter",
    "ResourceRegistry",
    "get_resource_registry",
    "ResourceExistsError",
    "ResourceNotFoundError",
    "AdapterNotRegisteredError",
]
