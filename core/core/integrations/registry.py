"""
SupremeAI Integration Registry
==============================
বাংলা: সব optional integration-এর central registry। settings থেকে প্রতিটি
integration-এর enabled-status পড়ে ও সেটার metadata (scope, capabilities,
fallback) declare করে।

এই registry কোনো integration-কে enable/disable করে না — শুধু বর্তমান state
report করে। Enable/disable সব settings layer (env vars) এর মাধ্যমে হয়।
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Optional

from ..config import settings


class IntegrationScope(StrEnum):
    """Integration-এর deployment scope (Plan Section 16/17)।"""

    BACKEND = "backend"  # backend infrastructure (n8n, Appwrite server)
    USER_LOCAL = "user-local"  # user-এর local machine (Ollama)
    OBSERVABILITY = "observability"  # tracing/metrics (OTel, Langfuse, Sentry)
    OPTIONAL_PROVIDER = "optional-provider"  # pluggable adapter (Mem0, Graphiti, E2B)


class IntegrationStatus(StrEnum):
    """Integration-এর current operational status।"""

    ENABLED = "enabled"  # settings-এ enabled ও configured
    DISABLED = "disabled"  # settings-এ disabled
    MISCONFIGURED = "misconfigured"  # enabled কিন্তু required config missing
    NOT_ADOPTED = "not-adopted"  # এখনও integrate করা হয়নি (Plan P3 items)


@dataclass(frozen=True)
class IntegrationInfo:
    """একটি integration-এর full metadata (Plan Section 28)।"""

    key: str  # unique identifier (e.g., 'n8n', 'ollama')
    name: str  # human-readable name
    category: str  # 'automation' | 'storage' | 'messaging' | 'ai_provider' | 'observability' | 'sandbox' | 'memory' | 'coding_agent'
    scope: IntegrationScope
    enabled: bool  # settings-এ enabled কিনা
    status: IntegrationStatus
    required_for_core: bool = False  # Plan Section 39: core independence
    fallback: str | None = None  # enabled না থাকলে কী fallback
    privacy_mode: str | None = None  # 'full' | 'metadata_only' | 'disabled' (Section 34)
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    config_note: str = ""  # কী env vars দরকার
    version: str | None = None  # adapter version (future)


# ── Integration definitions ───────────────────────────────────────────────────
# Plan Section 2 ও 40 অনুযায়ী সব integration। প্রতিটির scope ও fallback স্পষ্ট।

# Issue #1818 (island-4 fix): premium integration gating now flows through the
# unified feature-flag checker (env tri-state → Supabase feature_flags table)
# instead of plain env-settings, so admin-managed DB flags affect runtime
# gating. Non-premium integrations (n8n, appwrite, ...) stay env-only.
from core.feature_flags import feature_flags as _premium_flags

_INTEGRATIONS: dict[str, IntegrationInfo] = {}


def _register(info: IntegrationInfo) -> None:
    _INTEGRATIONS[info.key] = info


def _bool_setting(name: str, default: bool = False) -> bool:
    """settings থেকে bool flag পড়ে — attribute না থাকলে default।"""
    val = getattr(settings, name, None)
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes")
    return bool(val)


def _str_setting(name: str, default: str = "") -> str:
    """settings থেকে str পড়ে — attribute না থাকলে default।"""
    val = getattr(settings, name, None)
    return str(val) if val else default


def _build_registry() -> None:
    """settings থেকে পড়ে registry populate করে। প্রতিটি call-এ rebuild হয়
    যাতে runtime-এ env var change ধরা যায় (test-এ helpful)।"""
    _INTEGRATIONS.clear()

    # ── Automation ──────────────────────────────────────────────────────────
    n8n_enabled = _bool_setting("n8n_enabled")
    n8n_base = _str_setting("n8n_base_url")
    n8n_status = (
        IntegrationStatus.ENABLED
        if n8n_enabled and n8n_base
        else IntegrationStatus.MISCONFIGURED
        if n8n_enabled and not n8n_base
        else IntegrationStatus.DISABLED
    )
    _register(
        IntegrationInfo(
            key="n8n",
            name="n8n Workflow Automation",
            category="automation",
            scope=IntegrationScope.BACKEND,
            enabled=n8n_enabled,
            status=n8n_status,
            required_for_core=False,
            fallback="event skipped (core operation continues)",
            capabilities=("workflow_dispatch", "webhook_signature", "retry_backoff"),
            config_note="N8N_ENABLED + N8N_BASE_URL + N8N_WEBHOOK_SECRET",
        )
    )

    # ── Storage ─────────────────────────────────────────────────────────────
    appwrite_enabled = _bool_setting("appwrite_enabled")
    appwrite_endpoint = _str_setting("appwrite_endpoint")
    appwrite_status = (
        IntegrationStatus.ENABLED
        if appwrite_enabled and appwrite_endpoint
        else IntegrationStatus.MISCONFIGURED
        if appwrite_enabled and not appwrite_endpoint
        else IntegrationStatus.DISABLED
    )
    _register(
        IntegrationInfo(
            key="appwrite",
            name="Appwrite (Storage/Messaging)",
            category="storage",
            scope=IntegrationScope.BACKEND,
            enabled=appwrite_enabled,
            status=appwrite_status,
            required_for_core=False,
            fallback="local storage adapter",
            capabilities=("storage", "messaging_optional"),
            config_note="APPWRITE_ENABLED + APPWRITE_ENDPOINT + APPWRITE_PROJECT_ID",
        )
    )

    # ── AI Provider (local) ────────────────────────────────────────────────
    ollama_url = _str_setting("ollama_url")
    ollama_enabled = bool(ollama_url)
    _register(
        IntegrationInfo(
            key="ollama",
            name="Ollama Local AI",
            category="ai_provider",
            scope=IntegrationScope.USER_LOCAL,
            enabled=ollama_enabled,
            status=IntegrationStatus.ENABLED if ollama_enabled else IntegrationStatus.DISABLED,
            required_for_core=False,
            fallback="cloud AI providers (Plan Section 16)",
            privacy_mode="full",  # local prompts stay local by design
            capabilities=("local_llm", "zero_cost_inference"),
            config_note="OLLAMA_URL (user-local, never backend infrastructure)",
        )
    )

    # ── Observability ───────────────────────────────────────────────────────
    sentry_dsn = _str_setting("sentry_dsn")
    _register(
        IntegrationInfo(
            key="sentry",
            name="Sentry Error Tracking",
            category="observability",
            scope=IntegrationScope.OBSERVABILITY,
            enabled=bool(sentry_dsn),
            status=IntegrationStatus.ENABLED if sentry_dsn else IntegrationStatus.DISABLED,
            required_for_core=False,
            fallback="loguru structured logs",
            capabilities=("error_tracking", "incident_workflow"),
            config_note="SENTRY_DSN",
        )
    )

    # ── Optional AI/LLM providers ──────────────────────────────────────────
    # LiteLLM — Plan Section 23: audit করা দরকার, dependency আছে কিন্তু wired কিনা verify করতে হবে
    _register(
        IntegrationInfo(
            key="litellm",
            name="LiteLLM Gateway",
            category="ai_provider",
            scope=IntegrationScope.OPTIONAL_PROVIDER,
            enabled=False,  # Plan: NOT YET verified as project-owned adapter
            status=IntegrationStatus.NOT_ADOPTED,
            required_for_core=False,
            fallback="existing direct providers (HF, OpenAI, Gemini)",
            capabilities=("model_routing",),
            config_note="Plan Section 23: audit required before enabling",
        )
    )

    # Langfuse — Plan Section 24
    _register(
        IntegrationInfo(
            key="langfuse",
            name="Langfuse AI Observability",
            category="observability",
            scope=IntegrationScope.OBSERVABILITY,
            enabled=False,
            status=IntegrationStatus.NOT_ADOPTED,
            required_for_core=False,
            fallback="OpenTelemetry traces",
            capabilities=("prompt_tracing", "evaluation"),
            config_note="Plan Section 24: audit required; never mandatory for AI availability",
        )
    )

    # ── Optional adapters (Plan P2) ─────────────────────────────────────────
    _register(
        IntegrationInfo(
            key="mem0",
            name="Mem0 Memory",
            category="memory",
            scope=IntegrationScope.OPTIONAL_PROVIDER,
            enabled=_premium_flags.mem0_enabled(),
            status=IntegrationStatus.ENABLED
            if _premium_flags.mem0_enabled()
            else IntegrationStatus.DISABLED,
            required_for_core=False,
            fallback="in-memory fallback (not durable — Plan Section 18)",
            capabilities=("memory_persistence",),
            config_note="SUPREMEAI_MEM0_ENABLED",
        )
    )

    _register(
        IntegrationInfo(
            key="graphiti",
            name="Graphiti Temporal Knowledge Graph",
            category="memory",
            scope=IntegrationScope.OPTIONAL_PROVIDER,
            enabled=_premium_flags.graphiti_enabled(),
            status=IntegrationStatus.ENABLED
            if _premium_flags.graphiti_enabled()
            else IntegrationStatus.DISABLED,
            required_for_core=False,
            fallback="none (Plan Section 19: fix async before broad enable)",
            capabilities=("temporal_knowledge_graph",),
            config_note="SUPREMEAI_GRAPHITI_ENABLED (sync/async issue flagged)",
        )
    )

    _register(
        IntegrationInfo(
            key="browser_use",
            name="Browser-Use Agentic Browser",
            category="browser",
            scope=IntegrationScope.OPTIONAL_PROVIDER,
            enabled=_premium_flags.browser_use_enabled(),
            status=IntegrationStatus.ENABLED
            if _premium_flags.browser_use_enabled()
            else IntegrationStatus.DISABLED,
            required_for_core=False,
            fallback="existing Playwright browser stack (Plan Section 20)",
            capabilities=("agentic_browsing",),
            config_note="SUPREMEAI_BROWSER_USE_ENABLED (audit vs Playwright first)",
        )
    )

    _register(
        IntegrationInfo(
            key="e2b",
            name="E2B Sandbox",
            category="sandbox",
            scope=IntegrationScope.OPTIONAL_PROVIDER,
            enabled=_premium_flags.e2b_enabled(),
            status=IntegrationStatus.ENABLED
            if _premium_flags.e2b_enabled()
            else IntegrationStatus.DISABLED,
            required_for_core=False,
            fallback="existing local/server sandbox (Plan Section 21)",
            capabilities=("code_sandbox",),
            config_note="SUPREMEAI_E2B_ENABLED",
        )
    )

    _register(
        IntegrationInfo(
            key="openhands",
            name="OpenHands Coding Agent",
            category="coding_agent",
            scope=IntegrationScope.OPTIONAL_PROVIDER,
            enabled=_premium_flags.openhands_enabled(),
            status=IntegrationStatus.ENABLED
            if _premium_flags.openhands_enabled()
            else IntegrationStatus.DISABLED,
            required_for_core=False,
            fallback="SupremeAI native code agent (Plan Section 22)",
            capabilities=("coding_agent",),
            config_note="SUPREMEAI_OPENHANDS_ENABLED + OPENHANDS_SERVER_URL",
        )
    )

    # ── Plan P3 (defer) ─────────────────────────────────────────────────────
    _register(
        IntegrationInfo(
            key="openfga",
            name="OpenFGA Authorization",
            category="authorization",
            scope=IntegrationScope.OPTIONAL_PROVIDER,
            enabled=False,
            status=IntegrationStatus.NOT_ADOPTED,
            required_for_core=False,
            fallback="existing RBAC (Plan Section 40: defer until resource-level authz needed)",
            capabilities=("fine_grained_authz",),
            config_note="Plan P3: defer",
        )
    )

    _register(
        IntegrationInfo(
            key="livekit",
            name="LiveKit Voice/Realtime",
            category="realtime",
            scope=IntegrationScope.OPTIONAL_PROVIDER,
            enabled=False,
            status=IntegrationStatus.NOT_ADOPTED,
            required_for_core=False,
            fallback="none (Plan Section 40: defer until voice/realtime is product requirement)",
            capabilities=("voice", "realtime"),
            config_note="Plan P3: defer",
        )
    )


def list_integrations() -> list[IntegrationInfo]:
    """সব registered integration-এর তালিকা (current state)।"""
    _build_registry()
    return list(_INTEGRATIONS.values())


def get_integration(key: str) -> IntegrationInfo | None:
    """একটি specific integration-এর info।"""
    _build_registry()
    return _INTEGRATIONS.get(key)


def is_enabled(key: str) -> bool:
    """একটি integration enabled কিনা (convenience)।"""
    info = get_integration(key)
    return bool(info and info.enabled)
