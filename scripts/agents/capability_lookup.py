#!/usr/bin/env python3
"""Capability Before Construction lookup (Roadmap v2.0 Phase 8 — #4145).

Answers the roadmap's mandatory pre-build ladder from the EXISTING inventories
(read-only, zero writes, zero new SSOT):

    Can existing capability solve this?  → YES → Reuse / compose
    NO → Can existing capabilities be combined?          → Compose
    NO → Only then consider new capability

Sources (both already CI-linted — inventory_lint.py / validate_capability_inventory.py):
  * docs/capability_inventory.json  — curated capability catalog
  * docs/architecture/inventory.yaml — module/provider/service inventory

CLI:
    python scripts/agents/capability_lookup.py "redis cache"
    python scripts/agents/capability_lookup.py --check "issue triage"
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
CAPABILITY_JSON = REPO_ROOT / "docs" / "capability_inventory.json"
INVENTORY_YAML = REPO_ROOT / "docs" / "architecture" / "inventory.yaml"


def _iter_capability_json() -> list[dict]:
    try:
        data = json.loads(CAPABILITY_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("capability inventory unreadable: %s", CAPABILITY_JSON, exc_info=True)
        return []
    items = data.get("capabilities", data) if isinstance(data, dict) else data
    return [c for c in items if isinstance(c, dict)]


def _iter_inventory_yaml() -> list[dict]:
    try:
        import yaml

        data = yaml.safe_load(INVENTORY_YAML.read_text(encoding="utf-8")) or {}
    except Exception:
        logger.debug("inventory.yaml unreadable: %s", INVENTORY_YAML, exc_info=True)
        return []
    out: list[dict] = []
    for section, entries in data.items():
        if section == "schema_version" or not isinstance(entries, list):
            continue
        for e in entries:
            if isinstance(e, dict) and e.get("name"):
                out.append({"_section": section, **e})
    return out


def search(query: str, limit: int = 8) -> list[dict]:
    """Substring search across both inventories (name/id/file/notes fields)."""
    q = (query or "").strip().lower()
    if not q:
        return []
    hits: list[dict] = []
    for c in _iter_capability_json():
        hay = " ".join(str(c.get(k, "")) for k in ("id", "name", "classification")).lower()
        if q in hay:
            hits.append({"source": "capability_inventory.json", "id": c.get("id"),
                         "name": c.get("name"), "classification": c.get("classification")})
    for e in _iter_inventory_yaml():
        hay = " ".join(str(e.get(k, "")) for k in ("name", "file", "class", "notes", "_section")).lower()
        if q in hay:
            hits.append({"source": "inventory.yaml", "section": e.get("_section"),
                         "name": e.get("name"), "file": e.get("file"), "status": e.get("status")})
    return hits[:limit]


def reuse_ladder(query: str) -> dict:
    """The Phase 8 ladder verdict: reuse → compose → new (with evidence)."""
    hits = search(query, limit=8)
    if hits:
        return {
            "verdict": "reuse",
            "query": query,
            "existing": hits,
            "next": "Reuse or compose these capabilities — do NOT build a parallel one (Rule A).",
        }
    return {
        "verdict": "compose_or_new",
        "query": query,
        "existing": [],
        "next": (
            "No direct match. 1) Can two existing capabilities be COMBINED? "
            "2) Only then propose a new capability — with an owner_issue + inventory entry."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Capability Before Construction lookup (#4145)")
    parser.add_argument("query", help="capability keyword, e.g. 'redis cache'")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 when no existing capability matches (pre-build gate)")
    args = parser.parse_args()
    result = reuse_ladder(args.query)
    print(json.dumps(result, indent=1))
    return 1 if (args.check and result["verdict"] != "reuse") else 0


if __name__ == "__main__":
    sys.exit(main())
