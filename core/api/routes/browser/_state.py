"""Shared legacy UI-state singletons for the browser compat endpoints.

Split out of the former single-module api/routes/browser.py verbatim.
These are mutated strictly IN PLACE (item assignment / ``.append``) by the
endpoint modules, so a single shared instance here preserves the old
module-global semantics. Names that are ever *rebound* via ``global``
(CREDENTIALS, URL_PERMISSIONS) deliberately live in their endpoint modules
instead, so the rebinding still hits the namespace the endpoints read.
"""

from typing import Any

# Legacy UI state is retained for compatibility while canonical automation is owner-scoped.
# New endpoints should use browser_compat_store; these aliases are migration shims.
BROWSER_STATUS: dict[str, Any] = {"browsing": False, "currentUrl": "about:blank"}
RECENT_ACTIVITIES: list[dict[str, Any]] = []
