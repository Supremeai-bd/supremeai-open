"""
SupremeAI Configuration Validator — Fail-Fast at Startup
🔬 Evolution v3.0: Schema-based environment variable validation

Validates ALL required environment variables at startup.
Provides clear error messages for misconfiguration.

Single source of truth (issue #1260, Wave 3.4): the canonical env-key
vocabulary lives in ``core/config_classification.py::CONFIG_SPECS``.
``CONFIG_SCHEMA`` below is a *derived view* of that registry — it declares
WHICH classified keys this schema validates at startup (a validator-policy
decision that cannot be filtered out of CONFIG_SPECS attributes, see the
comment on ``_CONFIG_SCHEMA_ORDER``), then builds one ``VarDefinition`` per
key, resolving names/aliases through the canonical registry. A key renamed
or removed in CONFIG_SPECS fails loudly here at import time instead of
silently drifting.

Usage:
    from core.config_validator import validate_config, ConfigValidationResult

    result = validate_config()
    if not result.is_valid:
        logger.debug(result.format_errors())
        sys.exit(1)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# Issue #542 (BE-10): unify the JWT secret floor with the other validators.
# Issue #1260 (Wave 3.4): CONFIG_SCHEMA derives from the canonical CONFIG_SPECS.
from core.config_classification import get_config_spec
from core.logging_config import logger
from core.secret_policy import (
    JWT_SECRET_ENV,
    JWT_SECRET_MIN_LENGTH,
    resolve_jwt_secret_env,
)


class VarType(StrEnum):
    STRING = "string"
    URL = "url"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    LIST = "list"
    ENUM = "enum"


class Severity(StrEnum):
    ERROR = "error"  # Blocks startup
    WARNING = "warning"  # Logs but continues
    INFO = "info"  # Informational only


@dataclass
class VarDefinition:
    """Definition of an environment variable to validate."""

    name: str
    var_type: VarType = VarType.STRING
    required: bool = False
    default: Any = None
    description: str = ""
    pattern: str | None = None  # Regex pattern
    min_value: int | float | None = None
    max_value: int | float | None = None
    allowed_values: list[str] | None = None  # For ENUM type
    severity: Severity = Severity.ERROR
    examples: list[str] = field(default_factory=list)


@dataclass
class ValidationError:
    """Single validation error/warning."""

    var_name: str
    severity: Severity
    message: str
    actual_value: str | None = None
    suggestion: str | None = None


@dataclass
class ConfigValidationResult:
    """Complete validation result."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    validated_vars: dict[str, Any] = field(default_factory=dict)

    def format_errors(self) -> str:
        """Format all errors for display."""
        lines = ["=" * 60, "❌ CONFIGURATION VALIDATION FAILED", "=" * 60]

        for err in self.errors:
            icon = "🚨" if err.severity == Severity.ERROR else "⚠️"
            lines.append(f"\n{icon} [{err.severity.value.upper()}] {err.var_name}")
            lines.append(f"   {err.message}")
            if err.actual_value:
                sensitive = any(
                    token in err.var_name.upper()
                    for token in ("SECRET", "KEY", "TOKEN", "PASSWORD", "CREDENTIAL")
                )
                display_value = "[REDACTED]" if sensitive else err.actual_value
                lines.append(f"   Actual value: '{display_value}'")
            if err.suggestion:
                lines.append(f"   💡 Suggestion: {err.suggestion}")

        lines.extend(
            ["", "-" * 40, f"Total errors: {len(self.errors)}, Warnings: {len(self.warnings)}"]
        )
        return "\n".join(lines)


# ==========================================================================
# CONFIGURATION SCHEMA — derived view over the canonical CONFIG_SPECS
# ==========================================================================
# Which classified keys this startup schema validates is validator POLICY, not
# a classification property: e.g. 112 CONFIG_SPECS entries share the exact
# (conditional, secret)/(env, vault)/(backend) signature of GEMINI_API_KEY but
# are deliberately not startup-validated, so no attribute filter can reproduce
# this subset. It is therefore an explicit ordered tuple, cross-checked against
# CONFIG_SPECS at import time by _build_config_schema(): renaming/removing a
# classified key breaks import here with a precise message instead of drifting.
#
# Validator-specific semantics (var_type / required / bounds / severity) live
# in _CONFIG_SCHEMA_PROFILES. USER_CORS_ORIGINS is validated under its legacy
# name but resolves through the canonical CORS_ORIGINS spec via the registry's
# alias map — proof the derivation is alias-aware. Descriptions stay the
# curated validator text: the CONFIG_SPECS descriptions for these keys are
# still auto-classification placeholders — curate CONFIG_SPECS first, then
# switch the builder over to spec.description.
#
# Keys NOT yet classified in CONFIG_SPECS stay as full definitions in
# _CONFIG_SCHEMA_OVERRIDES (issue #1260 follow-up: adopt them into
# CONFIG_SPECS, then move them into _CONFIG_SCHEMA_PROFILES).

