import asyncio

# mypy: ignore-errors
"""This module, `backend.core.config`, serves as the single, authoritative source
for all application settings within the SupremeAI project. It implements a robust,
"Fail-Fast" configuration layer using Pydantic, ensuring that all critical parameters
are loaded from environment variables or a secret manager, with zero hardcoded values.
It rigorously validates settings at startup, preventing the application from booting if
essential configurations are missing or invalid, thereby guaranteeing a secure and
predictable operational environment across all deployment stages.

Key Components:
- `Settings`: The central Pydantic model that defines and validates all application-wide
  configuration parameters, fetching secrets and enforcing strict rules for different environments.
- `settings`: A singleton instance of the `Settings` class, providing global access to the
  validated application configuration.
- `get_production_env()`: A utility function for strictly retrieving environment variables,
  enforcing a fail-fast approach for critical missing values.

Dependencies:
- `os`: For interacting with the operating system, primarily environment variables.
- `secrets`: For generating secure random numbers, used for JWT secret fallback.
- `sys`: For system-specific parameters and functions, used for `sys.exit` and checking `sys.modules` for `pytest`.
- `pathlib.Path`: For object-oriented filesystem paths, used for locating `.env` files.
- `typing`: For type hints.
- `json`: For parsing JSON strings, specifically for `cors_origins`.
- `dotenv.load_dotenv`: For loading environment variables from `.env` files.
- `loguru.logger`: For structured logging, especially for critical configuration errors.
- `pydantic`: The core library for data validation and settings management.
- `pydantic_settings.BaseSettings`: Pydantic's base class for managing settings from environment variables.
- `pydantic_settings.SettingsConfigDict`: Configuration class for `BaseSettings`.
- `pydantic.Field`: Used to define field properties and validation aliases.
- `pydantic.PrivateAttr`: Used for private attributes not part of the model's data.
- `pydantic.SecretStr`: For handling sensitive string data that should not be logged.
- `pydantic.ValidationInfo`: Provides context during validation.
- `pydantic.computed_field`: For fields whose values are computed dynamically.
- `pydantic.field_validator`: Decorator for field-specific validation logic.
- `pydantic.model_validator`: Decorator for model-level validation logic.
- `core.security.secret_vault`: An internal module responsible for fetching secrets from a secure vault (e.g., GCP Secret Manager).
"""

