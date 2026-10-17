#!/usr/bin/env python3
"""S09 — Deterministic Role Trigger Matrix (issue #489).

Two-Paradigm Dispatch Engine for the Continuous Agent Loop:

  1. দায়িত্ব অর্পণ       (Role & Responsibility Assignment)
  2. নীতি ও সীমারেখা     (Must-Follow Rules vs Negative Constraints)
  3. অস্ত্র বরাদ্দ        (Weapon/Tool Provisioning: Scoped RBAC)

Design contract (issue #489, acceptance criteria):

  * Dispatch is STRUCTURALLY DETERMINISTIC. Roles are selected by an exact
    event-type router plus an exact label-plane lookup — never by scanning
    free text. Keyword matching in issue titles/bodies (the legacy
    ``classify_task_role`` anti-pattern, e.g. matching the literal word
    "audit") is deprecated and has NO equivalent API in this module.
  * Least-Privilege RBAC: a role receives ONLY its designated weapons.
    ``assert_least_privilege`` and ``authorize`` fail closed on any tool
    outside the role's allowlist.
  * Every gate fails closed: unknown event, missing label, wrong payload
    value, or unknown role yields a DENY decision / ValueError — never a
    best-effort guess.
  * Single source of truth: tests and integrations import these constants;
    nothing here is duplicated downstream.

Pure stdlib. Dual-mode: ``python3 -m unittest`` compatible and runnable
directly:

    python3 scripts/agents/role_trigger_matrix.py --self-test
    python3 scripts/agents/role_trigger_matrix.py --dispatch-event \
        event:task.claimed --labels status:claimed,P1-high
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any, Final

# ---------------------------------------------------------------------------
# Doctrine constants
# ---------------------------------------------------------------------------

TASK_DRIVEN: Final = "task_driven"      # Event, Queue & Runway paradigm
TIME_DRIVEN: Final = "time_driven"      # Cron & Periodic Probe paradigm
PARADIGMS: Final = (TASK_DRIVEN, TIME_DRIVEN)

#: Issue #489 deprecates fragile keyword matching outright. This constant is
#: the machine-readable tombstone: integrations may assert it to prove the
#: dispatch plane never inspects free text.
KEYWORD_MATCHING_DEPRECATED: Final = True

#: Free-text parameters that legacy call sites still pass (title/body) are
#: ignored by contract. This tuple documents the deprecated channel.
DEPRECATED_TEXT_CHANNELS: Final = ("title", "body")

CORE_PHILOSOPHY_FILTERS: Final = (
    "Simple > Clever",
    "Complexity must earn existence",
    "Zero-Admin",
)
MIN_SCOUT_PROPOSALS: Final = 10
ADVERSARIAL_SCOPE: Final = "tests/adversarial/"
P0_LABEL: Final = "P0-critical"

DECISION_DISPATCH: Final = "DISPATCH"
DECISION_DENY: Final = "DENY"

#: Weapons that write code or mutate the repository. The auditor family and
#: every read-only role MUST hold none of these (Least-Privilege invariant).
CODE_WRITE_WEAPONS: Final = frozenset({
    "replace_file_content",
    "multi_replace_file_content",
    "write_to_file",
    "git_branch_create",
    "pr_create",
    "pr_branch_commit",
    "adversarial_commit",
})

#: The scoped-commit weapon is special: rules-breaker holds it, but only for
#: paths inside ADVERSARIAL_SCOPE. File-edit weapons remain forbidden.
SCOPED_COMMIT_WEAPON: Final = "adversarial_commit"

# ---------------------------------------------------------------------------
# Contract records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TriggerSpec:
    """Structured, deterministic trigger for one role.

    Only exact-match fields exist. There is no field capable of carrying
    free text to match on — by construction the dispatch plane cannot
    regress into keyword scanning.
    """

    event_type: str
    required_labels: tuple[str, ...] = ()
    schedule_kind: str | None = None          # "cron" | "fixed_rate" | None
    required_payload: tuple[str, ...] = ()    # keys that must be present+truthy
    payload_expectations: tuple[tuple[str, str], ...] = ()  # key -> exact value


@dataclass(frozen=True)
class RoleContract:
    """The Triad: responsibility + rule constraints + weapon provisioning."""

    role_id: str
    name: str
    name_bn: str
    weapon_type: str                     # লাঠি বনাম ছুরি — from the issue matrix
    paradigm: str                        # TASK_DRIVEN | TIME_DRIVEN
    responsibility: str                  # দায়িত্ব
    must_follow: tuple[str, ...]         # মানতে হবে
    must_not: tuple[str, ...]            # মানবে না (নিষেধ)
    weapons: frozenset[str]              # অস্ত্র (exact tool names)
    forbidden_operations: tuple[str, ...]
    trigger: TriggerSpec
    commit_scopes: tuple[str, ...] = ()  # empty = no path restriction by matrix
    issue_labels: tuple[str, ...] = ()   # labels the role may file (e.g. P0-critical)


# ---------------------------------------------------------------------------
# The 8 canonical role contracts (issue #489 — Comprehensive Role Directory)
# ---------------------------------------------------------------------------

ROLE_CONTRACTS: Final[Mapping[str, RoleContract]] = MappingProxyType({
    "coder": RoleContract(
        role_id="coder",
        name="Coder (Task Executor)",
        name_bn="টাস্ক এক্সিকিউটর",
        weapon_type="Surgical Knife 🔪",
        paradigm=TASK_DRIVEN,
        responsibility=(
            "Implement the precise feature code or bug fix for an unclaimed "
            "backlog issue (ব্যাকলগে থাকা আনক্লেমড ইস্যুতে সুনির্দিষ্ট ফিচার কোড "
            "বা বাগ ফিক্স বাস্তবায়ন)।"
        ),
        must_follow=(
            "smallest safe change inside scope (স্কোপের ভেতর সবচেয়ে ছোট নিরাপদ পরিবর্তন)",
            "single-lock policy (সিঙ্গেল-লক নীতি)",
            "test evidence (টেস্ট এভিডেন্স)",
        ),
        must_not=(
            "writing code without a claim (ক্লেইম ছাড়া কোড লেখা নিষেধ)",
            "working while the PR runway is jammed (PR রানওয়ে জ্যাম থাকলে কাজ করা নিষেধ)",
            "architectural rewrites (আর্কিটেকচারাল রিরাইট নিষিদ্ধ)",
        ),
        weapons=frozenset({
            "replace_file_content",
            "multi_replace_file_content",
            "write_to_file",
            "test_runner",
            "git_branch_create",
            "pr_create",
        }),
        forbidden_operations=(
            "claiming without atomic lock",
            "breaking scope",
        ),
        trigger=TriggerSpec(
            event_type="event:task.claimed",
            required_labels=("status:claimed",),
        ),
    ),
    "ci-fixer": RoleContract(
        role_id="ci-fixer",
        name="CI Fixer (Runway Healer)",
        name_bn="রানওয়ে হিলার",
        weapon_type="Emergency Defibrillator ⚡",
        paradigm=TASK_DRIVEN,
        responsibility=(
            "Heal failing CI checks on in-flight PRs immediately — "
            "Runway-First priority (ইন-ফ্লাইট PR ফেইল করলে তাৎক্ষণিকভাবে সিআই "
            "চেক/গার্ড সবুজ করা)।"
        ),
        must_follow=(
            "root-cause resolution (রুট-কজ সমাধান)",
            "evidence update (এভিডেন্স আপডেট)",
            "permanent guard or test fix (পার্মানেন্ট গার্ড বা টেস্ট ফিক্স)",
        ),
        must_not=(
            "taking new feature/backlog work (নতুন ফিচার বা ব্যাকলগ ধরা নিষেধ)",
            "force-merge or rule bypass (রুলস বাইপাস করে ফোর্স-মার্জ সম্পূর্ণ নিষিদ্ধ)",
        ),
        weapons=frozenset({
            "replace_file_content",
            "multi_replace_file_content",
            "write_to_file",
            "ci_log_inspector",
            "test_preflight",
            "pr_branch_commit",
        }),
        forbidden_operations=(
            "opening new backlog issues",
            "bypassing checks",
        ),
        trigger=TriggerSpec(
            event_type="event:pr.ci_failed",
            required_payload=("pr_number",),
            payload_expectations=(("checks_state", "failing"),),
        ),
    ),
    "task-auditor": RoleContract(
        role_id="task-auditor",
        name="Task Auditor (Pre-Landing Compliance)",
        name_bn="পিআর ল্যান্ডিং ও কমপ্লায়েন্স নিরীক্ষক",
        weapon_type="Policy Stamp 📋",
        paradigm=TASK_DRIVEN,
        responsibility=(
            "Verify boundary rules, decision ledger and secret scanning just "
            "before a PR lands (পিআর ল্যান্ড করার ঠিক পূর্বে বাউন্ডারি রুলস, "
            "ডিসিশন লেজার ও সিক্রেট স্ক্যানিং ভেরিফাই)।"
        ),
        must_follow=(
            "fail-closed policy (ফেইল-ক্লোজড পলিসি)",
            "zero-residual check (জিরো-রেসিডুয়াল চেক)",
        ),
        must_not=(
            "writing or editing feature code (নিজে ফিচার কোড লেখা বা এডিট করা সম্পূর্ণ নিষিদ্ধ)",
        ),
        weapons=frozenset({
            "boundary_sanitization_guard_runner",
            "gitleaks_scanner",
            "pr_review_approve_block",
        }),
        forbidden_operations=(
            "modifying source code",
        ),
        trigger=TriggerSpec(
            event_type="event:pr.pre_landing",
            payload_expectations=(("landing_gate", "armed"),),
        ),
    ),
    "ecosystem-scout": RoleContract(
        role_id="ecosystem-scout",
        name="Ecosystem Scout (Global Tech Radar & Strategic Critic)",
        name_bn="গ্লোবাল টেক রাডার ও স্ট্র্যাটেজিক ক্রিটিক",
        weapon_type="Long-Range Telescope 🔭",
        paradigm=TIME_DRIVEN,
        responsibility=(
            "Observe external AI releases (Meta, Anthropic, OpenAI, DeepSeek…) "
            "and deliver full-spectrum evaluations — pros, cons, anti-patterns, "
            "risks and 'এটা করা যাবে না' — proposing at least 10 actionable "
            "issues (মিনিমাম ১০টি অ্যাকশনেবল ইস্যু প্রপোজ)।"
        ),
        must_follow=(
            "SupremeAI core philosophy filter (সুপ্রিমএআই কোর ফিলোসফি ফিল্টার)",
            "objective criticism (অবজেক্টিভ ক্রিটিসিজম)",
        ),
        must_not=(
            "blindly following hype (অন্ধভাবে কোনো হাইপ ফলো করা নিষেধ)",
            "editing or pushing local code (লোকাল কোডবেজে ফাইল এডিট বা কোড পুশ সম্পূর্ণ নিষিদ্ধ)",
        ),
        weapons=frozenset({
            "search_web",
            "read_url_content",
            "gh_issue_create",
        }),
        forbidden_operations=(
            "local code modifications",
            "uncritical hype",
        ),
        trigger=TriggerSpec(
            event_type="event:schedule.ecosystem_scan",
            schedule_kind="cron",
            required_payload=("schedule_expr",),
        ),
    ),
    "federation-auditor": RoleContract(
        role_id="federation-auditor",
        name="Federation Auditor (11 Internal Satellites)",
        name_bn="অভ্যন্তরীণ ১১টি রিপোর নিরীক্ষক",
        weapon_type="Ledger Microscope 🔬",
        paradigm=TIME_DRIVEN,
        responsibility=(
            "Inspect the 11 canonical satellite repos: head-commit parity, "
            "drift, license compliance and transit cleanliness (১১টি স্যাটেলাইট "
            "রিপো হেড কমিট প্যারিটি, ড্রিফট, লাইসেন্স কমপ্লায়েন্স ও ট্রানজিট "
            "ক্লিনলিনেস নিরীক্ষা)।"
        ),
        must_follow=(
            "impartial audit report (পক্ষপাতহীন অডিট রিপোর্ট)",
            "SSOT mapping of the 11 satellites (১১টি স্যাটেলাইটের এসএসওটি ম্যাপিং)",
        ),
        must_not=(
            "changing source code (সোর্স কোডে নিজে কোনো পরিবর্তন আনবে না)",
        ),
        weapons=frozenset({
            "multi_repo_git_inspector",
            "gh_issue_create",
        }),
        forbidden_operations=(
            "direct code edits",
        ),
        trigger=TriggerSpec(
            event_type="event:schedule.federation_audit",
            schedule_kind="cron",
            required_payload=("schedule_expr",),
        ),
    ),
    "human-eye": RoleContract(
        role_id="human-eye",
        name="Human Eye (PR, Styling & Aesthetic Team)",
        name_bn="সুপ্রিমএআই-এর পিআর, স্টাইলিং ও এস্থেটিক টিম",
        weapon_type="Stylist Camera & Mirror 📸",
        paradigm=TIME_DRIVEN,
        responsibility=(
            "Act as SupremeAI's personal stylist & PR QA director: fix the "
            "presentation before it takes the stage — visual excellence, "
            "color harmony, typography, premium feel (অ্যাপের ভিজ্যুয়াল "
            "এক্সিলেন্স নিশ্চিত করা)।"
        ),
        must_follow=(
            "aesthetic excellence (এস্থেটিক এক্সিলেন্স)",
            "first-impression quality (ফার্স্ট ইমপ্রেশন কোয়ালিটি)",
        ),
        must_not=(
            "editing source code (নিজে সোর্স কোড এডিট করবে না — কেবল ডিজাইন ও "
            "এস্থেটিক নির্দেশনাসহ ইস্যু তৈরি করবে)",
        ),
        weapons=frozenset({
            "browser_subagent",
            "gh_issue_create",
        }),
        forbidden_operations=(
            "modifying CSS/TS code directly",
            "git push / code write",
        ),
        trigger=TriggerSpec(
            event_type="event:schedule.visual_review",
            schedule_kind="fixed_rate",
            required_payload=("schedule_expr",),
        ),
    ),
    "rules-breaker": RoleContract(
        role_id="rules-breaker",
        name="Rules Breaker (Red Team, Chaos Engineer & Boundary Hacker)",
        name_bn="রেড-টিম, কেওস ইঞ্জিনিয়ার ও বাউন্ডারি হ্যাকার",
        weapon_type="Sledgehammer & Lockpick 🔨",
        paradigm=TIME_DRIVEN,
        responsibility=(
            "Dual-vector hacker attacks: (1) break the guards when you see "
            "them — race conditions, double claims, encoded payloads; "
            "(2) measure the damage ceiling where no guard exists — memory "
            "leaks, CPU spikes, DoS proof (ডুয়াল-ভেক্টর আক্রমণ)।"
        ),
        must_follow=(
            "commit failing exploit tests as damage proof (ধ্বংসের প্রমাণ হিসেবে "
            "ফেইলিং এক্সপ্লয়েট টেস্ট কমিট)",
            f"file {P0_LABEL} issues (P0-critical ইস্যু ফাইল করা বাধ্যতামূলক)",
        ),
        must_not=(
            "writing the security patch yourself (নিজে সিকিউরিটি প্যাচ কোড লিখবে না)",
            "causing permanent production damage (প্রোডাকশনে কোনো পার্মানেন্ট ক্ষতি করবে না)",
        ),
        weapons=frozenset({
            "adversarial_fuzzer",
            "adversarial_attack_runner",
            SCOPED_COMMIT_WEAPON,
            "gh_issue_create",
        }),
        forbidden_operations=(
            "production changes",
            "attempting self-patch",
        ),
        trigger=TriggerSpec(
            event_type="event:schedule.adversarial_probe",
            schedule_kind="fixed_rate",
            required_payload=("schedule_expr",),
        ),
        commit_scopes=(ADVERSARIAL_SCOPE,),
        issue_labels=(P0_LABEL,),
    ),
    "platform-guardian": RoleContract(
        role_id="platform-guardian",
        name="3rd-Party Platform Guardian (External Service Sentry)",
        name_bn="এক্সটার্নাল সার্ভিস সেন্ট্রি",
        weapon_type="Routing Circuit Breaker 🔌",
        paradigm=TIME_DRIVEN,
        responsibility=(
            "Monitor uptime, latency and quota freshness of every AI model "
            "provider (সমস্ত এআই মডেল প্রোভাইডারের আপটাইম, লেটেন্সি ও কোটা "
            "ফ্রেশনেস মনিটর)।"
        ),
        must_follow=(
            "zero-admin self-healing: auto-failover when possible, otherwise "
            "file an issue immediately (জিরো-অ্যাডমিন সেলফ-হিলিং)",
        ),
        must_not=(
            "interrupting healthy routes without cause (সুস্থ রাউটে অহেতুক "
            "ট্রাফিক ইন্টারাপ্ট নিষেধ)",
        ),
        weapons=frozenset({
            "provider_prober",
            "failover_toggle",
            "gh_issue_create",
        }),
        forbidden_operations=(
            "modifying permanent config files",
        ),
        trigger=TriggerSpec(
            event_type="event:provider.health_alert",
            payload_expectations=(("alert_state", "unhealthy"),),
        ),
    ),
})

ROLE_IDS: Final = tuple(ROLE_CONTRACTS)

#: Deterministic event router: exactly one role per canonical event type.
EVENT_INDEX: Final[Mapping[str, str]] = MappingProxyType({
    contract.trigger.event_type: role_id
    for role_id, contract in ROLE_CONTRACTS.items()
})

# ---------------------------------------------------------------------------
# Deterministic label-plane lookup (replaces legacy keyword classification)
# ---------------------------------------------------------------------------

#: Exact label -> role with deterministic priority. Labels are the structured
#: signal plane already trusted by the claim guard ("claim = label plane OR
#: atomic-claim comment"); matching here is exact-string equality, never
#: substring scanning of titles/bodies.
LABEL_TRIGGER_INDEX: Final[Mapping[str, str]] = MappingProxyType({
    "status:runway": "ci-fixer",       # priority 0 — jammed runway first
    "gate:pre-landing": "task-auditor",  # priority 1 — landing gate armed
    "status:claimed": "coder",          # priority 2 — claimed task execution
})
LABEL_PRIORITY: Final = ("status:runway", "gate:pre-landing", "status:claimed")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchSignal:
    """Structured dispatch input. NO free-text field exists by design.

    ``payload`` carries structured key/value facts only (pr numbers, check
    states, schedule expressions) — values are compared by exact equality,
    never scanned.
    """

    event_type: str
    labels: frozenset[str] = frozenset()
    payload: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class DispatchDecision:
    decision: str                       # DISPATCH | DENY
    role_id: str | None
    reason: str
    paradigm: str | None = None
    weapons: frozenset[str] = frozenset()
    missing_labels: tuple[str, ...] = ()

    def to_json(self) -> str:
        return json.dumps({
            "decision": self.decision,
            "role_id": self.role_id,
            "reason": self.reason,
            "paradigm": self.paradigm,
            "weapons": sorted(self.weapons),
            "missing_labels": list(self.missing_labels),
        }, ensure_ascii=False, sort_keys=True)


def _deny(reason: str, *, labels_missing: Iterable[str] = ()) -> DispatchDecision:
    return DispatchDecision(
        decision=DECISION_DENY,
        role_id=None,
        reason=reason,
        missing_labels=tuple(sorted(labels_missing)),
    )


def dispatch(signal: DispatchSignal) -> DispatchDecision:
    """Route a structured signal to a role. Deterministic, fail-closed."""
    if not isinstance(signal, DispatchSignal):
        raise TypeError("dispatch() accepts only a structured DispatchSignal")
    role_id = EVENT_INDEX.get(signal.event_type)
    if role_id is None:
        return _deny("UNKNOWN_EVENT")
    contract = ROLE_CONTRACTS[role_id]
    spec = contract.trigger

    labels = frozenset(signal.labels)
    missing = tuple(lbl for lbl in spec.required_labels if lbl not in labels)
    if missing:
        return _deny("LABEL_GATE", labels_missing=missing)

    if spec.schedule_kind is not None:
        if signal.payload.get("schedule_kind") != spec.schedule_kind:
            return _deny("SCHEDULE_GATE")

    for key in spec.required_payload:
        if not signal.payload.get(key):
            return _deny("PAYLOAD_GATE")

    for key, expected in spec.payload_expectations:
        if signal.payload.get(key) != expected:
            return _deny("PAYLOAD_MISMATCH")

    return DispatchDecision(
        decision=DECISION_DISPATCH,
        role_id=role_id,
        reason="OK",
        paradigm=contract.paradigm,
        weapons=provision_weapons(role_id),
    )


def dispatch_from_labels(labels: Iterable[str]) -> DispatchDecision:
    """Deterministic label-plane dispatch (legacy classify_task_role successor).

    Exact-match lookup on the structured label plane with fixed priority:
    runway healing > landing gate > claimed task. Anything else is a DENY —
    never a keyword guess.
    """
    present = frozenset(labels)
    for label in LABEL_PRIORITY:
        if label in present:
            role_id = LABEL_TRIGGER_INDEX[label]
            contract = ROLE_CONTRACTS[role_id]
            return DispatchDecision(
                decision=DECISION_DISPATCH,
                role_id=role_id,
                reason=f"LABEL_TRIGGER:{label}",
                paradigm=contract.paradigm,
                weapons=provision_weapons(role_id),
            )
    return _deny("NO_TRIGGER")


# ---------------------------------------------------------------------------
# RBAC — Least-Privilege weapon provisioning
# ---------------------------------------------------------------------------


class LeastPrivilegeViolation(ValueError):
    """Raised when a role is offered a weapon outside its allowlist."""


def get_contract(role_id: str) -> RoleContract:
    """Fail-closed contract lookup."""
    contract = ROLE_CONTRACTS.get(role_id)
    if contract is None:
        raise ValueError(
            f"Unknown role_id: {role_id!r}. Must be one of {sorted(ROLE_CONTRACTS)}"
        )
    return contract


def provision_weapons(role_id: str) -> frozenset[str]:
    """Return the exact weapon allowlist for a role (Least Privilege)."""
    return get_contract(role_id).weapons


def authorize(role_id: str, tool: str) -> bool:
    """Fail-closed authorization: unknown role or foreign tool -> False."""
    contract = ROLE_CONTRACTS.get(role_id)
    if contract is None:
        return False
    return tool in contract.weapons


def assert_least_privilege(role_id: str, requested: Iterable[str]) -> None:
    """Raise unless every requested tool is inside the role's allowlist."""
    contract = get_contract(role_id)
    foreign = sorted(set(requested) - contract.weapons)
    if foreign:
        raise LeastPrivilegeViolation(
            f"role {role_id!r} may not receive weapons {foreign} "
            f"(allowlist: {sorted(contract.weapons)})"
        )


