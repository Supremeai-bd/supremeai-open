"""Capability Registry — the ecosystem's source of truth for what SupremeAI can do.

ROADMAP §12–§16, §55. Implements:
  - Capability + version + dependency + runtime tier + permission + health + usage
  - Lifecycle state machine (IDEA → DISCOVERED → PROPOSED → APPROVAL_PENDING →
    APPROVED → BUILDING → VALIDATING → ACTIVE → MEASURED → PROMOTE/ARCHIVE)
  - The cardinal rule: REUSE > ADAPT > EXTEND > CREATE (capability explosion guard)
  - Hot/Warm/Cold runtime tiers (keep knowledge; unload expensive runtime)

বাংলা: এটি ROADMAP §12-এ বর্ণিত Capability Registry-র production foundation।
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from adaptive_engine._store import ensure_columns, get_conn, jdump, jload

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CapabilityLifecycleState(enum.StrEnum):
    """ROADMAP §13 — full capability lifecycle."""

    IDEA = "IDEA"
    DISCOVERED = "DISCOVERED"
    PROPOSED = "PROPOSED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    APPROVED = "APPROVED"
    BUILDING = "BUILDING"
    VALIDATING = "VALIDATING"
    ACTIVE = "ACTIVE"
    MEASURED = "MEASURED"
    DEPRECATED = "DEPRECATED"
    ARCHIVED = "ARCHIVED"
    BLOCKED = "BLOCKED"


class CapabilityRuntimeTier(enum.StrEnum):
    """ROADMAP §15 — Hot / Warm / Cold runtime strategy."""

    HOT = "HOT"  # common/high-value, always easy to activate
    WARM = "WARM"  # metadata available, deps lazily loaded
    COLD = "COLD"  # archived; knowledge kept, runtime unloaded


class CapabilitySearchKind(enum.StrEnum):
    """ROADMAP §14 — search order before creating anything new."""

    EXACT = "EXACT"
    SEMANTIC = "SEMANTIC"
    TOOL = "TOOL"
    AGENT = "AGENT"
    WORKFLOW = "WORKFLOW"
    ADAPTER = "ADAPTER"


# বাংলা: ROADMAP §14 — নতুন capability বানানোর আগে এই transition map-এর সাথে মিলিয়ে
# নিশ্চিত করতে হবে যে REUSE > ADAPT > EXTEND > CREATE পথ অনুসরণ করা হয়েছে।
_ALLOWED_TRANSITIONS: dict[CapabilityLifecycleState, set[CapabilityLifecycleState]] = {
    CapabilityLifecycleState.IDEA: {
        CapabilityLifecycleState.DISCOVERED,
        CapabilityLifecycleState.PROPOSED,
        CapabilityLifecycleState.BLOCKED,
    },
    CapabilityLifecycleState.DISCOVERED: {
        CapabilityLifecycleState.PROPOSED,
        CapabilityLifecycleState.BLOCKED,
    },
    CapabilityLifecycleState.PROPOSED: {
        CapabilityLifecycleState.APPROVAL_PENDING,
        CapabilityLifecycleState.BLOCKED,
    },
    CapabilityLifecycleState.APPROVAL_PENDING: {
        CapabilityLifecycleState.APPROVED,
        CapabilityLifecycleState.BLOCKED,
    },
    CapabilityLifecycleState.APPROVED: {
        CapabilityLifecycleState.BUILDING,
        CapabilityLifecycleState.BLOCKED,
    },
    CapabilityLifecycleState.BUILDING: {
        CapabilityLifecycleState.VALIDATING,
        CapabilityLifecycleState.BLOCKED,
    },
    CapabilityLifecycleState.VALIDATING: {
        CapabilityLifecycleState.ACTIVE,
        CapabilityLifecycleState.BLOCKED,
    },
    CapabilityLifecycleState.ACTIVE: {
        CapabilityLifecycleState.MEASURED,
        CapabilityLifecycleState.DEPRECATED,
        CapabilityLifecycleState.BLOCKED,
    },
    CapabilityLifecycleState.MEASURED: {
        CapabilityLifecycleState.ACTIVE,  # promote/hot
        CapabilityLifecycleState.DEPRECATED,
        CapabilityLifecycleState.ARCHIVED,
    },
    CapabilityLifecycleState.DEPRECATED: {CapabilityLifecycleState.ARCHIVED},
    CapabilityLifecycleState.ARCHIVED: {CapabilityLifecycleState.IDEA},  # reactivate later
    CapabilityLifecycleState.BLOCKED: {
        CapabilityLifecycleState.PROPOSED,
        CapabilityLifecycleState.ARCHIVED,
    },
}


class CapabilityStateError(Exception):
    """Raised when a lifecycle transition is illegal (ROADMAP §13)."""


class CapabilityExistsError(Exception):
    """Raised when an exact-match capability already exists (explosion guard)."""


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Capability(BaseModel):
    """A single capability entry (ROADMAP §12)."""

    capability_id: str = Field(default_factory=lambda: f"cap-{uuid.uuid4().hex[:16]}")
    name: str
    purpose: str
    version: str = "0.1.0"
    # বাংলা: capability signature — exact-match dedup-এর জন্য stable hash।
    signature: str  # e.g. "pdf.extract.text.v1"
    category: str = "general"
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)  # other capability_ids
    permissions: list[str] = Field(default_factory=list)
    execution_method: str = "in_process"  # in_process | worker | browser | kaggle | external
    resource_requirements: dict[str, Any] = Field(default_factory=dict)
    verification_strategy: dict[str, Any] = Field(default_factory=dict)
    security_level: str = "standard"  # standard | elevated | privileged
    quality_score: float = 0.0
    usage_count: int = 0
    success_rate: float = 0.0
    lifecycle_state: CapabilityLifecycleState = CapabilityLifecycleState.IDEA
    runtime_tier: CapabilityRuntimeTier = CapabilityRuntimeTier.WARM
    source: str = "internal"  # internal | learned | acquired
    provenance: dict[str, Any] = Field(default_factory=dict)
    owner: str = "system"
    tenant_id: str | None = None
    activation_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    promoted_at: str | None = None
    archived_at: str | None = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class CapabilityRegistry:
    """Capability Registry — single source of truth (ROADMAP §12, §14, §55)."""

    TABLE = "ecosystem_capabilities"

    def __init__(self) -> None:
        self._ensure_schema()

    # -- schema -------------------------------------------------------------

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.TABLE} (
                    capability_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    version TEXT NOT NULL DEFAULT '0.1.0',
                    signature TEXT NOT NULL UNIQUE,
                    category TEXT NOT NULL DEFAULT 'general',
                    inputs TEXT NOT NULL DEFAULT '[]',
                    outputs TEXT NOT NULL DEFAULT '[]',
                    dependencies TEXT NOT NULL DEFAULT '[]',
                    permissions TEXT NOT NULL DEFAULT '[]',
                    execution_method TEXT NOT NULL DEFAULT 'in_process',
                    resource_requirements TEXT NOT NULL DEFAULT '{{}}',
                    verification_strategy TEXT NOT NULL DEFAULT '{{}}',
                    security_level TEXT NOT NULL DEFAULT 'standard',
                    quality_score REAL NOT NULL DEFAULT 0,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    success_rate REAL NOT NULL DEFAULT 0,
                    lifecycle_state TEXT NOT NULL DEFAULT 'IDEA',
                    runtime_tier TEXT NOT NULL DEFAULT 'WARM',
                    source TEXT NOT NULL DEFAULT 'internal',
                    provenance TEXT NOT NULL DEFAULT '{{}}',
                    owner TEXT NOT NULL DEFAULT 'system',
                    tenant_id TEXT,
                    activation_metadata TEXT NOT NULL DEFAULT '{{}}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    promoted_at TEXT,
                    archived_at TEXT
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_state "
                f"ON {self.TABLE}(lifecycle_state)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_category ON {self.TABLE}(category)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.TABLE}_signature ON {self.TABLE}(signature)"
            )
            conn.commit()

    # -- CRUD --------------------------------------------------------------

    def register(self, capability: Capability) -> Capability:
        """Insert a new capability; reject duplicate signatures (explosion guard)."""
        if self.find_by_signature(capability.signature):
            raise CapabilityExistsError(
                f"Capability with signature '{capability.signature}' already exists "
                "(ROADMAP §55: REUSE before CREATE)."
            )
        with get_conn() as conn:
            conn.execute(
                self._insert_sql(),
                self._row(capability),
            )
            conn.commit()
        return capability

    def get(self, capability_id: str) -> Capability | None:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
        return self._from_row(row) if row else None

    def find_by_signature(self, signature: str) -> Capability | None:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE signature = ?",
                (signature,),
            ).fetchone()
        return self._from_row(row) if row else None

    def list(
        self,
        *,
        state: CapabilityLifecycleState | None = None,
        category: str | None = None,
        runtime_tier: CapabilityRuntimeTier | None = None,
        owner: str | None = None,
        tenant_id: str | None = None,
        limit: int = 200,
    ) -> list[Capability]:
        clauses: list[str] = []
        params: list[Any] = []
        if state is not None:
            clauses.append("lifecycle_state = ?")
            params.append(state)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if runtime_tier is not None:
            clauses.append("runtime_tier = ?")
            params.append(runtime_tier)
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

    # -- lifecycle ----------------------------------------------------------

    def transition(
        self,
        capability_id: str,
        to_state: CapabilityLifecycleState,
        *,
        actor: str = "system",
        reason: str | None = None,
    ) -> Capability:
        cap = self.get(capability_id)
        if cap is None:
            raise CapabilityStateError(f"Capability {capability_id} not found")
        allowed = _ALLOWED_TRANSITIONS.get(cap.lifecycle_state, set())
        if to_state not in allowed:
            raise CapabilityStateError(
                f"Illegal transition {cap.lifecycle_state} → {to_state} "
                f"(allowed: {sorted(s for s in allowed)})"
            )
        now = datetime.now(UTC).isoformat()
        extra: dict[str, Any] = {"updated_at": now, "lifecycle_state": to_state}
        if to_state == CapabilityLifecycleState.MEASURED:
            extra["promoted_at"] = now
        if to_state == CapabilityLifecycleState.ARCHIVED:
            extra["archived_at"] = now
        sets = ", ".join(f"{k} = ?" for k in extra)
        params: list[Any] = list(extra.values()) + [capability_id]
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET {sets} WHERE capability_id = ?",
                params,
            )
            conn.commit()
        return self.get(capability_id)  # type: ignore[return-value]

    def promote(self, capability_id: str, *, actor: str = "system") -> Capability:
        """ROADMAP §13 — promote a measured capability to HOT runtime."""
        cap = self.get(capability_id)
        if cap is None:
            raise CapabilityStateError(capability_id)
        # বাংলা: শুধু MEASURED বা ACTIVE অবস্থা থেকে HOT-এ promote করা যায়।
        if cap.lifecycle_state not in {
            CapabilityLifecycleState.MEASURED,
            CapabilityLifecycleState.ACTIVE,
        }:
            raise CapabilityStateError(
                f"Cannot promote {capability_id}: must be MEASURED or ACTIVE"
            )
        with get_conn() as conn:
            conn.execute(
                f"UPDATE {self.TABLE} SET runtime_tier = ?, updated_at = ? WHERE capability_id = ?",
                (CapabilityRuntimeTier.HOT, datetime.now(UTC).isoformat(), capability_id),
            )
            conn.commit()
        return self.get(capability_id)  # type: ignore[return-value]

    def archive(self, capability_id: str, *, actor: str = "system") -> Capability:
        return self.transition(capability_id, CapabilityLifecycleState.ARCHIVED, actor=actor)

    def delete(self, capability_id: str) -> bool:
        """Hard-delete a capability (admin C5).

        Only ARCHIVED capabilities may be deleted — anything still active must
        go through the lifecycle first (honest contract, no silent teardown).
        Returns False when the id is unknown; raises CapabilityStateError when
        the capability is not ARCHIVED yet.
        """
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT lifecycle_state FROM {self.TABLE} WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
            if row is None:
                return False
            if row["lifecycle_state"] != CapabilityLifecycleState.ARCHIVED:
                raise CapabilityStateError(
                    f"capability {capability_id} must be ARCHIVED before delete "
                    f"(current: {row['lifecycle_state']})"
                )
            cur = conn.execute(
                f"DELETE FROM {self.TABLE} WHERE capability_id = ?",
                (capability_id,),
            )
            conn.commit()
            return bool(cur.rowcount)

    def record_usage(
        self,
        capability_id: str,
        *,
        success: bool,
        quality_delta: float = 0.0,
    ) -> Capability:
        """ROADMAP §23 — feed verification results back into capability metrics."""
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT usage_count, success_rate FROM {self.TABLE} WHERE capability_id = ?",
                (capability_id,),
            ).fetchone()
            if row is None:
                raise CapabilityStateError(capability_id)
            n = int(row["usage_count"]) + 1
            old_rate = float(row["success_rate"])
            # বাংলা: incremental moving average (no full rescan needed).
            new_rate = old_rate + ((1.0 if success else 0.0) - old_rate) / n
            conn.execute(
                f"UPDATE {self.TABLE} SET usage_count = ?, success_rate = ?, "
                f"quality_score = MIN(1.0, quality_score + ?), updated_at = ? "
                f"WHERE capability_id = ?",
                (
                    n,
                    new_rate,
                    max(0.0, quality_delta),
                    datetime.now(UTC).isoformat(),
                    capability_id,
                ),
            )
            conn.commit()
        return self.get(capability_id)  # type: ignore[return-value]

    # -- search (REUSE > ADAPT > EXTEND > CREATE) ---------------------------

    def search_for_requirement(
        self,
        requirement: str,
        *,
        signature_hint: str | None = None,
        category_hint: str | None = None,
        limit: int = 10,
    ) -> list[Capability]:
        """ROADMAP §14 — search exact → semantic → tools → agents → workflows → adapters.

        বাংলা: এখানে একটি lightweight signature/keyword search দেওয়া হলো।
        ভবিষ্যতে semantic similarity + agent/workflow registry-র সাথে যুক্ত হবে।
        """
        clauses = ["lifecycle_state IN (?, ?, ?)"]
        params: list[Any] = [
            CapabilityLifecycleState.ACTIVE,
            CapabilityLifecycleState.MEASURED,
            CapabilityLifecycleState.WARM if False else CapabilityLifecycleState.ACTIVE,
        ]
        # dedup params
        params = [
            CapabilityLifecycleState.ACTIVE,
            CapabilityLifecycleState.MEASURED,
        ]
        clauses = ["lifecycle_state IN (?, ?)"]
        if signature_hint:
            clauses.append("signature LIKE ?")
            params.append(f"%{signature_hint}%")
        if category_hint:
            clauses.append("category = ?")
            params.append(category_hint)
        req_like = f"%{requirement.lower()}%"
        clauses.append("(LOWER(name) LIKE ? OR LOWER(purpose) LIKE ?)")
        params.extend([req_like, req_like])
        params.append(limit)
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE {' AND '.join(clauses)} "
                f"ORDER BY usage_count DESC, quality_score DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._from_row(r) for r in rows]

    # -- internals ----------------------------------------------------------

    def _insert_sql(self) -> str:
        cols = (
            "capability_id, name, purpose, version, signature, category, inputs, "
            "outputs, dependencies, permissions, execution_method, "
            "resource_requirements, verification_strategy, security_level, "
            "quality_score, usage_count, success_rate, lifecycle_state, "
            "runtime_tier, source, provenance, owner, tenant_id, "
            "activation_metadata, created_at, updated_at, promoted_at, archived_at"
        )
        placeholders = ", ".join(["?"] * 28)
        return f"INSERT INTO {self.TABLE} ({cols}) VALUES ({placeholders})"

    def _row(self, c: Capability) -> tuple[Any, ...]:
        return (
            c.capability_id,
            c.name,
            c.purpose,
            c.version,
            c.signature,
            c.category,
            jdump(c.inputs),
            jdump(c.outputs),
            jdump(c.dependencies),
            jdump(c.permissions),
            c.execution_method,
            jdump(c.resource_requirements),
            jdump(c.verification_strategy),
            c.security_level,
            c.quality_score,
            c.usage_count,
            c.success_rate,
            c.lifecycle_state,
            c.runtime_tier,
            c.source,
            jdump(c.provenance),
            c.owner,
            c.tenant_id,
            jdump(c.activation_metadata),
            c.created_at,
            c.updated_at,
            c.promoted_at,
            c.archived_at,
        )

    def _from_row(self, row: Any) -> Capability:
        return Capability(
            capability_id=row["capability_id"],
            name=row["name"],
            purpose=row["purpose"],
            version=row["version"],
            signature=row["signature"],
            category=row["category"],
            inputs=jload(row["inputs"], []),
            outputs=jload(row["outputs"], []),
            dependencies=jload(row["dependencies"], []),
            permissions=jload(row["permissions"], []),
            execution_method=row["execution_method"],
            resource_requirements=jload(row["resource_requirements"], {}),
            verification_strategy=jload(row["verification_strategy"], {}),
            security_level=row["security_level"],
            quality_score=float(row["quality_score"] or 0),
            usage_count=int(row["usage_count"] or 0),
            success_rate=float(row["success_rate"] or 0),
            lifecycle_state=CapabilityLifecycleState(row["lifecycle_state"]),
            runtime_tier=CapabilityRuntimeTier(row["runtime_tier"]),
            source=row["source"],
            provenance=jload(row["provenance"], {}),
            owner=row["owner"],
            tenant_id=row["tenant_id"],
            activation_metadata=jload(row["activation_metadata"], {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            promoted_at=row["promoted_at"],
            archived_at=row["archived_at"],
        )


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry


__all__ = [
    "Capability",
    "CapabilityLifecycleState",
    "CapabilityRuntimeTier",
    "CapabilitySearchKind",
    "CapabilityStateError",
    "CapabilityExistsError",
    "CapabilityRegistry",
    "get_capability_registry",
]
