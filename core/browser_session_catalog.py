from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4


@dataclass
class SavedBrowserSession:
    tenant_id: str
    owner_id: str
    label: str
    url: str
    session_id: str | None = None
    id: str = field(default_factory=lambda: f"saved_{uuid4().hex}")
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_login_at: datetime | None = None
    revoked: bool = False


class BrowserSessionCatalog:
    def __init__(self) -> None:
        self._items: dict[str, SavedBrowserSession] = {}

    def save(self, item: SavedBrowserSession) -> SavedBrowserSession:
        if not item.tenant_id or not item.owner_id:
            raise ValueError("tenant and owner are required")
        self._items[item.id] = item
        return item

    def list(self, tenant_id: str, owner_id: str) -> list[SavedBrowserSession]:
        return [
            item
            for item in self._items.values()
            if item.tenant_id == tenant_id and item.owner_id == owner_id and not item.revoked
        ]

    def revoke(self, item_id: str, tenant_id: str, owner_id: str) -> bool:
        item = self._items.get(item_id)
        if item is None or item.tenant_id != tenant_id or item.owner_id != owner_id:
            return False
        item.revoked = True
        return True


browser_session_catalog = BrowserSessionCatalog()