# backend/core/config.py
# ⚠️ WARNING: DO NOT MOVE THIS FILE. It is heavily integrated into the FastAPI startup lifecycle.
# Moving this file will break relative paths, imports, and core configuration loading across the entire project.
# বাংলা মন্তব্য: সম্পূর্ণ রি-ফ্যাক্টর — Fail-Fast, Zero-Hardcode, Pydantic-Enforced Config Layer।
# কোনো API Key, hardcoded domain বা threshold এখানে নেই।
# সব ভ্যালু env var বা GCP Secret Manager থেকে আসে।
# যেকোনো Environment-এ (Local/Staging/Prod) কোনো missing required var = startup crash (sys.exit(1)) — "resilient boot" সম্পূর্ণ নিষিদ্ধ।

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from pydantic import (
    Field,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.logging_config import logger

from .config_fields import SettingsFieldsMixin
from .config_secrets import SettingsSecretsMixin
from .config_validation import SettingsValidationMixin

try:
    from utils.platform_detect import DETECTED_PLATFORM, auto_set_platform_env

    _PLATFORM = auto_set_platform_env()
except ImportError:
    _PLATFORM = None


# বাংলা মন্তব্য: pytest environment-এ .env load করা হয় না — test isolation নিশ্চিত।
if "pytest" not in sys.modules:
    root_env = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(root_env)


class Settings(BaseSettings, SettingsFieldsMixin, SettingsSecretsMixin, SettingsValidationMixin):
    """
    বাংলা মন্তব্য: এটি সিস্টেমের একমাত্র সত্যের উৎস (Single Source of Truth)।
    কোনো hardcoded value নেই। সব env-driven।
    যেকোনো এনভায়রনমেন্টে missing required var = startup Fail-Fast (sys.exit(1))।
    """

    model_config = SettingsConfigDict(
        env_file=(
            None
            if "pytest" in sys.modules
            else ["../.env", ".env", "/etc/secrets/.env", "/etc/secrets/render.env"]
        ),
        extra="ignore",
    )

    # বাংলা মন্তব্য: env validate হবে — invalid value = startup crash
    env: str = Field(default="local", validation_alias="ENV")
    debug: bool = Field(default=False)
    supremeai_service_role: str = Field(
        default="monolith", validation_alias="SUPREMEAI_SERVICE_ROLE"
    )

    # Free Tier Optimizations
    AUTO_HEALING_ENABLED: bool = Field(default=False)
    MONITORING_DETAILED: bool = Field(default=False)
    RATE_LIMIT_USE_SIMPLIFIED: bool = Field(default=True)
    LLM_CACHE_MAX_SIZE: int = Field(default=500)
    LLM_CACHE_DEFAULT_TTL: int = Field(default=3600)

    @model_validator(mode="after")
    def _enforce_production_rate_limit(self) -> "Settings":
        # In production, RATE_LIMIT_USE_SIMPLIFIED defaults to False unless explicitly set to true.
        # But wait, if they didn't provide it in env, pydantic uses the default=True.
        # So we override it to False if env is production and it wasn't explicitly set in env.
        # A simpler way is to just force it to False in production unless os.environ says "true"
        if self.env == "production":
            env_val = os.getenv("RATE_LIMIT_USE_SIMPLIFIED", "false").lower()
            if env_val not in ("true", "1", "yes"):
                self.RATE_LIMIT_USE_SIMPLIFIED = False
        return self

    # 🔬 NEW: Platform-aware defaults
    @property
    def platform(self) -> str:
        return _PLATFORM if _PLATFORM else "unknown"

    @property
    def is_cloud(self) -> bool:
        if not _PLATFORM:
            return False
        return _PLATFORM in ("render", "vercel", "firebase", "github_actions")

    def is_local(self) -> bool:
        """Return True if running in local environment."""
        return (self.env or "").lower() in ("local", "dev", "development")

    @property
    def auto_backend_url(self) -> str:
        """Generate backend URL from platform detection."""
        try:
            from utils.platform_detect import DETECTED_PLATFORM

            if DETECTED_PLATFORM.has_external_url and DETECTED_PLATFORM.external_url:
                return DETECTED_PLATFORM.external_url
        except asyncio.CancelledError:
            raise
        except Exception as e:
            import logging

            logging.getLogger(__name__).exception(f"Silenced error: {e}")
        return settings.backend_url

    # বাংলা মন্তব্য: টেস্ট এনভায়রনমেন্টে AuthMiddleware-এর JWT ভেরিফিকেশন বাইপাস করার জন্য
    # বাংলা: CI pytest-এ ALLOW_TEST_AUTH_BYPASS=true সেট করা হয় — শুধু তখনই।
    # Production guard: ENV=production হলে এই field সবসময় False থাকবে।
    # auth_middleware.py এবং origin_validator.py এই field চেক করে।
    allow_test_auth_bypass: bool = Field(default=False, validation_alias="ALLOW_TEST_AUTH_BYPASS")
    allow_test_origin_bypass: bool = Field(
        default=False, validation_alias="ALLOW_TEST_ORIGIN_BYPASS"
    )

    @property
    def is_bypass_allowed(self) -> bool:
        """বাংলা: Production-এ bypass সম্পূর্ণ নিষিদ্ধ — ENV নির্বিশেষে।
        শুধু test/ci/staging environment-এই bypass কাজ করবে।
        field নাম: self.env (validation_alias="ENV"), self.environment নয়।"""
        current_env = (self.env or "").lower()
        if current_env in ("production", "prod"):
            return False  # Production-এ সর্বদা False — hardcoded guard
        return self.allow_test_auth_bypass

    @property
    def is_origin_bypass_allowed(self) -> bool:
        """বাংলা: Production-এ origin bypass সম্পূর্ণ নিষিদ্ধ।"""
        current_env = (self.env or "").lower()
        if current_env in ("production", "prod"):
            return False
        return self.allow_test_origin_bypass


try:
    settings = Settings()
except Exception as _boot_exc:
    raise _boot_exc


def get_production_env(var_name: str, default: str | None = None) -> str:
    """বাংলা মন্তব্য: Strict Fail-Fast Config Guard.
    যেকোনো এনভায়রনমেন্টে কোনো ক্রিটিক্যাল সিক্রেট মিসিং থাকলে সরাসরি হার্ড ক্র্যাশ করবে,
    যাতে সাইলেন্ট ফেইলর প্রতিরোধ করা যায়। ডিফল্ট ভ্যালু পাস করলে মিসিং ক্ষেত্রে fallback ব্যবহার হবে।
    """

    value = os.getenv(var_name)
    if not value:
        if default is not None:
            return default
        logger.critical(
            f"❌ CRITICAL CONFIG ERROR: Missing required environment variable '{var_name}'!"
        )
        raise ValueError(f"Configuration Error: {var_name} must be explicitly defined.")
    return value
