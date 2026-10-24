# backend/core/llm/provider_registry.py
"""Runtime provider registry (#3214) — provider-agnostic capability selection.

#3214-এর ছোটতম architecture-preserving ধাপ: বিদ্যমান static ম্যাপগুলোকে
(llm_gateway.registry-এর single source of truth) runtime object-এ বাঁধা, যাতে —

  * Credential / Provider / Model / Capability আলাদাভাবে represent হয় (AC-1),
  * invalid provider কোড পরিবর্তন ছাড়াই runtime-এ disable হয় (AC-3),
  * healthy alternate provider স্বয়ংক্রিয়ভাবে নির্বাচিত হয় (AC-4),
  * retired model structured state হিসেবে দৃশ্যমান থাকে (AC-5),
  * raw key কখনো ধরা/লগ হয় না — শুধু settings-attr-এর নাম (AC-6)।

দ্বিতীয় কোনো routing/health system তৈরি হয় না (issue guardrail):
key-level cooldown/rotation বিদ্যমান `_provider_key_pool`-এর একচেটিয়া
দায়িত্ব — এই registry সেটি ডুপ্লিকেট করে না (pool-এর API async এবং raw
key value চায়, যা AC-6-এর কারণে এখানে আসতেই পারে না)। এই মডিউল শুধু
*নির্বাচন* করে; কল আগের মতোই বিদ্যমান gateway/adapter দিয়ে যায়।
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

# বাংলা মন্তব্য (#3214): duplicate source of truth নয় — বিদ্যমান registry-র
# static maps + retired-set থেকেই state নির্মিত হয়।
from core.llm.llm_gateway.registry import (
    _MODEL_KEY_MAP,
    _PROVIDER_API_BASES,
    _RETIRED_MODELS,
)


class Capability(StrEnum):
    """Issue-উদ্ধৃত capability শ্রেণি — application এটাই চায়, model নয়।"""

    TEXT = "text"
    VISION = "vision"
    TOOL_CALLING = "tool_calling"
    REASONING = "reasoning"
    EMBEDDING = "embedding"


class ProviderHealth(StrEnum):
    """Provider-লেভেল runtime state (AC-3)। key-cooldown এখানে নয়।"""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CredentialDescriptor:
    """শুধু *কোথায়* key আছে — value কখনোই এখানে আসে না (AC-6)।"""

    provider: str
    settings_attr: str


@dataclass(frozen=True)
class ModelDescriptor:
    model: str
    provider: str
    capabilities: frozenset[Capability]
    retired: bool = False


@dataclass(frozen=True)
class ProviderDescriptor:
    name: str
    credential: CredentialDescriptor
    api_base: str | None
    models: tuple[ModelDescriptor, ...]


@dataclass(frozen=True)
class Selection:
    """select()-এর ফল — SDK object নয়, descriptor (adapter isolation, AC-2)।"""

    model: ModelDescriptor
    provider: ProviderDescriptor


@dataclass
class NoCompatibleProviderError(LookupError):
    """Fail-honest (issue guardrail): কোনো compatible healthy provider নেই।

    নীরবে অন্য semantics-এ চলে যাওয়া নিষেধ — structured evidence সহ ব্যর্থ হও।
    """

    capability: Capability
    evidence: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        reasons = "; ".join(f"{m}={r}" for m, r in sorted(self.evidence.items()))
        return f"no healthy provider serves capability '{self.capability.value}'" + (
            f" [{reasons}]" if reasons else ""
        )


class ProviderRegistry:
    """Capability→provider নির্বাচন — বিদ্যমান static maps থেকে নির্মিত।

    Model→provider ম্যাপ repo-তে স্ট্যাটিকভাবে নেই (call-time prefix
    convention); তাই নির্মাণে *ঘোষিত* model→(provider, capabilities) ম্যাপ
    নেয় — কলার তার নিজস্ব routing policy থেকে দেয়। এতে এই মডিউল কোনো
    model-তালিকা hardcode করে না (second source of truth এড়ানো)।
    """

    def __init__(
        self,
        models: dict[str, tuple[str, frozenset[Capability]]],
        provider_overrides: dict[str, CredentialDescriptor] | None = None,
    ) -> None:
        self._models: dict[str, ModelDescriptor] = {
            model_id: ModelDescriptor(
                model=model_id,
                provider=provider,
                capabilities=caps,
                retired=model_id in _RETIRED_MODELS,
            )
            for model_id, (provider, caps) in models.items()
        }
        providers = {d.provider for d in self._models.values()}
        unknown = providers - set(_MODEL_KEY_MAP)
        if unknown:
            raise ValueError(f"models reference providers without credentials: {sorted(unknown)}")
        self._providers: dict[str, ProviderDescriptor] = {
            name: ProviderDescriptor(
                name=name,
                credential=(provider_overrides or {}).get(name)
                or CredentialDescriptor(provider=name, settings_attr=_MODEL_KEY_MAP[name]),
                api_base=_PROVIDER_API_BASES.get(name),
                models=tuple(d for d in self._models.values() if d.provider == name),
            )
            for name in sorted(providers)
        }
        # Runtime disable-state (AC-3): কোড পরিবর্তন ছাড়াই invalid
        # provider বন্ধ করার জায়গা — instance-scoped (শেয়ার্ড নয়)।
        self._health: dict[str, ProviderHealth] = {
            name: ProviderHealth.AVAILABLE for name in self._providers
        }
        self._reasons: dict[str, str] = {}

    # ---- runtime health (AC-3) ------------------------------------------

    def mark_unavailable(self, provider: str, reason: str) -> None:
        if provider not in self._providers:
            raise KeyError(f"unknown provider {provider!r}")
        if not reason.strip():  # fail-honest: কারণ ছাড়া বন্ধ করা যায় না
            raise ValueError("reason required to mark a provider unavailable")
        self._health[provider] = ProviderHealth.UNAVAILABLE
        self._reasons[provider] = reason

    def mark_available(self, provider: str) -> None:
        if provider not in self._providers:
            raise KeyError(f"unknown provider {provider!r}")
        self._health[provider] = ProviderHealth.AVAILABLE
        self._reasons.pop(provider, None)

    # ---- selection (AC-4) ------------------------------------------------

    def select(
        self,
        capability: Capability,
        exclude_models: frozenset[str] | set[str] = frozenset(),
    ) -> Selection:
        """প্রথম healthy candidate দেয়; না পেলে fail-honest।

        Deterministic walk: sorted model-id (একই ইনপুট → একই সিদ্ধান্ত)।
        """
        evidence: dict[str, str] = {}
        candidates: list[ModelDescriptor] = []
        for desc in sorted(self._models.values(), key=lambda d: d.model):
            if capability not in desc.capabilities:
                continue
            if desc.retired:
                evidence[desc.model] = "retired"
                continue
            if desc.model in exclude_models:
                evidence[desc.model] = "excluded"
                continue
            candidates.append(desc)
        for desc in candidates:
            if self._health[desc.provider] is not ProviderHealth.AVAILABLE:
                evidence[desc.model] = self._reasons.get(desc.provider, "unavailable")
                continue
            return Selection(model=desc, provider=self._providers[desc.provider])
        raise NoCompatibleProviderError(capability=capability, evidence=evidence)

    # ---- observability (AC-5) --------------------------------------------

    def health_snapshot(self) -> dict[str, str]:
        """প্রতি provider অবস্থা + retired model — raw key ছাড়া (AC-5/6)।"""
        out: dict[str, str] = {name: health.value for name, health in self._health.items()}
        for model in self._models.values():
            if model.retired:
                out[f"model:{model.model}"] = "retired"
        return out
