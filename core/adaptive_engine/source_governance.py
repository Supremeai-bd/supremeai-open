"""Source Governance — permission-first internet learning (ROADMAP §7–§10, §57).

বাংলা: ROADMAP §7 — always-on does NOT mean unrestricted। source-এর state:
UNKNOWN → DISCOVERED → APPROVAL_PENDING → ALLOWLISTED → BLOCKED → DEFERRED।

ROADMAP §9: permission-first learning — discover → analyze → ask permission →
admin: APPROVE / REJECT / DEFER → সিদ্ধান্তটি reusable policy হয়ে যায়।

ROADMAP §10: প্রতিটি learned item-এ source / URL / type / retrieval time /
provenance / confidence / cross-check status থাকবে।

ROADMAP §56: knowledge explosion protection — relevance/confidence/freshness/
usage/duplication দিয়ে low-value transient তথ্য discard বা summarize।
"""

from __future__ import annotations

import enum
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from adaptive_engine._store import get_conn, jdump, jload


class SourceState(enum.StrEnum):
    """ROADMAP §8 — source lifecycle."""

    UNKNOWN = "UNKNOWN"
    DISCOVERED = "DISCOVERED"
    APPROVAL_PENDING = "APPROVAL_PENDING"
    ALLOWLISTED = "ALLOWLISTED"
    BLOCKED = "BLOCKED"
    DEFERRED = "DEFERRED"


class SourceCategory(enum.StrEnum):
    AI_DOCS = "AI_DOCS"
    OSS_REPO = "OSS_REPO"
    TECH_DOCS = "TECH_DOCS"
    RESEARCH = "RESEARCH"
    STANDARDS = "STANDARDS"
    PUBLIC_API = "PUBLIC_API"
    TECH_BLOG = "TECH_BLOG"
    MODEL_PROVIDER_DOCS = "MODEL_PROVIDER_DOCS"
    APPROVED_SITE = "APPROVED_SITE"
    APPROVED_DATASET = "APPROVED_DATASET"
    UNKNOWN = "UNKNOWN"


# বাংলা: ROADMAP §8 — সিদ্ধান্ত সাপেক্ষে state transitions।
_ALLOWED: dict[SourceState, set[SourceState]] = {
    SourceState.UNKNOWN: {
        SourceState.DISCOVERED,
        SourceState.BLOCKED,
        SourceState.ALLOWLISTED,
    },
    SourceState.DISCOVERED: {
        SourceState.APPROVAL_PENDING,
        SourceState.ALLOWLISTED,
        SourceState.BLOCKED,
        SourceState.DEFERRED,
    },
    SourceState.APPROVAL_PENDING: {
        SourceState.ALLOWLISTED,
        SourceState.BLOCKED,
        SourceState.DEFERRED,
    },
    SourceState.ALLOWLISTED: {SourceState.BLOCKED, SourceState.DEFERRED},
    SourceState.BLOCKED: {
        SourceState.APPROVAL_PENDING,
        SourceState.ALLOWLISTED,
    },
    SourceState.DEFERRED: {
        SourceState.APPROVAL_PENDING,
        SourceState.ALLOWLISTED,
        SourceState.BLOCKED,
    },
}


class SourcePolicy(BaseModel):
    """ROADMAP §8 — admin-defined policy for a source/category/domain."""

    policy_id: str = Field(default_factory=lambda: f"pol-{uuid.uuid4().hex[:16]}")
    name: str
    scope: str = "domain"  # source | category | provider | domain | repository | organization
    scope_value: str
    decision: SourceState = SourceState.ALLOWLISTED
    reason: str | None = None
    rate_limit_per_minute: int = 30
    crawl_budget_per_day: int = 500
    requires_approval: bool = False
    auto_policies_generated: list[str] = Field(default_factory=list)
    created_by: str = "admin"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class LearnedItem(BaseModel):
    """ROADMAP §10 — every learned item carries full provenance."""

    item_id: str = Field(default_factory=lambda: f"learn-{uuid.uuid4().hex[:16]}")
    source_url: str
    source_id: str | None = None
    source_type: SourceCategory = SourceCategory.UNKNOWN
    title: str | None = None
    summary: str | None = None
    content_hash: str | None = None
    retrieved_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    source_version: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0  # 0..1
    cross_check_status: str = "pending"  # pending | verified | contradicted | unverified
    policy_decision: str = "unknown"  # allow | conditional | block | unknown
    capabilities_affected: list[str] = Field(default_factory=list)
    relevance: float = 0.0  # ROADMAP §56
    freshness: float = 1.0
    usage_count: int = 0
    duplicate_of: str | None = None
    raw_blob_ref: str | None = None  # pointer to object storage, not inline


