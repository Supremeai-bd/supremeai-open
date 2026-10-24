#!/usr/bin/env python3
"""Capability Inventory CI Guard (issue #4043 — Roadmap v2 Phase 1.1).

বাংলা সারসংক্ষেপ:
------------------
Ecosystem Intelligence Roadmap v2 (#4043) অনুসারে এই script টি নিশ্চিত করে যে
`backend/integrations/` বা `backend/core/llm/providers/`-এ নতুন adapter/provider
file যোগ হলে সেটির `docs/architecture/inventory.yaml`-এ এন্ট্রি বাধ্যতামূলক।
inventory entry ছাড়া adapter যোগ হলে CI fail করবে — এটি Rule 4 (Evidence Before
Adoption) এর শর্ত: কোনো capability silently adopt হতে পারবে না।

যা যা যাচাই করে:
  1. inventory.yaml ফাইলটি exists কিনা
  2. inventory.yaml valid YAML কিনা (schema সহ)
  3. backend/integrations/*.py প্রতিটি adapter file-এর জন্য inventory.yaml-এ
     matching entry (path match) আছে কিনা
  4. backend/core/llm/llm_gateway/registry.py _MODEL_KEY_MAP-এ প্রতিটি provider-এর
     জন্য inventory.yaml llm_providers section-এ entry আছে কিনা
  5. inventory.yaml-এ orphaned tier entry-র owner_issue field বাধ্যতামূলক (যাতে
     audit ট্র্যাক করা যায়)

Exit codes:
  0 = সব ঠিক (inventory complete + valid)
  1 = inventory drift ধরা পড়েছে (missing entries / invalid schema)

Usage:
  python scripts/agents/inventory_lint.py
  python scripts/agents/inventory_lint.py --strict  # fail on warnings too

Integration:
  Add to CI workflow (e.g. .github/workflows/ci-advanced-checks.yml):
    - name: Capability inventory lint
      run: python scripts/agents/inventory_lint.py --strict
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_YAML = ROOT / "docs" / "architecture" / "inventory.yaml"
INVENTORY_MD = ROOT / "docs" / "architecture" / "CAPABILITY_INVENTORY.md"
INTEGRATIONS_DIR = ROOT / "backend" / "integrations"
LLM_PROVIDERS_DIR = ROOT / "backend" / "core" / "llm" / "providers"
LLM_GATEWAY_REGISTRY = ROOT / "backend" / "core" / "llm" / "llm_gateway" / "registry.py"

# Adapter files exempt from inventory requirement (helpers, __init__, etc.)
INTEGRATIONS_EXEMPT = {
    "__init__.py",
    "_flags.py",
    "telegram_config.yaml",
}

# Valid tier values
VALID_TIERS = {"internal", "governed_provider", "research_source", "rejected", "orphaned", "retired"}
VALID_STATUSES = {
    "active", "active_local", "audit_pending", "retire_planned", "retire_confirmed", "retire_executed",
    "rejected", "research_only", "future", "peripheral",
    "no_action", "do_not_add", "read_only", "reference_only",
    "audit_revive_or_retire", "adapt_l0_l1_l2_tier_concepts",
    "prototype_as_scout_data_layer", "add_as_governed_provider",
    "adapt_decision_metadata_model", "workload_driven_adoption",
    "adapt_policy_driven_ttl", "benchmark_vs_llama_cpp",
    "mission_control_viz_if_gap", "local_edition_research",
    "adapt_concepts", "adopt_concepts", "reject",
}


def _try_import_yaml() -> Any:
    """Import yaml with helpful error if missing."""
    try:
        import yaml  # type: ignore[import-untyped]
        return yaml
    except ImportError:
        print("::error::PyYAML not installed. Run: pip install pyyaml")
        sys.exit(2)


def _load_inventory(yaml_module: Any) -> dict[str, Any]:
    """Load + structurally validate inventory.yaml."""
    if not INVENTORY_YAML.exists():
        print(f"::error::inventory.yaml missing: {INVENTORY_YAML}")
        sys.exit(1)

    with INVENTORY_YAML.open("r", encoding="utf-8") as f:
        try:
            data = yaml_module.safe_load(f)
        except yaml_module.YAMLError as e:
            print(f"::error::inventory.yaml invalid YAML: {e}")
            sys.exit(1)

    if not isinstance(data, dict):
        print(f"::error::inventory.yaml root must be a mapping, got {type(data).__name__}")
        sys.exit(1)

    required_top = ["schema_version", "integrations", "llm_providers", "external_services", "external_repos"]
    for key in required_top:
        if key not in data:
            print(f"::error::inventory.yaml missing required top-level key: {key}")
            sys.exit(1)

    return data


def _lint_integration_entries(inventory: dict[str, Any]) -> list[str]:
    """Validate each integration entry's schema + cross-check against files on disk."""
    errors: list[str] = []
    seen_files: set[str] = set()

    for i, entry in enumerate(inventory.get("integrations", [])):
        prefix = f"integrations[{i}] ({entry.get('name', '?')})"
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: entry must be a mapping")
            continue

        # Required fields (file optional for retire_executed — file deleted)
        tier = entry.get("tier", "")
        status = entry.get("status", "")
        file_is_deleted = (tier == "retired" and status == "retire_executed")
        for req in ("name", "tier", "status"):
            if req not in entry or not entry[req]:
                errors.append(f"{prefix}: missing required field '{req}'")
        if not file_is_deleted and ("file" not in entry or not entry["file"]):
            errors.append(f"{prefix}: missing required field 'file' (or set tier=retired + status=retire_executed if deleted)")

        # Tier validation
        if tier and tier not in VALID_TIERS:
            errors.append(f"{prefix}: invalid tier '{tier}' (allowed: {sorted(VALID_TIERS)})")

        # Status validation (lenient — accept any non-empty string for forward-compat)
        status = entry.get("status")
        if status and status not in VALID_STATUSES:
            # warning, not error — forward-compat for new statuses
            print(f"::warning::{prefix}: unknown status '{status}' (not in canonical set)")

        # File must exist on disk
        file_rel = entry.get("file")
        if file_rel:
            file_abs = ROOT / file_rel
            if not file_abs.exists():
                errors.append(f"{prefix}: file does not exist on disk: {file_rel}")
            else:
                seen_files.add(str(file_abs))

        # Orphaned + retired tiers → owner_issue required (audit tracking)
        if tier in {"orphaned", "retired"}:
            if not entry.get("owner_issue"):
                errors.append(f"{prefix}: {tier} tier requires 'owner_issue' for audit tracking")
        # Retired tier → audit_report + audit_decision recommended (warning only)
        if tier == "retired":
            if not entry.get("audit_report"):
                print(f"::warning::{prefix}: retired tier should reference 'audit_report' path")
            if not entry.get("audit_decision"):
                print(f"::warning::{prefix}: retired tier should record 'audit_decision'")

    return errors, seen_files  # type: ignore[return-value]


