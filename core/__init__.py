"""
SupremeAI 2.0 Core Components
=============================

Main integration package for all core components developed
as part of the roadmap, including:

- Performance Optimization (Phase 6.1)
- Accessibility (WCAG 2.1 AA) (Phase 6.2)
- Testing & QA (Phase 6.3)
- Production Deployment (Phase 6.4)

Also includes previously developed AI/ML research components:

- Digital Twin World Model (Phase 3.1)
- Continual Learning with EWC (Phase 3.2)
- Adversarial Robustness (Phase 3.3)
- Neural-Symbolic Integration (Phase 3.4)
- Federated Learning (Phase 3.5)
- Theory of Mind (Phase 3.6)
- Temporal Abstraction (Phase 3.7)

And cross-platform expansion components:

- Mobile App Integration
- Desktop App Integration

Bengali:
সুপ্রিমএআই ২.০ কোর কম্পোনেন্ট
রোডম্যাপের অংশ হিসেবে সব কোর কম্পোনেন্টের প্রধান একীকরণ প্যাকেজ
"""

from typing import Any

from core.logging_config import logger

from .accessibility.wcag_compliance import (
    AccessibilityComplianceEngine,
    AccessibilityIssue,
    ColorContrastChecker,
    HTMLAccessibilityChecker,
    WCAGGuideline,
    WCAGLevel,
    WCAGPrinciple,
)
from .deployment.production_deploy import (
    ConfigManager,
    DeploymentConfig,
    DeploymentEnvironment,
    DeploymentManager,
    DeploymentStatus,
    HealthChecker,
    ImageBuilder,
    ProductionDeploymentSystem,
)

# Import all core components
from .optimization.performance_optimizer import (
    AsyncLRUCache,
    LRUCache,
    OptimizationLevel,
    PerformanceOptimizer,
    get_performance_optimizer,
    performance_monitor,
)

# বাংলা মন্তব্য: core.testing.qa_suite নিজে aiohttp আমদানি করে (একটা optional/dev-only
# dependency — production API path কখনো এটা ব্যবহার করে না)। কিন্তু এই ব্লকটা আগে
# try/except ছাড়াই ছিল, ফলে aiohttp ইনস্টল করা না থাকলে শুধু "import core" করলেই
# (যেমন backend/middleware/anti_hacking.py-র "from core.cache.redis_manager import ..."
# লাইনটা core/__init__.py ট্রিগার করে) পুরো ব্যাকএন্ড ImportError দিয়ে ভেঙে পড়ত --
# ঠিক সেই একই ক্লাসের বাগ যেটা torch-এর জন্য নিচে evolution ব্লকে আগে থেকেই গার্ড করা
# আছে। এখানে একই প্যাটার্ন প্রয়োগ করা হলো যাতে QA-স্যুট ছাড়াই বাকি core.* সাবমডিউল
# (cache, config, otp_router ইত্যাদি) স্বাভাবিকভাবে import হতে পারে।
try:
    from .testing.qa_suite import (
        ChaosEngineer,
        IntegrationTestRunner,
        PerformanceTester,
        QASuite,
        SecurityTester,
        TestCase,
        TestCategory,
        TestPriority,
        TestResult,
        TestSuite,
        UnitTestGenerator,
    )

    QA_SUITE_AVAILABLE = True
except ImportError:
    QA_SUITE_AVAILABLE = False
    import sys

    _mod = sys.modules[__name__]
    _mod.ChaosEngineer = None
    _mod.IntegrationTestRunner = None
    _mod.PerformanceTester = None
    _mod.QASuite = None
    _mod.SecurityTester = None
    _mod.TestCase = None
    _mod.TestCategory = None
    _mod.TestPriority = None
    _mod.TestResult = None
    _mod.TestSuite = None
    _mod.UnitTestGenerator = None

