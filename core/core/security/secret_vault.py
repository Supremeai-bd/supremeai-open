"""Enterprise Cloud Secret Vault (Infisical / Doppler) with strict secret handling.

বাংলা: এন্টারপ্রাইজ ক্লাউড সিক্রেট ভল্ট — ইন-মেমরি ক্যাশে TTL-সহ, Fail-Closed।
Fetches production API keys directly into memory from Infisical.
Removes the need for monolithic GCP Secret Manager.
Strict secret handling ensures exceptions are raised for missing secrets.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING

from core.errors.error_bus import with_error_bus
from core.logging_config import logger

# Fixed import path - using relative import
from ..messaging.event_bus import ErrorContext, ErrorEvent, error_event_bus

if TYPE_CHECKING:
    from infisical_client import GetSecretOptions, ListSecretsOptions

try:
    from infisical_client import (
        AuthenticationOptions,
        ClientSettings,
        GetSecretOptions,
        InfisicalClient,
        ListSecretsOptions,
        UniversalAuthMethod,
    )
except ImportError as e:
    from core.logging_config import logger

    logger.warning(f"Failed to import infisical_client: {e}")
    InfisicalClient = None  # type: ignore[assignment]

# ── Constants ──────────────────────────────────────────────────────────────────
CACHE_TTL_SECONDS: int = int(os.getenv("SECRET_CACHE_TTL") or "300")  # 5 min default
INFISICAL_TIMEOUT: int = int(os.getenv("INFISICAL_TIMEOUT") or "10")  # 10s default

# ── Secret classification (BE-13, issue #545) ─────────────────────────────────
# Secrets that may legitimately be absent in production/staging: a missing
# value only degrades the corresponding integration (INFO log, empty/None
# returned). EVERY other secret is FAIL-CLOSED: a missing value raises
# RuntimeError so a forgotten secret can never silently become "" downstream
# (e.g. STRIPE_WEBHOOK_SECRET → SecretStr("") accepting forged webhook events).
# To ship a new optional integration, explicitly add its key here.
OPTIONAL_SECRETS: set[str] = {
    "ADMIN_NOTIFICATION_EMAIL",
    "DISCORD_OTP_WEBHOOK_URL",
    "DISCORD_WEBHOOK_URL",
    "DISCORD_BOT_TOKEN",
    "RESEND_API_KEY",
    "NVIDIA_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "GROQ_API_KEY",
    "GITHUB_CLIENT_ID",
    "GITHUB_CLIENT_SECRET",
    "HF_API_KEY",
    "NEO4J_URI",
    "NEO4J_USER",
    "NEO4J_PASSWORD",
    "TELEGRAM_BOT_TOKEN",
    "ADMIN_TELEGRAM_CHAT_ID",
    # Consumers handle absence explicitly (core/db_ssl.py warns and relies on
    # certifi when unset), so absence must degrade, not raise.
    "SUPABASE_DB_CA_CERT",
    # Billing integrations: config_validation.validate_all explicitly warns
    # ("Billing features will run in mock mode" / "Webhook validation
    # disabled") and continues — absence is a loud degradation, not a boot
    # abort. Without these here, every production boot without Stripe
    # configured crashed at the validate_all property access (issue #601
    # real-boot probes caught this before a deploy did).
    "STRIPE_API_KEY",
    "STRIPE_WEBHOOK_SECRET",
    # Alternate / generic database URL: when absent in production, system falls back to SUPABASE_DATABASE_URL_POOLER
    "DATABASE_URL",
    "NEON_DATABASE_URL",
    "NEON_API_KEY",
    # Additional AI / cloud providers (optional integrations)
    "ANTHROPIC_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "TOGETHER_API_KEY",
    "FIRECRAWL_API_KEY",
    "RUNPOD_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_ID",
    "BYNARA_API_KEY",
    "BAI_API_KEY",
    "V0_API_KEY",
    # validate_all warns ("Production missing config vars: CI_WEBHOOK_SECRET.
    # Running in degraded zero-cost mode") and continues - warn-optional.
    "CI_WEBHOOK_SECRET",
}
# Infra-critical secrets whose absence aborts boot — kept as a separate set so
# they get the CRITICAL log + alert event before the fail-closed raise.
HARD_REQUIRED_SECRETS: set[str] = {
    "SUPABASE_DATABASE_URL_POOLER",
    "SUPABASE_URL",
    "SUPABASE_KEY",
    "REDIS_URL",
    "SUPREMEAI_JWT_SECRET",
    "ENCRYPTION_KEY",
    "SUPREMEAI_API_KEY",
}


class _CacheEntry:
    """Cache entry with TTL expiry."""

    __slots__ = ("expires_at", "value")

    def __init__(self, value: str, ttl: int = CACHE_TTL_SECONDS) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


class SecretNotFoundError(Exception):
    """Raised when a secret is not found in any source in production environment."""

    pass


class ProductionSecretVault:
    """Enterprise Cloud Secret Vault with TTL-based caching and fail-closed behavior.

    বাংলা: TTL-ভিত্তিক ক্যাশিং এবং Fail-Closed আচরণ সহ এন্টারপ্রাইজ ক্লাউড সিক্রেট ভল্ট।
    """

    def __init__(self) -> None:
        self.env = os.getenv("ENV", "local").lower()
        self.project_id = os.getenv("INFISICAL_PROJECT_ID")
        self.client_id = os.getenv("INFISICAL_CLIENT_ID")
        self.client_secret = os.getenv("INFISICAL_CLIENT_SECRET")
        self.token = os.getenv("INFISICAL_TOKEN")

        self.client: InfisicalClient | None = None
        self._cache: dict[str, _CacheEntry] = {}
        self._circuit_breaker_open: bool = False
        # Issue #901: half-open auto-recovery — once the circuit opens we
        # remember when (monotonic time) so a single probe can be sent after
        # `_half_open_after_seconds` cooldown. Without this the breaker stayed
        # OPEN forever until process restart, so a transient Infisical outage
        # permanently blocked every agent's secret fetch even after recovery.
        self._circuit_opened_at: float | None = None
        self._half_open_after_seconds: int = int(os.getenv("VAULT_HALF_OPEN_AFTER") or "60")

        # TTL overrides for smart caching (Infisical API quota optimization)
        self._ttl_overrides: dict[str, int] = {
            "FEATURE_FLAGS": 3600,  # 1 hour
            "PUBLIC_CONFIG": 1800,  # 30 min
            "API_ENDPOINTS": 900,  # 15 min
            "LLM_PROVIDER_KEYS": 300,  # 5 min
            "DATABASE_CONFIG": 300,  # 5 min
        }

        # বাংলা মন্তব্য: PRE_COMMIT=1 বা TESTING=1 থাকলে Infisical init skip করো।
        # এটি pre-commit hook hang প্রতিরোধ করে — network call হবে না।
        _is_precommit = os.getenv("PRE_COMMIT") == "1" or os.getenv("TESTING") == "1"
        if _is_precommit:
            logger.debug("PRE_COMMIT/TESTING mode: Skipping Infisical initialization.")
            return

        if InfisicalClient and (self.token or (self.client_id and self.client_secret)):
            try:
                self._init_infisical_client()
            except Exception as e:
                logger.error(
                    f"Infisical initialization failed (invalid token/credentials): {e}. Bypassing Cloud Vault."
                )
        else:
            logger.info("Infisical missing or no credentials found. Bypassing Cloud Vault.")

    # ── Half-open recovery helpers (issue #901) ───────────────────────────────
    def _should_attempt_half_open_recovery(self) -> bool:
        """Return True iff the circuit is OPEN and cooldown has elapsed.

        বাংলা: সার্কিট OPEN হলেও প্রতি _half_open_after_seconds সেকেন্ড পর একটি
        probe রিকোয়েস্ট পাঠানোর অনুমতি দেয়। এটি একটি single-request probe:
        সফল হলে _close_circuit() পুরো সার্কিট বন্ধ করে দেয়, ফেইল হলে
        _open_circuit() টাইমার রিসেট করে। এইভাবে transient Infisical outage
        থেকে স্বয়ংক্রিয়ভাবে recover হয় — manual restart লাগে না (issue #901)।
        """
        if not self._circuit_breaker_open or self._circuit_opened_at is None:
            return False
        return (time.monotonic() - self._circuit_opened_at) >= self._half_open_after_seconds

    def _open_circuit(self) -> None:
        """Open (or reopen) the circuit and (re)start the half-open cooldown.

        বাংলা: সার্কিট OPEN করে + _circuit_opened_at রিকর্ড করে যাতে
        _should_attempt_half_open_recovery() পরবর্তী probe এর জন্য cooldown
        মাপতে পারে। Reopen হলেও (একটি ফেইল হওয়া probe থেকে) টাইমার রিসেট
        হয়ে যায় — ফলে পরের probe অন্তত 60s পরেই চেষ্টা করবে।
        """
        if not self._circuit_breaker_open:
            logger.warning(
                f"Vault circuit breaker OPEN — half-open probe will retry in "
                f"{self._half_open_after_seconds}s (issue #901)"
            )
        self._circuit_breaker_open = True
        self._circuit_opened_at = time.monotonic()

    def _close_circuit(self) -> None:
        """Close the circuit after a successful probe.

        বাংলা: সফল probe এর পর সার্কিট CLOSED করে — normal operation resume।
        """
        if self._circuit_breaker_open:
            logger.info("Vault circuit breaker CLOSED — Infisical recovered (issue #901)")
        self._circuit_breaker_open = False
        self._circuit_opened_at = None

    def _resolve_infisical_environment(self) -> str:
        """Resolve the Infisical environment slug — single source of truth.

        বাংলা: Issue #899 — async fetch path পূর্বে hardcoded
        `environment = "dev" if self.env == "local" else "prod"` ব্যবহার করত,
        যার ফলে staging environment-এও production vault পড়া হতো (cross-env
        isolation breach)। এই method কে sync (`fetch_secret`) ও bulk
        (`fetch_all_secrets`) path-এর একই mapping + INFISICAL_ENV override
        contract honor করানো হয়েছে।

        Priority:
            1. `INFISICAL_ENV` env var override (12-factor explicit override)
            2. `self.env` থেকে derived slug:
               - "production" → "prod"
               - "staging"    → "staging"
               - else         → "dev"

        Returns:
            str: Infisical environment slug ("prod" | "staging" | "dev" বা override)।
        """
        infisical_env = os.environ.get("INFISICAL_ENV")
        if infisical_env:
            return infisical_env
        if self.env == "production":
            return "prod"
        if self.env == "staging":
            return "staging"
        return "dev"

    @with_error_bus("_init_infisical_client")
    def _init_infisical_client(self) -> None:
        """Initialize Infisical client with strict timeout protection."""
        import concurrent.futures

        def _do_init():
            if self.client_id and self.client_secret:
                return InfisicalClient(
                    ClientSettings(
                        auth=AuthenticationOptions(
                            universal_auth=UniversalAuthMethod(
                                client_id=self.client_id,
                                client_secret=self.client_secret,
                            )
                        )
                    )
                )
            elif self.token:
                return InfisicalClient(ClientSettings(access_token=self.token))
            return None

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_init)
                # Enforce strict timeout (default 10s) to prevent container boot hangs
                self.client = future.result(timeout=INFISICAL_TIMEOUT)

            if self.client:
                logger.info(
                    f"Production Secret Vault hooked into Infisical (Timeout: {INFISICAL_TIMEOUT}s)"
                )
        except concurrent.futures.TimeoutError:
            logger.error(
                f"Infisical init TIMEOUT after {INFISICAL_TIMEOUT}s. Bypassing Cloud Vault."
            )
        except (ConnectionError, TimeoutError, ValueError) as exc:
            logger.warning(f"Failed to bind Infisical Client: {exc}. Falling back to raw env.")
        except Exception:
            logger.opt(exception=True).warning(
                "Unexpected error initializing Infisical client. Falling back to raw env."
            )

    @with_error_bus("fetch_secret")
    def fetch_secret(self, secret_id: str, default: str | None = None) -> str:
        """Fetch a secret from Infisical with TTL-based caching.

        বাংলা: TTL-ভিত্তিক ক্যাশিং সহ Infisical থেকে সিক্রেট ফেচ।

        Raises:
            RuntimeError: If secret not found in Infisical or env in production.
        """
        # Circuit Breaker check — issue #901: allow ONE probe after cooldown so
        # the breaker self-recovers instead of staying OPEN forever.
        if self._circuit_breaker_open:
            if not self._should_attempt_half_open_recovery():
                return self._fallback_to_env(secret_id, default)
            logger.info(
                f"Vault circuit breaker HALF_OPEN — probe attempt for '{secret_id}' "
                f"after {self._half_open_after_seconds}s cooldown (issue #901)"
            )
            # Drop any stale cached env-fallback value so the probe actually
            # reaches Infisical instead of short-circuiting via the cache.
            # If the probe fails, _fallback_to_env re-caches a fresh fallback.
            self._cache.pop(secret_id, None)

        ttl = self._ttl_overrides.get(secret_id, CACHE_TTL_SECONDS)

        # বাংলা মন্তব্য: এনভায়রনমেন্ট ভেরিয়েবল ভল্টের উপরে প্রাধান্য পায় (12-factor)।
        # এতে Render-এর env কনফিগ দিয়ে সিক্রেট ইমার্জেন্সি-ফিক্স/ওভাররাইড করা যায়
        # ইনফিসিক্যাল স্পর্শ না করেই। শুধু তখনই প্রযোজ্য যখন ভ্যারিয়েবল সেট থাকে।
        env_override = os.getenv(secret_id)
        if env_override:
            self._cache[secret_id] = _CacheEntry(env_override, ttl=ttl)
            return env_override

        # Check cache first
        cached = self._cache.get(secret_id)
        if cached and not cached.is_expired:
            return cached.value

        # If cache expired, remove it
        if cached and cached.is_expired:
            del self._cache[secret_id]

        if not self.client or not self.project_id:
            return self._fallback_to_env(secret_id, default)

        try:
            # বাংলা মন্তব্য: Issue #899 — sync path এখন single source of truth
            # `_resolve_infisical_environment()` ব্যবহার করে (async/bulk path-এর
            # সাথে মিল রাখতে)।
            infisical_env = self._resolve_infisical_environment()

            options = GetSecretOptions(
                environment=infisical_env,
                project_id=self.project_id,
                secret_name=secret_id,
            )

            # Exponential backoff retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    secret_value = self.client.getSecret(options=options).secret_value
                    self._cache[secret_id] = _CacheEntry(secret_value, ttl=ttl)
                    # Issue #901: probe succeeded — close the circuit so normal
                    # operation resumes without process restart.
                    if self._circuit_breaker_open:
                        self._close_circuit()
                    return secret_value
                except (ConnectionError, TimeoutError) as exc:
                    if attempt < max_retries - 1:
                        sleep_time = 2**attempt
                        logger.warning(
                            f"Retrying Infisical fetch for {secret_id} in {sleep_time}s due to: {exc}"
                        )
                        # BE-12 (issue #544): a blocking time.sleep() on the
                        # event-loop thread freezes every concurrent request
                        # and the liveness probe for the whole backoff. Only
                        # sleep when we are on a plain worker thread (scripts,
                        # thread pools); when a running loop is detected on
                        # this thread, skip the sync backoff and retry
                        # immediately — async paths must go through
                        # fetch_secret_async / apreload_secrets instead.
                        try:
                            asyncio.get_running_loop()
                        except RuntimeError:
                            time.sleep(sleep_time)
                        else:
                            logger.warning(
                                f"fetch_secret({secret_id}): sync backoff skipped on "
                                "event-loop thread (BE-12); retrying immediately."
                            )
                    else:
                        raise exc from exc
            # বাংলা মন্তব্য: mypy-এর Missing return statement এরর এড়াতে লুপের শেষে raise দেওয়া হলো, যদিও বাস্তবে এটি কখনো রিচ হবে না।
            raise RuntimeError("Unexpected end of retry loop without success or exception")
        except (ConnectionError, TimeoutError) as exc:
            # Issue #901: _open_circuit resets the half-open cooldown timer so
            # a follow-up probe is attempted after the configured window.
            self._open_circuit()
            logger.warning(
                f"Unable to reach Infisical for {secret_id}: {exc}. Circuit breaker OPEN. Using fallback environment."
            )
            error_event_bus.emit(
                ErrorEvent(
                    module="secret_vault",
                    error_type="VAULT_FETCH_TIMEOUT",
                    message=f"Failed to fetch {secret_id} from Infisical after retries: {exc}",
                    severity="WARNING",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"secret_id": secret_id},
                )
            )
            return self._fallback_to_env(secret_id, default)
        except Exception as exc:
            err_str = str(exc).lower()
            # Do not open circuit breaker for missing secrets or generic API errors
            if (
                "not found" in err_str
                or "404" in err_str
                or "400" in err_str
                or "not_found" in err_str
            ):
                logger.warning(f"Secret '{secret_id}' not found in Infisical. Using fallback.")
                return self._fallback_to_env(secret_id, default)

            self._open_circuit()
            logger.opt(exception=True).warning(
                f"Unexpected error fetching {secret_id} from Infisical. Circuit breaker OPEN. Using fallback."
            )
            error_event_bus.emit(
                ErrorEvent(
                    module="secret_vault",
                    error_type="VAULT_FETCH_ERROR",
                    message=f"Unexpected error fetching {secret_id}: {exc}",
                    severity="ERROR",
                    structured_context=ErrorContext(module="auto_fixed"),
                    context={"secret_id": secret_id},
                )
            )
            return self._fallback_to_env(secret_id, default)

    @with_error_bus("fetch_secret_async")
    async def fetch_secret_async(self, secret_id: str, default: str | None = None) -> str:
        """Fetch a secret from Infisical asynchronously (Bug #5 fix)."""
        # Issue #901: half-open probe (see fetch_secret docstring).
        if self._circuit_breaker_open:
            if not self._should_attempt_half_open_recovery():
                return self._fallback_to_env(secret_id, default)
            logger.info(
                f"Vault circuit breaker HALF_OPEN — async probe for '{secret_id}' "
                f"after {self._half_open_after_seconds}s cooldown (issue #901)"
            )
            # Drop stale cached fallback so the probe actually hits Infisical.
            self._cache.pop(secret_id, None)

        cached = self._cache.get(secret_id)
        # FIX(test-campaign 7): is_expired is a @property — calling it as a
        # method raised TypeError on every async cache hit. Sync path was correct.
        if cached and not cached.is_expired:
            return cached.value

        if not self.client:
            return self._fallback_to_env(secret_id, default)

        try:
            import asyncio

            from infisical_client import GetSecretOptions

            # বাংলা মন্তব্য: Issue #899 — async path এখন single source of truth
            # `_resolve_infisical_environment()` ব্যবহার করে। পূর্বে এখানে
            # hardcoded `"dev" if self.env == "local" else "prod"` ছিল —
            # যার ফলে staging environment-এও production vault পড়া হতো।
            infisical_env = self._resolve_infisical_environment()

            options = GetSecretOptions(
                environment=infisical_env,
                project_id=self.project_id,
                secret_name=secret_id,
            )

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    secret_value = await asyncio.to_thread(
                        lambda: self.client.getSecret(options=options).secret_value
                    )
                    self._cache[secret_id] = _CacheEntry(secret_value, ttl=600)
                    # Issue #901: probe succeeded — close the circuit.
                    if self._circuit_breaker_open:
                        self._close_circuit()
                    return secret_value
                except (ConnectionError, TimeoutError) as exc:
                    if attempt < max_retries - 1:
                        sleep_time = 2**attempt
                        logger.warning(
                            f"Retrying Infisical async fetch for {secret_id} in {sleep_time}s due to: {exc}"
                        )
                        await asyncio.sleep(sleep_time)
                    else:
                        raise exc from exc
            raise RuntimeError("Unexpected end of retry loop without success or exception")
        except (ConnectionError, TimeoutError) as exc:
            # Issue #901: reset half-open cooldown timer so probe retries later.
            self._open_circuit()
            logger.warning(
                f"Unable to reach Infisical for {secret_id}: {exc}. Circuit breaker OPEN."
            )
            return self._fallback_to_env(secret_id, default)
        except Exception as exc:
            err_str = str(exc).lower()
            if (
                "not found" in err_str
                or "404" in err_str
                or "400" in err_str
                or "not_found" in err_str
            ):
                logger.warning(f"Secret '{secret_id}' not found in Infisical. Using fallback.")
                return self._fallback_to_env(secret_id, default)

            self._open_circuit()
            logger.opt(exception=True).warning(
                f"Unexpected error fetching {secret_id} from Infisical."
            )
            return self._fallback_to_env(secret_id, default)

    @with_error_bus("_fallback_to_env")
    def _fallback_to_env(self, secret_id: str, default: str | None) -> str:
        """Fallback to environment variable.

        বাংলা মন্তব্য: এনভায়রনমেন্ট ভেরিয়েবলে ফলব্যাক। প্রোডাকশন/স্টেজিং-এ OPTIONAL_SECRETS-এ
        স্পষ্টভাবে তালিকাভুক্ত সিক্রেট না থাকলে এখন fail-closed (RuntimeError) — অজানা
        সিক্রেট আর নীরবে "" হয়ে ডাউনস্ট্রিমে চলে যাবে না (BE-13, issue #545)।
        Local/dev-এ আগের মতোই graceful mock fallback রাখা হয়েছে।
        """
        # Issue #935 (BE-13 fail-closed contract): in production/staging the
        # env_override short-circuit in fetch_secret handles the legitimate
        # env-var-override case (12-factor) BEFORE this fallback is reached.
        # Therefore reaching _fallback_to_env means Infisical failed AND the
        # env-override path didn't fire. For HARD_REQUIRED_SECRETS with
        # default=None the fail-closed contract MUST hold regardless of any
        # incidental env_value, otherwise a forgotten hard-required secret
        # silently degrades instead of aborting boot. (Before this guard the
        # early `if env_value` branch swallowed the failure when the env var
        # happened to be set — e.g. via conftest app-fixture pollution or a
        # stale CI env — breaking test_hard_required_missing_in_prod_fail_closed.)
        if (
            self.env in ("production", "staging")
            and default is None
            and secret_id in HARD_REQUIRED_SECRETS
        ):
            logger.critical(
                f"🚨 CRITICAL: Secret '{secret_id}' missing in {self.env}! Sending alert..."
            )
            try:
                error_event_bus.emit(
                    ErrorEvent(
                        module="secret_vault",
                        error_type="CRITICAL_SECRET_MISSING",
                        message=f"Secret '{secret_id}' not found in Infisical or env!",
                        severity="CRITICAL",
                        context={"secret_id": secret_id},
                    )
                )
            except Exception as exc:
                logger.debug(f"Failed to emit error event: {exc}")
            # বাংলা মন্তব্য: infra-critical secret অনুপস্থিত হলে Fail-closed।
            raise RuntimeError(
                f"CRITICAL: Secret '{secret_id}' not found in {self.env}! Fail-closed."
            )

        env_value = os.getenv(secret_id)
        if env_value:
            env_fallback = env_value
        elif self.env in ("production", "staging"):
            # BE-13 (issue #545): in production/staging the classification
            # sets decide. NOTE: an env var explicitly set to "" is treated as
            # missing (empty value is never a valid secret).
            if secret_id in OPTIONAL_SECRETS:
                logger.info(f"ℹ️ Optional secret '{secret_id}' missing in {self.env}. Skipping.")
                env_fallback = default if default is not None else ""
            elif default is None and secret_id in HARD_REQUIRED_SECRETS:
                logger.critical(
                    f"🚨 CRITICAL: Secret '{secret_id}' missing in {self.env}! Sending alert..."
                )
                try:
                    error_event_bus.emit(
                        ErrorEvent(
                            module="secret_vault",
                            error_type="CRITICAL_SECRET_MISSING",
                            message=f"Secret '{secret_id}' not found in Infisical or env!",
                            severity="CRITICAL",
                            context={"secret_id": secret_id},
                        )
                    )
                except Exception as exc:
                    logger.debug(f"Failed to emit error event: {exc}")
                # বাংলা মন্তব্য: infra-critical secret অনুপস্থিত হলে Fail-closed।
                raise RuntimeError(
                    f"CRITICAL: Secret '{secret_id}' not found in {self.env}! Fail-closed."
                )
            else:
                # BE-13 (issue #545): default fail-closed for every secret not
                # explicitly opted into OPTIONAL_SECRETS. A secret forgotten in
                # the classification sets (e.g. a new key added to
                # _CORE_SECRET_KEYS, or STRIPE_WEBHOOK_SECRET read by the
                # webhook-verification path) must never silently become ""
                # downstream — previously this branch only logged a WARNING and
                # returned "" (or swallowed the caller's default=""), so an
                # empty SecretStr("") reached webhook verification and accepted
                # forged events. Operators opt unknown/optional secrets in
                # explicitly instead.
                raise RuntimeError(
                    f"Secret '{secret_id}' is missing in {self.env} and is not in the "
                    f"optional allowlist (BE-13 fail-closed). Provision it via Infisical/env, "
                    f"or add it to OPTIONAL_SECRETS in core/security/secret_vault.py if it is "
                    f"genuinely optional."
                )
        else:
            logger.warning(f"Mocking missing secret '{secret_id}' for {self.env} environment.")
            if default is not None:
                env_fallback = default
            elif secret_id == "SUPREMEAI_JWT_SECRET":
                # বাংলা মন্তব্য: Local/CI মকিং-এর ক্ষেত্রে JWT Secret সর্বনিম্ন 64 বাইট সিকিউরিটি নিশ্চিত করা হলো
                import secrets

                env_fallback = secrets.token_urlsafe(64)
            elif secret_id == "SUPABASE_URL":
                env_fallback = "https://mock.supabase.co"
            elif secret_id == "SUPABASE_KEY":
                env_fallback = "mock-key"
            else:
                env_fallback = f"mock_{secret_id}"
        self._cache[secret_id] = _CacheEntry(env_fallback)
        return env_fallback

    def get_secret(self, secret_id: str, default: str | None = None) -> str:
        """Get a secret or raise SecretNotFoundError if not found in production.

        বাংলা: সিক্রেট পাওয়া গেল না হলে SecretNotFoundError এরর রেজ করুন।
        """
        value = self.fetch_secret(secret_id, default)
        if value is None and self.env in ("production", "staging"):
            error_msg = f"🚨 CRITICAL: Secret '{secret_id}' not found in Infisical or environment variables."
            logger.critical(error_msg)
            raise SecretNotFoundError(error_msg)
        return value or default or ""

    # NOTE: The async implementation of fetch_secret_async is defined above at the
    # @with_error_bus("fetch_secret_async") decorator — do NOT redefine it here.

    @with_error_bus("fetch_json_secret")
    def fetch_json_secret(self, secret_id: str, default: dict | None = None) -> dict:
        """Fetch a secret that contains JSON (useful for grouped secrets).

        বাংলা: JSON সিক্রেট ফেচ করার সুবিধা।
        """
        import json

        raw_val = self.fetch_secret(secret_id, None)
        if (
            not raw_val
            or not isinstance(raw_val, str)
            or not raw_val.strip().startswith(("{", "["))
        ):
            return default if default is not None else {}
        try:
            return json.loads(raw_val)
        except json.JSONDecodeError as e:
            if self.env in ("production", "staging"):
                logger.error(f"Failed to decode JSON secret '{secret_id}': {e}")
            else:
                logger.debug(f"Non-JSON or mock value for secret '{secret_id}': {e}")
            return default or {}

    async def fetch_json_secret_async(self, secret_id: str, default: dict | None = None) -> dict:
        return await asyncio.to_thread(self.fetch_json_secret, secret_id, default)

    def fetch_all_secrets(self, environment: str | None = None) -> dict[str, str]:
        """Single bulk call — সব secrets এক HTTP call-এ ফেচ করে dict রিটার্ন করে।

        বাংলা: `listSecrets()` ব্যবহার করে একটাই API call-এ পুরো environment-এর
        সব secrets লোড করে in-memory cache-এ inject করে। Sequential per-secret
        loop (~30s) থেকে এক call (~0.7s)-এ নামিয়ে আনে startup time।

        Returns:
            dict[str, str]: {"SECRET_KEY": "secret_value", ...}
            Circuit breaker open বা client missing হলে empty dict।
        """
        # Issue #901: half-open probe path — allow bulk fetch to attempt
        # recovery too (otherwise a stuck-open breaker would block every
        # bulk preload until process restart).
        if self._circuit_breaker_open:
            if not self._should_attempt_half_open_recovery():
                logger.debug("fetch_all_secrets: circuit breaker open, skipping bulk fetch.")
                return {}
            logger.info("Vault circuit breaker HALF_OPEN — probe via bulk fetch (issue #901)")

        if not self.client or not self.project_id:
            logger.debug("fetch_all_secrets: no Infisical client/project_id, skipping.")
            return {}

        # Determine environment slug
        # বাংলা মন্তব্য: Issue #899 — bulk path এখন single source of truth
        # `_resolve_infisical_environment()` ব্যবহার করে (sync/async path-এর সাথে
        # মিল রাখতে)। Explicit `environment` parameter সর্বদা priority পায়।
        if environment:
            infisical_env = environment
        else:
            infisical_env = self._resolve_infisical_environment()

        try:
            import concurrent.futures

            def _do_list():
                return self.client.listSecrets(
                    ListSecretsOptions(
                        environment=infisical_env,
                        project_id=self.project_id,
                        path="/",
                        expand_secret_references=True,
                        attach_to_process_env=False,
                        include_imports=True,
                    )
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(_do_list)
                secrets_list = future.result(timeout=INFISICAL_TIMEOUT)

            result: dict[str, str] = {}
            ttl = CACHE_TTL_SECONDS
            for secret in secrets_list:
                key = secret.secret_key
                val = secret.secret_value or ""
                result[key] = val
                # Inject directly into TTL cache — individual fetch_secret() calls will hit cache
                self._cache[key] = _CacheEntry(val, ttl=ttl)

            logger.info(
                f"✅ Bulk fetch complete: {len(result)} secrets loaded from Infisical "
                f"(env={infisical_env}) in one HTTP call."
            )
            # Issue #901: bulk probe succeeded — close the circuit.
            if self._circuit_breaker_open:
                self._close_circuit()
            return result

        except concurrent.futures.TimeoutError:
            logger.warning(
                f"fetch_all_secrets TIMEOUT after {INFISICAL_TIMEOUT}s. "
                "Falling back to individual secret fetches."
            )
            return {}
        except Exception as exc:
            err_str = str(exc).lower()
            if "not found" in err_str or "404" in err_str or "403" in err_str:
                logger.warning(f"fetch_all_secrets: access error — {exc}. Falling back.")
            else:
                logger.opt(exception=True).warning(
                    f"fetch_all_secrets: unexpected error — {exc}. Falling back."
                )
            return {}

    def invalidate_cache(self, secret_id: str | None = None) -> None:
        """Invalidate cache for a specific secret or clear all.

        বাংলা মন্তব্য: নির্দিষ্ট সিক্রেট বা পুরো ক্যাশে ইনভ্যালিডেট।
        """
        if secret_id:
            self._cache.pop(secret_id, None)
        else:
            self._cache.clear()

    def set_secret(self, key: str, value: str) -> None:
        """Store a secret in the in-memory cache."""
        self._cache[key] = _CacheEntry(value)

    def delete_secret(self, key: str) -> None:
        """Remove a secret from the in-memory cache."""
        self._cache.pop(key, None)

    def list_secrets(self) -> list[str]:
        """Return all cached secret keys."""
        return list(self._cache.keys())


# Global Vault Singleton Instance
_secret_vault_instance: ProductionSecretVault | None = None
_vault_initialized: bool = False


def get_secret_vault() -> ProductionSecretVault:
    """Get or create the global secret vault singleton.

    বাংলা মন্তব্য: লেজি সিঙ্গেলটন — প্রথম ব্যবহারের সময় ইনিশিয়ালাইজ হয়।
    ইম্পোর্ট টাইমে নয়, তাই settings লোড হওয়ার আগে vault তৈরি হয় না।
    """
    global _secret_vault_instance, _vault_initialized
    if not _vault_initialized:
        _secret_vault_instance = ProductionSecretVault()
        _vault_initialized = True
    return _secret_vault_instance  # type: ignore


def reset_secret_vault() -> None:
    """বাংলা মন্তব্য: টেস্ট আইসোলেশনের জন্য vault রিসেট — শুধু টেস্টে ব্যবহার করুন।"""
    global _secret_vault_instance, _vault_initialized
    _secret_vault_instance = None
    _vault_initialized = False


# বাংলা মন্তব্য: Module-level instantiation সরানো হলো — এখন লেজি।
# পুরানো কোড যদি `from core.security.secret_vault import secret_vault` করে,
# তাহলে এটি এখনও কাজ করবে কারণ __getattr__ ডাইনামিকালি get_secret_vault() কল করবে।
# কিন্তু সরাসরি `secret_vault` ভ্যারিয়েবল আর module level-এ নেই।
# Backward compatibility-র জন্য __getattr__ হ্যান্ডলার যোগ করা হলো।
def __getattr__(name: str):
    """বাংলা মন্তব্য: Backward-compatible lazy access — পুরানো import প্যাটার্ন ভাঙে না।"""
    if name == "secret_vault":
        return get_secret_vault()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
