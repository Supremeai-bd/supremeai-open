"""Browser router (``/api/browser``) — package layout.

Formerly a single ~1,507-line module (api/routes/browser.py); now split into
cohesive submodules. The public contract is unchanged:

* ``from api.routes.browser import router`` still yields one
  :class:`fastapi.APIRouter` with prefix ``/api/browser``, tag ``browser``
  and the same ``get_current_user_token`` router-level dependency;
* every route, Pydantic model, helper and module-level state singleton the
  old module exposed is still importable from this package (the
  ``from ._<module> import ...`` statements below double as re-exports);
* routes are registered on ``router`` in exactly the original order (the
  submodule imports below are intentionally ordered to reproduce the old
  file top-to-bottom), so OpenAPI output and route matching are identical;
* ``tests/core/test_browser_credentials.py`` clears
  ``CREDENTIALS`` / ``RECENT_ACTIVITIES`` / ``FINDINGS`` through
  this package namespace — the re-exported names are the SAME objects the
  endpoint modules use, so the in-place ``.clear()`` calls behave exactly
  as they did against the monolithic module.

State-singleton placement note: singletons that are only ever mutated in
place (item assignment / append / pop / clear) live in ``_state.py`` or with
their endpoint group and are shared by import. The two singletons that are
REBOUND via ``global`` (``CREDENTIALS`` in ``delete_credential``,
``URL_PERMISSIONS`` in ``delete_url``) live in the same module as the
endpoints that rebind them, preserving old ``global`` semantics.

Import cycle note: the ``_*.py`` submodules import ``router`` from this
package while it is still being initialised. That is safe because ``router``
is defined BEFORE the submodule imports run.

Import-time side effects (scraper-service URL read + ``MultiLevelCache``
instantiation) live only in ``_scraping.py``, mirroring the monolithic
module where they ran once at import time."""

import asyncio  # noqa: F401  (module-attr parity with pre-split module)
import hashlib  # noqa: F401  (module-attr parity with pre-split module)
import ipaddress  # noqa: F401  (module-attr parity with pre-split module)
import json  # noqa: F401  (module-attr parity with pre-split module)
import os  # noqa: F401  (module-attr parity with pre-split module)
import socket  # noqa: F401  (module-attr parity with pre-split module)
import urllib.error  # noqa: F401  (module-attr parity with pre-split module)
import urllib.request  # noqa: F401  (module-attr parity with pre-split module)
import uuid  # noqa: F401  (module-attr parity with pre-split module)
from datetime import UTC, datetime  # noqa: F401  (module-attr parity)
from typing import Any, Literal  # noqa: F401  (module-attr parity)
from urllib.parse import urlparse  # noqa: F401  (module-attr parity)

import httpx  # noqa: F401  (module-attr parity with pre-split module)
from fastapi import APIRouter, Depends, HTTPException, Response  # noqa: F401  (module-attr parity)
from pydantic import BaseModel, Field  # noqa: F401  (module-attr parity)

from api.deps import get_current_tenant, get_current_user_token  # noqa: F401  (module-attr parity)
from api.routes.admin_dashboard import require_admin_token  # noqa: F401  (module-attr parity)
from core.browser_compat_store import browser_compat_store  # noqa: F401  (module-attr parity)
from core.browser_session_catalog import (  # noqa: F401  (module-attr parity)
    SavedBrowserSession,
    browser_session_catalog,
)
from core.browser_session_manager import session_manager  # noqa: F401  (module-attr parity)
from core.cache.redis_manager import MultiLevelCache  # noqa: F401  (module-attr parity)
from core.config import settings  # noqa: F401  (module-attr parity with pre-split module)
from core.effective_policy import get_effective_policy, policy_store  # noqa: F401  (parity)
from core.errors.error_bus import with_error_bus  # noqa: F401  (module-attr parity)
from core.kernel.audit_logger import AuditLogger  # noqa: F401  (module-attr parity)
from core.logging_config import logger  # noqa: F401  (module-attr parity)
from core.neon_repository import (  # noqa: F401  (module-attr parity)
    create_task as create_neon_task,
)
from core.neon_repository import (  # noqa: F401  (module-attr parity)
    delete_task as delete_neon_task,
)
from core.neon_repository import (  # noqa: F401  (module-attr parity)
    list_tasks as list_neon_tasks,
)
from core.neon_repository import (  # noqa: F401  (module-attr parity)
    load_policy as load_neon_policy,
)
from core.neon_repository import (  # noqa: F401  (module-attr parity)
    save_policy as save_neon_policy,
)
from core.neon_repository import (  # noqa: F401  (module-attr parity)
    update_task_status as update_neon_task_status,
)
from core.security.secure_credential_store import (  # noqa: F401  (module-attr parity)
    SecureCredentialStore,
)
from core.task_policy import evaluate_goal  # noqa: F401  (module-attr parity)
from tools.ai_agents.browser_agent import BrowseRequest  # noqa: F401  (module-attr parity)

router = APIRouter(
    prefix="/api/browser", tags=["browser"], dependencies=[Depends(get_current_user_token)]
)

# ── Submodule imports below register routes on ``router`` in EXACTLY the
#    original single-file order. Do not reorder. ────────────────────────────

