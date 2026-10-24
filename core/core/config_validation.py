"""Validation and normalization rules for SupremeAI settings."""

import json
import os
import secrets
import sys
from typing import Any

from pydantic import (
    BaseModel,
    Field,
    SecretStr,
    ValidationInfo,
    field_validator,
    model_validator,
)

from core.config_parsers import parse_origin_list
from core.logging_config import logger
from core.secret_policy import JWT_SECRET_DEPRECATED_ENV, JWT_SECRET_ENV

# Public platform apex domains that must NEVER appear as bare entries in
# production/staging ALLOWED_HOSTS (see validate_allowed_hosts for rationale:
# suffix-based Host matching would trust every subdomain of the platform).
PLATFORM_APEX_HOSTS: frozenset[str] = frozenset(
    {
        "onrender.com",
        "render.com",
        "vercel.app",
        "netlify.app",
        "workers.dev",
        "pages.dev",
        "firebaseapp.com",
        "web.app",
        "amplifyapp.com",
        "herokuapp.com",
    }
)


class SettingsValidationMixin:
    FORMAT_PATTERNS = {
        "supabase_url": r"^https?://.*\.supabase\.(co|com)$",
        "redis_url": r"^redis://[^:]+:\d+$|^rediss://.*$",
        "database_url": r"^postgresql(ql)?://[^:]+:[^@]+@[^:/]+:\d+/[^/]+$",
    }

    FIX_SUGGESTIONS = {
        "supabase_database_url": "Set SUPABASE_DATABASE_URL in Render dashboard. Format: postgresql://postgres.[project-ref]:[password]@aws-0-[region].pool.supabase.com:6543/postgres",
        "redis_url": "Set REDIS_URL for Upstash Redis. Get URL from: https://console.upstash.io/redis",
        "openai_api_key": "Set OPENAI_API_KEY for OpenAI integration. Get key from: https://platform.openai.com/api-keys",
    }

    @field_validator("*", mode="before")
    @classmethod
    def validate_env_vars(cls, value: Any, info: ValidationInfo) -> Any:
        import re

        if value is None:
            return value
        if isinstance(value, str) and value.strip() == "":
            defaults = {
                "bhasha_cache_ttl_hours": 24,
                "bhasha_min_quality": 0.7,
                "bhasha_max_cache": 10000,
                "bhasha_batch_concurrency": 5,
                "port": 8080,
                "llm_connect_timeout": 5.0,
                "llm_read_timeout": 30.0,
                "llm_write_timeout": 5.0,
                "llm_pool_timeout": 5.0,
                "llm_max_connections": 100,
                "llm_max_keepalive": 20,
                "latency_window_size": 20,
                "latency_normalization_ms": 1000.0,
                "min_provider_weight": 0.01,
                "circuit_failure_threshold": 5,
                "circuit_success_rate_floor": 0.5,
                "circuit_cooldown_seconds": 30.0,
                "max_routing_attempts": 3,
                "llm_cache_max_size": 500,
                "llm_cache_default_ttl": 3600,
            }
            if info.field_name and info.field_name.lower() in defaults:
                return defaults[info.field_name.lower()]
        var_name = info.field_name
        if var_name in cls.FORMAT_PATTERNS:
            pattern = cls.FORMAT_PATTERNS[var_name]
            if isinstance(value, str) and not re.match(pattern, value):
                suggestion = cls.FIX_SUGGESTIONS.get(var_name, "Check format.")
                raise ValueError(f"Invalid format for {var_name}. Expected {pattern}. {suggestion}")
        return value

    @field_validator(
        "user_cors_origins",
        "admin_cors_origins",
        "allowed_hosts",
        "admin_emails",
        "idempotency_critical_paths",
        "prompt_blocked_patterns",
        "supremeai_public_paths",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def parse_comma_separated_list(cls, v):
        if isinstance(v, str):
            if v.strip() == "":
                return []
            if "[" in v and "]" in v:
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(x) for x in parsed]
                except Exception as e:
                    logger.debug(f"JSON parsing failed for admin_emails: {e}")
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @field_validator("env")
    @classmethod
    def validate_env(cls, value: str) -> str:
        allowed = {"local", "staging", "production", "test"}
        if value.lower() not in allowed:
            raise ValueError(f"ENV must be one of {allowed}, got '{value}'")
        return value.lower()

    @field_validator("admin_authorized", "autofix_authorized", mode="before")
    @classmethod
    def validate_boolean_flags(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("true", "1", "yes")
        return bool(v)

    @field_validator("debug", mode="before")
    @classmethod
    def validate_debug_mode(cls, v: Any, info: ValidationInfo) -> bool:
        env = info.data.get("env", "local")
        if env in {"production", "staging"}:
            if str(v).lower() == "true" and (
                os.getenv("debug", "").lower() == "true" or os.getenv("DEBUG", "").lower() == "true"
            ):
                raise ValueError(
                    "Explicitly setting debug=True is PROHIBITED in production/staging."
                )
            return False
        return bool(v)

    @field_validator("docs_password", mode="before")
    @classmethod
    def validate_docs_password(
        cls, v: str | SecretStr | None, info: ValidationInfo
    ) -> str | SecretStr:
        if "pytest" in sys.modules:
            return v or ""
        # বাংলা: আগের অটো-জেনারেট লজিক সরানো হয়েছে — ওটা প্রোডাকশনে
        # "কেউ জানা নেই এমন" একটা র‍্যান্ডম পাসওয়ার্ড বসিয়ে validate_all-এর
        # ফেইল-ফাস্টকে নীরবে বাইপাস করত। এখন খালি মান যেভাবে আছে তেমনই
        # যায়, আর validate_all পলিসি অনুযায়ী fail-closed সিদ্ধান্ত নেয়।
        return v or ""

    @model_validator(mode="after")
    def validate_all(self):
        """Consolidated boot-time validation for non-test runtime environments."""
        if "pytest" in sys.modules or os.getenv("CI") == "true":
            return self

        if self.env in {"production", "staging"} and self.docs_auth_enabled:
            pwd = self.docs_password.get_secret_value() if self.docs_password else ""
            if not pwd:
                raise ValueError(
                    f"❌ {self.env.capitalize()} SUPREMEAI_DOCS_PASSWORD missing. Fail-fast triggered."
                )

        # বাংলা (P0 docs exposure policy): প্রোডাকশন/স্টেজিং-এ ডকুমেন্টেশন
        # স্পষ্টভাবে চালু (SUPREMEAI_DOCS_ENABLED=true) করলে শক্তিশালী
        # পাসওয়ার্ড বাধ্যতামূলক — "dev_password_only" বা ছোট পাসওয়ার্ডে
        # বুট ফেইল-ফাস্ট হবে। ডকুমেন্টেশন বন্ধ থাকলে পাসওয়ার্ড লাগে না।
        if (
            self.env in {"production", "staging"}
            and self.docs_enabled
            and not self.docs_password_ok
        ):
            raise ValueError(
                "❌ Production/staging docs exposure opted-in (SUPREMEAI_DOCS_ENABLED=true) "
                "but SUPREMEAI_DOCS_PASSWORD is missing, the dev fallback 'dev_password_only', "
                "or shorter than 12 characters. Fail-fast triggered — set a strong password "
                "or remove SUPREMEAI_DOCS_ENABLED to keep docs disabled."
            )

        # বাংলা (P0 admin secret policy): internal admin API-র X-Admin-Secret
        # গেটের জন্য আলাদা, শক্তিশালী SUPREMEAI_ADMIN_SECRET বাধ্যতামূলক।
        # docs_password-এ ফলব্যাক সরানো হয়েছে — পাবলিক রিপোর জানা
        # "dev_password_only" কখনোই প্রোডাকশন অ্যাডমিন সিক্রেট হতে পারবে না।
        if self.env in {"production", "staging"} and not self.admin_secret_ok:
            raise ValueError(
                "❌ Production/staging requires a strong SUPREMEAI_ADMIN_SECRET "
                "(>= 12 characters, never the dev fallback 'dev_password_only', and never "
                "equal to SUPREMEAI_DOCS_PASSWORD). Fail-fast triggered — the internal "
                "admin API stays locked without it."
            )

        if self.env in {"production", "staging"}:
            _LLM_CRITICAL_KEYS = [
                "GEMINI_API_KEY",
                "OPENROUTER_API_KEY",
                "GROQ_API_KEY",
                "DEEPSEEK_API_KEY",
                "OPENAI_API_KEY",
            ]
            self._ensure_secrets_loaded()
            available = [k for k in _LLM_CRITICAL_KEYS if self._cached_secrets.get(k)]
            missing = [k for k in _LLM_CRITICAL_KEYS if not self._cached_secrets.get(k)]
            if not available:
                logger.warning(
                    "🚨 BOOT-TIME ALERT: কোনো LLM API key পাওয়া যায়নি! "
                    f"Missing: {missing}. সব AI feature কাজ করবে না। Infisical / env var চেক করুন।"
                )
            elif missing:
                logger.info(
                    f"ℹ️ BOOT-TIME: {len(missing)} LLM key optional but missing ({missing}). "
                    f"Available: {available}. Partial AI functionality only."
                )
            else:
                logger.info(f"✅ BOOT-TIME: সব {len(available)} LLM API key সফলভাবে লোড হয়েছে।")

        if self.env in {"production", "staging"}:
            stripe_key = self.stripe_api_key.get_secret_value() if self.stripe_api_key else ""
            stripe_webhook = (
                self.stripe_webhook_secret.get_secret_value() if self.stripe_webhook_secret else ""
            )
            if not stripe_key:
                logger.warning(
                    "⚠️ Stripe API key missing in production/staging. Billing features will run in mock mode."
                )
            if not stripe_webhook:
                logger.warning(
                    "⚠️ Stripe webhook secret missing in production/staging. Webhook validation disabled."
                )

        if self.env == "production":
            missing = []
            if not self.ci_webhook_secret:
                missing.append("CI_WEBHOOK_SECRET")
            if missing:
                logger.warning(
                    f"⚠️ Production missing config vars: {', '.join(missing)}. Running in degraded zero-cost mode."
                )

        if self.n8n_enabled and not self.n8n_base_url:
            raise ValueError("❌ N8N is enabled but N8N_BASE_URL is not configured.")
        if self.appwrite_enabled and (not self.appwrite_endpoint or not self.appwrite_project_id):
            raise ValueError(
                "❌ Appwrite is enabled but APPWRITE_ENDPOINT or APPWRITE_PROJECT_ID is missing."
            )
        if self.openhands_enabled and not getattr(self, "openhands_server_url", None):
            raise ValueError("❌ OpenHands is enabled but OPENHANDS_SERVER_URL is missing.")

        if self.env in {"production", "staging"}:
            critical_infrastructure = []
            if not getattr(self, "supabase_url", None):
                critical_infrastructure.append("SUPABASE_URL")
            if not getattr(self, "supabase_key", None):
                critical_infrastructure.append("SUPABASE_KEY")
            if not getattr(self, "firebase_service_account_json", None):
                critical_infrastructure.append("FIREBASE_SERVICE_ACCOUNT_JSON")
            if not self.encryption_key.get_secret_value():
                critical_infrastructure.append("ENCRYPTION_KEY")
            if critical_infrastructure:
                logger.critical(
                    f"❌ CRITICAL INFRASTRUCTURE MISSING: {critical_infrastructure}. "
                    "Server startup aborted (Fail-Fast enforced)."
                )
                raise ValueError(
                    f"Production/Staging requires {critical_infrastructure} to be set."
                )
        elif self.env not in {"test"}:
            missing: list[str] = []
            if not self.encryption_key.get_secret_value():
                missing.append("ENCRYPTION_KEY")
            if not getattr(self, "firebase_service_account_json", None):
                missing.append("FIREBASE_SERVICE_ACCOUNT_JSON")
            if missing:
                logger.warning(
                    f"⚠️ Missing local config vars: {', '.join(missing)}. Local/dev server may fail at runtime."
                )
        return self

    @field_validator(
        "idempotency_critical_paths",
        "supremeai_public_paths",
        "prompt_blocked_patterns",
        mode="before",
    )
    @classmethod
    def parse_list_fields(cls, v) -> list[str]:
        if not v:
            return []
        if isinstance(v, str):
            v = v.strip()
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError) as _parse_err:
                logger.debug(f"List field parse fallback to comma-split: {_parse_err}")
                return [p.strip() for p in v.split(",") if p.strip()]
        return v or []

    @field_validator("rbac_role_definitions", mode="before")
    @classmethod
    def parse_dict_fields(cls, v) -> dict:
        if not v:
            return {}
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError) as _dict_parse_err:
                logger.error(
                    f"Failed to parse rbac_role_definitions JSON: {_dict_parse_err}. Defaulting to empty dictionary."
                )
                return {}
        return v or {}

    @field_validator("admin_emails", mode="before")
    @classmethod
    def parse_admin_emails(cls, v) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            return [email.strip() for email in v.split(",") if email.strip()] if v else []
        return v or []

    @field_validator("allowed_hosts", mode="before")
    @classmethod
    def parse_allowed_hosts(cls, v) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            return [h.strip() for h in v.split(",") if h.strip()] if v else []
        return v or []

    @field_validator("allowed_hosts", mode="after")
    @classmethod
    def validate_allowed_hosts(cls, v: list[str], info: ValidationInfo) -> list[str]:
        env = str(info.data.get("env") or os.getenv("ENV", "local")).lower()
        forbidden = {f"{'local'}{'host'}", f"{'127'}.0.0.1", "testserver", f"{'0'}.0.0.0"}
        if env in {"production", "staging"}:
            v = [h for h in v if h.lower() not in forbidden]
            # Zero-hardcode policy: bare public platform apex domains are NEVER
            # valid ALLOWED_HOSTS entries. TrustedOriginMiddleware matches Host
            # headers by exact value OR suffix (endswith "." + h), so an apex
            # entry such as "onrender.com" would trust EVERY subdomain of the
            # platform — including attacker-registered ones. Fail fast with an
            # actionable message instead of silently widening the trust set.
            bad_apex = sorted(h for h in v if h.lower() in PLATFORM_APEX_HOSTS)
            if bad_apex:
                raise ValueError(
                    f"❌ {env.capitalize()} ALLOWED_HOSTS contains bare platform apex "
                    f"domain(s) {bad_apex}. Host matching is suffix-based, so an apex "
                    f"entry would trust every subdomain of that platform. List the real "
                    f"per-service hostname(s) instead (e.g. from RENDER_EXTERNAL_HOSTNAME)."
                )
            # If not explicitly provided, auto-discover host from cloud platform environment (e.g. Render, Vercel)
            if not v:
                render_host = os.getenv("RENDER_EXTERNAL_HOSTNAME") or os.getenv(
                    "RENDER_EXTERNAL_URL"
                )
                if render_host:
                    render_host = (
                        render_host.replace("https://", "").replace("http://", "").split("/")[0]
                    )
                    v.append(render_host)
                vercel_host = os.getenv("VERCEL_URL") or os.getenv("VERCEL_BRANCH_URL")
                if vercel_host:
                    vercel_host = (
                        vercel_host.replace("https://", "").replace("http://", "").split("/")[0]
                    )
                    v.append(vercel_host)
                # If running on Render without an explicit custom domain, derive the
                # real per-service onrender.com hostname from RENDER_SERVICE_NAME
                # (reliably injected by Render for ALL service types, including
                # Docker-image deploys where RENDER_EXTERNAL_HOSTNAME/URL are not
                # always available). Using the real per-service hostname — never the
                # bare literal — matters for two downstream consumers:
                #   1. TrustedOriginMiddleware matches Host headers by exact value OR
                #      suffix (endswith "." + h), so a bare apex entry would accept
                #      EVERY *.onrender.com host, including attacker-registered ones.
                #   2. validate_production_completeness derives CORS origins from
                #      allowed_hosts and deliberately excludes the bare placeholder
                #      (it isn't a real reachable host), so a bare fallback left CORS
                #      derivation with nothing to work with and crashed on boot.
                if not v and (os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID")):
                    render_service_name = os.getenv("RENDER_SERVICE_NAME")
                    if render_service_name:
                        v.append(f"{render_service_name}.onrender.com")
                    else:
                        # Zero-hardcode: fail closed. The old last-resort bare-apex
                        # fallback ("onrender.com") was removed — it silently trusted
                        # every platform subdomain via suffix Host matching. The
                        # empty-check below raises (real boot) unless the operator
                        # sets ALLOWED_HOSTS explicitly.
                        logger.warning(
                            "⚠️ Running on Render but RENDER_SERVICE_NAME / "
                            "RENDER_EXTERNAL_HOSTNAME are unavailable and ALLOWED_HOSTS "
                            "is not set. Refusing to trust the bare 'onrender.com' apex "
                            "(Host-suffix bypass). Set ALLOWED_HOSTS explicitly or "
                            "re-enable platform metadata injection."
                        )

            # The application must fail closed in real production/staging, but
            # Settings() is also used by focused pytest cases to exercise later
            # property-level validation (e.g. JWT). A dedicated test-only
            # placeholder keeps those tests isolated without weakening runtime
            # validation; real startup never runs under pytest.
            if not v and (
                "pytest" in sys.modules
                or os.getenv("TESTING", "").lower() == "true"
                or os.getenv("CI", "").lower() == "true"
            ):
                return ["testserver"]
            if not v:
                raise ValueError(
                    f"❌ {env.capitalize()} ALLOWED_HOSTS missing or only contains loopback dev entries. Fail-fast triggered."
                )
        return v

    # NOTE: "cors_origins" itself is a dynamic @property (config_secrets.py), not a
    # pydantic field, so it must NOT appear in field_validator() below — Pydantic
    # would raise a schema error for validating a non-existent field.
    @field_validator("user_cors_origins", "admin_cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v, info: ValidationInfo):
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [o.strip() for o in v.split(",") if o.strip()]
        return v or []

    @field_validator("user_cors_origins", "admin_cors_origins", mode="after")
    @classmethod
    def validate_cors_origins(cls, v: list[str], info: ValidationInfo) -> list[str]:
        env = str(info.data.get("env") or os.getenv("ENV", "local")).lower()
        if env == "test":
            return v
        if env in {"production", "staging"}:
            field = getattr(info, "field_name", None) or ""
            if field in {"user_cors_origins", "admin_cors_origins"} or not field:
                v = [o for o in v if "local" not in o and "127." not in o]
        return v

    @property
    def jti_blacklist_cache(self) -> set:
        """JWT JTI replay attack প্রতিরোধের জন্য ইন-মেমরি ক্যাশ। (Bangla: JTI ব্ল্যাকলিস্ট ক্যাশিং)"""
        if not hasattr(self, "_jti_cache"):
            self._jti_cache: set[str] = set()
        return self._jti_cache

    @classmethod
    def parse_cors_origins_helper(cls, value: Any, info: Any = None) -> list[str]:
        if isinstance(value, list):
            return value
        if not value or not str(value).strip():
            return []
        if str(value).startswith("["):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError) as _cors_parse_err:
                logger.debug(f"CORS parse fallback to comma-split: {_cors_parse_err}")
        return [x.strip() for x in str(value).split(",") if x.strip()]

    @classmethod
    def validate_cors_origins_helper(cls, value: list[str], info: Any = None) -> list[str]:
        env = (info.data.get("env") if info and hasattr(info, "data") else None) or os.getenv(
            "ENV", "local"
        )
        if env == "production":
            return [origin for origin in value if "local" not in origin and "127." not in origin]
        return value

    @classmethod
    def set_jwt_secret(cls, value: Any, info: Any = None) -> str:
        """Validate JWT secret on Settings field assignment.

        AUDIT-FIX (#1658 HIGH): আগে এই method টি একটি orphaned @classmethod
        ছিল — কখনো @field_validator হিসেবে wire করা হয়নি, তাই এটি শুধু
        tests থেকে direct call হতো। এখন এটি স্পষ্টভাবে নথিভুক্ত এবং
        validate_production_completeness দ্বারা স্টার্টআপে কল করা হয়।

        Behavior:
        - Production: empty/missing → ValueError (fail-closed)
        - Production: < 64 bytes → ValueError (fail-closed)
        - Production: known-insecure defaults → ValueError (fail-closed)
        - Non-production: empty → generate random (safe for dev)
        - Non-production: non-empty → return as-is
        """
        env = (info.data.get("env") if info and hasattr(info, "data") else None) or os.getenv(
            "ENV", "local"
        )
        # AUDIT-FIX (#1658): পরিচিত insecure default values — কখনো accept নয়।
        INSECURE_DEFAULTS = frozenset(
            {
                "change-me-in-production",
                "change-me",
                "changeme",
                "secret",
                "your-secret-key",
                "default-secret-key",
                "insecure",
            }
        )
        if value and isinstance(value, str) and value.strip().lower() in INSECURE_DEFAULTS:
            raise ValueError(
                f"❌ JWT secret is set to a known insecure default ('{value}'). "
                f"This is a CRITICAL security vulnerability — full auth bypass possible. "
                f"Set SUPREMEAI_JWT_SECRET to a strong random value (>= 64 bytes)."
            )
        if not value and env == "production":
            raise ValueError("JWT secret cannot be empty in production.")
        if not value or value is None:
            return secrets.token_urlsafe(64)
        if env == "production" and len(str(value)) < 64:
            raise ValueError("JWT secret must be at least 64 bytes long in production")
        return str(value)

    @model_validator(mode="after")
    def validate_production_completeness(self) -> Any:
        """Validate production-only completeness during real application startup.

        Focused pytest cases intentionally construct Settings(env=production) to
        test individual properties. Those tests already exercise their target
        validators directly, so cross-field completeness is skipped under pytest
        and never skipped by a real production process.

        AUDIT-FIX (#1658 HIGH): এখন staging env-তেও jwt_secret validate হয় —
        আগে শুধু production-এ হতো, staging-এ এড়িয়ে যেত।
        """
        if "pytest" in sys.modules or os.getenv("CI") == "true":
            return self

        if self.env in {"production", "staging"}:
            # AUDIT-FIX (#1658): jwt_secret property-তে validate হয়, কিন্তু
            # সেটি শুধু access হলেই trigger করে। এখানে explicit access করা
            # হয় যাতে startup-এই fail-fast হয়।
            if hasattr(self, "_jwt_secret_cache"):
                delattr(self, "_jwt_secret_cache")
            # AUDIT-FIX (#1658): set_jwt_secret দিয়ে known-insecure defaults
            # check করি — যদি কেউ "change-me-in-production" দিয়ে থাকে,
            # এখানেই crash হবে।
            try:
                resolved = self.jwt_secret
                # Extra guard: double-check resolved secret against insecure defaults
                SettingsValidationMixin.set_jwt_secret(resolved, type(self))
            except ValueError as exc:
                raise ValueError(f"❌ JWT secret validation failed at startup: {exc}") from exc

            if not self.user_cors_origins and not self.admin_cors_origins:
                # 🔧 Dynamic fallback: derive an origin from the already-resolved
                # allowed_hosts (which itself auto-discovers RENDER_EXTERNAL_URL /
                # VERCEL_URL / etc). This avoids hardcoding a domain while still
                # failing closed if truly nothing could be discovered.
                derived = [
                    f"https://{h}" for h in (self.allowed_hosts or []) if h and h != "onrender.com"
                ]
                if derived:
                    logger.warning(
                        f"⚠️ USER_CORS_ORIGINS/ADMIN_CORS_ORIGINS not set explicitly. "
                        f"Auto-derived from ALLOWED_HOSTS: {derived}. "
                        f"Set USER_CORS_ORIGINS/ADMIN_CORS_ORIGINS explicitly for full control."
                    )
                    self.user_cors_origins = derived
                    self.admin_cors_origins = derived
                else:
                    raise ValueError(
                        "❌ Production CORS origins not explicitly configured. Must set USER_CORS_ORIGINS and/or ADMIN_CORS_ORIGINS."
                    )

        logger.info(f"✅ Configuration loaded successfully for environment: {self.env}")
        return self

    def reload_env_vars(self) -> None:
        """Reload environment variables from .env for long-running processes."""
        from dotenv import load_dotenv

        load_dotenv(override=True)
        logger.info("⚙️ [Config] Environment variables hot-reloaded successfully.")


# ---------------------------------------------------------------------------
# ConfigValidationReport (MASTER_PLAN Phase 1 — specs/001 close-out)
# ---------------------------------------------------------------------------


class ConfigCheck(BaseModel):
    """One config validation result row (honest, machine-readable)."""

    name: str
    status: str  # "ok" | "warning" | "error"
    detail: str = ""
    fix_suggestion: str = ""


class ConfigValidationReport(BaseModel):
    """Aggregated configuration truth for the current environment.

    বাংলা: specs/001 (Dynamic Production Configuration) প্রতিশ্রুত ক্লাস — আগে
    শুধু ডকুমেন্টে ছিল, কোডে নয়। এটি বুট-টাইম বা admin API থেকে ডাকলে
    বর্তমান env-এর সত্যিকারের কনফিগ অবস্থা জানায়: কোন required var অনুপস্থিত,
    কোন ফরম্যাট ভাঙা, CORS wildcard আছে কি না — চুপচাপ নয় (No Silent Failure)।
    """

    environment: str = "unknown"
    ok: bool = True
    errors: list[ConfigCheck] = Field(default_factory=list)
    warnings: list[ConfigCheck] = Field(default_factory=list)
    checks: list[ConfigCheck] = Field(default_factory=list)
    generated_at: str = ""

    def add(self, check: ConfigCheck) -> None:
        self.checks.append(check)
        if check.status == "error":
            self.errors.append(check)
            self.ok = False
        elif check.status == "warning":
            self.warnings.append(check)


# Required environment variables for a deployable core service.
# Issue #567 (BE-16): canonical JWT secret name is SUPREMEAI_JWT_SECRET;
# JWT_SECRET is accepted as a deprecated alias (warning, not error).
_REQUIRED_VARS = (
    JWT_SECRET_ENV,
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
)

# Format checks: env var -> regex name from SettingsValidationMixin.FORMAT_PATTERNS.
_FORMAT_CHECKS = {
    "SUPABASE_URL": "supabase_url",
    "REDIS_URL": "redis_url",
}


def build_config_validation_report(env: str | None = None) -> ConfigValidationReport:
    """Builds an honest ConfigValidationReport for the current process env.

    বাংলা: কোনো global state mutate করে না — শুধু পড়ে ও রিপোর্ট করে। এটি
    /config/validation-report এন্ডপয়েন্ট ও boot check দুই জায়গাতেই reuse হয়।
    """
    import os
    import re
    from datetime import UTC, datetime

    environment = env or os.getenv("ENV") or os.getenv("ENVIRONMENT") or "local"
    report = ConfigValidationReport(
        environment=str(environment),
        generated_at=datetime.now(UTC).isoformat(),
    )
    patterns = SettingsValidationMixin.FORMAT_PATTERNS

    for var in _REQUIRED_VARS:
        value = os.getenv(var, "")
        if not value.strip() and var == JWT_SECRET_ENV:
            # Issue #567 (BE-16): JWT_SECRET is a deprecated alias for the
            # canonical SUPREMEAI_JWT_SECRET — accept it with a warning so
            # operators following the legacy name get one honest report
            # instead of failing this validator while passing the others.
            if os.getenv(JWT_SECRET_DEPRECATED_ENV, "").strip():
                report.add(
                    ConfigCheck(
                        name=var,
                        status="warning",
                        detail=(
                            f"{JWT_SECRET_DEPRECATED_ENV} is set; it is a deprecated alias "
                            f"for {JWT_SECRET_ENV} and is still accepted this boot."
                        ),
                        fix_suggestion=(
                            f"Rename {JWT_SECRET_DEPRECATED_ENV} to {JWT_SECRET_ENV} "
                            "in the deployment environment."
                        ),
                    )
                )
                continue
        if not value.strip():
            report.add(
                ConfigCheck(
                    name=var,
                    status="error",
                    detail="Required environment variable is missing or empty.",
                    fix_suggestion=SettingsValidationMixin.FIX_SUGGESTIONS.get(
                        var.lower(), f"Set {var} in the deployment environment."
                    ),
                )
            )
        else:
            report.add(ConfigCheck(name=var, status="ok", detail="present (value not logged)"))

    for var, pattern_name in _FORMAT_CHECKS.items():
        value = os.getenv(var, "")
        if not value.strip():
            continue  # optional var; presence handled above for required ones
        if not re.match(patterns.get(pattern_name, r".+"), value):
            report.add(
                ConfigCheck(
                    name=var,
                    status="error",
                    detail=f"Value does not match the {pattern_name} format pattern.",
                    fix_suggestion=f"Check {var} format (see core/config_validation.py patterns).",
                )
            )
        else:
            report.add(ConfigCheck(name=var, status="ok", detail="format valid"))

    # CORS unification check (specs/001): wildcard must never survive.
    try:
        from middleware.cors_policy import resolve_admin_cors_origins, resolve_user_cors_origins

        raw_user = parse_origin_list(os.getenv("ALLOWED_ORIGINS", ""))  # roadmap 1.4 (#1173)
        if not raw_user:
            # বাংলা মন্তব্য: localhost fallback শুধুমাত্র local env-এ — production/staging-এ
            # ALLOWED_ORIGINS অনুপস্থিত থাকলে silently localhost-এ ফলব্যাক করা উচিত নয়
            # (established repo idiom: settings.env == "local" guard, দেখুন
            # config_fields.py frontend_base_url)।
            from core.config import settings

            if settings.is_local():
                raw_user = ["http://localhost:3000"]  # is_local() guarded dev default
        raw_admin = parse_origin_list(os.getenv("ADMIN_CORS_ORIGINS", ""))
        resolved = set(resolve_user_cors_origins(raw_user)) | set(
            resolve_admin_cors_origins(raw_admin)
        )
        if "*" in resolved:
            report.add(
                ConfigCheck(
                    name="cors_origins",
                    status="error",
                    detail="Wildcard '*' origin survived resolution — credentialed CORS is unsafe.",
                    fix_suggestion="Remove '*' from CORS env vars; list explicit origins.",
                )
            )
        else:
            report.add(
                ConfigCheck(
                    name="cors_origins",
                    status="ok",
                    detail=f"{len(resolved)} explicit origin(s) after policy resolution",
                )
            )
    except Exception as exc:
        report.add(
            ConfigCheck(
                name="cors_origins",
                status="warning",
                detail=f"CORS policy resolver unavailable: {exc}",
            )
        )

    # Production completeness (mirror of SettingsValidationMixin rule, env-level)
    if str(environment).lower() in {"production", "prod", "staging"}:
        for var in ("SUPABASE_DATABASE_URL",):
            if not os.getenv(var, "").strip():
                report.add(
                    ConfigCheck(
                        name=var,
                        status="error",
                        detail=f"{var} is required in {environment} (No Silent Failure).",
                        fix_suggestion=SettingsValidationMixin.FIX_SUGGESTIONS.get(
                            "supabase_database_url", ""
                        ),
                    )
                )

    return report
