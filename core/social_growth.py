from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from core.state_store import durable_state


class SocialPlatform(StrEnum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"


class DraftStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    PUBLISHED = "published"
    REJECTED = "rejected"
    PAUSED = "paused"


@dataclass
class SocialDraft:
    tenant_id: str
    author_id: str
    platform: SocialPlatform
    body: str
    media_urls: tuple[str, ...] = ()
    scheduled_for: datetime | None = None
    id: str = field(default_factory=lambda: f"social_{uuid4().hex}")
    status: DraftStatus = DraftStatus.DRAFT
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    approved_by: str | None = None
    published_at: datetime | None = None
    audit: list[dict[str, Any]] = field(default_factory=list)


class SocialGrowthCircle:
    """Approval-first social operations; no credentials or passwords are handled here.

    Issue #451: drafts + tenant pause-flags now write through to the durable
    state store (Redis federation + in-process mirror) so a deploy/restart no
    longer silently erases pending social content.
    """

    def __init__(self) -> None:
        self._drafts: dict[str, SocialDraft] = {}
        self._paused_tenants: set[str] = set()
        self._store = durable_state("social_drafts")

    # ── persistence helpers (issue #451) ─────────────────────────────
    @staticmethod
    def _serialize(draft: SocialDraft) -> dict[str, Any]:
        data = asdict(draft)
        data["platform"] = draft.platform.value
        data["status"] = draft.status.value
        return data

    @staticmethod
    def _deserialize(data: dict[str, Any]) -> SocialDraft:
        draft = SocialDraft(
            tenant_id=data["tenant_id"],
            author_id=data["author_id"],
            platform=SocialPlatform(data["platform"]),
            body=data["body"],
        )
        draft.id = data["id"]
        draft.status = DraftStatus(data["status"])
        draft.created_at = datetime.fromisoformat(data["created_at"])
        draft.approved_by = data.get("approved_by")
        draft.published_at = (
            datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None
        )
        draft.audit = list(data.get("audit") or [])
        return draft

    def hydrate(self) -> None:
        """Reload durable records into memory (called at boot; safe re-run)."""
        for key, data in self._store.mirror_items().items():
            if key.startswith("__paused__:"):
                self._paused_tenants.add(key.removeprefix("__paused__:"))
            else:
                try:
                    draft = self._deserialize(data)
                except Exception:
                    continue  # malformed record — skip, never boot-block
                self._drafts[draft.id] = draft

    def _record(self, draft: SocialDraft) -> None:
        self._store.set(draft.id, self._serialize(draft))

    def create_draft(self, draft: SocialDraft) -> SocialDraft:
        if draft.tenant_id in self._paused_tenants:
            raise PermissionError("Social publishing is paused for this tenant")
        if not draft.body.strip():
            raise ValueError("Social draft body is required")
        draft.audit.append({"event": "draft.created", "actor_id": draft.author_id})
        self._drafts[draft.id] = draft
        self._record(draft)
        return draft

    def list_drafts(self, tenant_id: str) -> list[SocialDraft]:
        return [draft for draft in self._drafts.values() if draft.tenant_id == tenant_id]

    def approve(self, draft_id: str, tenant_id: str, approver_id: str) -> SocialDraft:
        draft = self._owned(draft_id, tenant_id)
        if draft.status is not DraftStatus.DRAFT:
            raise ValueError("Only draft content can be approved")
        draft.status = DraftStatus.APPROVED
        draft.approved_by = approver_id
        draft.audit.append({"event": "draft.approved", "actor_id": approver_id})
        self._record(draft)
        return draft

    def pause(self, tenant_id: str) -> None:
        self._paused_tenants.add(tenant_id)
        self._store.set(f"__paused__:{tenant_id}", True)
        for draft in self.list_drafts(tenant_id):
            if draft.status in {DraftStatus.DRAFT, DraftStatus.APPROVED}:
                draft.status = DraftStatus.PAUSED
                self._record(draft)

    def resume(self, tenant_id: str) -> None:
        self._paused_tenants.discard(tenant_id)
        self._store.delete(f"__paused__:{tenant_id}")

    def _owned(self, draft_id: str, tenant_id: str) -> SocialDraft:
        draft = self._drafts.get(draft_id)
        if draft is None or draft.tenant_id != tenant_id:
            raise KeyError("Social draft not found")
        return draft


social_growth_circle = SocialGrowthCircle()
