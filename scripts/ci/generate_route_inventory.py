from __future__ import annotations

import argparse
import json
import hashlib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OPENAPI = REPO_ROOT / "backend" / "openapi.json"
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "generated" / "route_inventory.json"


def _security(operation: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    schemes = root.get("components", {}).get("securitySchemes", {})
    declared = operation.get("security", root.get("security", []))
    return {"required": bool(declared), "schemes": sorted({name for item in declared for name in item}) if declared else []}


def build_inventory(document: dict[str, Any], source: str = "backend/openapi.json") -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    for path, path_item in sorted(document.get("paths", {}).items()):
        for method, operation in sorted(path_item.items()):
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head", "trace"}:
                continue
            operation = operation if isinstance(operation, dict) else {}
            routes.append({
                "method": method.upper(),
                "path": path,
                "operation_id": operation.get("operationId"),
                "tags": operation.get("tags", []),
                "summary": operation.get("summary") or operation.get("description"),
                "auth": _security(operation, document),
                "tenant_scope": "unclassified",
                "persistence": "unclassified",
                "events": "unclassified",
                "owner": operation.get("x-owner", "unassigned"),
                "tests": "unclassified",
            })
    return {
        "schema_version": "1.0",
        "source": source,
        "source_sha256": hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest(),
        "route_count": len(routes),
        "routes": routes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a route/capability inventory from OpenAPI")
    parser.add_argument("--openapi", type=Path, default=DEFAULT_OPENAPI)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    document = json.loads(args.openapi.read_text(encoding="utf-8"))
    inventory = build_inventory(document, args.openapi.relative_to(REPO_ROOT).as_posix() if args.openapi.is_relative_to(REPO_ROOT) else args.openapi.as_posix())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"Generated {inventory['route_count']} routes at {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
