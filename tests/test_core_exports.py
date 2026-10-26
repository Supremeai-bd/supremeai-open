"""__all__ integrity invariant for the core package (#1347).

Guards the contract that __all__ never advertises a permanently-None symbol.
Conditional-None (optional heavy deps such as torch/aiohttp) stays legal and
is asserted through the lazy-None contract instead.
"""

import core


def test_every_all_entry_is_importable():
    for name in core.__all__:
        value = getattr(core, name)
        assert value is not None or name in core._EVOLUTION_LAZY_EXPORTS or name in core._QA_LAZY_EXPORTS, (
            f"core.{name} is permanently-None while listed in __all__ (#1347 invariant)"
        )


def test_deleted_symbols_are_gone():
    import pytest

    for dead in (
        "DigitalTwinWorldModel",
        "get_digital_twin_model",
        "FLConfig",
        "AggregationMethod",
        "MathematicalReasoningEngine",
        "TheoryOfMindSystem",
        "ToMConfig",
        "ToMLevel",
        "TemporalAbstractionSystem",
        "TemporalAbstractionConfig",
        "TemporalGranularity",
    ):
        assert dead not in core.__all__
        with pytest.raises(AttributeError):
            getattr(core, dead)
