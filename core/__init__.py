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

try:
    from core.monitoring.logging_config import logger
except ImportError:
    try:
        from logging_config import logger
    except ImportError:
        logger = None

# bridge-20261027-core-hygiene (#1347): the former triple try/except chain
# (relative -> bare -> absolute) imported the SAME symbols three different
# ways. `core` is only ever imported as a package, so one canonical
# package-relative path per symbol is enough — the fallback ladder just
# tripled maintenance surface and hid real breakage behind silent orderings.
# bridge-20261027-fix-coreci-ci-green: accessibility/, deployment/ and
# optimization/ are OPTIONAL platform submodules. Satellite deployments
# (supremeai-core) ship without them — cleanup PRs removed the duplicated
# trees — so the hard imports above made `import core` (and therefore every
# `from core.X import …` consumer, e.g. decision_engine via core.logging_config)
# fail at import time, which killed pytest collection and kept the Core CI red
# across every sync. Same guard pattern as the qa_suite and evolution blocks
# below: one canonical package-relative path per symbol (#1347), an
# availability flag, and a PEP 562 lazy re-export on first access.
try:
    from .accessibility.wcag_compliance import (
        AccessibilityComplianceEngine,
        AccessibilityIssue,
        ColorContrastChecker,
        HTMLAccessibilityChecker,
        WCAGGuideline,
        WCAGLevel,
        WCAGPrinciple,
    )

    ACCESSIBILITY_AVAILABLE = True
except (ImportError, ValueError):
    ACCESSIBILITY_AVAILABLE = False

try:
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

    DEPLOYMENT_AVAILABLE = True
except (ImportError, ValueError):
    DEPLOYMENT_AVAILABLE = False

try:
    from .optimization.performance_optimizer import (
        AsyncLRUCache,
        LRUCache,
        OptimizationLevel,
        PerformanceOptimizer,
        get_performance_optimizer,
        performance_monitor,
    )

    OPTIMIZATION_AVAILABLE = True
except (ImportError, ValueError):
    OPTIMIZATION_AVAILABLE = False

# Optional platform re-exports: name -> (canonical module, attr). Resolved on
# first access; None when the submodule is not shipped in this deployment
# (same conditional-None contract as the evolution/QA blocks).
_PLATFORM_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "AccessibilityComplianceEngine": ("core.accessibility.wcag_compliance", "AccessibilityComplianceEngine"),
    "AccessibilityIssue": ("core.accessibility.wcag_compliance", "AccessibilityIssue"),
    "ColorContrastChecker": ("core.accessibility.wcag_compliance", "ColorContrastChecker"),
    "HTMLAccessibilityChecker": ("core.accessibility.wcag_compliance", "HTMLAccessibilityChecker"),
    "WCAGGuideline": ("core.accessibility.wcag_compliance", "WCAGGuideline"),
    "WCAGLevel": ("core.accessibility.wcag_compliance", "WCAGLevel"),
    "WCAGPrinciple": ("core.accessibility.wcag_compliance", "WCAGPrinciple"),
    "ConfigManager": ("core.deployment.production_deploy", "ConfigManager"),
    "DeploymentConfig": ("core.deployment.production_deploy", "DeploymentConfig"),
    "DeploymentEnvironment": ("core.deployment.production_deploy", "DeploymentEnvironment"),
    "DeploymentManager": ("core.deployment.production_deploy", "DeploymentManager"),
    "DeploymentStatus": ("core.deployment.production_deploy", "DeploymentStatus"),
    "HealthChecker": ("core.deployment.production_deploy", "HealthChecker"),
    "ImageBuilder": ("core.deployment.production_deploy", "ImageBuilder"),
    "ProductionDeploymentSystem": ("core.deployment.production_deploy", "ProductionDeploymentSystem"),
    "AsyncLRUCache": ("core.optimization.performance_optimizer", "AsyncLRUCache"),
    "LRUCache": ("core.optimization.performance_optimizer", "LRUCache"),
    "OptimizationLevel": ("core.optimization.performance_optimizer", "OptimizationLevel"),
    "PerformanceOptimizer": ("core.optimization.performance_optimizer", "PerformanceOptimizer"),
    "get_performance_optimizer": ("core.optimization.performance_optimizer", "get_performance_optimizer"),
    "performance_monitor": ("core.optimization.performance_optimizer", "performance_monitor"),
}