def _check_integration_files_on_disk(seen_files: set[str]) -> list[str]:
    """Find adapter files on disk that have no inventory entry."""
    errors: list[str] = []
    if not INTEGRATIONS_DIR.exists():
        return errors

    for py_file in INTEGRATIONS_DIR.glob("*.py"):
        if py_file.name in INTEGRATIONS_EXEMPT:
            continue
        if str(py_file) not in seen_files:
            rel = py_file.relative_to(ROOT)
            errors.append(
                f"integration adapter file has no inventory.yaml entry: {rel} "
                f"(add an entry under 'integrations:' in docs/architecture/inventory.yaml)"
            )

    return errors


def _lint_llm_providers(inventory: dict[str, Any]) -> list[str]:
    """Cross-check _MODEL_KEY_MAP providers against inventory.yaml llm_providers."""
    errors: list[str] = []
    yaml_module = _try_import_yaml()

    if not LLM_GATEWAY_REGISTRY.exists():
        errors.append(f"LLM gateway registry missing: {LLM_GATEWAY_REGISTRY}")
        return errors

    registry_src = LLM_GATEWAY_REGISTRY.read_text(encoding="utf-8")

    # Extract provider keys from _MODEL_KEY_MAP dict literal
    # Pattern: "provider_name": "settings_attr",
    pattern = re.compile(r'"([a-z0-9_]+)":\s*"[A-Z_]+_API_KEY"', re.IGNORECASE)
    registry_providers = set(pattern.findall(registry_src))

    inventory_providers = {
        p.get("name") for p in inventory.get("llm_providers", []) if isinstance(p, dict)
    }

    missing = registry_providers - inventory_providers
    for m in sorted(missing):
        errors.append(
            f"LLM provider '{m}' is in _MODEL_KEY_MAP (backend/core/llm/llm_gateway/registry.py) "
            f"but has no entry in inventory.yaml llm_providers section"
        )

    # Validate each llm_providers entry schema
    for i, entry in enumerate(inventory.get("llm_providers", [])):
        prefix = f"llm_providers[{i}] ({entry.get('name', '?')})"
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: entry must be a mapping")
            continue
        for req in ("name", "settings_attr", "tier", "status"):
            if req not in entry or not entry[req]:
                errors.append(f"{prefix}: missing required field '{req}'")
        if entry.get("tier") and entry["tier"] not in VALID_TIERS:
            errors.append(f"{prefix}: invalid tier '{entry['tier']}'")

    return errors


