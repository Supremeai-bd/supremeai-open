"""Backward compatibility shim for core.rules_mutator.

Canonical domain module: core.ip_blocklist_manager
"""

from core.ip_blocklist_manager import IPBlocklistManager, RulesMutator

__all__ = ["RulesMutator", "IPBlocklistManager"]