def assert_commit_scope(role_id: str, path: str) -> None:
    """Enforce commit path scopes declared on the contract (fail-closed)."""
    contract = get_contract(role_id)
    if not contract.commit_scopes:
        return
    for scope in contract.commit_scopes:
        if path.replace("\\", "/").startswith(scope):
            return
    raise LeastPrivilegeViolation(
        f"role {role_id!r} may only commit under {list(contract.commit_scopes)}, "
        f"got {path!r}"
    )


# ---------------------------------------------------------------------------
# Role-specific output contracts (issue #489 acceptance criteria)
# ---------------------------------------------------------------------------


class ScoutBatchError(ValueError):
    """Raised when an Ecosystem Scout batch violates its contract."""


@dataclass(frozen=True)
class ScoutProposal:
    """Full-spectrum evaluation record (pros + cons + anti-patterns + risks
    + 'এটা করা যাবে না'), filtered through the core philosophy."""

    title: str
    source: str
    pros: tuple[str, ...]
    cons: tuple[str, ...]
    anti_patterns: tuple[str, ...]
    risks: tuple[str, ...]
    dont_do_this: tuple[str, ...]        # "এটা করা যাবে না"
    philosophy_verdict: str              # one of CORE_PHILOSOPHY_FILTERS


def validate_scout_batch(proposals: Iterable[ScoutProposal]) -> tuple[int, ...]:
    """Fail-closed validation. Returns accepted indices (all of them)."""
    batch = tuple(proposals)
    if len(batch) < MIN_SCOUT_PROPOSALS:
        raise ScoutBatchError(
            f"Ecosystem Scout must propose at least {MIN_SCOUT_PROPOSALS} "
            f"actionable issues, got {len(batch)}"
        )
    for i, p in enumerate(batch):
        if not isinstance(p, ScoutProposal):
            raise ScoutBatchError(f"proposal #{i} is not a ScoutProposal")
        for field_name in ("title", "source", "philosophy_verdict"):
            if not getattr(p, field_name):
                raise ScoutBatchError(f"proposal #{i}: empty {field_name}")
        for field_name in ("pros", "cons", "risks", "dont_do_this"):
            if not getattr(p, field_name):
                raise ScoutBatchError(
                    f"proposal #{i}: full-spectrum field {field_name!r} is empty "
                    "(pros/cons/risks/'এটা করা যাবে না' are all mandatory)"
                )
        if p.philosophy_verdict not in CORE_PHILOSOPHY_FILTERS:
            raise ScoutBatchError(
                f"proposal #{i}: philosophy_verdict {p.philosophy_verdict!r} "
                f"not in {list(CORE_PHILOSOPHY_FILTERS)}"
            )
    return tuple(range(len(batch)))