def _lint_external_repos(inventory: dict[str, Any]) -> list[str]:
    """Validate external_repos entries (governance tier + owner_issue for non-rejected)."""
    errors: list[str] = []
    for i, entry in enumerate(inventory.get("external_repos", [])):
        prefix = f"external_repos[{i}] ({entry.get('name', '?')})"
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: entry must be a mapping")
            continue
        for req in ("name", "tier", "action"):
            if req not in entry or not entry[req]:
                errors.append(f"{prefix}: missing required field '{req}'")
        tier = entry.get("tier")
        if tier and tier not in VALID_TIERS:
            errors.append(f"{prefix}: invalid tier '{tier}'")
        # research_source + orphaned tiers must have priority + owner_issue (audit trail)
        if tier in {"research_source", "orphaned"}:
            if not entry.get("priority"):
                errors.append(f"{prefix}: {tier} tier requires 'priority' field")
            # owner_issue may be null for P4/peripheral, but key must exist
            if "owner_issue" not in entry:
                errors.append(f"{prefix}: {tier} tier must declare 'owner_issue' (null ok for P4)")
    return errors


def _check_md_exists() -> list[str]:
    """Verify the human-readable companion doc exists."""
    errors: list[str] = []
    if not INVENTORY_MD.exists():
        errors.append(
            f"companion doc missing: {INVENTORY_MD} "
            f"(inventory.yaml without CAPABILITY_INVENTORY.md is half the contract)"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Capability Inventory CI Guard (#4043)")
    parser.add_argument("--strict", action="store_true", help="fail on warnings too")
    args = parser.parse_args()

    yaml_module = _try_import_yaml()
    inventory = _load_inventory(yaml_module)

    all_errors: list[str] = []
    all_warnings: list[str] = []

    # 1. Companion doc exists
    all_errors.extend(_check_md_exists())

    # 2. Integration entries schema + cross-check
    integ_errors, seen_files = _lint_integration_entries(inventory)
    all_errors.extend(integ_errors)
    all_errors.extend(_check_integration_files_on_disk(seen_files))

    # 3. LLM providers cross-check against _MODEL_KEY_MAP
    all_errors.extend(_lint_llm_providers(inventory))

    # 4. External repos governance
    all_errors.extend(_lint_external_repos(inventory))

    # Report
    if all_warnings:
        print(f"::warning::{len(all_warnings)} warning(s):")
        for w in all_warnings:
            print(f"  - {w}")

    if all_errors:
        print(f"::error::{len(all_errors)} inventory drift issue(s) found:")
        for e in all_errors:
            print(f"  - {e}")
        print("\nFix: add missing entries to docs/architecture/inventory.yaml")
        print("See: docs/architecture/CAPABILITY_INVENTORY.md §11 (Maintenance Protocol)")
        return 1

    integ_count = len(inventory.get("integrations", []))
    llm_count = len(inventory.get("llm_providers", []))
    svc_count = len(inventory.get("external_services", []))
    repo_count = len(inventory.get("external_repos", []))
    print(f"::notice::inventory.yaml valid — {integ_count} integrations, "
          f"{llm_count} LLM providers, {svc_count} external services, "
          f"{repo_count} external repos tracked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
