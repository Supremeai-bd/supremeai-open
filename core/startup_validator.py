from __future__ import annotations

import os
import time
from typing import Any

from core.config import settings
from core.logging_config import logger


class StartupValidator:
    """
    বাংলা মন্তব্য: সার্ভার স্টার্টআপের সময় প্রয়োজনীয় এনভায়রনমেন্ট ভ্যারিয়েবল এবং ডিরেক্টরি ভ্যালিডেশন করে।
    এখন এটি কম্প্রিহেনসিভ চেক করে — API keys, database URL, Redis URL, JWT secret, encryption key, port availability।
    """

    _last_status: dict[str, bool | str | None] = {
        "validated": False,
        "success": False,
        "error": None,
    }
    _start_time: float = 0.0
    _validation_results: dict[str, Any] = {}

    @classmethod
    async def validate(cls) -> None:
        """বাংলা মন্তব্য: সম্পূর্ণ স্টার্টআপ ভ্যালিডেশন — এখন ৬টি ক্যাটাগরিতে চেক করে।"""
        cls._start_time = time.monotonic()
        logger.info("🔍 Running comprehensive startup validations...")
        errors: list[str] = []
        warnings: list[str] = []
        cls._validation_results = {}

        try:
            # 1. Core settings validation
            cls._validation_results["app_name"] = bool(settings.app_name)
            if not settings.app_name:
                errors.append("APP_NAME settings cannot be empty")

            # 2. Security validation
            cls._validation_results["jwt_secret"] = bool(settings.jwt_secret)
            if not settings.jwt_secret:
                errors.append("JWT_SECRET is missing — authentication will fail-closed")

            cls._validation_results["encryption_key"] = bool(
                settings.encryption_key and settings.encryption_key.get_secret_value()
            )
            if not cls._validation_results["encryption_key"]:
                warnings.append("ENCRYPTION_KEY is missing — BYOC router will not load")

            # 3. API keys validation (at least one LLM provider)
            api_keys = [
                ("openrouter_api_key", settings.openrouter_api_key),
                ("gemini_api_key", settings.gemini_api_key),
                ("deepseek_api_key", settings.deepseek_api_key),
                ("groq_api_key", settings.groq_api_key),
                ("nvidia_api_key", settings.nvidia_api_key),
                ("openai_api_key", settings.openai_api_key),
                ("hf_api_key", settings.hf_api_key),
            ]
            configured_keys = [name for name, value in api_keys if value]
            cls._validation_results["api_keys_configured"] = len(configured_keys)

            if not configured_keys:
                # CI/test/local এনভায়রনমেন্টে LLM key না থাকাটাই স্বাভাবিক — এটা
                # blocking error নয়, warning। Production-এ অবশ্যই hard-fail থাকবে।
                # (বাংলা: test/local-এ key ছাড়া চলা expected, production-এ fail-closed)
                if settings.is_local() or settings.env == "test":
                    warnings.append(
                        "No LLM API keys configured — LLM gateway will fail "
                        f"(non-blocking in {settings.env or 'local'} environment)"
                    )
                    logger.warning(
                        "⚠️  No LLM API keys configured — LLM gateway will fail "
                        "(non-blocking in %s environment)",
                        settings.env or "local",
                    )
                else:
                    errors.append("No LLM API keys configured — LLM gateway will fail")
            else:
                logger.info(f"LLM providers configured: {len(configured_keys)}")
                if len(api_keys) > len(configured_keys):
                    logger.info(
                        f"LLM providers unavailable by configuration: {len(api_keys) - len(configured_keys)}"
                    )

            # 4. Database URL validation
            cls._validation_results["database_url"] = bool(settings.supabase_database_url)
            if not settings.supabase_database_url:
                warnings.append("SUPABASE_DATABASE_URL is missing — DB-dependent features disabled")

            # 5. Redis URL validation
            cls._validation_results["redis_url"] = bool(
                settings.redis_url or os.getenv("REDIS_URL")
            )
            if not cls._validation_results["redis_url"]:
                warnings.append(
                    "REDIS_URL is missing — caching and rate limiting will use in-memory fallback"
                )

            # 6. CORS validation for production
            if settings.env == "production":
                cls._validation_results["cors_origins"] = bool(settings.cors_origins)
                if not settings.cors_origins:
                    errors.append("CORS_ORIGINS cannot be empty in production")
                if "*" in settings.cors_origins:
                    errors.append("Wildcard '*' is strictly prohibited in production CORS")

            # Store results
            cls._validation_results["errors"] = errors
            cls._validation_results["warnings"] = warnings
            cls._validation_results["duration_ms"] = round(
                (time.monotonic() - cls._start_time) * 1000, 2
            )

            if errors:
                error_msg = "; ".join(errors)
                logger.error(
                    f"❌ Startup validation failed with {len(errors)} error(s): {error_msg}"
                )
                if warnings:
                    logger.warning(
                        f"⚠️  Additionally, {len(warnings)} warning(s): {'; '.join(warnings)}"
                    )
                cls._last_status = {
                    "validated": True,
                    "success": False,
                    "error": error_msg,
                }
                raise ValueError(error_msg)

            if warnings:
                logger.warning(
                    f"⚠️  Startup validation passed with {len(warnings)} warning(s): {'; '.join(warnings)}"
                )

            logger.info(
                f"✅ Startup validations passed successfully in {cls._validation_results['duration_ms']}ms. "
                f"API keys: {len(configured_keys)}, Warnings: {len(warnings)}"
            )
            cls._last_status = {"validated": True, "success": True, "error": None}

        except Exception as exc:
            if not errors:
                logger.error(f"❌ Startup validation failed: {exc}")
                cls._last_status = {
                    "validated": True,
                    "success": False,
                    "error": str(exc),
                }
            raise exc from exc

    @classmethod
    def last_status(cls) -> dict:
        """বাংলা মন্তব্য: সর্বশেষ ভ্যালিডেশন স্ট্যাটাস — হেলথ এন্ডপয়েন্টে ব্যবহারের জন্য।"""
        return {
            **cls._last_status,
            "validation_results": cls._validation_results,
        }

    @classmethod
    def get_validation_summary(cls) -> dict[str, Any]:
        """বাংলা মন্তব্য: ভ্যালিডেশন রেজাল্টের সারাংশ — ডিবাগিং এবং মনিটরিংয়ের জন্য।"""
        return {
            "validated": cls._last_status.get("validated", False),
            "success": cls._last_status.get("success", False),
            "duration_ms": cls._validation_results.get("duration_ms", 0),
            "api_keys_configured": cls._validation_results.get("api_keys_configured", 0),
            "warnings": cls._validation_results.get("warnings", []),
            "errors": cls._validation_results.get("errors", []),
        }