_CONFIG_SCHEMA_ORDER: tuple[str, ...] = (
    # --- Core ---
    "ENV",
    "PORT",
    "HOST",
    # --- Backend URLs ---
    "BACKEND_URL",
    # --- CORS ---
    "USER_CORS_ORIGINS",
    "ADMIN_CORS_ORIGINS",
    # --- Security ---
    JWT_SECRET_ENV,
    "ENFORCE_ANTI_HACKING",
    # --- Database ---
    "DATABASE_URL",
    # --- LLM Providers ---
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    # --- Rate Limits ---
    "GEMINI_RPM_LIMIT",
    "GROQ_RPM_LIMIT",
    "OPENROUTER_RPM_LIMIT",
    # --- Scraper Service ---
    "SCRAPER_MAX_CONCURRENCY",
    "SCRAPER_TIMEOUT_SECONDS",
    # --- Feature Flags ---
    "SELF_HEALING_ENABLED",
    "COST_GUARD_ENABLED",
)


@dataclass(frozen=True)
class _VarProfile:
    """Startup-validator semantics for one classified key (see profiles map)."""

    description: str = ""
    var_type: VarType = VarType.STRING
    required: bool = False
    default: Any = None
    pattern: str | None = None  # Regex pattern
    min_value: int | float | None = None
    max_value: int | float | None = None
    allowed_values: tuple[str, ...] | None = None  # For ENUM type
    severity: Severity = Severity.ERROR
    examples: tuple[str, ...] = ()


_CONFIG_SCHEMA_PROFILES: dict[str, _VarProfile] = {
    "ENV": _VarProfile(
        var_type=VarType.ENUM,
        required=True,
        allowed_values=("local", "development", "test", "staging", "production"),
        description="Application environment",
        examples=("development", "production", "local", "test"),
    ),
    "PORT": _VarProfile(
        var_type=VarType.INTEGER,
        default=8080,
        min_value=1024,
        max_value=65535,
        description="Server port",
    ),
    "HOST": _VarProfile(default="0.0.0.0", description="Server bind address"),
    "BACKEND_URL": _VarProfile(
        var_type=VarType.URL,
        required=True,
        severity=Severity.WARNING,
        pattern=r"^https?://.+",
        description="Public backend URL",
        examples=("https://api.example.com",),
    ),
    "USER_CORS_ORIGINS": _VarProfile(
        var_type=VarType.LIST,
        default=[],
        description="Allowed CORS origins for user portal",
        examples=('["https://supremeai.web.app"]',),
    ),
    "ADMIN_CORS_ORIGINS": _VarProfile(
        var_type=VarType.LIST,
        default=[],
        description="Allowed CORS origins for admin portal",
    ),
    JWT_SECRET_ENV: _VarProfile(
        var_type=VarType.STRING,
        required=True,
        severity=Severity.ERROR,
        # Issue #542 (BE-10): was 32, which let a too-short secret pass boot
        # validation and blow up mid-request when settings.jwt_secret raised
        # RuntimeError (>=64 floor). Now shares JWT_SECRET_MIN_LENGTH with
        # config_secrets.py and env_validator.py.
        # Issue #567 (BE-16): canonical env-var name; JWT_SECRET is accepted
        # as a deprecated alias in _validate_var with a deprecation warning.
        min_value=JWT_SECRET_MIN_LENGTH,
        description=f"JWT signing secret (min {JWT_SECRET_MIN_LENGTH} chars)",
        examples=("your-super-secret-key-at-least-64-bytes-change-me-0123456789abcdef-abcdef",),
    ),
    "ENFORCE_ANTI_HACKING": _VarProfile(
        var_type=VarType.BOOLEAN,
        default=False,
        description="Enable anti-hacking measures",
    ),
    "GEMINI_API_KEY": _VarProfile(
        var_type=VarType.STRING,
        severity=Severity.INFO,
        description="Google Gemini API key",
    ),
    "GROQ_API_KEY": _VarProfile(
        var_type=VarType.STRING,
        severity=Severity.INFO,
        description="Groq API key",
    ),
    "OPENROUTER_API_KEY": _VarProfile(
        var_type=VarType.STRING,
        severity=Severity.INFO,
        description="OpenRouter API key",
    ),
    "GEMINI_RPM_LIMIT": _VarProfile(
        var_type=VarType.INTEGER, default=9, min_value=1, max_value=1000
    ),
    "GROQ_RPM_LIMIT": _VarProfile(
        var_type=VarType.INTEGER, default=28, min_value=1, max_value=1000
    ),
    "OPENROUTER_RPM_LIMIT": _VarProfile(
        var_type=VarType.INTEGER,
        default=19,
        min_value=1,
        max_value=1000,
    ),
}

