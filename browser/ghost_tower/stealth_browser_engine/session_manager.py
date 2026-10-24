"""CDP/Playwright session lifecycle wrapper (fail-closed capabilities).

The runtime tier supports two attachment modes:
  1. Playwright-managed launch (`mode="playwright"`) — requires the optional
     playwright package; imported LAZILY inside `start()` so that importing
     this module never fails in offline verification environments.
  2. Direct CDP attachment (`mode="cdp"`) — records a ws/http endpoint and
     validates its scheme without opening sockets (connection happens in the
     execution tier, never in CI).

No method here performs I/O at import time; `close()` is idempotent.
"""

from __future__ import annotations

from .config import BrowserProfile, get_profile

__all__ = [
    "BrowserSessionManager",
    "RuntimeCapabilityError",
    "playwright_available",
]


class RuntimeCapabilityError(RuntimeError):
    """Raised when a requested runtime capability is not installed."""


def playwright_available() -> bool:
    """Capability probe (import-time side-effect free)."""
    try:
        import playwright  # noqa: F401  # capability probe: import success/failure IS the check
    except ImportError:
        return False
    return True


class BrowserSessionManager:
    """Owns one browser session lifecycle; usable as a context manager."""

    def __init__(
        self,
        profile: BrowserProfile | None = None,
        cdp_endpoint: str | None = None,
        headless: bool = True,
    ) -> None:
        if profile is None:
            profile = get_profile("windows_chrome_stable")
        profile.validate()
        self.profile = profile
        self.headless = bool(headless)
        self._cdp_endpoint: str | None = None
        self._session_started = False
        self._closed = False
        if cdp_endpoint is not None:
            self.attach_cdp(cdp_endpoint)

    # -- state ------------------------------------------------------------
    @property
    def mode(self) -> str:
        return "cdp" if self._cdp_endpoint else "playwright"

    @property
    def cdp_endpoint(self) -> str | None:
        return self._cdp_endpoint

    @property
    def started(self) -> bool:
        return self._session_started

    # -- lifecycle ---------------------------------------------------------
    def attach_cdp(self, endpoint: str) -> None:
        """Validate and record a CDP endpoint (no socket is opened here)."""
        if not endpoint or not isinstance(endpoint, str):
            raise ValueError("cdp endpoint must be a non-empty string")
        lowered = endpoint.lower()
        if not lowered.startswith(("ws://", "wss://", "http://", "https://")):
            raise ValueError(
                "cdp endpoint must use ws://, wss://, http:// or https:// scheme"
            )
        self._cdp_endpoint = endpoint

    def start(self) -> BrowserSessionManager:
        """Begin the session; fail-closed with a precise capability error."""
        if self._closed:
            raise RuntimeError("session already closed; create a new manager")
        if self._session_started:
            return self
        if self._cdp_endpoint:
            # CDP attachment is validated here; socket work belongs to the
            # execution tier and is never performed during verification.
            self._session_started = True
            return self
        if not playwright_available():
            raise RuntimeCapabilityError(
                "playwright is not installed; install with: "
                "pip install playwright && playwright install chromium "
                "— or attach a CDP endpoint instead"
            )
        # Execution tier hook: the actual launch is performed by the caller
        # integration; the seed keeps the runtime importable and testable.
        self._session_started = True
        return self

    def close(self) -> None:
        """Idempotent shutdown."""
        self._closed = True
        self._session_started = False

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> BrowserSessionManager:
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