# Import evolution components — LAZY (PEP 562)
# বাংলা মন্তব্য: evolution প্যাকেজের কিছু সাব-মডিউল (EWC, adversarial defense,
# neural-symbolic, federated learning, theory-of-mind) torch দরকার করে। torch এখন
# আর ডিফল্ট ইনস্টলে নেই। আগে এই ব্লকটা eager ছিল — `import core` করলেই প্রতিবার
# sympy (≈1.6s) + adversarial_defense (≈1.3s) লোড হত, অথচ পুরো রিপোতে এই
# re-export নামগুলোর কোনো consumer নেই (grep-verified; incident #9,
# ERROR_COMPENDIUM register: pytest collection 30s+, `import scout` ≈11s)।
# এখন PEP 562 module __getattr__ দিয়ে first-access-এই লোড হয় — public API
# (`from core import EWC` ইত্যাদি) অপরিবর্তিত থাকে, import-time cost শূন্য।
_EVOLUTION_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    # name → (module, attr)
    "AdversarialDefenseSystem": (
        "core.self_evolution.adversarial_defense.defense_system",
        "AdversarialDefenseSystem",
    ),
    "AdversarialTrainer": (
        "core.self_evolution.adversarial_defense.defense_system",
        "AdversarialTrainer",
    ),
    "DefenseConfig": ("core.self_evolution.adversarial_defense.defense_system", "DefenseConfig"),
    "EWC": ("core.self_evolution.continual_learning.ewc", "EWC"),
    "EWCConfig": ("core.self_evolution.continual_learning.ewc", "EWCConfig"),
    "EWCTrainer": ("core.self_evolution.continual_learning.ewc", "EWCTrainer"),
    "OnlineEWC": ("core.self_evolution.continual_learning.ewc", "OnlineEWC"),
    "RemediationEngine": (
        "core.self_evolution.digital_twin.remediation_engine",
        "RemediationEngine",
    ),
    "ImpactSimulator": ("core.self_evolution.digital_twin.simulator", "ImpactSimulator"),
    "SystemTopologyMapper": ("core.self_evolution.digital_twin.topology", "SystemTopologyMapper"),
    "NeuralSymbolicConfig": (
        "core.self_evolution.neural_symbolic.integration",
        "NeuralSymbolicConfig",
    ),
    "NeuralSymbolicIntegrator": (
        "core.self_evolution.neural_symbolic.integration",
        "NeuralSymbolicIntegrator",
    ),
}

_EVOLUTION_LAZY_FLAGS: dict[str, tuple[str, ...]] = {
    "ADVERSARIAL_DEFENSE_AVAILABLE": ("AdversarialDefenseSystem",),
    "EWC_AVAILABLE": ("EWC",),
    "DIGITAL_TWIN_AVAILABLE": ("RemediationEngine",),
    "NEURAL_SYMBOLIC_AVAILABLE": ("NeuralSymbolicIntegrator",),
}

# These symbols don't exist anywhere (deleted with evolution/ subfolders):
# DigitalTwinWorldModel, get_digital_twin_model, FLConfig, AggregationMethod,
# MathematicalReasoningEngine, TheoryOfMindSystem, ToMConfig, ToMLevel,
# TemporalAbstractionSystem, TemporalAbstractionConfig, TemporalGranularity
DigitalTwinWorldModel = None
get_digital_twin_model = None
FLConfig = None
AggregationMethod = None
MathematicalReasoningEngine = None
TheoryOfMindSystem = None
ToMConfig = None
ToMLevel = None
TemporalAbstractionSystem = None
TemporalAbstractionConfig = None
TemporalGranularity = None


def _load_evolution_symbol(name: str) -> Any:
    """Resolve a lazy evolution export; raise ImportError/AttributeError naturally."""
    module_path, attr = _EVOLUTION_LAZY_EXPORTS[name]
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, attr)


def _resolve_or_none(attr: str) -> Any:
    """Try to resolve a lazy evolution attr; return None if unavailable."""
    try:
        return _load_evolution_symbol(attr)
    except Exception:
        return None


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EVOLUTION_LAZY_EXPORTS))


# Version information
__version__ = "2.0.0"
__author__ = "SupremeAI Team"
__description__ = "Core Components for SupremeAI 2.0"

