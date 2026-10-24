"""FCC circles package — Federated Capability Circle Architecture.

Public surface:
- contracts: canonical models (CircleName, ExecutionContext, results…)
- envelopes: the ONLY cross-circle wire format (FCC contract)
- centers:   one local coordinator per circle
- governance_core: the small Global Governance Core
- registry:  legacy flat registry (pre-FCC compatibility surface)
- bootstrap: build_circle_registry (legacy) + build_federation (FCC)
"""

from core.circles.bootstrap import build_circle_registry, build_federation
from core.circles.centers import CircleCenter, build_default_centers
from core.circles.contracts import (
    CapabilityRef,
    CapabilityRequest,
    CircleManifest,
    CircleName,
    EventEnvelope,
    ExecutionContext,
    ExecutionResult,
    ExecutionStatus,
    PolicyDecision,
    RiskLevel,
)
from core.circles.envelopes import (
    ExecutionEnvelope,
    ExecutionError,
    ResultEnvelope,
    result_envelope_from_execution,
)
from core.circles.event_journal import CircleEventJournal, circle_event_journal
from core.circles.governance_core import (
    GovernanceCore,
    default_global_policy,
    get_governance_core,
    reset_governance_core,
)
from core.circles.manifests import default_manifests
from core.circles.registry import CircleRegistry, circle_registry

__all__ = [
    # contracts
    "CapabilityRef",
    "CapabilityRequest",
    "CircleManifest",
    "CircleName",
    "EventEnvelope",
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionStatus",
    "PolicyDecision",
    "RiskLevel",
    # envelopes (FCC wire contract)
    "ExecutionEnvelope",
    "ExecutionError",
    "ResultEnvelope",
    "result_envelope_from_execution",
    # centers
    "CircleCenter",
    "build_default_centers",
    # governance core
    "GovernanceCore",
    "default_global_policy",
    "get_governance_core",
    "reset_governance_core",
    # registries & bootstrap
    "CircleRegistry",
    "circle_registry",
    "build_circle_registry",
    "build_federation",
    "default_manifests",
    "CircleEventJournal",
    "circle_event_journal",
]