class SourceStateError(Exception):
    pass


class SourceGovernance:
    """Source governance + learning quality (ROADMAP §7–§10, §56, §57)."""

    SOURCE_TABLE = "ecosystem_sources"
    POLICY_TABLE = "ecosystem_source_policies"
    LEARNED_TABLE = "ecosystem_learned_items"

    def __init__(self) -> None:
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with get_conn() as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.SOURCE_TABLE} (
                    source_id TEXT PRIMARY KEY,
                    url TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'UNKNOWN',
                    category TEXT NOT NULL DEFAULT 'UNKNOWN',
                    trust_score REAL NOT NULL DEFAULT 0,
                    risk_score REAL NOT NULL DEFAULT 0,
                    cost_score REAL NOT NULL DEFAULT 0,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{{}}',
                    owner TEXT NOT NULL DEFAULT 'system',
                    tenant_id TEXT
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.POLICY_TABLE} (
                    policy_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    scope_value TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT,
                    rate_limit_per_minute INTEGER NOT NULL DEFAULT 30,
                    crawl_budget_per_day INTEGER NOT NULL DEFAULT 500,
                    requires_approval INTEGER NOT NULL DEFAULT 0,
                    auto_policies_generated TEXT NOT NULL DEFAULT '[]',
                    created_by TEXT NOT NULL DEFAULT 'admin',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.LEARNED_TABLE} (
                    item_id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL,
                    source_id TEXT,
                    source_type TEXT NOT NULL DEFAULT 'UNKNOWN',
                    title TEXT,
                    summary TEXT,
                    content_hash TEXT,
                    retrieved_at TEXT NOT NULL,
                    source_version TEXT,
                    provenance TEXT NOT NULL DEFAULT '{{}}',
                    confidence REAL NOT NULL DEFAULT 0,
                    cross_check_status TEXT NOT NULL DEFAULT 'pending',
                    policy_decision TEXT NOT NULL DEFAULT 'unknown',
                    capabilities_affected TEXT NOT NULL DEFAULT '[]',
                    relevance REAL NOT NULL DEFAULT 0,
                    freshness REAL NOT NULL DEFAULT 1,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    duplicate_of TEXT,
                    raw_blob_ref TEXT
                )
                """
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.LEARNED_TABLE}_source "
                f"ON {self.LEARNED_TABLE}(source_url)"
            )
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{self.LEARNED_TABLE}_conf "
                f"ON {self.LEARNED_TABLE}(confidence)"
            )
            conn.commit()

    # -- discovery ---------------------------------------------------------

    def discover(self, url: str, *, category: SourceCategory | None = None) -> dict[str, Any]:
        """ROADMAP §57 — record a discovered source; apply policy to auto-allowlist."""
        domain = self._domain_of(url)
        source_id = f"src-{hashlib.sha256(url.encode()).hexdigest()[:16]}"
        now = datetime.now(UTC).isoformat()
        state = SourceState.DISCOVERED
        # বাংলা: ROADMAP §9 — policy আগে থেকে মিললে সেটা apply হবে (admin approval fatigue কমানো)।
        policy = self.match_policy(domain=domain, category=category)
        if policy is not None:
            state = policy.decision
        with get_conn() as conn:
            conn.execute(
                f"INSERT OR IGNORE INTO {self.SOURCE_TABLE} "
                f"(source_id, url, domain, state, category, trust_score, risk_score, "
                f"cost_score, first_seen_at, last_seen_at, metadata, owner) "
                f"VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?, '{{}}', 'system')",
                (
                    source_id,
                    url,
                    domain,
                    state,
                    category or SourceCategory.UNKNOWN,
                    now,
                    now,
                ),
            )
            # update last_seen + state if already known
            conn.execute(
                f"UPDATE {self.SOURCE_TABLE} SET last_seen_at = ? WHERE source_id = ?",
                (now, source_id),
            )
            conn.commit()
        return {"source_id": source_id, "url": url, "state": state}

    def list_sources(
        self,
        *,
        state: SourceState | str | None = None,
        category: SourceCategory | str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """List discovered sources (admin SO1), newest-seen first."""
        clauses: list[str] = []
        params: list[Any] = []
        if state is not None:
            clauses.append("state = ?")
            params.append(str(state))
        if category is not None:
            clauses.append("category = ?")
            params.append(str(category))
        params.append(limit)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.SOURCE_TABLE} {where} ORDER BY last_seen_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_source(self, source_id: str) -> dict[str, Any] | None:
        """Fetch one source by id (admin SO4); None when unknown."""
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT * FROM {self.SOURCE_TABLE} WHERE source_id = ?",
                (source_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def transition_source(
        self, source_id: str, to_state: SourceState, *, actor: str = "admin"
    ) -> dict[str, Any]:
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT state FROM {self.SOURCE_TABLE} WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            if row is None:
                raise SourceStateError(source_id)
            current = SourceState(row["state"])
            if to_state not in _ALLOWED.get(current, set()):
                raise SourceStateError(f"Illegal source transition {current} → {to_state}")
            conn.execute(
                f"UPDATE {self.SOURCE_TABLE} SET state = ? WHERE source_id = ?",
                (to_state, source_id),
            )
            conn.commit()
        return {"source_id": source_id, "state": to_state, "by": actor}

    def is_allowed(self, url: str) -> bool:
        """ROADMAP §7 — quick check whether a URL is allowlisted by policy."""
        domain = self._domain_of(url)
        with get_conn() as conn:
            row = conn.execute(
                f"SELECT state FROM {self.SOURCE_TABLE} WHERE url = ? OR domain = ? "
                f"ORDER BY last_seen_at DESC LIMIT 1",
                (url, domain),
            ).fetchone()
        if row is None:
            # no record → check policy match (category/domain allowlist)
            policy = self.match_policy(domain=domain)
            return policy is not None and policy.decision == SourceState.ALLOWLISTED
        return SourceState(row["state"]) == SourceState.ALLOWLISTED

    # -- policies ----------------------------------------------------------

    def list_policies(self, *, limit: int = 200) -> list[SourcePolicy]:
        """List source policies (admin SP1), newest first."""
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.POLICY_TABLE} ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._policy_from_row(r) for r in rows]

    def delete_policy(self, policy_id: str) -> bool:
        """Hard-delete a policy (admin SP3); False when unknown."""
        with get_conn() as conn:
            cur = conn.execute(
                f"DELETE FROM {self.POLICY_TABLE} WHERE policy_id = ?",
                (policy_id,),
            )
            conn.commit()
            return bool(cur.rowcount)

    def delete_learned(self, item_id: str) -> bool:
        """Hard-delete a learned item (admin LE3); False when unknown."""
        with get_conn() as conn:
            cur = conn.execute(
                f"DELETE FROM {self.LEARNED_TABLE} WHERE item_id = ?",
                (item_id,),
            )
            conn.commit()
            return bool(cur.rowcount)

    def add_policy(self, policy: SourcePolicy) -> SourcePolicy:
        with get_conn() as conn:
            conn.execute(
                f"INSERT INTO {self.POLICY_TABLE} "
                f"(policy_id, name, scope, scope_value, decision, reason, "
                f"rate_limit_per_minute, crawl_budget_per_day, requires_approval, "
                f"auto_policies_generated, created_by, created_at) "
                f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    policy.policy_id,
                    policy.name,
                    policy.scope,
                    policy.scope_value,
                    policy.decision,
                    policy.reason,
                    policy.rate_limit_per_minute,
                    policy.crawl_budget_per_day,
                    int(policy.requires_approval),
                    jdump(policy.auto_policies_generated),
                    policy.created_by,
                    policy.created_at,
                ),
            )
            conn.commit()
        return policy

    def match_policy(
        self,
        *,
        domain: str | None = None,
        category: SourceCategory | None = None,
        provider: str | None = None,
    ) -> SourcePolicy | None:
        """ROADMAP §8 — find the most specific matching policy."""
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.POLICY_TABLE} ORDER BY created_at DESC"
            ).fetchall()
        candidates = []
        for row in rows:
            p = self._policy_from_row(row)
            hit = False
            specificity = 0
            if p.scope == "domain" and domain and p.scope_value == domain:
                hit, specificity = True, 3
            elif p.scope == "category" and category and p.scope_value == str(category):
                hit, specificity = True, 2
            elif p.scope == "provider" and provider and p.scope_value == provider:
                hit, specificity = True, 1
            if hit:
                candidates.append((specificity, p))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # -- learned items -----------------------------------------------------

    def record_learned(self, item: LearnedItem) -> LearnedItem:
        """ROADMAP §10, §56 — persist a learned item with full provenance."""
        if item.content_hash is None and item.summary:
            item.content_hash = hashlib.sha256(item.summary.encode()).hexdigest()
        # duplicate detection
        if item.content_hash:
            with get_conn() as conn:
                dup = conn.execute(
                    f"SELECT item_id FROM {self.LEARNED_TABLE} "
                    f"WHERE content_hash = ? AND item_id != ?",
                    (item.content_hash, item.item_id),
                ).fetchone()
            if dup:
                item.duplicate_of = dup["item_id"]
        with get_conn() as conn:
            conn.execute(
                self._learned_insert_sql(),
                self._learned_row(item),
            )
            conn.commit()
        return item

    def list_learned(
        self,
        *,
        min_confidence: float = 0.0,
        min_relevance: float = 0.0,
        source_type: SourceCategory | None = None,
        limit: int = 100,
    ) -> list[LearnedItem]:
        clauses = ["confidence >= ?", "relevance >= ?"]
        params: list[Any] = [min_confidence, min_relevance]
        if source_type is not None:
            clauses.append("source_type = ?")
            params.append(source_type)
        params.append(limit)
        with get_conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM {self.LEARNED_TABLE} WHERE {' AND '.join(clauses)} "
                f"ORDER BY retrieved_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._learned_from_row(r) for r in rows]

    def prune_low_value(self, *, older_than_days: int = 30, min_relevance: float = 0.1) -> int:
        """ROADMAP §56 — discard/summarize low-value transient knowledge."""
        cutoff = (datetime.now(UTC) - timedelta(days=older_than_days)).isoformat()
        with get_conn() as conn:
            cur = conn.execute(
                f"DELETE FROM {self.LEARNED_TABLE} "
                f"WHERE retrieved_at < ? AND relevance < ? AND usage_count = 0",
                (cutoff, min_relevance),
            )
            conn.commit()
            return cur.rowcount or 0

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _domain_of(url: str) -> str:
        try:
            from urllib.parse import urlparse

            netloc = urlparse(url).netloc.lower()
            return netloc.removeprefix("www.")
        except Exception:
            return url

    def _learned_insert_sql(self) -> str:
        cols = (
            "item_id, source_url, source_id, source_type, title, summary, "
            "content_hash, retrieved_at, source_version, provenance, confidence, "
            "cross_check_status, policy_decision, capabilities_affected, relevance, "
            "freshness, usage_count, duplicate_of, raw_blob_ref"
        )
        placeholders = ", ".join(["?"] * 19)
        return f"INSERT INTO {self.LEARNED_TABLE} ({cols}) VALUES ({placeholders})"

    def _learned_row(self, i: LearnedItem) -> tuple[Any, ...]:
        return (
            i.item_id,
            i.source_url,
            i.source_id,
            i.source_type,
            i.title,
            i.summary,
            i.content_hash,
            i.retrieved_at,
            i.source_version,
            jdump(i.provenance),
            i.confidence,
            i.cross_check_status,
            i.policy_decision,
            jdump(i.capabilities_affected),
            i.relevance,
            i.freshness,
            i.usage_count,
            i.duplicate_of,
            i.raw_blob_ref,
        )

    def _learned_from_row(self, row: Any) -> LearnedItem:
        return LearnedItem(
            item_id=row["item_id"],
            source_url=row["source_url"],
            source_id=row["source_id"],
            source_type=SourceCategory(row["source_type"]),
            title=row["title"],
            summary=row["summary"],
            content_hash=row["content_hash"],
            retrieved_at=row["retrieved_at"],
            source_version=row["source_version"],
            provenance=jload(row["provenance"], {}),
            confidence=float(row["confidence"] or 0),
            cross_check_status=row["cross_check_status"],
            policy_decision=row["policy_decision"],
            capabilities_affected=jload(row["capabilities_affected"], []),
            relevance=float(row["relevance"] or 0),
            freshness=float(row["freshness"] or 1),
            usage_count=int(row["usage_count"] or 0),
            duplicate_of=row["duplicate_of"],
            raw_blob_ref=row["raw_blob_ref"],
        )

    def _policy_from_row(self, row: Any) -> SourcePolicy:
        return SourcePolicy(
            policy_id=row["policy_id"],
            name=row["name"],
            scope=row["scope"],
            scope_value=row["scope_value"],
            decision=SourceState(row["decision"]),
            reason=row["reason"],
            rate_limit_per_minute=int(row["rate_limit_per_minute"] or 30),
            crawl_budget_per_day=int(row["crawl_budget_per_day"] or 500),
            requires_approval=bool(row["requires_approval"]),
            auto_policies_generated=jload(row["auto_policies_generated"], []),
            created_by=row["created_by"],
            created_at=row["created_at"],
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_gov: SourceGovernance | None = None


def get_source_governance() -> SourceGovernance:
    global _gov
    if _gov is None:
        _gov = SourceGovernance()
    return _gov


__all__ = [
    "SourceState",
    "SourceCategory",
    "SourcePolicy",
    "LearnedItem",
    "SourceStateError",
    "SourceGovernance",
    "get_source_governance",
]