# বাংলা মন্তব্য: core.testing.qa_suite নিজে aiohttp আমদানি করে (একটা optional/dev-only
# dependency — production API path কখনো এটা ব্যবহার করে না)। কিন্তু এই ব্লকটা আগে
# try/except ছাড়াই ছিল, ফলে aiohttp ইনস্টল করা না থাকলে শুধু "import core" করলেই
# (যেমন backend/middleware/anti_hacking.py-র "from core.cache.redis_manager import ..."
# লাইনটা core/__init__.py ট্রিগার করে) পুরো ব্যাকএন্ড ImportError দিয়ে ভেঙে পড়ত --
# ঠিক সেই একই ক্লাসের বাগ যেটা torch-এর জন্য নিচে evolution ব্লকে আগে থেকেই গার্ড করা
# আছে। এখানে একই প্যাটার্ন প্রয়োগ করা হলো যাতে QA-স্যুট ছাড়াই বাকি core.* সাবমডিউল
# (cache, config, otp_router ইত্যাদি) স্বাভাবিকভাবে import হতে পারে।
# aiohttp (used by core.testing.qa_suite) is a dev-only dependency — keep the
# optional availability flag, but with ONE canonical import path instead of a
# three-level fallback ladder (#1347).
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
except (ImportError, ValueError):
    QA_SUITE_AVAILABLE = False

_QA_LAZY_EXPORTS = (
    "ChaosEngineer",
    "IntegrationTestRunner",
    "PerformanceTester",
    "QASuite",
    "SecurityTester",
    "TestCase",
    "TestCategory",
    "TestPriority",
    "TestResult",
    "TestSuite",
    "UnitTestGenerator",
)
_SELF_CHECK_EXPORTS = ("get_complete_ai_system", "run_complete_system_test")

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

# bridge-20261027-core-hygiene (#1347): the 11 permanently-None aliases for
# symbols deleted with the evolution/ subfolders (DigitalTwinWorldModel,
# TheoryOfMindSystem, FLConfig, TemporalAbstraction*, ToM*, …) were removed.
# `__all__` no longer lies about what exists: importing one of them now raises
# the honest AttributeError via PEP 562 instead of returning a None time-bomb.


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
    "AsyncLRUCache",
    "ChaosEngineer",
    "ColorContrastChecker",
    "ConfigManager",
    "DefenseConfig",
    "DeploymentConfig",
    "DeploymentEnvironment",
    "DeploymentManager",
    "DeploymentStatus",
            "EWCConfig",
    "EWCTrainer",
    "HTMLAccessibilityChecker",
    "HealthChecker",
    "ImageBuilder",
    "ImpactSimulator",
    "IntegrationTestRunner",
    "LRUCache",
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
        "TestCase",
    "TestCategory",
    "TestPriority",
    "TestResult",
    "TestSuite",
        "UnitTestGenerator",
    "WCAGGuideline",
    "WCAGLevel",
    "WCAGPrinciple",
    "get_performance_optimizer",
    "performance_monitor",
]


def __getattr__(name: str) -> Any:
    """PEP 562 lazy access — evolution re-exports first, then submodule fallback.

    Bengali: core package er submodule gulo dynamically import korar fallback handler.
    Evolution re-export names (incident #9) load on first access only.
    """
    import importlib

    if name in _PLATFORM_LAZY_EXPORTS:
        module_path, attr = _PLATFORM_LAZY_EXPORTS[name]
        try:
            value = getattr(importlib.import_module(module_path), attr)
        except (ImportError, AttributeError):
            value = None
        globals()[name] = value
        return value
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
    if name in _QA_LAZY_EXPORTS:
        # aiohttp-optional QA symbols keep their historical None contract
        # (#1347: conditional-None is allowed; permanently-None is not).
        if QA_SUITE_AVAILABLE:
            return importlib.import_module("core.testing.qa_suite") and globals().get(name)
        globals()[name] = None
        return None
    if name in _SELF_CHECK_EXPORTS:
        mod = importlib.import_module("core.selfcheck")
        value = getattr(mod, name)
        globals()[name] = value
        return value
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
