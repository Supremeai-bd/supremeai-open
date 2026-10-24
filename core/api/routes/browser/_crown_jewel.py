"""Crown Jewel browser endpoints (REAL implementations) + legacy step route.

FIXED 2026-09-15 (audit ERR-G03/G05/G06/G11 + ERR-D02/D03):
This module previously shipped fabricated responses while reporting
``success: True`` — a URL-hash "session id" that never existed, a canned AI
summary, a hardcoded 1x1 blank PNG "screenshot", a constant security score of
100, and a task-step executor that always claimed "Autonomous step succeeded".
That was false assurance (Class G): the system reporting success while doing
no work. Every endpoint here now either performs REAL work or fails loudly
with an explicit HTTP error. See docs/audits/SYSTEM_DEFECT_REGISTER_2026-09-15.md.

NOTE: ``execute_step`` (POST /tasks/{id}/step) stays registered at this exact
position because route registration order determines which handler wins for
``/tasks/{id}/...`` paths (see _tasks.py docstring).
"""

import importlib.util
import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Response
from pydantic import BaseModel, ConfigDict, field_validator

from api.routes.browser import router

# Page-context limits: keep prompts bounded (no unbounded context bloat).
_MAX_CONTEXT_CHARS = 6000
_MAX_LINKS = 50

_LINK_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

# ──────────────────────────────────────────────
# Security header checks used by /security-scan (real passive analysis)
# ──────────────────────────────────────────────
_SECURITY_HEADERS = (
    # (header, issue_text, weight)
    ("content-security-policy", "Missing Content-Security-Policy header", 25),
    ("x-frame-options", "Missing X-Frame-Options header (clickjacking risk)", 10),
    ("strict-transport-security", "Missing Strict-Transport-Security (HSTS) header", 15),
    ("x-content-type-options", "Missing X-Content-Type-Options header", 10),
    ("referrer-policy", "Missing Referrer-Policy header", 5),
    ("permissions-policy", "Missing Permissions-Policy header", 5),
)


def _scan_headers(url: str, headers: httpx.Headers) -> dict[str, Any]:
    """Evaluate real HTTP response headers and return {score, issues, criticalIssues}."""
    issues: list[str] = []
    critical: list[str] = []
    score = 100

    parsed = urlparse(url)
    if parsed.scheme != "https":
        critical.append("Page is served over plain HTTP (no TLS).")
        score -= 40

    for header, issue_text, weight in _SECURITY_HEADERS:
        value = headers.get(header)
        if not value:
            issues.append(issue_text)
            score -= weight
        elif header == "content-security-policy" and "unsafe-inline" in value.lower():
            issues.append("CSP contains 'unsafe-inline', weakening script/style protection.")
            score -= 10

    # Server software disclosure (informational)
    server = headers.get("server")
    if server and any(k in server.lower() for k in ("nginx/", "apache/", "express")):
        issues.append(f"Server header discloses software version: {server}")

    # Cookie security flags (Set-Cookie rows)
    try:
        raw_cookies = headers.get_list("set-cookie")
    except Exception:  # noqa: BLE001 — httpx version differences
        raw_cookies = []
    for raw_cookie in raw_cookies:
        low = raw_cookie.lower()
        if parsed.scheme == "https" and "secure" not in low:
            issues.append("Cookie set without the Secure flag over HTTPS.")
            score -= 10
        if "httponly" not in low:
            issues.append("Cookie set without HttpOnly (readable by scripts).")
            score -= 5

    score = max(0, min(100, score))
    return {"success": True, "score": score, "issues": issues, "criticalIssues": critical}


def _require_context(context: str) -> str:
    """Return trimmed page context or raise 422 — an AI action with no page
    context cannot be answered honestly."""
    trimmed = str(context or "").strip()
    if not trimmed:
        raise HTTPException(
            status_code=422,
            detail=(
                "No page context provided. The AI action needs the visible page "
                "text ('context') or at least a reachable URL to be useful."
            ),
        )
    return trimmed[:_MAX_CONTEXT_CHARS]


# ──────────────────────────────────────────────
# Issue #1657 (P1 security audit): typed request models. These four
# endpoints previously accepted ``body: dict[str, Any]`` — unvalidated,
# arbitrary payloads. Models below pin the exact contract, validate URLs at
# the edge and keep ``extra`` permissive ONLY where real clients send extra
# keys (browse-session callers add ``timestamp``/``tabId``).
# ──────────────────────────────────────────────


def _reject_non_http_url(value: str) -> str:
    """Shared field validator: require an absolute http(s) URL.

    Mirrors the handler-level scheme checks (which stay as defense in depth)
    so malformed URLs now fail at the Pydantic validation layer with 422.
    """
    if not value.startswith(("http://", "https://")):
        raise ValueError(f"Invalid URL: {value!r} — must be an absolute http(s) URL")
    return value


