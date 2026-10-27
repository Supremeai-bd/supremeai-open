#!/usr/bin/env python3
"""Instruction Builder — deterministic 5-section role instruction (issue #104).

মানসিক চুক্তি: MODE/RULES/ACTIONS/FORBIDDEN/VALIDATION — লিভিং SSOT
`role_trigger_matrix.ROLE_CONTRACTS` থেকে deterministic composition। LLM বাধ্যতামূলক
নয় — শুধু pure function + template composition (zero-cost doctrine অক্ষত)।

# পুনর্নির্মাণ-নোট (2026-10-28, অডিট F7-r2 — Superior Replacement, Invariant 3):
# মূল মডিউলটি #1526 loop rewrite-এ মুছে-ফেলা contract surface-এর ওপর দাঁড়িয়ে ছিল —
# primary path `continuous_agent_loop._load_agent_rules` (যে প্রতীক কোনো revision-এই
# ছিল না — F7) এবং fallback `role_registry.get_role_contract` (main-এ অস্তিত্বহীন)।
# ফলে প্রতিটি কলে অনিবার্য ImportError — zero importer, zero test, dead-on-arrival
# fossil। ডকুমেন্টেশনও মিথ্যা বলত (AGENT_RULES.md §3 RULES-এর উৎস — ফাইলটি নেই)।
# এই সংস্করণ phantom প্রতীকের বদলে জীবন্ত SSOT-কে সরাসরি পড়ে — কোনো নতুন SSOT নয়
# (P2/P3 সম্মত), শুধু read-only VIEW।

Read-only VIEW — নতুন SSOT নয় (P2/P3 সম্মান করে):
  MODE       → RoleContract.paradigm + role_id/name (ট্রিগার-ম্যাট্রিক্সের নিজ ক্ষেত্র)
  RULES      → RoleContract.must_follow (canonical bullets — বাংলা-ইংরেজি জোড়া)
  ACTIONS    → RoleContract.weapons (SSOT dispatch weapons — exact tool names)
  FORBIDDEN  → RoleContract.must_not + RoleContract.forbidden_operations
  VALIDATION → canonical 3-tier ladder (VERIFICATION_TIERS) + Verification Contract

# সিকোয়েন্স-নোট: এই মডিউল loop-কে import করে না — circular import অসম্ভব নয়,
# অপ্রয়োজনীয়। Canonical-merge নাম (যেমন cadence-এর 'auditor') এখানে সমাধান হয় না —
# caller-কে ROLE_IDS-concrete role পাঠাতে হবে (fail-closed ValueError, নীরব অনুমান নয়)।
"""

from __future__ import annotations

from typing import Any

try:  # flat context (python scripts/agents/… চালানো হলে / tests-এর sys.path.insert)
    from role_trigger_matrix import ROLE_CONTRACTS
except ImportError:  # package context (scripts.agents.… হিসেবে import হলে)
    from scripts.agents.role_trigger_matrix import ROLE_CONTRACTS

# canonical 3-tier verification ladder — issue #104 §৪-এর Verification Contract-এর
# সাথে সাংগত্যপূর্ণ জেনেরিক লেবেল (প্রতিটি tier-এর বিশদ রোল-ভেদে contract["verification"]-এ)
VALIDATION_TIERS: tuple[str, ...] = (
    "tier-1: reflection check (git grep dead-reference sweep)",
    "tier-2: boot smoke (python -c \"import backend.main\")",
    "tier-3: pytest suite green",
)


def load_role_rules(role: str) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """জীবন্ত SSOT থেকে (applicable, prohibited, source) — fail-closed।

    # বাংলা মন্তব্য: ROLE_CONTRACTS-এ না থাকা role মানে নীরব-fallback নয়, ValueError —
    # U2: চুপচাপ শূন্য নয়। ফেরত-লেবেলটি সত্যিকারের উৎস বহন করে (আর কাল্পনিক
    # 'continuous_agent_loop._load_agent_rules' নয় — F7-এর শিক্ষা)।
    """
    try:
        contract = ROLE_CONTRACTS[role]
    except KeyError:
        raise ValueError(
            f"unknown dispatch role: {role!r}; known roles: {sorted(ROLE_CONTRACTS)}"
        ) from None
    applicable: tuple[str, ...] = tuple(contract.must_follow)
    prohibited: tuple[str, ...] = tuple(contract.must_not) + tuple(
        contract.forbidden_operations
    )
    return applicable, prohibited, "role_trigger_matrix.ROLE_CONTRACTS"


