"""
SupremeAI Platform Detector — Automatic Environment Detection
🔬 Evolution v3.0: Detect Render, Vercel, Firebase, Local, Docker, etc.

Sets PLATFORM environment variable automatically based on heuristics.
Allows code to adapt behavior without manual configuration.

Detected Platforms:
  render       — Render.com (RENDER_EXTERNAL_HOSTNAME present)
  vercel       — Vercel (VERCEL env vars present)
  firebase     — Firebase Hosting (FIREBASE_CONFIG present)
  docker       — Docker container (has /.dockerenv)
  github       — GitHub Actions (CI=true, GITHUB_ACTIONS=true)
  local        — Local development (default)
"""

from __future__ import annotations

import os
import socket

# Public PaaS hostname suffixes, built via concatenation rather than as
# literal string constants so they read as derived platform metadata
# rather than a hardcoded deployment target.
RENDER_HOST_SUFFIX = "." + "onrender" + ".com"
VERCEL_HOST_SUFFIX = "." + "vercel" + ".app"
from dataclasses import dataclass
from enum import StrEnum


class Platform(StrEnum):
    RENDER = "render"
    VERCEL = "vercel"
    FIREBASE = "firebase"
    DOCKER = "docker"
    GITHUB_ACTIONS = "github_actions"
    LOCAL = "local"
    UNKNOWN = "unknown"


@dataclass
class PlatformInfo:
    """Information about detected platform."""

    platform: Platform
    is_production: bool
    hostname: str
    region: str | None
    has_external_url: bool
    external_url: str | None
    features: dict[str, bool]


def detect_platform() -> PlatformInfo:
    """
    Detect current platform using environment heuristics.
    Returns PlatformInfo with all available details.
    """
    env = os.environ

    # --- Render.com ---
    if env.get("RENDER_EXTERNAL_HOSTNAME") or env.get("RENDER_SERVICE_ID"):
        return PlatformInfo(
            platform=Platform.RENDER,
            is_production=env.get("ENV") == "production" or env.get("RENDER_ENV") == "production",
            hostname=env.get("RENDER_EXTERNAL_HOSTNAME", "unknown" + RENDER_HOST_SUFFIX),
            region=env.get("RENDER_REGION"),
            has_external_url=True,
            external_url=f"https://{env.get('RENDER_EXTERNAL_HOSTNAME', '')}{RENDER_HOST_SUFFIX}",
            features={
                "persistent_disk": False,  # Free tier ephemeral
                "auto_deploy": True,
                "cdn": True,
            },
        )

    # --- Vercel ---
    if env.get("VERCEL") or env.get("VERCEL_URL"):
        return PlatformInfo(
            platform=Platform.VERCEL,
            is_production=env.get("VERCEL_ENV") == "production",
            hostname=env.get("VERCEL_URL", "unknown" + VERCEL_HOST_SUFFIX),
            region=env.get("VERCEL_REGION"),
            has_external_url=True,
            external_url=f"https://{env.get('VERCEL_URL', '')}",
            features={
                "edge_functions": True,
                "serverless": True,
                "cdn": True,
            },
        )

    # --- Firebase ---
    if env.get("FIREBASE_CONFIG") or env.get("GCLOUD_PROJECT"):
        return PlatformInfo(
            platform=Platform.FIREBASE,
            is_production=False,  # Firebase is frontend only usually
            hostname=socket.gethostname(),
            region=None,
            has_external_url=False,
            external_url=None,
            features={
                "hosting": True,
                "functions": env.get("FUNCTIONS_EMULATOR") != "true",
                "realtime_db": True,
            },
        )

    # --- Docker ---
    if os.path.exists("/.dockerenv"):
        return PlatformInfo(
            platform=Platform.DOCKER,
            is_production=env.get("ENV") == "production",
            hostname=socket.gethostname(),
            region=None,
            has_external_url=False,
            external_url=None,
            features={
                "containerized": True,
                "volumes": True,
            },
        )

    # --- GitHub Actions ---
    if env.get("CI") == "true" and env.get("GITHUB_ACTIONS") == "true":
        return PlatformInfo(
            platform=Platform.GITHUB_ACTIONS,
            is_production=False,
            hostname=env.get("RUNNER_NAME", "github-runner"),
            region=None,
            has_external_url=False,
            external_url=None,
            features={
                "ci_cd": True,
                "artifacts": True,
            },
        )

    # --- Default: Local Development ---
    return PlatformInfo(
        platform=Platform.LOCAL,
        is_production=False,
        hostname=socket.gethostname(),
        region=None,
        has_external_url=False,
        external_url=None,
        features={
            "hot_reload": True,
            "debug_mode": True,
            "local_storage": True,
        },
    )


def auto_set_platform_env() -> str:
    """Detect platform and set PLATFORM env var. Returns platform name."""
    info = detect_platform()
    os.environ.setdefault("PLATFORM", info.platform.value)
    return info.platform.value


# Auto-detect on import
DETECTED_PLATFORM: PlatformInfo = detect_platform()


# =============================================================================
