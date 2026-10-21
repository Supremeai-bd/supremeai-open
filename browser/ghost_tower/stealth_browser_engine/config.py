"""Browser profile configurations for the supremeai-browser runtime.

Fail-closed design:
  - Every profile is a frozen value object; mutating a copy is the only path.
  - Presets describe STANDARD, widely deployed fingerprints (no exotic or
    randomized vendor strings; see stealth_profile for coherent noise).
  - Nothing here performs I/O, so importing this module is always safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

__all__ = [
    "PRESETS",
    "BrowserProfile",
    "get_profile",
    "profile_names",
]


@dataclass(frozen=True)
class BrowserProfile:
    """Immutable description of one browser identity."""

    name: str
    user_agent: str
    viewport: tuple[int, int] = (1920, 1080)
    locale: str = "en-US"
    timezone_id: str = "UTC"
    device_scale_factor: float = 1.0
    is_mobile: bool = False
    has_touch: bool = False
    stealth_level: int = 2  # 0=off, 1=basic, 2=hardened, 3=max
    extra_headers: dict[str, str] = field(default_factory=dict)

    def with_overrides(self, **overrides) -> BrowserProfile:
        """Return a modified copy; unknown fields raise TypeError (fail-closed)."""
        return replace(self, **overrides)

    def validate(self) -> None:
        """Raise ValueError when any invariant is violated."""
        if not self.name or not self.name.strip():
            raise ValueError("profile name must be non-empty")
        width, height = self.viewport
        if not (200 <= width <= 7680 and 200 <= height <= 4320):
            raise ValueError(f"viewport out of supported range: {self.viewport}")
        if self.device_scale_factor <= 0:
            raise ValueError("device_scale_factor must be positive")
        if not 0 <= self.stealth_level <= 3:
            raise ValueError("stealth_level must be within 0..3")
        ua = self.user_agent
        if not ua or len(ua) < 40 or len(ua) > 512:
            raise ValueError("user_agent missing or implausible length")
        for header in self.extra_headers:
            if ":" in header:
                raise ValueError(f"header name must not contain colon: {header!r}")


_PRESET_LIST = [
    BrowserProfile(
        name="windows_chrome_stable",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        stealth_level=2,
    ),
    BrowserProfile(
        name="windows_edge_stable",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0"
        ),
        stealth_level=2,
    ),
    BrowserProfile(
        name="macos_safari_stable",
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.6 Safari/605.1.15"
        ),
        viewport=(1728, 1117),
        stealth_level=1,
    ),
    BrowserProfile(
        name="linux_firefox_esr",
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
        ),
        stealth_level=1,
    ),
    BrowserProfile(
        name="mobile_android_chrome",
        user_agent=(
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36"
        ),
        viewport=(412, 915),
        device_scale_factor=2.625,
        is_mobile=True,
        has_touch=True,
        stealth_level=2,
    ),
]

PRESETS: dict[str, BrowserProfile] = {p.name: p for p in _PRESET_LIST}


def get_profile(name: str) -> BrowserProfile:
    """Fetch a preset by name; unknown names fail closed with a clear error."""
    try:
        return PRESETS[name]
    except KeyError:
        known = ", ".join(sorted(PRESETS))
        raise KeyError(f"unknown profile {name!r}; known profiles: {known}") from None


def profile_names() -> tuple[str, ...]:
    """Sorted preset names (stable for tests and docs)."""
    return tuple(sorted(PRESETS))
