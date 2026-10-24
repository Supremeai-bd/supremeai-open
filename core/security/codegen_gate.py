"""Fail-closed gate for in-process execution of LLM-generated code (issue #704).

#704 (P2): ``backend/tools/ephemeral_synthesizer.py`` and
``backend/services/tool_forge.py`` execute LLM-generated Python via in-process
``exec()`` with a restricted ``__builtins__`` namespace. Restricted builtins are
NOT a security boundary (attribute-chain escapes are well known), so running
model-generated code inside the API process is a sandbox-escape / RCE risk.

Remediation strategy (issue #704 item 2): the in-process path is **fail-closed
by default**. All production/staging deployments refuse to exec unless the
explicit escape hatch ``SUPREMEAI_ALLOW_INPROCESS_CODEGEN`` is set to a truthy
value — intended for local development only. When the gate is off, call sites
return/raise their own structured error conventions and log a warning; nothing
is executed.

A real isolated runner exists in the repo (``backend/sandbox/docker_sandbox.py``,
``backend/tools/devops/docker_sandbox.py: DockerSandbox.run_secure`` — no
network, read-only FS, memory/CPU caps, hard timeout), but its API is
stdout/exit-code based and synchronous, so routing the return-value-oriented
async call sites through it cannot be done safely blind. Until that wiring
lands, this gate makes the in-process path opt-in.
"""

from __future__ import annotations

import os

from core.logging_config import logger

# Explicit opt-in env var. Default (unset/empty/any non-truthy value) = OFF.
ALLOW_INPROCESS_CODEGEN_ENV = "SUPREMEAI_ALLOW_INPROCESS_CODEGEN"

# Truthy spellings accepted for the escape hatch (matches repo convention,
# e.g. config.py: ("true", "1", "yes")). Compared lowercase via .lower().
_TRUTHY_VALUES = frozenset({"1", "true", "yes"})

_boot_warning_emitted = False


def inprocess_codegen_enabled() -> bool:
    """Return True only when in-process codegen exec was explicitly enabled.

    Reads the env var at call time (not import time) so tests and operators can
    toggle it without process reloads. Anything other than an explicit truthy
    value keeps the gate closed (fail-closed default).
    """
    return os.getenv(ALLOW_INPROCESS_CODEGEN_ENV, "").strip().lower() in _TRUTHY_VALUES


def denied_reason(context: str) -> str:
    """Structured denial message used by gated call sites (#704)."""
    return (
        "In-process LLM codegen execution is disabled by security policy "
        f"(issue #704, gate: {context}). Restricted builtins are not a sandbox; "
        f"model-generated code must run in an isolated runner. To allow it for "
        f"LOCAL DEVELOPMENT ONLY, set {ALLOW_INPROCESS_CODEGEN_ENV}=true."
    )


def warn_inprocess_codegen_boot(context: str) -> None:
    """Emit the loud one-time boot warning when the escape hatch is enabled."""
    global _boot_warning_emitted
    if _boot_warning_emitted:
        return
    _boot_warning_emitted = True
    logger.warning(
        "🚨 [codegen-gate] IN-PROCESS LLM CODEGEN EXECUTION IS ENABLED "
        f"({ALLOW_INPROCESS_CODEGEN_ENV} is set truthy; gate: {context}). "
        "Model-generated Python will run inside the API process — restricted "
        "builtins are NOT a security boundary. This mode is for local "
        "development only; production/staging must keep the gate off."
    )
