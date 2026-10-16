"""Public surface for the SupremeAI stealth browser sandbox (issue #335).

Fail-closed exports only: every public name below is safe to import without
any third-party dependency present. The Playwright-backed engine is a lazy
adapter inside :mod:`sandbox.browser_runtime` and is never imported at module
load time, so `import sandbox` stays dependency-free and offline-safe.
"""

from sandbox.browser_runtime import (
    BrowserEngine,
    BrowserRuntime,
    EngineCrashedError,
    EngineUnavailableError,
    InvalidArgumentError,
    MockEngine,
    NavigationBlockedError,
    NavigationPolicy,
    PlaywrightEngine,
    ProxyConfig,
    ProxyPool,
    ProxyPoolExhaustedError,
    RateLimitCooldownError,
    RuntimeTimeoutError,
    StealthProfile,
    TOOL_CATALOG,
    TOOL_NAMES,
    invoke_tool,
)

__all__ = [
    "BrowserEngine",
    "BrowserRuntime",
    "EngineCrashedError",
    "EngineUnavailableError",
    "InvalidArgumentError",
    "MockEngine",
    "NavigationBlockedError",
    "NavigationPolicy",
    "PlaywrightEngine",
    "ProxyConfig",
    "ProxyPool",
    "ProxyPoolExhaustedError",
    "RateLimitCooldownError",
    "RuntimeTimeoutError",
    "StealthProfile",
    "TOOL_CATALOG",
    "TOOL_NAMES",
    "invoke_tool",
]

__version__ = "1.0.0"