class ExploitContractError(ValueError):
    """Raised when a Rules Breaker exploit report violates its contract."""


@dataclass(frozen=True)
class ExploitReport:
    """Dual-vector damage-proof record committed under tests/adversarial/."""

    vector: str                          # guard_evasion | unguarded_damage
    failing_test_path: str               # must live under tests/adversarial/
    p0_issue_filed: bool                 # P0-critical issue mandatory
    damage_evidence: str = ""
    patch_code_present: bool = False     # self-patch forbidden


def validate_exploit_report(report: ExploitReport) -> None:
    if report.vector not in ("guard_evasion", "unguarded_damage"):
        raise ExploitContractError(
            f"vector must be guard_evasion|unguarded_damage, got {report.vector!r}"
        )
    normalized = report.failing_test_path.replace("\\", "/")
    if not normalized.startswith(ADVERSARIAL_SCOPE):
        raise ExploitContractError(
            f"failing exploit tests MUST live under {ADVERSARIAL_SCOPE}/ "
            f"(commit scope), got {report.failing_test_path!r}"
        )
    if not report.p0_issue_filed:
        raise ExploitContractError(f"a {P0_LABEL} issue MUST be filed")
    if report.patch_code_present:
        raise ExploitContractError("self-patching is forbidden for rules-breaker")
    if report.vector == "unguarded_damage" and not report.damage_evidence:
        raise ExploitContractError(
            "unguarded_damage vector requires measured damage evidence "
            "(memory leak / CPU spike / DoS proof)"
        )


