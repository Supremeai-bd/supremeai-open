from __future__ import annotations

import json
import sys
from pathlib import Path


def validate(matrix_path: str) -> dict:
    data = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    modules = data.get("modules", [])
    required = {"backend/adaptive_engine/capability_registry.py", "backend/adaptive_engine/capability_node.py", "backend/adaptive_engine/governed_executor.py"}
    present = {item["path"] for item in modules}
    missing = sorted(required - present)
    return {"ok": not missing, "missing": missing, "module_count": len(modules)}


if __name__ == "__main__":
    result = validate(sys.argv[1] if len(sys.argv) > 1 else "docs/generated/module_capability_matrix.json")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
