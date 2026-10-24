"""Legacy surf action endpoints — RETIRED (Wave 2.3 truth purge, issue #1240).

FIXED 2026-09-25 (audit M04 / WAVE_MASTER_PLAN §Wave 2.3):
This module previously shipped fabricated success responses while performing
no work — a hardcoded 1x1 transparent PNG for ``/surf/screenshot``, and
navigate/click/fill/click-at/type-key handlers that only appended a string to
an in-memory activity list and returned ``success: True`` without touching any
browser (Class-G false assurance: the system reporting success while doing no
work). ``/surf/accessibility`` returned a canned tree and
``/simulate-activity`` let callers inject fabricated activity entries.

Per the "real work or loud failure" doctrine (issue #445) and the
``_crown_jewel.py`` fix precedent, every endpoint here now fails loudly with
an explicit error that points callers to the REAL owner-scoped automation
stack in ``_automation.py`` (``/api/browser/automation/*``), which performs
actual Playwright-backed work via ``core.browser_session_manager``.

The request models are retained (re-exported by the package ``__init__`` for
backward compatibility); only the fabricated endpoint behaviour is retired.

Verified 2026-09-25: zero consumers of these paths exist in frontend/src,
apps/, packages/, shared/, or backend/tests (rg scan evidence on issue #1240).
"""

from fastapi import HTTPException
from pydantic import BaseModel

from api.routes.browser import router

_REAL_AUTOMATION = (
    "Legacy surf endpoints are retired (issue #1240): they reported fabricated "
    "success without performing any browser work. Use the real owner-scoped "
    "automation stack instead: POST /api/browser/automation/sessions to create "
    "an isolated session, then POST /api/browser/automation/sessions/"
    "{session_id}/actions with action=navigate|click|fill|type|screenshot."
)


class NavigateRequest(BaseModel):
    url: str


class ClickRequest(BaseModel):
    selector: str


class FillRequest(BaseModel):
    selector: str
    value: str


class ClickAtRequest(BaseModel):
    x: int
    y: int


class KeyRequest(BaseModel):
    key: str


class SimulateActivityRequest(BaseModel):
    """Typed body for the RETIRED /simulate-activity route (issue #1657).

    The handler still fails loudly with 501, but the request is now validated
    by a Pydantic model instead of a bare ``dict``. Extras stay ignored — the
    retirement contract test posts arbitrary legacy payloads and pins the 501.
    """

    # No declared fields: the endpoint does no work and reads nothing from
    # the body. Extras are silently ignored (Pydantic default).


def _retired() -> HTTPException:
    return HTTPException(status_code=501, detail=_REAL_AUTOMATION)


@router.get("/surf/screenshot")
def get_screenshot():
    """Retired: previously returned a hardcoded 1x1 blank PNG as a fake screenshot."""
    raise _retired()


@router.post("/surf/navigate")
def navigate(req: NavigateRequest):
    """Retired: previously mutated an in-memory dict and faked success."""
    raise _retired()


@router.post("/surf/click")
def click(req: ClickRequest):
    """Retired: previously appended to an activity list and faked success."""
    raise _retired()


@router.post("/surf/fill")
def fill(req: FillRequest):
    """Retired: previously appended to an activity list and faked success."""
    raise _retired()


@router.post("/surf/click-at")
def click_at(req: ClickAtRequest):
    """Retired: previously appended to an activity list and faked success."""
    raise _retired()


@router.post("/surf/type-key")
def type_key(req: KeyRequest):
    """Retired: previously appended to an activity list and faked success."""
    raise _retired()


@router.get("/surf/accessibility")
def get_accessibility_tree():
    """Retired: previously returned a canned fabricated accessibility tree."""
    raise _retired()


@router.post("/simulate-activity")
def simulate_activity(body: SimulateActivityRequest):
    """Retired: previously let callers inject fabricated activity entries."""
    raise _retired()