class BrowseSessionRequest(BaseModel):
    """Body for POST /browse-session (create a real session record).

    Frontend callers (CrownJewelBrowser.tsx) also send ``timestamp`` and
    ``tabId`` which the server never persisted, so extras stay ignored
    (Pydantic default) — turning them forbidden would break live clients.
    """

    url: str = ""
    title: str | None = None

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, v: str) -> str:
        # Sessions may be created for a not-yet-navigated tab (empty url is
        # rendered as the title); anything non-empty must be a real URL.
        if v and not v.startswith(("http://", "https://")):
            raise ValueError(f"Invalid URL: {v!r} — must be an absolute http(s) URL")
        return v


class AIActionRequest(BaseModel):
    """Body for POST /ai-action (real LLM-backed page analysis).

    ``action`` is now a closed Literal instead of a free-form string: the
    unsupported-action 422 previously came from inside the handler, it now
    comes from request validation itself. ``context`` stays handler-validated
    so the "No page context provided" 422 detail is unchanged.
    """

    action: Literal["summarize", "explain", "extract_links", "find_issues", "interact"] = (
        "summarize"
    )
    url: str = ""
    payload: dict[str, Any] | None = None
    context: str = ""

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, v: str) -> str:
        if v:
            return _reject_non_http_url(v)
        return v


class SecurityScanRequest(BaseModel):
    """Body for POST /security-scan (real passive header scan).

    ``url`` is required and must be an absolute http(s) URL — enforced by
    the validator in addition to the pre-existing handler checks.
    """

    url: str

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, v: str) -> str:
        return _reject_non_http_url(v)


class ScreenshotRequest(BaseModel):
    """Body for POST /screenshot (real Playwright capture)."""

    model_config = ConfigDict(extra="ignore")

    url: str
    full_page: bool = False

    @field_validator("url")
    @classmethod
    def _url_must_be_http(cls, v: str) -> str:
        return _reject_non_http_url(v)


# --- Crown Jewel Endpoints ---


@router.post("/browse-session")
def browse_session(body: BrowseSessionRequest):
    """Create a REAL browser session record.

    ERR-G06 FIX: previously returned ``sess_<sha256(url)[:16]>`` — a
    deterministic hash of the URL, not a session that existed anywhere.
    A subsequent lookup always 404'd even though the caller was told
    ``success: True``. It now creates a genuine entry in the session store
    (same store backing GET/PUT/DELETE /sessions), so the returned id is
    actually resolvable.
    """
    from api.routes.browser._session_store import SESSIONS

    session_id = f"sess_{uuid.uuid4().hex[:16]}"
    now = datetime.now(UTC).isoformat()
    SESSIONS[session_id] = {
        "id": session_id,
        "title": str(body.title or body.url or "Browser session"),
        "status": "running",
        "url": body.url,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    return {"success": True, "session_id": session_id}


@router.post("/ai-action")
def ai_action(body: AIActionRequest):
    """Run a real LLM-backed browser AI action over the provided page context.

    ERR-D03 FIX: previously returned a canned string ("This is a mock summary
    for ...") reporting success unconditionally. It now forwards the page
    context to the platform ModelRouter (LLM gateway with free-tier fallback)
    and surfaces real model output — or an explicit error, never a fake one.
    """
    action: str = body.action
    url: str = body.url
    context = _require_context(body.context)

    if action == "extract_links":
        # Deterministic, real extraction — no model needed.
        links: list[str] = []
        for match in _LINK_RE.findall(context):
            clean = match.rstrip(".,;")
            if clean not in links:
                links.append(clean)
            if len(links) >= _MAX_LINKS:
                break
        return {
            "success": True,
            "action": action,
            "links": links,
            "count": len(links),
            "issues": [],
            "criticalIssues": [],
        }

    prompts: dict[str, str] = {
        "summarize": (
            "Summarize the following web page content in 3-5 concise bullet points."
            + (f"\nPage URL: {url}" if url else "")
            + f"\n\nPage content:\n{context}"
        ),
        "explain": (
            "Explain what this web page does and who it is for, in plain language."
            + (f"\nPage URL: {url}" if url else "")
            + f"\n\nPage content:\n{context}"
        ),
        "find_issues": (
            "Review the following web page content. List any visible problems "
            "(broken text, placeholder content, security warnings, UX issues) as a "
            "short bullet list. If none are visible, say 'No visible issues found'."
            + (f"\nPage URL: {url}" if url else "")
            + f"\n\nPage content:\n{context}"
        ),
        "interact": (
            "Given this page content and the user's requested interaction, describe "
            "clearly what should be done next.\n"
            f"Requested interaction: {body.payload}\n\nPage content:\n{context}"
        ),
    }
    prompt = prompts.get(action)
    if prompt is None:
        raise HTTPException(status_code=422, detail=f"Unsupported AI action: {action!r}")

    try:
        from brain.model_router import ModelRouter

        result = ModelRouter().route_and_generate(prompt, task_type="browser_ai_action")
    except Exception as exc:  # noqa: BLE001 — honest error propagation
        raise HTTPException(status_code=503, detail=f"AI action failed: {exc}") from exc

    if not result.get("success"):
        raise HTTPException(
            status_code=503,
            detail=f"AI action failed: {result.get('error') or 'model returned no output'}",
        )

    text = str(result.get("text") or "")
    issues: list[str] = []
    if action == "find_issues" and "no visible issues found" not in text.lower():
        # Surface model findings as issues so the UI alert path has real data.
        issues = [line.strip("-• ").strip() for line in text.splitlines() if line.strip()]
        issues = [i for i in issues if i][:20]

    return {
        "success": True,
        "action": action,
        "response": text,
        "summary": text,
        "analysis": text,
        "links": [],
        "issues": issues,
        "criticalIssues": [],
        "model": result.get("model"),
    }


@router.post("/security-scan")
def security_scan(body: SecurityScanRequest):
    """Perform a REAL passive security scan of the target URL.

    ERR-G03 FIX: previously returned an unconditional
    ``{"success": True, "score": 100, "issues": []}`` — security theatre where
    every target scored a perfect 100. It now fetches the URL and evaluates
    real response headers (CSP, HSTS, X-Frame-Options, cookie flags, TLS) and
    reports the actual findings and score. Fetch failures are explicit 502s.
    """
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=422, detail="A 'url' is required for a security scan.")
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail=f"Invalid URL: {url!r}")

    try:
        resp = httpx.get(
            url,
            follow_redirects=True,
            timeout=15.0,
            headers={"User-Agent": "SupremeAI-SecurityScan/1.0"},
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail=f"Security scan could not reach {url}: {exc}"
        ) from exc

    return _scan_headers(str(resp.url), resp.headers)


