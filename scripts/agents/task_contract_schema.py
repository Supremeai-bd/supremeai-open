#!/usr/bin/env python3
"""Canonical Universal Task-Contract Schema v1 (#3088 §1, §8)।
=========================================================
# বাংলা মন্তব্য (#3088): "Task Type বদলাবে, কিন্তু envelope বদলাবে না।"
এই মডিউলটাই একমাত্র canonical task-contract — agent নিজের workflow/contract
invent করতে পারবে না; সবাই একই machine-validated envelope মানবে, boundary-র
ভিতরে implementation freedom থাকবে।

তিনটি ভিন্ন TaskContract-উত্তরাধিকার আজ পর্যন্ত চালু (backend/core,
backend/external_agents/contracts, continuous_agent_loop) — কোনোটিই এই
envelope নয়। এই schema সেগুলোর **replacement নয়** (big-bang নিষিদ্ধ);
এটি canonical envelope যা build_task_contract (loop) ধীরে ধীরে গ্রহণ করবে।

মূল ক্ষমতা:
  - TaskContract dataclass — spec §1-এর প্রতিটি ফিল্ড
  - contract_hash() — provenance-safe approval-এর ভিত্তি (spec §5:
    "Contract বদলালে পুরনো approval invalid হবে")
  - validate() — schema-স্তরের গার্ড-যাচাই (GUARD-TEMPLATE/GROUP/ADMIN-চেক)
  - STANDARD_OUTPUTS — প্রতিটি task_type-এর নির্দিষ্ট আউটপুট-ধাপ (spec §1)
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass

TASK_CONTRACT_VERSION = 1

# ── Enum-equivalents (spec §1) ───────────────────────────────────────────────
TASK_TYPES = (
    "AUDIT", "PLAN", "IMPLEMENT", "FIX_CI", "REVIEW",
    "SECURITY_AUDIT", "DISCOVERY", "MERGE", "ADMIN_DECISION",
)
PRIORITIES = ("P0", "P1", "P2", "P3")
ADMIN_GATE_STATUSES = ("NOT_REQUIRED", "WAITING", "APPROVED", "REJECTED")

# Standard task outputs (spec §1 "Standard task outputs") — প্রতিটি task_type-এর
# আউটপুট-ধাপ machine-readable; agent নিজের ধাপ invent করবে না।
STANDARD_OUTPUTS: dict[str, list[str]] = {
    "AUDIT": ["Evidence", "Root Cause", "Risk", "Recommendation", "Issue(s)"],
    "PLAN": ["Findings", "Reuse Analysis", "Dependencies", "Group/Seq Plan"],
    "IMPLEMENT": ["Scope", "Implementation", "Tests", "Evidence", "PR"],
    "FIX_CI": ["Failure", "Root Cause", "Minimal Fix", "Rerun", "Evidence"],
    "SECURITY_AUDIT": ["Attack Surface", "Finding", "Severity", "Evidence", "Remediation Issue"],
    "DISCOVERY": ["New Finding", "Evidence", "Existing-work Check", "Parent/Related Issue"],
    "REVIEW": ["Scope", "Gates", "Diff/Architecture Review", "Decision"],
    "MERGE": ["Preconditions", "Gate Results", "Decision", "Post-merge watch"],
    "ADMIN_DECISION": ["Options", "Trade-offs", "Recommendation", "Decision Request"],
}

# বাংলা মন্তব্য: instruction envelope-এর নির্দিষ্ট ক্রম (spec §8) — orchestrator
# প্রত্যেক agent-কে একই structure-এ পাঠাবে।
ENVELOPE_SECTIONS = (
    "SUPREMEAI TASK CONTRACT",
    "TASK / OBJECTIVE / GROUP / PRIORITY / SEQUENCE",
    "SCOPE / DEPENDENCIES / ADMIN GATE",
    "UNIVERSAL RULES / ROLE CONTRACT",
    "REQUIRED ACTIONS / FORBIDDEN ACTIONS",
    "REQUIRED EVIDENCE / VERIFICATION / ACCEPTANCE",
    "STOP CONDITIONS / OUTPUT FORMAT",
)


@dataclass
class AdminGate:
    """Spec §5 — provenance-safe admin gate।"""

    required: bool = False
    status: str = "NOT_REQUIRED"
    # approval provenance (spec §5: label যথেষ্ট নয় — identity+timestamp+version)
    approved_by: str | None = None
    approved_at: str | None = None
    contract_hash_at_approval: str | None = None
    decision_reference: str | None = None


@dataclass
class TaskContract:
    """#3088 §1 — universal envelope। Task type বদলায়, envelope বদলায় না।"""

    version: int = TASK_CONTRACT_VERSION
    task_id: str = ""
    issue: int | None = None
    task_type: str = "IMPLEMENT"
    group: str = ""
    sequence: int | None = None
    priority: str = "P2"
    objective: str = ""
    touching_files: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    predecessor: int | None = None
    rules_universal: list[str] = field(default_factory=list)
    rules_task_specific: list[str] = field(default_factory=list)
    permissions: dict[str, Any] = field(default_factory=dict)
    forbidden_actions: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    admin_gate: AdminGate = field(default_factory=AdminGate)
    decision_ledger_required: bool = True
    output_format: str = "structured"

    # ── serialization ────────────────────────────────────────────────────
    def to_dict(self) -> dict:
        d = asdict(self)
        d["standard_output_steps"] = STANDARD_OUTPUTS.get(self.task_type, [])
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TaskContract":
        gate = data.get("admin_gate") or {}
        admin = AdminGate(
            required=bool(gate.get("required", False)),
            status=str(gate.get("status", "NOT_REQUIRED")),
            approved_by=gate.get("approved_by"),
            approved_at=gate.get("approved_at"),
            contract_hash_at_approval=gate.get("contract_hash_at_approval"),
            decision_reference=gate.get("decision_reference"),
        )
        # বাংলা মন্তব্য: অপরিচিত key নীরবে বাদ — forward-compat (v2 ফিল্ড)।
        known = {f for f in cls.__dataclass_fields__ if f != "admin_gate"}
        payload = {k: v for k, v in data.items() if k in known}
        payload["admin_gate"] = admin
        return cls(**payload)

    def contract_hash(self) -> str:
        """Canonical JSON-এর sha256[:16] — approval-provenance-এর ভিত্তি।

        # বাংলা মন্তব্য (spec §5): approval রেকর্ড করার সময় এই hash জমা হবে;
        contract বদলালে (objective/scope/priority...) hash বদলে যাবে →
        পুরনো approval স্বয়ংক্রিয় invalid — re-approval লাগবে।
        """
        payload = self.to_dict()
        payload.pop("standard_output_steps", None)
        payload.pop("admin_gate", None)  # approval-স্টেট নয়, কাজের সংজ্ঞাই hash
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    # ── validation ───────────────────────────────────────────────────────
    def validate(self) -> list[str]:
        """Schema-স্তরের গার্ড-যাচাই — ভাঙলে তালিকা ফেরত (raise নয়)।

        # বাংলা মন্তব্য: প্রতিটি চেক spec-এর নির্দিষ্ট GUARD-এর schema-পাশ:
          - task_type/priority/sequence → GUARD-TEMPLATE (envelope চুক্তি)
          - group → GUARD-GROUP
          - predecessor < issue → GUARD-SEQUENCE (schema-পাশ)
          - admin_gate.status → GUARD-ADMIN (APPROVED ছাড়া WAITING কাজ দেবে না)
        """
        errors: list[str] = []
        if self.version != TASK_CONTRACT_VERSION:
            errors.append(f"unsupported contract version: {self.version} (expected {TASK_CONTRACT_VERSION})")
        if not self.task_id:
            errors.append("task_id empty")
        if self.task_type not in TASK_TYPES:
            errors.append(f"invalid task_type: {self.task_type} (allowed: {', '.join(TASK_TYPES)})")
        if self.priority not in PRIORITIES:
            errors.append(f"invalid priority: {self.priority} (allowed: {', '.join(PRIORITIES)})")
        if not self.group:
            errors.append("primary group empty — spec §2: প্রতিটি ইস্যুর primary group বাধ্যতামূলক")
        if self.sequence is not None and self.sequence < 1:
            errors.append(f"sequence must be ≥1, got {self.sequence}")
        if self.predecessor is not None and self.issue is not None and self.predecessor >= self.issue:
            # বাংলা মন্তব্য: predecessor সংখ্যাগতভাবে আগের ইস্যু হওয়া উচিত —
            # ভবিষ্যতের ইস্যু-নম্বর predecessor হলে seq-chain ভাঙা (typo-সন্দেহ)।
            errors.append(f"predecessor #{self.predecessor} must precede issue #{self.issue}")
        if not self.objective.strip():
            errors.append("objective empty — কী অর্জন করতে হবে তা ছাড়া contract অচল")
        if self.admin_gate.status not in ADMIN_GATE_STATUSES:
            errors.append(f"invalid admin_gate.status: {self.admin_gate.status}")
        if self.admin_gate.required and self.admin_gate.status in ("NOT_REQUIRED",):
            errors.append("admin_gate.required=true কিন্তু status=NOT_REQUIRED — WAITING হওয়া উচিত")
        if self.admin_gate.status == "APPROVED" and not self.admin_gate.approved_by:
            errors.append("APPROVED status-এ approved_by (provenance) বাধ্যতামূলক — spec §5")
        if self.admin_gate.status == "APPROVED" and not self.admin_gate.contract_hash_at_approval:
            errors.append("APPROVED status-এ contract_hash_at_approval বাধ্যতামূলক (approval চুক্তি-সংস্করণ-বাঁধা)")
        return errors

    def is_approved_for_work(self) -> bool:
        """GUARD-ADMIN schema-পাশ: কাজ-শুরুর যোগ্য কিনা।

        # বাংলা মন্তব্য: required=False → কাজ যোগ্য; required=True হলে
        status=APPROVED এবং approval-সময়ের hash বর্তমান hash-এর সাথে মিলতে
        হবে — "Contract বদলালে পুরনো approval invalid" (spec §5)।
        """
        if not self.admin_gate.required:
            return True
        if self.admin_gate.status != "APPROVED":
            return False
        return self.admin_gate.contract_hash_at_approval == self.contract_hash()

    def render_envelope(self) -> str:
        """Spec §8 — one standard instruction envelope (human-readable)।"""
        gate = self.admin_gate
        return "\n".join([
            "SUPREMEAI TASK CONTRACT",
            f"TASK: {self.task_type} · OBJECTIVE: {self.objective}",
            f"GROUP: {self.group} · PRIORITY: {self.priority} · SEQUENCE: {self.sequence or '-'}",
            f"SCOPE: {', '.join(self.touching_files) or '-'}"
            + (f" | FORBIDDEN: {', '.join(self.forbidden_paths)}" if self.forbidden_paths else ""),
            f"DEPENDENCIES: {', '.join(self.dependencies) or '-'} · PREDECESSOR: {self.predecessor or '-'}"
            f" · ADMIN GATE: {'required/' + gate.status if gate.required else 'not-required'}",
            f"UNIVERSAL RULES: {'; '.join(self.rules_universal) or '-'}",
            f"REQUIRED ACTIONS: {', '.join(self.required_evidence) or '-'}"
            f" · FORBIDDEN ACTIONS: {', '.join(self.forbidden_actions) or '-'}",
            f"REQUIRED EVIDENCE: {', '.join(self.required_evidence) or '-'}"
            f" · VERIFICATION: {', '.join(self.verification) or '-'}"
            f" · ACCEPTANCE: {', '.join(self.acceptance) or '-'}",
            f"STOP CONDITIONS: {', '.join(self.stop_conditions) or '-'}"
            f" · OUTPUT FORMAT: {self.output_format} (steps: {' → '.join(STANDARD_OUTPUTS.get(self.task_type, []))})",
        ])


