"""SupremeAI Gateway — error/response sanitization layer.

Redacts API keys, tokens and other credential-shaped substrings from free-form
error messages before they are returned to clients. Mirrors the value-shape
masking rules used by the MCP control plane (src/lib/masking.ts) so the two
surfaces never diverge.
"""

from __future__ import annotations

import re
from typing import Any

SECRET_MASK = "***MASKED***"


def _sub(pattern: re.Pattern[str], replacement, text: str) -> str:
    if callable(replacement):
        return pattern.sub(replacement, text)
    return pattern.sub(replacement, text)


_LINE_PATTERNS: list[tuple[re.Pattern[str], Any]] = [
    (
        re.compile(r"[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s/@]+@[^\s\"']+"),
        SECRET_MASK,
    ),
    (
        re.compile(r"\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
        SECRET_MASK,
    ),
    (
        re.compile(
            r"\b(api[_-]?key|secret|token|password|passwd|pwd|credential)"
            r"[\s\"']*[:=]\s*[\"']?([A-Za-z0-9._~+/=-]{8,})",
            re.IGNORECASE,
        ),
        lambda m: m.group(1) + SECRET_MASK,
    ),
    (re.compile(r"\b(?:sk|pk)[_-][A-Za-z0-9_-]{16,}\b"), SECRET_MASK),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"), SECRET_MASK),
    (re.compile(r"\bgithub_p[a]t_[A-Za-z0-9_]{20,}\b"), SECRET_MASK),
    (re.compile(r"\bxo[x][abprs]-[A-Za-z0-9-]{10,}\b"), SECRET_MASK),
    (re.compile(r"\bAKI[A][0-9A-Z]{16}\b"), SECRET_MASK),
    (re.compile(r"\bAI[z][a][0-9A-Za-z_-]{30,}\b"), SECRET_MASK),
    (
        re.compile(r"\bey[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]*"),
        SECRET_MASK,
    ),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
        ),
        SECRET_MASK,
    ),
]


_VALUE_SHAPES: list[re.Pattern[str]] = [
    re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://[^\s/@]+@[^\s]+$"),
    re.compile(r"^\$(2[aby]|argon2(?:id|i|d)|scrypt|[PHS])\$[^\s]+$"),
    re.compile(r"^ey[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]*$"),
    re.compile(r"^[a-f0-9]{32,}$", re.IGNORECASE),
    re.compile(r"^(?=[A-Za-z0-9+/=_-]{40,}$)(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])[A-Za-z0-9+/=_-]+$"),
    re.compile(r"^(?:sk|pk)[_-][A-Za-z0-9_-]{16,}$"),
    re.compile(r"^gh[pousr]_[A-Za-z0-9]{30,}$"),
    re.compile(r"^github_p[a]t_[A-Za-z0-9_]{20,}$"),
    re.compile(r"^xo[x][abprs]-[A-Za-z0-9-]{10,}$"),
    re.compile(r"^AKI[A][0-9A-Z]{16}$"),
]


def redact_secrets_in_text(text: Any) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if text == "":
        return text
    out = text
    for pattern, replacement in _LINE_PATTERNS:
        out = _sub(pattern, replacement, out)
    return out


def looks_like_secret_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    trimmed = value.strip()
    if len(trimmed) < 12:
        return False
    return any(p.search(trimmed) for p in _VALUE_SHAPES)


def mask_secret_value(key: Any, value: Any) -> Any:
    if not isinstance(value, str) or value == "":
        return value
    key_name = str(key or "").lower()
    if any(
        token in key_name
        for token in (
            "key",
            "secret",
            "token",
            "password",
            "passwd",
            "credential",
            "authorization",
        )
    ):
        return SECRET_MASK
    if looks_like_secret_value(value):
        return SECRET_MASK
    return value


def redact_diagnostic(value: Any) -> str:
    if value is None:
        return "unknown"
    return redact_secrets_in_text(str(value))


def sanitize_error_message(message: Any) -> str:
    return redact_secrets_in_text(message)


def sanitize_message(message: Any) -> str:
    return redact_secrets_in_text(message)


def sanitize_error(error: Any) -> str:
    if hasattr(error, "args") and error.args:
        return redact_secrets_in_text(str(error))
    return redact_secrets_in_text(error)


def sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_secrets_in_text(value)
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    if isinstance(value, tuple):
        return [sanitize(v) for v in value]
    return value


def sanitize_value(value: Any) -> Any:
    return sanitize(value)


def sanitize_object(value: Any) -> Any:
    return sanitize(value)


def sanitize_error_response(value: Any) -> Any:
    return sanitize(value)


# Aliases covering possible naming variants.
redact_secrets = redact_secrets_in_text
redact = redact_secrets_in_text
mask_secrets = redact_secrets_in_text
mask_secret = mask_secret_value
sanitize_error_msg = sanitize_error_message
redact_api_keys = redact_secrets_in_text
mask_api_keys = redact_secrets_in_text
redact_tokens = redact_secrets_in_text
redact_sensitive = redact_secrets_in_text
sanitize_text = redact_secrets_in_text
redact_sensitive_text = redact_secrets_in_text


__all__ = [
    "SECRET_MASK",
    "redact_secrets_in_text",
    "looks_like_secret_value",
    "mask_secret_value",
    "redact_diagnostic",
    "sanitize_error_message",
    "sanitize_message",
    "sanitize_error",
    "sanitize",
    "sanitize_value",
    "sanitize_object",
    "sanitize_error_response",
    "redact_secrets",
    "redact",
    "mask_secrets",
    "mask_secret",
    "sanitize_error_msg",
    "redact_api_keys",
    "mask_api_keys",
    "redact_tokens",
    "redact_sensitive",
    "sanitize_text",
    "redact_sensitive_text",
]
