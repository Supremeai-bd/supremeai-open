"""Gap analyzer — cross-reference inventory.yaml (#4055).

বাংলা: discovered repo SupremeAI-তে ইতিমধ্যে আছে কিনা যাচাই করে। inventory.yaml
থেকে existing capabilities list পড়ে দেখে কোনো gap কিনা।
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import ScoutFinding


def load_inventory_repos(
    inventory_path: str | Path = "docs/architecture/inventory.yaml",
) -> dict[str, dict[str, Any]]:
    """Load external_repos from inventory.yaml.

    বাংলা: inventory.yaml-এর external_repos section থেকে সব repo load করে।
    Returns dict mapping repo_name (lowercase) -> entry dict.
    """
    try:
        import yaml
    except ImportError:
        return {}

    p = Path(inventory_path)
    if not p.exists():
        return {}

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    repos: dict[str, dict[str, Any]] = {}
    for entry in data.get("external_repos", []) or []:
        name = str(entry.get("name", "")).lower().strip()
        if name:
            repos[name] = entry
    return repos


def analyze_gap(
    finding: ScoutFinding,
    inventory_repos: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analyze if a finding fills a gap in SupremeAI's capabilities.

    বাংলা: finding-টি SupremeAI-তে ইতিমধ্যে আছে কিনা যাচাই করে। থাকলে gap=False।

    Returns:
        dict with: is_known, existing_tier, existing_action, gap_analysis
    """
    if inventory_repos is None:
        inventory_repos = load_inventory_repos()

    # Normalize finding repo name for lookup
    repo_name_lower = finding.repo_name.lower().strip()

    # Check if repo is already in inventory
    is_known = False
    existing_entry: dict[str, Any] = {}
    for inv_name, entry in inventory_repos.items():
        # Match by repo name (partial — e.g., "browser-use" matches "browser_use")
        if inv_name in repo_name_lower or repo_name_lower in inv_name:
            is_known = True
            existing_entry = entry
            break
        # Also check if any topic matches
        for topic in finding.topics:
            if topic.lower() in inv_name:
                is_known = True
                existing_entry = entry
                break
        if is_known:
            break

    return {
        "is_known": is_known,
        "existing_tier": existing_entry.get("tier", ""),
        "existing_action": existing_entry.get("action", ""),
        "gap": not is_known,
        "analyzed": True,
    }


def analyze_gaps_batch(
    findings: list[ScoutFinding],
    inventory_repos: dict[str, dict[str, Any]] | None = None,
) -> list[ScoutFinding]:
    """Analyze gaps for a batch of findings. Updates finding.gap_analysis.

    বাংলা: একসাথে অনেক findings-এর gap analysis করে। inventory একবার load হয়।
    """
    if inventory_repos is None:
        inventory_repos = load_inventory_repos()

    # Can't mutate frozen dataclass — return new findings with updated gap_analysis
    from dataclasses import replace

    updated: list[ScoutFinding] = []
    for f in findings:
        gap = analyze_gap(f, inventory_repos)
        updated.append(replace(f, gap_analysis=gap))
    return updated
