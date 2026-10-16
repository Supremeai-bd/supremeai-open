"""SupremeAI deterministic 8-step agent runner harness (issue #334).

Package root. Offline-safe by doctrine: importing this package performs
zero file/network I/O and has zero third-party dependencies (AGENT_RULES.md
§13 — zero-dependency doctrine). All behaviour lives in
:mod:`runner.agent_runner`; this module only re-exports the public surface.
"""

from runner.agent_runner import (  # noqa: F401
    AGENT_LOOP_SPEC_SSOT,
    ENVELOPE_FORMAT,
    ENVELOPE_VERSION,
    RUNNER_CONTRACT_VERSION,
    STEPS,
    VERIFY_TIERS,
    AgentRunner,
    ClaimError,
    EnvelopeError,
    RunnerError,
    ScopeViolation,
    VerificationError,
    load_envelope,
)

__all__ = [
    "AGENT_LOOP_SPEC_SSOT",
    "ENVELOPE_FORMAT",
    "ENVELOPE_VERSION",
    "RUNNER_CONTRACT_VERSION",
    "STEPS",
    "VERIFY_TIERS",
    "AgentRunner",
    "ClaimError",
    "EnvelopeError",
    "RunnerError",
    "ScopeViolation",
    "VerificationError",
    "load_envelope",
]
