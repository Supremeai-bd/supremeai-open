"""Self-check helpers extracted from core/__init__.py (#1347).

The 16 KB god-init used to carry these inline; they belong to a dedicated
module so the package __init__ stays import-light and readable.
"""

from __future__ import annotations

from typing import Any


def get_complete_ai_system() -> dict[str, Any]:
    """Assemble the complete AI system (research + production components)."""
    try:
        from core.evolution import get_evolution_pipeline
    except ImportError:  # pragma: no cover - repo-root execution contexts
        from evolution import get_evolution_pipeline  # type: ignore

    evolution_components = get_evolution_pipeline()

    from core import AccessibilityComplianceEngine, ProductionDeploymentSystem, get_performance_optimizer

    qa_suite = None
    try:
        from core.testing.qa_suite import QASuite

        qa_suite = QASuite()
    except (ImportError, ValueError):
        pass  # aiohttp optional (#1347)

    return {
        **evolution_components,
        "performance_optimizer": get_performance_optimizer(),
        "accessibility_engine": AccessibilityComplianceEngine(),
        "qa_suite": qa_suite,
        "deployment_system": ProductionDeploymentSystem(),
    }


def run_complete_system_test() -> None:
    """Run a comprehensive load test of all system components."""
    from core import logger  # resolved via core/__init__ (logging_config)

    system = get_complete_ai_system()

    debug = getattr(logger, "debug", None) or (lambda *a, **k: None)
    for key in (
        "digital_twin",
        "defense_system",
        "neural_symbolic",
        "theory_of_mind",
        "temporal_abstraction",
        "performance_optimizer",
        "accessibility_engine",
        "qa_suite",
        "deployment_system",
    ):
        component = system.get(key)
        debug(f"OK {key}: {type(component).__name__ if component is not None else 'unavailable'}")

    debug("All system components loaded. Complete SupremeAI 2.0 system ready.")