from . import (
    _automation,  # noqa: F401,E402  (route registration + re-exports)
    _cognitive,  # noqa: F401,E402  (route registration + re-exports)
    _credentials,  # noqa: F401,E402  (route registration + re-exports)
    _crown_jewel,  # noqa: F401,E402  (route registration + re-exports)
    _learning,  # noqa: F401,E402  (route registration + re-exports)
    _legacy_status,  # noqa: F401,E402  (route registration + re-exports)
    _policy,  # noqa: F401,E402  (route registration + re-exports)
    _render_proxy,  # noqa: F401,E402  (route registration + re-exports)
    _scraping,  # noqa: F401,E402  (route registration + re-exports)
    _session_store,  # noqa: F401,E402  (route registration + re-exports)
    _state,  # noqa: F401,E402  (shared in-place-mutation state)
    _surf_actions,  # noqa: F401,E402  (route registration + re-exports)
    _surf_controls,  # noqa: F401,E402  (route registration + re-exports)
    _tasks,  # noqa: F401,E402  (route registration + re-exports)
    _url_permissions,  # noqa: F401,E402  (route registration + re-exports)
)
from ._automation import (  # noqa: F401,E402  (re-exports)
    AutomationSessionRequest,
    BrowserActionRequest,
    BrowserSessionResponse,
    SavedSessionRequest,
    close_automation_session,
    create_automation_session,
    execute_automation_action,
    list_automation_sessions,
    list_saved_sessions,
    pause_automation,
    resume_automation,
    revoke_saved_session,
    save_session,
)
from ._cognitive import (  # noqa: F401,E402  (re-exports)
    SemanticClickRequest,
    SwarmExploreRequest,
    explore_swarm,
    run_autonomous_goal,
    semantic_click,
    smart_click,
)
from ._credentials import (  # noqa: F401,E402  (re-exports)
    CREDENTIALS,
    CredentialRequest,
    CredentialUseRequest,
    delete_credential,
    get_audit,
    get_credential_store,
    get_credentials,
    revoke_credential,
    save_credential,
    use_credential,
)
from ._crown_jewel import (  # noqa: F401,E402  (re-exports)
    AIActionRequest,
    BrowseSessionRequest,
    ScreenshotRequest,
    SecurityScanRequest,
    ai_action,
    browse_session,
    capture_screenshot,
    execute_step,
    save_screenshot_to_gallery,
    security_scan,
)
from ._health import (  # noqa: F401,E402  (re-exports)
    browser_service_health,
    public_router,  # dependency-free /health probe (#1490 contract, #2258 port)
)
from ._learning import (  # noqa: F401,E402  (re-exports)
    SYSTEM_LEARNING,
    ToggleLearningRequest,
    get_system_learning,
    toggle_learning,
)
from ._legacy_status import (  # noqa: F401,E402  (re-exports)
    get_recent_activity,
    get_status,
    start_surf,
    stop_surf,
)
from ._policy import (  # noqa: F401,E402  (re-exports)
    PolicyUpdateRequest,
    UserPolicyUpdateRequest,
    get_policy,
    get_tasks,
    update_admin_policy,
    update_user_policy,
)
from ._render_proxy import (  # noqa: F401,E402  (re-exports)
    _BLOCKED_NETS,
    _frame_ancestors_sources,
    _host_is_blocked,
    render_proxy,
)
from ._scraping import (  # noqa: F401,E402  (re-exports)
    _SCRAPE_CACHE_TTL,
    _SCRAPER_URL,
    ScrapeRequest,
    _cached_scrape,
    _proxy_to_scraper,
    _scrape_cache,
    _scrape_cache_key,
    browse,
    extract,
    scrape,
)
from ._session_store import (  # noqa: F401,E402  (re-exports)
    SESSIONS,
    SessionIn,
    SessionMessageIn,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    update_session,
)
from ._state import BROWSER_STATUS, RECENT_ACTIVITIES  # noqa: F401,E402  (re-exports)
from ._surf_actions import (  # noqa: F401,E402  (re-exports)
    ClickAtRequest,
    ClickRequest,
    FillRequest,
    KeyRequest,
    NavigateRequest,
    SimulateActivityRequest,
    click,
    click_at,
    fill,
    get_accessibility_tree,
    get_screenshot,
    navigate,
    simulate_activity,
    type_key,
)
from ._surf_controls import (  # noqa: F401,E402  (re-exports)
    PAUSED_STATE,
    SurfControlRequest,
    get_paused_state,
    pause_manual,
    resume_surf,
    skip_auth,
)
from ._tasks import (  # noqa: F401,E402  (re-exports)
    EXECUTION_CAP_MS,
    FINDINGS,
    GoalRequest,
    TaskPreviewRequest,
    _set_task_status,
    add_finding,
    create_task,
    delete_task,
    get_findings,
    preview_task,
    set_task_circuit_open,
    set_task_complete,
    set_task_failed,
)
from ._url_permissions import (  # noqa: F401,E402  (re-exports)
    PERMISSION_REQUESTS,
    URL_PERMISSIONS,
    DecisionRequest,
    UrlPermissionRequest,
    add_allowed_url,
    add_denied_url,
    allow_all_urls,
    decision,
    delete_url,
    get_allowed_urls,
    get_denied_urls,
    get_requests,
)