class VisualFindingError(ValueError):
    """Raised when a Human Eye finding proposes direct code edits."""


@dataclass(frozen=True)
class VisualFinding:
    """Human Eye output: an issue with design direction, never a code edit."""

    surface: str
    finding: str
    color_harmony_ok: bool
    typography_ok: bool
    premium_feel_ok: bool
    recommended_issue: str               # aesthetic direction for the filed issue
    code_edit_proposed: bool = False     # must stay False — issue-only role


def validate_visual_finding(finding: VisualFinding) -> None:
    if finding.code_edit_proposed:
        raise VisualFindingError(
            "human-eye files issues only; direct CSS/TS edits are forbidden"
        )
    for field_name in ("surface", "finding", "recommended_issue"):
        if not getattr(finding, field_name):
            raise VisualFindingError(f"empty {field_name}")


# ---------------------------------------------------------------------------
# Self-test (doctrine: every reference module ships one)
# ---------------------------------------------------------------------------


def self_test() -> bool:
    """Offline invariants. Returns True, or raises AssertionError."""
    # Directory shape: 8 roles, bijective events, paradigm partition.
    assert len(ROLE_CONTRACTS) == 8, len(ROLE_CONTRACTS)
    assert len(EVENT_INDEX) == 8
    assert set(EVENT_INDEX) == {c.trigger.event_type for c in ROLE_CONTRACTS.values()}
    task_roles = {r for r, c in ROLE_CONTRACTS.items() if c.paradigm == TASK_DRIVEN}
    time_roles = {r for r, c in ROLE_CONTRACTS.items() if c.paradigm == TIME_DRIVEN}
    assert task_roles == {"coder", "ci-fixer", "task-auditor"}, task_roles
    assert time_roles == {
        "ecosystem-scout", "federation-auditor", "human-eye",
        "rules-breaker", "platform-guardian",
    }, time_roles

    # Triad completeness.
    for contract in ROLE_CONTRACTS.values():
        assert contract.responsibility
        assert contract.must_follow and contract.must_not
        assert contract.weapons
        assert contract.forbidden_operations
        assert contract.paradigm in PARADIGMS
        assert contract.trigger.event_type in EVENT_INDEX

    # Dispatch: happy paths.
    ok = dispatch(DispatchSignal("event:task.claimed", frozenset({"status:claimed"})))
    assert ok.decision == DECISION_DISPATCH and ok.role_id == "coder"
    ok = dispatch(DispatchSignal("event:pr.ci_failed", payload={
        "pr_number": 42, "checks_state": "failing"}))
    assert ok.decision == DECISION_DISPATCH and ok.role_id == "ci-fixer"
    ok = dispatch(DispatchSignal("event:schedule.ecosystem_scan", payload={
        "schedule_kind": "cron", "schedule_expr": "0 9 * * 1"}))
    assert ok.decision == DECISION_DISPATCH and ok.role_id == "ecosystem-scout"

    # Dispatch: fail-closed paths.
    assert dispatch(DispatchSignal("event:unknown")).reason == "UNKNOWN_EVENT"
    assert dispatch(DispatchSignal("event:task.claimed")).reason == "LABEL_GATE"
    assert dispatch(DispatchSignal("event:pr.ci_failed", payload={
        "pr_number": 1, "checks_state": "passing"})).reason == "PAYLOAD_MISMATCH"
    assert dispatch(DispatchSignal("event:schedule.visual_review", payload={
        "schedule_kind": "cron", "schedule_expr": "x"})).reason == "SCHEDULE_GATE"
    assert dispatch(DispatchSignal("event:provider.health_alert", payload={
        "alert_state": "healthy"})).reason == "PAYLOAD_MISMATCH"

    # Label plane: exact-match with priority, deny otherwise.
    assert dispatch_from_labels(["status:runway", "status:claimed"]).role_id == "ci-fixer"
    assert dispatch_from_labels(["gate:pre-landing", "status:claimed"]).role_id == "task-auditor"
    assert dispatch_from_labels(["status:claimed"]).role_id == "coder"
    assert dispatch_from_labels(["P1-high", "area:ci"]).reason == "NO_TRIGGER"
    assert dispatch_from_labels([]).reason == "NO_TRIGGER"

    # RBAC: least privilege holds.
    assert provision_weapons("coder") == ROLE_CONTRACTS["coder"].weapons
    assert authorize("coder", "write_to_file")
    assert not authorize("coder", "pr_review_approve_block")
    assert not authorize("nonexistent-role", "write_to_file")
    read_only_roles = ("task-auditor", "ecosystem-scout", "federation-auditor",
                       "human-eye", "platform-guardian")
    for role in read_only_roles:
        assert not (provision_weapons(role) & CODE_WRITE_WEAPONS), role
    assert not (provision_weapons("rules-breaker") & {
        "replace_file_content", "multi_replace_file_content", "write_to_file"})
    try:
        assert_least_privilege("task-auditor", ["write_to_file"])
        raise SystemExit("least-privilege gate failed open")
    except LeastPrivilegeViolation:
        pass
    assert_commit_scope("rules-breaker", "tests/adversarial/x.py")
    try:
        assert_commit_scope("rules-breaker", "src/main.py")
        raise SystemExit("adversarial scope gate failed open")
    except LeastPrivilegeViolation:
        pass

    # Scout contract.
    def _proposal(n: int) -> ScoutProposal:
        return ScoutProposal(
            title=f"proposal {n}", source="web", pros=("p",), cons=("c",),
            anti_patterns=("a",), risks=("r",), dont_do_this=("d",),
            philosophy_verdict=CORE_PHILOSOPHY_FILTERS[0])
    assert validate_scout_batch([_proposal(i) for i in range(MIN_SCOUT_PROPOSALS)])
    try:
        validate_scout_batch([_proposal(i) for i in range(MIN_SCOUT_PROPOSALS - 1)])
        raise SystemExit("scout minimum failed open")
    except ScoutBatchError:
        pass
    try:
        validate_scout_batch([replace(_proposal(0), risks=())
                              for _ in range(MIN_SCOUT_PROPOSALS)])
        raise SystemExit("scout risk field failed open")
    except ScoutBatchError:
        pass

    # Exploit contract.
    validate_exploit_report(ExploitReport(
        vector="guard_evasion", failing_test_path="tests/adversarial/t.py",
        p0_issue_filed=True))
    for bad in (
        ExploitReport("other", "tests/adversarial/t.py", True),
        ExploitReport("guard_evasion", "src/t.py", True),
        ExploitReport("guard_evasion", "tests/adversarial/t.py", False),
        ExploitReport("guard_evasion", "tests/adversarial/t.py", True,
                      patch_code_present=True),
        ExploitReport("unguarded_damage", "tests/adversarial/t.py", True),
    ):
        try:
            validate_exploit_report(bad)
            raise SystemExit(f"exploit contract failed open: {bad!r}")
        except ExploitContractError:
            pass

    # Human Eye contract.
    validate_visual_finding(VisualFinding(
        surface="dashboard", finding="contrast too low",
        color_harmony_ok=False, typography_ok=True, premium_feel_ok=True,
        recommended_issue="raise contrast on KPI cards"))
    try:
        validate_visual_finding(VisualFinding(
            surface="dashboard", finding="x", color_harmony_ok=True,
            typography_ok=True, premium_feel_ok=True, recommended_issue="y",
            code_edit_proposed=True))
        raise SystemExit("human-eye write gate failed open")
    except VisualFindingError:
        pass

    # Keyword deprecation tombstones.
    assert KEYWORD_MATCHING_DEPRECATED is True
    assert set(DispatchSignal.__dataclass_fields__) == {
        "event_type", "labels", "payload"}
    assert not hasattr(sys.modules[__name__], "classify_task_role"), \
        "deprecated keyword API must not exist on the matrix module"
    assert not hasattr(sys.modules[__name__], "classify_from_text")

    return True


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--dispatch-event", metavar="EVENT_TYPE")
    parser.add_argument("--labels", default="", help="comma-separated exact labels")
    parser.add_argument("--payload", default="",
                        help="comma-separated key=value pairs")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("SELF-TEST OK: role_trigger_matrix")
        return 0

    if args.dispatch_event:
        payload_kwargs: dict[str, Any] = {}
        for chunk in filter(None, (p.strip() for p in args.payload.split(","))):
            key, _, value = chunk.partition("=")
            payload_kwargs[key] = value
        signal = DispatchSignal(
            event_type=args.dispatch_event,
            labels=frozenset(filter(None, (l.strip() for l in args.labels.split(",")))),
            payload=MappingProxyType(payload_kwargs),
        )
        print(dispatch(signal).to_json())
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
