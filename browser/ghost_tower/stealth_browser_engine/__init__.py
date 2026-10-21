"""supremeai-browser runtime: stealth automation sandbox foundation.

Package surface (issue #502 seed-foundation):
  - config: BrowserProfile presets (immutable, validated)
  - stealth_profile: coherent deterministic fingerprints + natural input
  - session_manager: Playwright/CDP lifecycle with fail-closed capabilities
  - semantic_extractor: token-saving semantic DOM trees
  - content_pruner: Crawl4AI-pattern boilerplate pruning to Markdown
  - infinite_scanner: scroll planning + lazy-load expansion
  - cookie_bridge: walled-garden session import/export

Core is stdlib-only; playwright/lxml are OPTIONAL execution-tier extras.
"""
from .config import BrowserProfile, get_profile, profile_names
from .content_pruner import ContentPruner, PrunedContent, link_density
from .cookie_bridge import (
    CookieBridge,
    CookieRecord,
    WalledGardenViolation,
)
from .infinite_scanner import FeedExpander, ScrollPlan, ScrollStep, SCROLL_AND_EXPAND_JS
from .semantic_extractor import (
    SemanticNode,
    SemanticTree,
    estimate_tokens,
    extract_semantic_tree,
)
from .session_manager import (
    BrowserSessionManager,
    RuntimeCapabilityError,
    playwright_available,
)
from .stealth_profile import StealthProfile, bezier_path, generate, webgl_pairs

__version__ = "0.1.0"

__all__ = [
    "BrowserProfile",
    "get_profile",
    "profile_names",
    "ContentPruner",
    "PrunedContent",
    "link_density",
    "CookieBridge",
    "CookieRecord",
    "WalledGardenViolation",
    "FeedExpander",
    "ScrollPlan",
    "ScrollStep",
    "SCROLL_AND_EXPAND_JS",
    "SemanticNode",
    "SemanticTree",
    "estimate_tokens",
    "extract_semantic_tree",
    "BrowserSessionManager",
    "RuntimeCapabilityError",
    "playwright_available",
    "StealthProfile",
    "bezier_path",
    "generate",
    "webgl_pairs",
    "__version__",
]