_CONFIG_SCHEMA_OVERRIDES: dict[str, VarDefinition] = {
    "DATABASE_URL": VarDefinition(
        name="DATABASE_URL",
        var_type=VarType.URL,
        severity=Severity.WARNING,
        description="Database connection URL",
    ),
    "SCRAPER_MAX_CONCURRENCY": VarDefinition(
        name="SCRAPER_MAX_CONCURRENCY",
        var_type=VarType.INTEGER,
        default=3,
        min_value=1,
        max_value=10,
    ),
    "SCRAPER_TIMEOUT_SECONDS": VarDefinition(
        name="SCRAPER_TIMEOUT_SECONDS",
        var_type=VarType.INTEGER,
        default=45,
        min_value=10,
        max_value=300,
    ),
    "SELF_HEALING_ENABLED": VarDefinition(
        name="SELF_HEALING_ENABLED",
        var_type=VarType.BOOLEAN,
        default=True,
        description="Enable self-healing mode",
    ),
    "COST_GUARD_ENABLED": VarDefinition(
        name="COST_GUARD_ENABLED",
        var_type=VarType.BOOLEAN,
        default=True,
        description="Enable cost guard",
    ),
}


def _build_config_schema() -> list[VarDefinition]:
    """Derive CONFIG_SCHEMA from CONFIG_SPECS + startup-validator profiles.

    Fails loudly when the startup-validation policy and the canonical registry
    drift apart (unclassified key, missing profile, renamed spec).
    """
    schema: list[VarDefinition] = []
    for name in _CONFIG_SCHEMA_ORDER:
        override = _CONFIG_SCHEMA_OVERRIDES.get(name)
        if override is not None:
            schema.append(override)
            continue
        spec = get_config_spec(name)
        if spec is None:
            raise RuntimeError(
                f"CONFIG_SCHEMA member {name!r} is not classified in "
                "core/config_classification.py CONFIG_SPECS (issue #1260). "
                "Classify it there (or add it to _CONFIG_SCHEMA_OVERRIDES with "
                "a reason) before startup validation can use it."
            )
        try:
            profile = _CONFIG_SCHEMA_PROFILES[name]
        except KeyError as exc:
            raise RuntimeError(
                f"CONFIG_SCHEMA member {name!r} has no _CONFIG_SCHEMA_PROFILES "
                "entry — declare its validation semantics (var_type/required/"
                "bounds) in core/config_validator.py."
            ) from exc
        schema.append(
            VarDefinition(
                name=name,
                var_type=profile.var_type,
                required=profile.required,
                default=profile.default,
                # Curated validator text; spec.description is intentionally NOT
                # used yet (auto-classified placeholders, see block comment).
                description=profile.description,
                pattern=profile.pattern,
                min_value=profile.min_value,
                max_value=profile.max_value,
                allowed_values=list(profile.allowed_values)
                if profile.allowed_values is not None
                else None,
                severity=profile.severity,
                examples=list(profile.examples),
            )
        )
    return schema


CONFIG_SCHEMA: list[VarDefinition] = _build_config_schema()


