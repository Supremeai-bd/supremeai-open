"""Canonical browser automation endpoints (owner-scoped).

Split out of the former single-module api/routes/browser.py verbatim:
saved-session catalog CRUD, isolated automation session lifecycle and the
generic per-session action executor. Routes register on the shared
``router`` in the original file order (see package ``__init__.py``).
"""

from typing import Literal

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import get_current_user_token
from api.routes.browser import router
from core.browser_session_catalog import SavedBrowserSession, browser_session_catalog
from core.browser_session_manager import session_manager


class AutomationSessionRequest(BaseModel):
    """Create an isolated session; credentials are entered by the user in-browser."""

    label: str = Field(default="Browser session", min_length=1, max_length=120)
    saved_url: str | None = Field(default=None, max_length=2048)


class SavedSessionRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=1, max_length=2048)
    session_id: str | None = Field(default=None, max_length=128)


class BrowserActionRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    action: Literal["navigate", "click", "fill", "type", "screenshot", "content", "extract"]
    url: str | None = Field(default=None, max_length=2048)
    selector: str | None = Field(default=None, min_length=1, max_length=512)
    value: str | None = Field(default=None, max_length=20_000)
    full_page: bool = False


class BrowserSessionResponse(BaseModel):
    session_id: str
    status: str
    url: str


@router.get("/automation/saved-sessions")
async def list_saved_sessions(user: dict = Depends(get_current_user_token)):
    owner_id = str(user.get("sub") or "")
    tenant_id = str(user.get("tenant_id") or "")
    if not owner_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Authenticated tenant claim required")
    return {
        "sessions": [item.__dict__ for item in browser_session_catalog.list(tenant_id, owner_id)]
    }


@router.post("/automation/saved-sessions")
async def save_session(payload: SavedSessionRequest, user: dict = Depends(get_current_user_token)):
    from core.security import is_safe_url

    owner_id = str(user.get("sub") or "")
    tenant_id = str(user.get("tenant_id") or "")
    if not owner_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Authenticated tenant claim required")
    if not owner_id or not tenant_id or not is_safe_url(payload.url):
        raise HTTPException(
            status_code=400, detail="Valid authenticated owner and safe URL are required"
        )
    item = browser_session_catalog.save(
        SavedBrowserSession(
            tenant_id=tenant_id,
            owner_id=owner_id,
            label=payload.label,
            url=payload.url,
            session_id=payload.session_id,
        )
    )
    return {"session": item.__dict__}


@router.delete("/automation/saved-sessions/{saved_session_id}")
async def revoke_saved_session(saved_session_id: str, user: dict = Depends(get_current_user_token)):
    owner_id = str(user.get("sub") or "")
    tenant_id = str(user.get("tenant_id") or "")
    if not owner_id or not tenant_id:
        raise HTTPException(status_code=401, detail="Authenticated tenant claim required")
    if not browser_session_catalog.revoke(saved_session_id, tenant_id, owner_id):
        raise HTTPException(status_code=404, detail="Saved browser session not found")
    return {"success": True}


@router.post("/automation/sessions", response_model=BrowserSessionResponse)
async def create_automation_session(
    req: AutomationSessionRequest,
    user_token: str = Depends(get_current_user_token),
):
    from core.security import is_safe_url

    if req.saved_url and not is_safe_url(req.saved_url):
        raise HTTPException(status_code=400, detail="Unsafe or invalid saved URL")
    session = await session_manager.create(user_token, label=req.label, saved_url=req.saved_url)
    return BrowserSessionResponse(session_id=session.id, status="ready", url=session.page.url)


@router.get("/automation/sessions")
async def list_automation_sessions(user_token: str = Depends(get_current_user_token)):
    return {"sessions": [s for s in session_manager.snapshot() if s["owner_id"] == user_token]}


@router.delete("/automation/sessions/{session_id}")
async def close_automation_session(
    session_id: str, user_token: str = Depends(get_current_user_token)
):
    if not await session_manager.close(session_id, user_token):
        raise HTTPException(status_code=404, detail="Browser session not found")
    return {"success": True}


@router.post("/automation/actions")
async def execute_automation_action(
    req: BrowserActionRequest, user_token: str = Depends(get_current_user_token)
):
    from core.security import is_safe_url

    async def _await_actionable(locator, action: str) -> None:
        """ERR-A06 FIX (2026-09-16): explicitly wait for the element to be
        visible before click/fill/type. On dynamic SPAs the node can match
        while still not actionable (mid re-render, animating, detached by a
        framework patch), which used to surface as raw 15s TimeoutErrors.
        A wait that still times out becomes an honest HTTP 408 with the
        verbatim reason instead of an opaque failure."""
        try:
            await locator.wait_for(state="visible", timeout=15_000)
        except Exception as exc:  # noqa: BLE001 — playwright TimeoutError et al.
            raise HTTPException(
                status_code=408,
                detail=f"Element {req.selector!r} not actionable for {action!r} within 15s: {exc}",
            ) from exc

    try:
        session = await session_manager.get(req.session_id, user_token)
    except PermissionError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    page = session.page
    action = req.action.lower()
    if action not in session.allowed_actions:
        raise HTTPException(status_code=403, detail="Action is not allowed for this session")
    if action == "navigate":
        if not req.url or not is_safe_url(req.url):
            raise HTTPException(status_code=400, detail="Unsafe or invalid URL")
        await page.goto(req.url, wait_until="domcontentloaded", timeout=30_000)
    elif action == "click":
        if not req.selector:
            raise HTTPException(status_code=422, detail="selector is required")
        locator = page.locator(req.selector)
        await _await_actionable(locator, "click")
        await locator.click(timeout=15_000)
    elif action in {"fill", "type"}:
        if not req.selector or req.value is None:
            raise HTTPException(status_code=422, detail="selector and value are required")
        locator = page.locator(req.selector)
        await _await_actionable(locator, action)
        await locator.fill(req.value, timeout=15_000)
    elif action == "screenshot":
        image = await page.screenshot(type="png", full_page=req.full_page)
        import base64

        return {
            "success": True,
            "action": action,
            "url": page.url,
            "screenshot": base64.b64encode(image).decode("ascii"),
        }
    elif action in {"content", "extract"}:
        return {
            "success": True,
            "action": action,
            "url": page.url,
            "content": await page.locator("body").inner_text(timeout=15_000),
        }
    else:
        raise HTTPException(status_code=422, detail="Unsupported browser action")
    return {"success": True, "action": action, "url": page.url}


@router.post("/automation/pause")
async def pause_automation(user: dict = Depends(get_current_user_token)):
    owner_id = str(user.get("sub") or "")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Authenticated owner required")
    session_manager.pause_owner(owner_id)
    return {"status": "paused"}


@router.post("/automation/resume")
async def resume_automation(user: dict = Depends(get_current_user_token)):
    owner_id = str(user.get("sub") or "")
    if not owner_id:
        raise HTTPException(status_code=401, detail="Authenticated owner required")
    session_manager.resume_owner(owner_id)
    return {"status": "active"}
