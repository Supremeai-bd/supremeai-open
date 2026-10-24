"""Browser Circle Center — sessions, navigation, sandbox.

Owns (per FCC plan): sessions, navigation, sandbox, takeover.
Domain adapter: ``core.browser_session_manager.session_manager`` (lazy).
Local permission rule: every session is namespaced to the owning actor —
a caller can never touch another actor's session.
"""

from __future__ import annotations

from core.circles.centers.base import CircleCenter, ExecutionEnvelope, LocalCapability
from core.circles.contracts import CircleName, RiskLevel

_SESSION_CAPABILITIES = {
    "browser.session.create",
    "browser.session.close",
    "browser.sessions.snapshot",
}


class BrowserCenter(CircleCenter):
    circle = CircleName.BROWSER
    display_name = "Browser automation"
    owner = "backend/core/browser_session_manager.py"

    def __init__(self) -> None:
        super().__init__()
        self.register(
            LocalCapability(
                name="browser.session.create",
                description="Create a browser session owned by the calling actor",
                risk_level=RiskLevel.MEDIUM,
                timeout_ms=30_000,
            ),
            self._create_session,
        )
        self.register(
            LocalCapability(
                name="browser.session.close",
                description="Close one of the calling actor's browser sessions",
                risk_level=RiskLevel.MEDIUM,
                timeout_ms=15_000,
            ),
            self._close_session,
        )
        self.register(
            LocalCapability(
                name="browser.sessions.snapshot",
                description="List the calling actor's browser sessions",
                risk_level=RiskLevel.LOW,
                timeout_ms=5_000,
                cache_ttl_ms=2_000,
            ),
            self._snapshot,
        )

    def local_permission(self, envelope: ExecutionEnvelope) -> str | None:
        if envelope.capability in _SESSION_CAPABILITIES:
            if envelope.capability == "browser.session.create":
                return None  # owner is derived from the execution context
            if not str(envelope.payload.get("session_id", "")).strip() and (
                envelope.capability == "browser.session.close"
            ):
                return "session_id is required for browser.session.close"
        return None

    def resolve_adapter(self, envelope: ExecutionEnvelope):  # noqa: ANN201
        from core.browser_session_manager import session_manager

        return session_manager

    async def _create_session(self, request) -> dict:
        manager = self.resolve_adapter(request)
        session = await manager.create(
            owner_id=request.context.actor_id,
            label=str(request.payload.get("label", "Browser session")),
            saved_url=request.payload.get("saved_url"),
        )
        # Return a safe projection — never the raw Playwright objects.
        return {
            "session_id": session.id,
            "owner_id": session.owner_id,
            "label": session.label,
            "saved_url": session.saved_url,
            "created_at": session.created_at,
        }

    async def _close_session(self, request) -> dict:
        manager = self.resolve_adapter(request)
        closed = await manager.close(
            str(request.payload.get("session_id", "")),
            owner_id=request.context.actor_id,
        )
        return {"session_id": request.payload.get("session_id"), "closed": closed}

    async def _snapshot(self, request) -> dict:
        manager = self.resolve_adapter(request)
        rows = [
            row for row in manager.snapshot() if row.get("owner_id") == request.context.actor_id
        ]
        return {"sessions": rows, "count": len(rows)}


__all__ = ["BrowserCenter"]