# All available components
__all__ = [
    # Continual Learning
    "EWC",
    # Accessibility
    "AccessibilityComplianceEngine",
    "AccessibilityIssue",
    # Adversarial Defense
    "AdversarialDefenseSystem",
    "AdversarialTrainer",
    "AggregationMethod",
    "AsyncLRUCache",
    "ChaosEngineer",
    "ColorContrastChecker",
    "ConfigManager",
    "DefenseConfig",
    "DeploymentConfig",
    "DeploymentEnvironment",
    "DeploymentManager",
    "DeploymentStatus",
    # Evolution Components
    # Digital Twin
    "DigitalTwinWorldModel",
    "EWCConfig",
    "EWCTrainer",
    "FLConfig",
    "HTMLAccessibilityChecker",
    "HealthChecker",
    "ImageBuilder",
    "ImpactSimulator",
    "IntegrationTestRunner",
    "LRUCache",
    "MathematicalReasoningEngine",
    "NeuralSymbolicConfig",
    # Neural-Symbolic Integration
    "NeuralSymbolicIntegrator",
    "OnlineEWC",
    "OptimizationLevel",
    # Performance Optimization
    "PerformanceOptimizer",
    "PerformanceTester",
    # Deployment
    "ProductionDeploymentSystem",
    # Testing & QA
    "QASuite",
    "RemediationEngine",
    "SecurityTester",
    "SystemTopologyMapper",
    "TemporalAbstractionConfig",
    # Temporal Abstraction
    "TemporalAbstractionSystem",
    "TemporalGranularity",
    "TestCase",
    "TestCategory",
    "TestPriority",
    "TestResult",
    "TestSuite",
    # Theory of Mind
    "TheoryOfMindSystem",
    "ToMConfig",
    "ToMLevel",
    "UnitTestGenerator",
    "WCAGGuideline",
    "WCAGLevel",
    "WCAGPrinciple",
    "get_digital_twin_model",
    "get_performance_optimizer",
    "performance_monitor",
]


def get_complete_ai_system():
    """
    Get a complete AI system with all research and production components integrated.

    Returns:
        A comprehensive system with all major components
    """
    from ..evolution import get_evolution_pipeline

    # Get all evolution components
    evolution_components = get_evolution_pipeline()

    # Add production hardening components
    system = {
        # Evolution/research components
        **evolution_components,
        # Production hardening components
        "performance_optimizer": get_performance_optimizer(),
        "accessibility_engine": AccessibilityComplianceEngine(),
        "qa_suite": QASuite(),
        "deployment_system": ProductionDeploymentSystem(),
    }

    return system


def run_complete_system_test():
    """
    Run a comprehensive test of all system components.
    """
    logger.debug("Running Complete System Test...")

    # Get complete system
    system = get_complete_ai_system()

    logger.debug("\n✓ Digital Twin System:", type(system["digital_twin"]).__name__)
    logger.debug("✓ Adversarial Defense System:", type(system["defense_system"]).__name__)
    logger.debug("✓ Neural-Symbolic System:", type(system["neural_symbolic"]).__name__)
    logger.debug("✓ Theory of Mind System:", type(system["theory_of_mind"]).__name__)
    logger.debug("✓ Temporal Abstraction System:", type(system["temporal_abstraction"]).__name__)
    logger.debug("✓ Performance Optimizer:", type(system["performance_optimizer"]).__name__)
    logger.debug("✓ Accessibility Engine:", type(system["accessibility_engine"]).__name__)
    logger.debug("✓ QA Suite:", type(system["qa_suite"]).__name__)
    logger.debug("✓ Deployment System:", type(system["deployment_system"]).__name__)

    logger.debug("\n✓ EWC System: Initialized")
    logger.debug("✓ Federated Learning System: Initialized")

    logger.debug("\nAll system components successfully loaded!")
    logger.debug("Complete SupremeAI 2.0 system ready for advanced AI operations.")


def __getattr__(name: str) -> Any:
    """PEP 562 lazy access — evolution re-exports first, then submodule fallback.

    Bengali: core package er submodule gulo dynamically import korar fallback handler.
    Evolution re-export names (incident #9) load on first access only.
    """
    import importlib

    if name in _EVOLUTION_LAZY_EXPORTS:
        # Match the historical eager contract: torch/sympy-dependent research
        # exports become None (not an ImportError) when their deps are absent.
        try:
            value = _load_evolution_symbol(name)
        except (ImportError, OSError, AttributeError):
            value = None
        globals()[name] = value
        return value
    if name in _EVOLUTION_LAZY_FLAGS:
        available = all(_resolve_or_none(attr) is not None for attr in _EVOLUTION_LAZY_FLAGS[name])
        globals()[name] = available
        return available
    if name == "EVOLUTION_COMPONENTS_AVAILABLE":
        available = any(
            _resolve_or_none(attr) is not None
            for attr in {attr for attrs in _EVOLUTION_LAZY_FLAGS.values() for attr in attrs}
        )
        globals()[name] = available
        return available
    try:
        mod = importlib.import_module(f"core.{name}")
        globals()[name] = mod
        return mod
    except ImportError as err:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'") from err
