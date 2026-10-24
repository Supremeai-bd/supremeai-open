#!/usr/bin/env python3
"""SupremeAI — sync_operational_truth.py (issue #2377, Deliverable 2).

Markdown/YAML registries → operational-truth DB-তে initial + recurring sync.
"সবকিছু নতুন করে বানাব না" — existing single-source docs থেকে শুধু live-state
অংশগুলো DB-তে যায় (no DB dumping ground):

  system_modules   ← docs/architecture/ECOSYSTEM_GRAPH_REGISTRY.yaml (#2399)
                     domains (10) + nodes (28) + db_model_domain_map (40)
  capabilities     ← docs/architecture/CAPABILITY_LEDGER.md (CAP-XX-NN rows)
  agent_leases     ← docs/master_docs/AGENT_SLOT_REGISTRY.yaml (pool templates)
  operational_tasks← docs/operations/ACTIVE_ISSUES_AND_PRIORITY_ROADMAP.md
  audit_queue      ← docs/audits/ACTIVE_AUDIT_QUEUE.md (GAP-NNN rows)
  secret_rotations ← docs/security/TOKEN_ROTATION_VERIFICATION.md (sections)

Usage:
    # Dry-run (কোনো DB লাগে না — CI/audit-safe):
    python scripts/operations/sync_operational_truth.py

    # Local SQLite mirror-এ লিখুন:
    python scripts/operations/sync_operational_truth.py --sqlite data/operational_truth.db

    # Canonical Supabase Postgres-এ লিখুন:
    python scripts/operations/sync_operational_truth.py \
        --db-url "$SUPABASE_DATABASE_URL_WRITER" --ensure-schema

    # নির্দিষ্ট টেবিল শুধু:
    python scripts/operations/sync_operational_truth.py --only capabilities,agent_leases
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from operational_truth_db import (  # noqa: E402
    TABLE_NAMES,
    connect,
    ensure_schema,
    upsert_rows,
)

GRAPH_REGISTRY = REPO_ROOT / "docs" / "architecture" / "ECOSYSTEM_GRAPH_REGISTRY.yaml"
CAPABILITY_LEDGER = REPO_ROOT / "docs" / "architecture" / "CAPABILITY_LEDGER.md"
SLOT_REGISTRY = REPO_ROOT / "docs" / "master_docs" / "AGENT_SLOT_REGISTRY.yaml"
ROADMAP = REPO_ROOT / "docs" / "operations" / "ACTIVE_ISSUES_AND_PRIORITY_ROADMAP.md"
AUDIT_QUEUE_DOC = REPO_ROOT / "docs" / "audits" / "ACTIVE_AUDIT_QUEUE.md"
TOKEN_ROTATION_DOC = REPO_ROOT / "docs" / "security" / "TOKEN_ROTATION_VERIFICATION.md"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


# ══════════════════════════════════════════════════════════════════════
# Parser 1: ECOSYSTEM_GRAPH_REGISTRY.yaml → system_modules
# ══════════════════════════════════════════════════════════════════════
def parse_graph_registry(path: Path = GRAPH_REGISTRY) -> list[dict[str, Any]]:
    import yaml  # CI-তে pyyaml ensured (artifact-regen-ও ব্যবহার করে)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    now = _now_iso()
    rows: list[dict[str, Any]] = []

    for dom in data.get("domains", []):
        rows.append(
            {
                "name": dom.get("name") or dom.get("id"),
                "kind": "domain",
                "layer": "domain",
                "domain_id": dom.get("id"),
                "status": "active",
                "owner_lane": None,
                "owning_paths": dom.get("owning_paths", []),
                "meta": {
                    "name_bn": dom.get("name_bn"),
                    "mission": dom.get("mission"),
                    "boundaries": dom.get("boundaries"),
                },
                "source_doc": str(path.relative_to(REPO_ROOT)),
                "updated_at": now,
            }
        )

    for node in data.get("nodes", []):
        dom = node.get("domain") or ""
        rows.append(
            {
                "name": node.get("id"),
                "kind": "node",
                "layer": node.get("type") or "node",
                "domain_id": dom.split("::")[0] if dom else None,
                "status": "active",
                "owning_paths": [node["path"]] if node.get("path") else [],
                "meta": {"summary": node.get("summary")},
                "source_doc": str(path.relative_to(REPO_ROOT)),
                "updated_at": now,
            }
        )

    # DB model → domain mapping — "DB schema সঠিক domain map করতে পারবে" (#2377)
    for model_file, domain_id in (data.get("db_model_domain_map") or {}).items():
        rows.append(
            {
                "name": model_file,
                "kind": "db-model",
                "layer": "db",
                "domain_id": domain_id,
                "status": "active",
                "owning_paths": [f"backend/models/{model_file}"],
                "meta": {},
                "source_doc": str(path.relative_to(REPO_ROOT)),
                "updated_at": now,
            }
        )
    return rows


# ══════════════════════════════════════════════════════════════════════
# Parser 2: CAPABILITY_LEDGER.md → capabilities
# ══════════════════════════════════════════════════════════════════════
_CAP_ROW = re.compile(
    r"^\|\s*\*\*`?(CAP-[A-Z]+-\d+)`?\*\*\s*\|(.+)\|$"
)
_LEDGER_STATUSES = {
    "VERIFIED", "PARTIAL", "IN_PROGRESS", "PLANNED", "PROPOSED", "DEPRECATED",
}


def _tier_from_evidence(evidence: str) -> int:
    """Evidence-hierarchy → tier 1-4 (derivation ডকুমেন্টেড, invention নয়)।

    4 = CODE+TEST+RUNTIME (পূর্ণ প্রোডাকশন-রেডি) · 3 = CODE+TEST
    2 = CODE only · 1 = DOCUMENT/PLAN_ONLY (spec আছে, কোড নেই)
    """
    ev = {e.strip("`* ").upper() for e in evidence.split(",") if e.strip("`* ")}
    if {"CODE", "TEST", "RUNTIME"} <= ev:
        return 4
    if {"CODE", "TEST"} <= ev:
        return 3
    if "CODE" in ev or "CI" in ev:
        return 2
    return 1


def parse_capability_ledger(path: Path = CAPABILITY_LEDGER) -> list[dict[str, Any]]:
    now = _now_iso()
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _CAP_ROW.match(line.strip())
        if not m:
            continue
        cap_id, rest = m.group(1), m.group(2)
        cells = [c.strip() for c in rest.split("|")]
        if len(cells) < 6:
            continue
        category = cells[0].strip("* ")
        name = cells[1].strip("* ")
        status = cells[2].strip("`* ")
        evidence = ", ".join(
            tok.strip("`* ") for tok in cells[3].split(",") if tok.strip("`* ")
        )
        canonical_path = cells[4].strip("`* ")
        preserve_raw = cells[5].strip("* ")
        target = cells[6].strip() if len(cells) > 6 else None
        if status not in _LEDGER_STATUSES:
            continue  # header/নন-দস্তাবেজ row — skip
        rows.append(
            {
                "capability_id": cap_id,
                "name": name,
                "category": category,
                "status": status,
                "tier": _tier_from_evidence(evidence),
                "evidence": evidence,
                "canonical_path": canonical_path or None,
                "preserve": preserve_raw.upper().startswith("MUST"),
                "target_architecture": target,
                "verification_proof": None,  # পরে audit প্রক্রিয়া পূরণ করবে
                "last_audit_at": None,
                "source_doc": str(path.relative_to(REPO_ROOT)),
                "updated_at": now,
            }
        )
    return rows


# ══════════════════════════════════════════════════════════════════════
# Parser 3: AGENT_SLOT_REGISTRY.yaml → agent_leases (pool templates)
# ══════════════════════════════════════════════════════════════════════
def parse_slot_registry(path: Path = SLOT_REGISTRY) -> list[dict[str, Any]]:
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    now = _now_iso()
    rows: list[dict[str, Any]] = []
    pools = data.get("role_pools", {}) or {}
    for pool_name, spec in pools.items():
        if not isinstance(spec, dict):
            continue
        rows.append(
            {
                "slot_id": f"pool:{pool_name}",
                "agent_name": spec.get("app"),
                "role": pool_name,
                "lane": pool_name,
                "issue_number": None,
                "branch_name": spec.get("branch_pattern") or spec.get("branch_slots"),
                "heartbeat_at": None,
                "expires_at": None,
                "state": "pool-template",
                "source": "slot-registry",
                "meta": {
                    "description": spec.get("description"),
                    "bot_identity": spec.get("bot_identity"),
                },
                "updated_at": now,
            }
        )
    return rows


# ══════════════════════════════════════════════════════════════════════
# Parser 4: ACTIVE_ISSUES_AND_PRIORITY_ROADMAP.md → operational_tasks
# ══════════════════════════════════════════════════════════════════════
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_TASK_ROW = re.compile(r"^\|\s*\*{0,2}(\d+)\*{0,2}\s*\|\s*\*{0,2}#(\d+)\*{0,2}\s*\|(.+)\|$")
_GROUP_LABEL = re.compile(r"group:([a-z0-9-]+)")


def parse_roadmap(path: Path = ROADMAP) -> list[dict[str, Any]]:
    now = _now_iso()
    text = path.read_text(encoding="utf-8").translate(_BN_DIGITS)
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    for line in text.splitlines():
        m = _TASK_ROW.match(line.strip())
        if not m:
            continue
        sequence, issue_number, rest = int(m.group(1)), int(m.group(2)), m.group(3)
        if issue_number in seen:
            continue  # একই issue একাধিক টেবিলে থাকতে পারে — প্রথম (highest-tier) রাখে
        cells = [c.strip() for c in rest.split("|")]
        title = cells[0].strip("`* ") if cells else None
        g = _GROUP_LABEL.search(rest)
        rows.append(
            {
                "issue_number": issue_number,
                "title": title,
                "group_name": g.group(1) if g else None,
                "sequence": sequence,
                "ripple_effect_score": None,  # auditor প্রক্রিয়া পরে পূরণ করবে
                "priority_tier": "foundation" if sequence <= 10 else "roadmap",
                "status": "open",
                "assigned_slot": None,
                "source_doc": str(path.relative_to(REPO_ROOT)),
                "updated_at": now,
            }
        )
        seen.add(issue_number)
    return rows


# ══════════════════════════════════════════════════════════════════════
# Parser 5: ACTIVE_AUDIT_QUEUE.md → audit_queue
# ══════════════════════════════════════════════════════════════════════
_GAP_ROW = re.compile(r"^\|\s*\d+\s*\|\s*~{0,2}(GAP-\d+)~{0,2}\s*\|(.+)\|$")


def parse_audit_queue(path: Path = AUDIT_QUEUE_DOC) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    now = _now_iso()
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _GAP_ROW.match(line.strip())
        if not m:
            continue
        finding_id, rest = m.group(1), m.group(2)
        cells = [c.strip() for c in rest.split("|")]
        if len(cells) < 5:
            continue
        category = cells[0].strip()
        target_path = cells[1].strip()
        description = cells[2].strip()
        status = cells[3].strip("[]` ")
        added_date = cells[4].strip()
        resolved = status.upper().startswith("RESOLVED")
        rows.append(
            {
                "finding_id": finding_id,
                "category": category or None,
                "target_path": target_path or None,
                "description": description or None,
                "status": status.upper() or "OPEN",
                "added_date": added_date or None,
                "resolved_at": now if resolved else None,
                "source_doc": str(path.relative_to(REPO_ROOT)),
                "updated_at": now,
            }
        )
    return rows


# ══════════════════════════════════════════════════════════════════════
# Parser 6: TOKEN_ROTATION_VERIFICATION.md → secret_rotations
# ══════════════════════════════════════════════════════════════════════
_ROT_SECTION = re.compile(r"^##\s+\d+\.\s+(.+)$")
# Active (non-comment) evidence line: "- 2026-09-XX · label · [REVOKED] status=401 · verified by ..."
_ROT_EVIDENCE = re.compile(r"^\s*-\s+\d{4}-\d{2}-\d{2}.*\[REVOKED\]")


def parse_token_rotation(path: Path = TOKEN_ROTATION_DOC) -> list[dict[str, Any]]:
    now = _now_iso()
    lines = path.read_text(encoding="utf-8").splitlines()

    # File-level base status — doc-এর নিজস্ব header সত্য (prose-scan নয়):
    # "> Status: **Harness + runbook active — ... pending (owner action)**"
    base_status = "runbook-active"
    for line in lines[:10]:
        if line.strip().startswith(">") and "Status:" in line:
            up = line.upper()
            if "PENDING" in up and "OWNER" in up:
                base_status = "pending-owner"
            break

    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        m = _ROT_SECTION.match(line.strip())
        if m:
            if current:
                rows.append(current)
            current = {
                "secret_name": m.group(1).strip(),
                "scope": "global",  # NOT NULL — composite unique key-এর অংশ
                "rotated_at": None,
                "verified_at": None,
                "status": base_status,
                "evidence": None,
                "notes": None,
                "source_doc": str(path.relative_to(REPO_ROOT)),
                "updated_at": now,
            }
            continue
        if current is None:
            continue
        # Active [REVOKED] evidence line থাকলেই verified (comment লাইন নয়)
        stripped = line.strip()
        if stripped and not stripped.startswith("<!--") and _ROT_EVIDENCE.match(stripped):
            current["status"] = "verified"
            current["evidence"] = stripped[:500]
    if current:
        rows.append(current)
    return rows


# ══════════════════════════════════════════════════════════════════════
# Sync orchestration
# ══════════════════════════════════════════════════════════════════════
_PARSERS: dict[str, tuple[Any, list[str]]] = {
    # table → (parser, conflict cols)
    "system_modules": (parse_graph_registry, ["name"]),
    "capabilities": (parse_capability_ledger, ["capability_id"]),
    "agent_leases": (parse_slot_registry, ["slot_id"]),
    "operational_tasks": (parse_roadmap, ["issue_number"]),
    "audit_queue": (parse_audit_queue, ["finding_id"]),
    "secret_rotations": (parse_token_rotation, ["secret_name", "scope"]),
}


def run_sync(
    only: list[str] | None = None,
    db_url: str | None = None,
    sqlite_path: str | None = None,
    ensure: bool = False,
    report_out: Path | None = None,
) -> dict[str, Any]:
    """সব (বা --only) টেবিল sync করে; DB target না থাকলে auto dry-run।"""
    targets = only or list(_PARSERS)
    for t in targets:
        if t not in _PARSERS:
            raise SystemExit(f"unknown table: {t} (valid: {', '.join(TABLE_NAMES)})")

    report: dict[str, Any] = {
        "mode": "dry-run" if not (db_url or sqlite_path) else "write",
        "started_at": _now_iso(),
        "tables": {},
    }

    parsed: dict[str, list[dict[str, Any]]] = {}
    for table in targets:
        parser, conflict = _PARSERS[table]
        try:
            rows = parser()
        except FileNotFoundError as exc:
            report["tables"][table] = {"error": f"source missing: {exc.filename}", "planned": 0}
            continue
        parsed[table] = rows
        report["tables"][table] = {"planned": len(rows), "conflict_cols": conflict}

    if db_url or sqlite_path:
        conn, flavor = connect(db_url=db_url, sqlite_path=sqlite_path)
        try:
            if ensure:
                created = ensure_schema(conn, flavor)
                report["schema_created"] = created
            for table, rows in parsed.items():
                conflict = _PARSERS[table][1]
                written = upsert_rows(conn, flavor, table, rows, conflict_cols=conflict)
                report["tables"][table]["written"] = written
        finally:
            conn.close()

    report["finished_at"] = _now_iso()
    if report_out:
        report_out.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


def _cli() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--db-url", default=None, help="Postgres URL (Supabase writer)")
    p.add_argument("--sqlite", default=None, help="SQLite path (local mirror)")
    p.add_argument("--ensure-schema", action="store_true", help="Create tables if missing")
    p.add_argument("--only", default=None, help="Comma-separated table list")
    p.add_argument("--report-out", default=None, help="Write JSON report to file")
    p.add_argument("--verbose", "-v", action="store_true")
    args = p.parse_args()

    only = [t.strip() for t in args.only.split(",")] if args.only else None
    report = run_sync(
        only=only,
        db_url=args.db_url,
        sqlite_path=args.sqlite,
        ensure=args.ensure_schema,
        report_out=Path(args.report_out) if args.report_out else None,
    )

    mode_tag = "DRY-RUN" if report["mode"] == "dry-run" else "WRITE"
    print(f"[sync] {mode_tag} @ {report['started_at']}")
    for table, info in report["tables"].items():
        if "error" in info:
            print(f"  ✗ {table}: {info['error']}")
            continue
        line = f"  ✓ {table}: {info['planned']} planned"
        if "written" in info:
            line += f" → {info['written']} upserted"
        print(line)
    if report.get("schema_created"):
        print(f"  + schema created: {', '.join(report['schema_created'])}")
    if args.report_out:
        print(f"  report → {args.report_out}")
    # dry-run বা write — দুই ক্ষেত্রেই parse-failure থাকলে non-zero
    has_error = any("error" in info for info in report["tables"].values())
    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(_cli())
