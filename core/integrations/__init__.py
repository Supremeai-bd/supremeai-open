"""
SupremeAI Integration Governance Layer
=======================================
বাংলা: Plan Section 28 অনুযায়ী — সব optional integration-এর একটি central
registry। প্রতিটি integration declare করে: name, version, enabled, health,
capabilities, configuration status, fallback, privacy mode।

নীতি (Plan Section 32): প্রতিটি integration default-disabled, এবং integration
OFF থাকলেও core কাজ করবে। এই registry শুধু observability দেয় — কোনো
integration-কে enable/disable করে না (সেটা settings layer-এর কাজ)।
"""

from .registry import (
    IntegrationInfo,
    IntegrationScope,
    IntegrationStatus,
    get_integration,
    is_enabled,
    list_integrations,
)

__all__ = [
    "IntegrationInfo",
    "IntegrationScope",
    "IntegrationStatus",
    "list_integrations",
    "get_integration",
    "is_enabled",
]