def _validate_var(var_def: VarDefinition, settings_obj: Any = None) -> ValidationError | None:
    """Validate a single environment variable."""
    raw_value = os.getenv(var_def.name)
    if not raw_value and var_def.name == JWT_SECRET_ENV:
        # Issue #567 (BE-16): JWT_SECRET is the deprecated alias — accepted
        # so legacy deploys keep validating; resolve_jwt_secret_env() emits
        # the deprecation warning when the alias is what satisfied the var.
        # Returns "" when neither var is set → None lets the settings_obj
        # fallback below still run (non-prod generated secret, vault, …).
        raw_value = resolve_jwt_secret_env() or None

    if raw_value is None and settings_obj is not None:
        prop_name = var_def.name.lower()
        if var_def.name == JWT_SECRET_ENV:
            # Issue #567 (BE-16): the settings attribute is `jwt_secret`, not
            # the canonical env-var name lowercased.
            prop_name = "jwt_secret"
        if hasattr(settings_obj, prop_name):
            try:
                val = getattr(settings_obj, prop_name)
                if val:
                    from pydantic import SecretStr

                    if isinstance(val, SecretStr):
                        raw_value = val.get_secret_value()
                    else:
                        raw_value = str(val)
            except Exception as exc:  # best-effort settings read — fallback to default
                import logging

                logging.getLogger(__name__).debug(
                    "[config_validator] failed to read '%s' from settings: %s", prop_name, exc
                )

    value = raw_value if raw_value is not None else var_def.default

    # Check required
    if var_def.required and value is None:
        return ValidationError(
            var_name=var_def.name,
            severity=var_def.severity,
            message=f"Required variable is not set. {var_def.description}",
            suggestion=f"Set {var_def.name}={'<value>' if not var_def.examples else var_def.examples[0]}",
        )

    # Use default if empty
    if value is None:
        return None

    # Type-specific validation
    if var_def.var_type == VarType.URL and value:
        if not re.match(var_def.pattern or r"^https?://.+", str(value)):
            return ValidationError(
                var_name=var_def.name,
                severity=var_def.severity,
                message=f"Invalid URL format: '{value}'",
                suggestion="URL must start with http:// or https://",
                actual_value=str(value),
            )

    elif var_def.var_type == VarType.ENUM and var_def.allowed_values:
        if str(value) not in var_def.allowed_values:
            return ValidationError(
                var_name=var_def.name,
                severity=var_def.severity,
                message=f"Invalid value: '{value}'. Must be one of: {var_def.allowed_values}",
                actual_value=str(value),
            )

    elif var_def.var_type == VarType.INTEGER:
        try:
            int_val = int(value)
            if var_def.min_value is not None and int_val < var_def.min_value:
                return ValidationError(
                    var_name=var_def.name,
                    severity=Severity.WARNING,
                    message=f"Value {int_val} below minimum {var_def.min_value}",
                )
            if var_def.max_value is not None and int_val > var_def.max_value:
                return ValidationError(
                    var_name=var_def.name,
                    severity=Severity.WARNING,
                    message=f"Value {int_val} above maximum {var_def.max_value}",
                )
        except (ValueError, TypeError):
            return ValidationError(
                var_name=var_def.name,
                severity=var_def.severity,
                message=f"Invalid integer: '{value}'",
            )

    elif var_def.var_type == VarType.BOOLEAN:
        if str(value).lower() not in ("true", "false", "1", "0", "", "none"):
            return ValidationError(
                var_name=var_def.name,
                severity=Severity.WARNING,
                message=f"Invalid boolean: '{value}'. Use true/false/1/0",
            )

    elif var_def.var_type == VarType.STRING:
        if var_def.min_value is not None and len(str(value)) < var_def.min_value:
            return ValidationError(
                var_name=var_def.name,
                severity=var_def.severity,
                message=f"Value length {len(str(value))} below minimum {var_def.min_value} characters",
            )
        if var_def.max_value is not None and len(str(value)) > var_def.max_value:
            return ValidationError(
                var_name=var_def.name,
                severity=var_def.severity,
                message=f"Value length {len(str(value))} above maximum {var_def.max_value} characters",
            )

    # Pattern match
    if var_def.pattern and value:
        if not re.match(var_def.pattern, str(value)):
            return ValidationError(
                var_name=var_def.name,
                severity=var_def.severity,
                message=f"Value doesn't match pattern {var_def.pattern}",
                actual_value=str(value),
            )

    return None


def validate_config() -> ConfigValidationResult:
    """Validate all configuration variables. Returns validation result."""
    from core.config import settings

    errors = []
    warnings = []
    validated = {}

    for var_def in CONFIG_SCHEMA:
        error = _validate_var(var_def, settings)

        # Retrieve final value
        raw = os.getenv(var_def.name)
        if raw is None:
            prop_name = var_def.name.lower()
            if hasattr(settings, prop_name):
                val = getattr(settings, prop_name)
                if val:
                    from pydantic import SecretStr

                    if isinstance(val, SecretStr):
                        raw = val.get_secret_value()
                    else:
                        raw = str(val)

        validated[var_def.name] = raw if raw is not None else var_def.default

        if error:
            if error.severity == Severity.ERROR:
                errors.append(error)
            else:
                warnings.append(error)

    return ConfigValidationResult(
        is_valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        validated_vars=validated,
    )


def print_config_summary() -> None:
    """Print masked configuration summary for debugging."""
    logger.debug("\n" + "=" * 50)
    logger.debug("🔧 Configuration Summary")
    logger.debug("=" * 50)

    sensitive_keys = ("SECRET", "KEY", "PASSWORD", "TOKEN")

    for var_def in CONFIG_SCHEMA:
        value = os.getenv(var_def.name, var_def.default)
        if value is None:
            display = "⟨not set⟩"
        elif any(s in var_def.name for s in sensitive_keys):
            display = "*****" if len(str(value)) > 0 else "⟨empty⟩"
        else:
            display = str(value)[:50] + ("..." if len(str(value)) > 50 else "")

        req_marker = " ✗" if var_def.required and value is None else " ✓"
        logger.debug(f"  {var_def.name:<30} = {display:<55}{req_marker}")

    logger.debug("=" * 50 + "\n")


# =============================================================================