def _load_rules(role: str) -> tuple[tuple[str, ...], tuple[str, ...], str]:
    """মূল call-shape-এর সামঞ্জস্য-এলিয়াস (issue #104 পৃষ্ঠ) — load_role_rules দেখুন।"""
    return load_role_rules(role)


def build_instruction(
    role: str,
    *,
    rules: tuple[tuple[str, ...], tuple[str, ...]] | None = None,
    contract: Any | None = None,
) -> dict[str, Any]:
    """৫-সেকশনের standard instruction block (dict) — pure function।

    # বাংলা মন্তব্য: rules/contract inject করা যায় (testability — ফাইল-নিরপেক্ষ);
    # না দিলে সব লিভিং SSOT (ROLE_CONTRACTS) থেকে লাইভ কম্পোজ। আউটপুট গঠন সর্বদা
    # এক — এটাই #104-এর "প্রতি run-এ একই contract একই গঠনে" চুক্তি।
    """
    try:
        c = contract if contract is not None else ROLE_CONTRACTS[role]
    except KeyError:
        raise ValueError(
            f"unknown dispatch role: {role!r}; known roles: {sorted(ROLE_CONTRACTS)}"
        ) from None

    role_id = getattr(c, "role_id", role)

    if rules is not None:
        applicable, prohibited = tuple(rules[0]), tuple(rules[1])
        rules_source = "injected"
    else:
        applicable, prohibited, rules_source = load_role_rules(role_id)

    return {
        "mode": {
            "role": role_id,
            "name": getattr(c, "name", role_id),
            "paradigm": getattr(c, "paradigm", "unknown"),
        },
        "rules": list(applicable),
        "actions": {
            "weapons": sorted(getattr(c, "weapons", ()) or ()),
        },
        "forbidden": list(prohibited),
        "validation": {
            "requirement": "follow issue Verification Contract",
            "tiers": list(VALIDATION_TIERS),
        },
        "source": {
            "rules_source": rules_source,
            "deterministic": True,
            "llm_required": False,
        },
    }


def render_instruction(block: dict[str, Any]) -> str:
    """dict block → standard ৫-সেকশন text envelope (deterministic রেন্ডার)।

    # বাংলা মন্তব্য: খালি সেকশনও স্পষ্টভাবে "- none declared" — চুপচাপ বাদ দেয় না,
    # যাতে envelope-গঠন প্রতি run-এ অভিন্ন থাকে (U2: অনুপস্থিতি-ও স্পষ্ট হওয়া চাই)।
    """
    mode = block.get("mode", {})
    actions = block.get("actions", {})
    validation = block.get("validation", {})

    lines = [
        "=== SUPREMEAI INSTRUCTION ENVELOPE (deterministic, zero-cost) ===",
        (
            f"MODE: role={mode.get('role', 'unknown')}"
            f" | paradigm={mode.get('paradigm', 'unknown')}"
            f" | name={mode.get('name', 'unknown')}"
        ),
    ]

    lines.append("RULES:")
    rules = block.get("rules") or []
    if rules:
        lines += [f"  - {r}" for r in rules]
    else:
        lines.append("  - none declared")

    lines.append("ACTIONS:")
    weapons = actions.get("weapons") or []
    lines.append(
        f"  - weapons: {', '.join(weapons) if weapons else 'none'}"
    )

    lines.append("FORBIDDEN:")
    forbidden = block.get("forbidden") or []
    if forbidden:
        lines += [f"  - {f}" for f in forbidden]
    else:
        lines.append("  - none declared")

    lines.append("VALIDATION:")
    lines.append(
        f"  - requirement: {validation.get('requirement', 'follow issue Verification Contract')}"
    )
    for tier in validation.get("tiers") or VALIDATION_TIERS:
        lines.append(f"  - {tier}")

    source = block.get("source", {})
    lines.append(
        f"--- source: {source.get('rules_source', 'unknown')}"
        f" | deterministic: {source.get('deterministic', True)}"
    )
    return "\n".join(lines)


def build_and_render(role: str) -> str:
    """সুবিধা-একক: লিভিং SSOT থেকে বিল্ড + রেন্ডার।"""
    return render_instruction(build_instruction(role))
