"""
Backward compatibility bridge: re-export all from browser_action_registry.
Preserves legacy imports for 'api.routes.site_actions' and 'backend.api.routes.site_actions'.
"""

from api.routes.browser_action_registry import (  # noqa: F401
    DB_PATH,
    SiteActionIn,
    TestSelectorRequest,
    _conn,
    _ensure_schema,
    _lock,
    _row_to_dict,
    create_site_action,
    delete_site_action,
    list_site_actions,
    router,
    test_selector,
    update_site_action,
)

__all__ = [
    "DB_PATH",
    "SiteActionIn",
    "TestSelectorRequest",
    "_conn",
    "_ensure_schema",
    "_lock",
    "_row_to_dict",
    "create_site_action",
    "delete_site_action",
    "list_site_actions",
    "router",
    "test_selector",
    "update_site_action",
]
