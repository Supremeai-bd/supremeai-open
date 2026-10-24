#!/usr/bin/env python3
"""Scope Gate — Step-security.1 (#109): claim-time customer-isolation enforcement.

# বাংলা মন্তব্য: plan taxonomy (supremeai_internal / customer_facing /
# combined_ecosystem) আগে শুধু docs-স্তরে enforce হতো (lint_plans.py — warn-only);
# claim path-এ কোনো runtime gate ছিল না। এই মডিউল fail-closed runtime gate —
# customer/tenant-scoped demand যদি supremeai_internal (Layer 1) task claim করে,
# deterministic refusal + evidence। Constitution boundary: "Layer 1 strictly
# prohibited in customer/tenant projects"।

**নাম-দ্ব্যর্থতা দ্রষ্টব্য:** এটি **claim-time** customer-isolation gate। PR-লেভেলের
**scope-conformance gate** ভিন্ন জিনিস — `.github/scripts/constitution/gates.py::
run_scope_gate` (touching-files ঘোষণা-মিল)। দুটোই "scope gate" পরিবার, কিন্তু
লাইফসাইকেল-স্টেজ ও প্যাকেজ আলাদা — একটার দ্বারা অন্যটা replaced হয় না।

Read-only reuse (P2): taxonomy SSOT = `scripts/governance/lint_plans.py::TARGET_SCOPES`
— নতুন taxonomy সংজ্ঞা এখানে নয়। Wiring: `continuous_agent_loop.py` claim path —
`claim_with_backoff`-এর ঠিক আগে (`scope_gate_preflight`) — fail-closed: gate
pass না করলে claim-ই হয় না।
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

# ── SSOT reuse (P2 — নতুন taxonomy সংজ্ঞা নয়) ──────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
from scripts.governance.lint_plans import TARGET_SCOPES  # noqa: E402

# বাংলা মন্তব্য: customer/tenant demand-lane — SSOT-র একমাত্র customer scope
# `customer_facing`; tenant demand সেই লেনেই চলে (alias নিচে)। অজানা মান =
# fail-closed refusal (U6 — চুপচাপ allow নয়)।
CUSTOMER_DEMAND_SCOPES = frozenset({"customer_facing", "customer_tenant", "tenant"})
TENANT_ALIASES = {"customer_tenant", "tenant"}  # → customer_facing লেনে normalize

# বাংলা মন্তব্য: demand-এর উৎস — env প্রাধান্য (customer project-এ চলা loop
# SUPREMEAI_DEMAND_SCOPE দিয়ে নিজের লেন ঘোষণা করে); না থাকলে ডিফল্ট = ভেতরের
# লেন (এই monorepo-র বর্তমান বাস্তবতা — explicit opt-in ছাড়া আচরণ অপরিবর্তিত)।
DEMAND_SCOPE_ENV = "SUPREMEAI_DEMAND_SCOPE"
DEFAULT_DEMAND_SCOPE = "supremeai_internal"

# বাংলা মন্তব্য: Layer-1 internal machinery prefixes — combined_ecosystem task-এ
# এই প্রিফিক্সের ফাইল declared হলে সেগুলো restricted-list-এ যায় (mission §২.৩)।
# প্রমাণ-ভিত্তি: প্ল্যাটফর্মের নিজের কোর-ইঞ্জিন + এজেন্ট-সিস্টেম + গেট-মেশিনারি।
INTERNAL_LAYER_PREFIXES = (
    "backend/core/",
    "scripts/agents/",
    "scripts/ci/",
    ".github/scripts/constitution/",
)

# issue body/label-এ target_scope metadata পার্সিং (deterministic, warn-free)
_TARGET_SCOPE_LINE_RE = re.compile(r"^\s*target_scope:\s*([A-Za-z_]+)\s*$", re.M)
_SCOPE_LABEL_RE = re.compile(r"^scope:([A-Za-z_]+)$")


def resolve_demand_scope(explicit: str | None = None) -> str:
    """demand-এর target_scope resolve — explicit > env > default (fail-closed নয়, ঘোষণা-চেইন)।

    # বাংলা মন্তব্য: অজানা মান এখানে raise করে না — evaluate_claim সেটাকেই
    # refuse করবে (invalid-demand-scope) — যাতে call-site কখনো ভেদ করতে না পারে।
    """
    if explicit:
        return explicit.strip().lower()
    env_val = (os.environ.get(DEMAND_SCOPE_ENV) or "").strip().lower()
    if env_val:
        return env_val
    return DEFAULT_DEMAND_SCOPE


def resolve_task_scope(labels: list[str] | None, issue_body: str | None) -> str:
    """task-এর target_scope resolve — label `scope:*` > body `target_scope:` > presumed Layer 1।

    # বাংলা মন্তব্য: ডিফল্ট "supremeai_internal" (presumed Layer 1) — এটাই
    # fail-closed: scope ঘোষণা না থাকলে task-কে ভেতরের লেন ধরা হয়, ফলে
    # customer demand-এ অঘোষিত task নিজে থেকেই refusal-এ পড়বে।
    """
    for lbl in labels or []:
        m = _SCOPE_LABEL_RE.match(str(lbl).strip())
        if m:
            return m.group(1).strip().lower()
    if issue_body:
        m = _TARGET_SCOPE_LINE_RE.search(issue_body)
        if m:
            return m.group(1).strip().lower()
    return "supremeai_internal"


def _restricted_internal_files(declared_files: list[str] | None) -> list[str]:
    """declared ∩ internal-layer → restricted list (combined_ecosystem marker-এর অংশ)।"""
    out: list[str] = []
    for f in declared_files or []:
        clean = str(f).strip().lstrip("./")
        if any(clean.startswith(p) for p in INTERNAL_LAYER_PREFIXES):
            out.append(clean)
    return sorted(set(out))


def evaluate_claim(
    demand_scope: str,
    task_scope: str,
    declared_files: list[str] | None = None,
) -> dict[str, Any]:
    """Fail-closed decision matrix — প্রতিটি refusal-এ evidence (কারণ+scope+fingerprint)।

    # বাংলা মন্তব্য (mission §২): (১) invalid taxonomy = refuse; (২) customer/
    # tenant demand × supremeai_internal task = refuse (customer-isolation);
    # (৩) combined_ecosystem = allow + explicit marker + internal restricted list;
    # (৪) সিদ্ধান্ত structured audit-line হিসেবে যায় (audit_log)।
    """
    demand = (demand_scope or "").strip().lower()
    task = (task_scope or "").strip().lower()

    # tenant alias → customer লেনে normalize (SSOT ভোকাবুলারি অক্ষত)
    if demand in TENANT_ALIASES:
        demand = "customer_facing"

    fp = hashlib.sha256(
        f"{demand}|{task}|{','.join(sorted(set(declared_files or [])))}".encode()
    ).hexdigest()[:12]

    decision: dict[str, Any] = {
        "gate": "scope_gate",
        "demand_scope": demand,
        "task_scope": task,
        "fingerprint": fp,
        "marker": None,
        "restricted_internal_files": [],
    }

    if task not in TARGET_SCOPES:
        decision.update(
            allowed=False,
            reason=f"invalid-task-scope: `{task}` not in {sorted(TARGET_SCOPES)} (SSOT: lint_plans.TARGET_SCOPES)",
        )
    elif demand not in TARGET_SCOPES and demand not in CUSTOMER_DEMAND_SCOPES:
        decision.update(
            allowed=False,
            reason=f"invalid-demand-scope: `{demand}` unknown (fail-closed U6)",
        )
    elif demand in CUSTOMER_DEMAND_SCOPES and task == "supremeai_internal":
        decision.update(
            allowed=False,
            reason=(
                "customer-isolation-violation: customer/tenant demand "
                f"(`{demand}`) may not claim supremeai_internal (Layer 1) task — "
                "constitution: Layer 1 strictly prohibited in customer/tenant projects"
            ),
        )
    else:
        marker = None
        restricted: list[str] = []
        if task == "combined_ecosystem":
            marker = "combined_ecosystem:internal-touch-restricted"
            restricted = _restricted_internal_files(declared_files)
        decision.update(allowed=True, reason="allow", marker=marker,
                        restricted_internal_files=restricted)
    return decision


def audit_log(decision: dict[str, Any]) -> str:
    """সিদ্ধান্ত → structured single-line JSON (deterministic — sort_keys)।"""
    return json.dumps(decision, sort_keys=True, ensure_ascii=False)


def scope_gate_preflight(
    issue_number: str | int,
    task: dict[str, Any] | None,
    declared_files: list[str] | None,
) -> dict[str, Any]:
    """Loop wiring entry: claim-এর আগে সম্পূর্ণ সিদ্ধান্ত (body fetch সহ)।

    # বাংলা মন্তব্য: body fetch ব্যর্থ হলে task scope presumed Layer 1 (fail-closed
    # — অজানা = কড়া)। এই ফাংশন loop-কে জানে না (circular-import নেই); gh CLI
    # PATH থেকে (atomic_claim.sh-এর মতোই)।
    """
    labels = list((task or {}).get("labels") or [])
    body = ""
    try:
        res = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--json", "body", "--jq", ".body"],
            capture_output=True, text=True, timeout=30,
        )
        if res.returncode == 0 and res.stdout:
            body = res.stdout
    except Exception:  # noqa: BLE001 — fetch ব্যর্থতাও fail-closed পথেই যায়
        body = ""
    return evaluate_claim(
        resolve_demand_scope(),
        resolve_task_scope(labels, body),
        declared_files,
    )


if __name__ == "__main__":
    import sys

    _d = evaluate_claim(
        resolve_demand_scope(sys.argv[1] if len(sys.argv) > 1 else None),
        sys.argv[2] if len(sys.argv) > 2 else "supremeai_internal",
        sys.argv[3:] or None,
    )
    print(audit_log(_d))
    sys.exit(0 if _d["allowed"] else 1)