def contract_from_issue(
    issue_number: int,
    title: str,
    labels: list[str],
    group: str,
    objective: str = "",
    touching_files: list[str] | None = None,
    priority: str = "P2",
    sequence: int | None = None,
    predecessor: int | None = None,
    admin_gate_required: bool = False,
) -> TaskContract:
    """Issue → canonical contract রূপান্তর (loop build_task_contract-এর ব্রিজ)।

    # বাংলা মন্তব্য: task_id স্থিতিশীল + deterministic — issue-নম্বর-ভিত্তিক
    (uuid নয়; একই ইস্যু থেকে সবসময় একই id, re-run-এ নতুন id জন্মাবে না)।
    """
    title_type = "IMPLEMENT"
    t = (title or "").split("(", 1)[0].strip().lower()
    mapping = {
        "fix": "FIX_CI", "feat": "IMPLEMENT", "refactor": "IMPLEMENT",
        "audit": "AUDIT", "test": "IMPLEMENT", "chore": "IMPLEMENT",
        "docs": "IMPLEMENT", "perf": "IMPLEMENT", "task": "IMPLEMENT", "ops": "IMPLEMENT",
    }
    # বাংলা মন্তব্য: admin-gate লেবেল থেকেই required-inference — caller
    # আলাদা করে বলতে না-ও পারে; দুই-উৎস থাকলে max (label-সত্য জিতবে)।
    admin_required = admin_gate_required or ("gate:admin-approval" in labels)
    if "gate:admin-approval" in labels:
        title_type = "ADMIN_DECISION"
    elif t in mapping:
        title_type = mapping[t]
    return TaskContract(
        task_id=f"task-issue-{issue_number}",
        issue=issue_number,
        task_type=title_type,
        group=group,
        sequence=sequence,
        priority=priority,
        objective=objective or (title or "").strip(),
        touching_files=list(touching_files or []),
        predecessor=predecessor,
        admin_gate=AdminGate(
            required=admin_required,
            status="WAITING" if admin_required else "NOT_REQUIRED",
        ),
    )


def main() -> int:
    """CLI smoke: নমুনা contract → validate + envelope (self-test)।"""
    c = contract_from_issue(
        3088, "feat(governance): standardize task templates",
        labels=["P1-high"], group="governance", objective="canonical task-contract model",
        touching_files=["scripts/agents/task_contract_schema.py"], priority="P1",
    )
    errors = c.validate()
    print(json.dumps(c.to_dict(), ensure_ascii=False, indent=2))
    print("--- envelope ---")
    print(c.render_envelope())
    print(f"contract_hash: {c.contract_hash()}")
    print(f"validation: {'OK' if not errors else errors}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