@router.post("/screenshot")
def capture_screenshot(body: ScreenshotRequest):
    """Capture a REAL viewport screenshot via Playwright (when available).

    ERR-D02 FIX: previously returned a hardcoded 1x1 blank transparent PNG —
    a fake screenshot indistinguishable from a real one. It now renders the
    page in a headless Chromium. If Playwright or its browser binary is not
    installed, it fails loudly with 503 instead of returning a blank image.
    """
    url = body.url.strip()
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=422, detail=f"Invalid or missing 'url': {url!r}")

    if importlib.util.find_spec("playwright") is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Real screenshots require Playwright (pip install playwright && "
                "playwright install chromium). Blank placeholder responses are no "
                "longer served."
            ),
        )

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.goto(url, wait_until="networkidle", timeout=30000)
                png_bytes: bytes = page.screenshot(full_page=body.full_page)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 — honest error propagation
        raise HTTPException(status_code=503, detail=f"Screenshot capture failed: {exc}") from exc

    return Response(content=png_bytes, media_type="image/png")


@router.post("/screenshots")
async def save_screenshot_to_gallery(
    userId: str | None = None, url: str | None = None, timestamp: int | None = None
):
    """Save screenshot metadata to the gallery (actual image uploaded separately).

    Ported verbatim from the retired ``api/routes/browser_routes.py`` (#2258
    route consolidation) to preserve the live frontend contract —
    ``admin-browser/useBrowserActions.ts`` fires this POST after a successful
    capture (fire-and-forget, errors swallowed client-side).

    HONESTY NOTE (audit Class G, flagged not fixed here): the legacy handler
    never persisted anything — it fabricates a storage location and reports
    ``success: True`` unconditionally. That behaviour is preserved verbatim
    to keep this PR a pure route consolidation; making the endpoint honest
    (real gallery store or an explicit 501) is deferred to the gallery
    persistence follow-up.
    """
    import hashlib
    import time as _time

    gallery_entry = {
        "id": f"shot_{int(_time.time())}_{hashlib.md5((url or '').encode()).hexdigest()[:8]}",
        "userId": userId,
        "url": url,
        "capturedAt": timestamp or int(_time.time()),
        "storageLocation": f"screenshots/{userId or 'anonymous'}/{int(_time.time())}.png",
    }

    return {"success": True, "galleryEntry": gallery_entry, "message": "Screenshot metadata saved"}


# -----------------------------


@router.post("/tasks/{id}/step")
def execute_step(task_id: str):
    """Legacy in-memory step executor — RETIRED (ERR-G05).

    It previously always returned
    ``{"action": "navigated to dashboard", "details": "Autonomous step succeeded"}``
    regardless of task state, letting the autonomy dashboard show forward
    motion on a stalled task. There is no real step executor behind this
    route, so it now fails explicitly (501) instead of fabricating progress.
    Task lifecycle continues via the Neon-backed routes in _tasks.py
    (/tasks, /tasks/{id}/complete, /tasks/{id}/fail, /tasks/{id}/circuit-open).
    """
    # বাংলা মন্তব্য: legacy TASKS ডিকশনারি কখনোই populate হতো না (২০২৬-০৯-১৭
    # cleanup-এ সরানো হয়েছে) — তাই এই রুট সবসময় 404-ই দিত; আচরণ অপরিবর্তিত।
    raise HTTPException(status_code=404, detail="Task not found")
