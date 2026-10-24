#!/usr/bin/env python3
"""M0-B (roadmap M0.2) guard: enforce that the Alembic version graph has exactly one head.

Pure-stdlib (AST-based) so CI can run it without installing the backend's
dependency set. It parses alembic_migrations/versions/*.py, extracts each
revision's `revision` and `down_revision` literals, builds the lineage graph
and fails if more than one head exists.

Background (audit F3): three heads existed at once (mcp_gw_0001,
a7b8c9d0e1f2, k5l6m7n8o9p0); a merge revision 6250e2a31d38 was introduced in
M0-B. This guard prevents the drift from coming back.

Usage:  python backend/scripts/check_single_alembic_head.py [versions_dir]
Exit codes: 0 = single head, 1 = multiple heads / graph error, 2 = no revisions found.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

DEFAULT_VERSIONS_DIR = Path(__file__).resolve().parent.parent / "alembic_migrations" / "versions"


def _literal_from_assign(node: ast.AST, name: str):
    """Return the constant value assigned to `name` at module level, else None."""
    if not isinstance(node, (ast.Assign, ast.AnnAssign)):
        return None
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    for target in targets:
        if isinstance(target, ast.Name) and target.id == name:
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            if isinstance(value, ast.Constant) and value.value is None:
                return None
            if isinstance(value, (ast.Tuple, ast.List)):
                parts = []
                for element in value.elts:
                    if isinstance(element, ast.Constant) and isinstance(element.value, str):
                        parts.append(element.value)
                    else:
                        return None
                return tuple(parts)
    return None


def collect_revisions(versions_dir: Path) -> dict[str, tuple]:
    """Map revision id -> tuple of parents (empty tuple when down_revision is None)."""
    revisions: dict[str, tuple] = {}
    for path in sorted(versions_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rev_id = None
        parents = ()
        for node in tree.body:
            for target_name, slot in (("revision", "rev"), ("down_revision", "down")):
                value = _literal_from_assign(node, target_name)
                if value is None:
                    continue
                if slot == "rev":
                    rev_id = value
                else:
                    parents = (value,) if isinstance(value, str) else tuple(value)
        if rev_id is None:
            raise SystemExit(f"ERROR: {path.name} does not define a literal `revision`")
        if rev_id in revisions:
            raise SystemExit(f"ERROR: duplicate revision id {rev_id!r} in {path.name}")
        revisions[rev_id] = parents
    return revisions


def find_heads(revisions: dict[str, tuple]) -> set[str]:
    """A head is a revision that no other revision descends from."""
    parents = {p for parent_tuple in revisions.values() for p in parent_tuple}
    missing = parents - set(revisions)
    if missing:
        raise SystemExit(f"ERROR: parent revisions referenced but not present: {sorted(missing)}")
    return set(revisions) - parents


def main() -> int:
    versions_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_VERSIONS_DIR
    if not versions_dir.is_dir():
        raise SystemExit(f"ERROR: versions dir not found: {versions_dir}")

    revisions = collect_revisions(versions_dir)
    if not revisions:
        print(f"ERROR: no revisions found under {versions_dir}")
        return 2

    heads = find_heads(revisions)
    print(f"alembic version graph: {len(revisions)} revisions, {len(heads)} head(s)")
    for head in sorted(heads):
        print(f"  head: {head}")

    if len(heads) != 1:
        print("FAIL: alembic must have exactly ONE head (roadmap M0-B / audit F3)")
        return 1
    print("OK: single alembic head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
