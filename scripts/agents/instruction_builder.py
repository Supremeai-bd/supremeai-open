#!/usr/bin/env python3
"""Instruction Builder — Step-intelligence.1 (#104, roadmap parent #113/#44).

৫-সেকশনের standard instruction contract (MODE/RULES/ACTIONS/FORBIDDEN/VALIDATION) —
`role_registry.get_role_contract()` + AGENT_RULES.md parsed policy থেকে deterministic
composition। LLM বাধ্যতামূলক নয় — শুধু pure function + template composition
(zero-cost doctrine অক্ষত)।

# বাংলা মন্তব্য (#104): সমস্যা ছিল — continuous_agent_loop.py-তে role-rules parsing
# ad-hocভাবে ছড়ানো (_parse_agent_rules_md, format_agent_rules_block, role_registry
# build_dynamic_prompt — প্রত্যেকটা আলাদা গঠন)। এই মডিউল একটাই standard আকৃতি দেয় —
# প্রতি run-এ একই contract একই গঠনে তৈরি হয় (deterministic)।

Read-only VIEW — নতুন SSOT নয় (P2/P3 সম্মান করে):
  MODE       → role_registry.AUTHORITY_TIERS (contract["authority"])
  RULES      → AGENT_RULES.md §3 parsed applicable bullets — লুপের প্রতিষ্ঠিত
               `_load_agent_rules` পুনর্ব্যবহার (AGENT_RULES §14: existing tooling
               first), fallback: contract["constraints"] লাইন-শ্রেণিবিভাগ
  ACTIONS    → credential_manager.TASK_SCOPED_ENV_KEYS + BOT_SLOT_CREDENTIALS scopes
               (contract["allowed_env_keys"] / contract["gh_scopes"])
  FORBIDDEN  → parsed prohibited bullets (একই উৎস)
  VALIDATION → role_registry.VERIFICATION_REQUIREMENTS + canonical 3 tiers

সিকোয়েন্স নোট (#104 SEQUENCE NOTE): continuous_agent_loop.py-তে wiring seq:5 —
এই PR শুধু module + tests। তাই loop-import এখানে **lazy** (ফাংশন-বডির ভেতরে):
seq:5-এ যখন loop module-level-এ এই builder-কে import করবে তখন circular import
যেন না হয় — lazy import সেই চক্র সম্ভব করেই না।
"""

from __future__ import annotations

from typing import Any

# canonical 3-tier verification ladder — issue #104 §৪-এর Verification Contract-এর
# সাথে সাংগত্যপূর্ণ জেনেরিক লেবেল (প্রতিটি tier-এর বিশদ রোল-ভেদে contract["verification"]-এ)
VALIDATION_TIERS: tuple[str, ...] = (
    "tier-1: reflection check (git grep dead-reference sweep)",
    "tier-2: boot smoke (python -c \"import backend.main\")",
    "tier-3: pytest suite green",
)

# বাংলা মন্তব্য: লুপের _PROHIBITED_MARKERS-এর আয়না-কপি — শুধু fallback পথে ব্যবহৃত
# (loop-import ব্যর্থ হলে); প্রাইমারি পথে শ্রেণিবিভাগ লুপের নিজ ফাংশনেই হয়।
_FALLBACK_PROHIBITED_MARKERS = ("do not", "must not", "never", "নিষিদ্ধ")


def _rules_from_contract_constraints(
    constraints: list[str],
) -> tuple[list[str], list[str]]:
    """Fallback: contract["constraints"] লাইন থেকে (applicable, prohibited) শ্রেণিবিভাগ।

    # বাংলা মন্তব্য: লুপের sentence-split semantics-এর হালকা প্রতিলিপি — প্যারাগ্রাফ
    # লাইনকে বাক্যে ভেঙে নেতিবাচক-মার্কারযুক্ত বাক্য prohibited। এটি স্বতন্ত্র পার্সার
    # নয় — শুধু graceful degradation (loop import অনুপস্থিতি)।
    """
    import re

    split_re = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'`\u0980-\u09FF])")
    applicable: list[str] = []
    prohibited: list[str] = []
    for para in constraints or []:
        for sent in split_re.split(para):
            sent = sent.strip()
            if not sent:
                continue
            applicable.append(sent)
            low = sent.lower()
            if any(mk in low for mk in _FALLBACK_PROHIBITED_MARKERS):
                prohibited.append(sent)
    return applicable, prohibited


def _load_rules(role: str) -> tuple[list[str], list[str], str]:
    """রোল-নিয়ম লোড — প্রতিষ্ঠিত একক-উৎস পার্সার, lazy import-এ।

    # বাংলা মন্তব্য: continuous_agent_loop._load_agent_rules = AGENT_RULES.md
    # (একক-উৎস) → rules.yml fallback চেইন — নিজে দ্বিতীয় পার্সার লেখা P2-লঙ্ঘন
    # হতো। Circular-import-এড়াতে import ফাংশন-বডির ভেতরে; ব্যর্থ হলে
    # role_registry-র constraints দিয়ে graceful fallback (U2: চুপচাপ শূন্য নয়,
    # উৎস-লেবেলসহ)।
    """
    try:
        from scripts.agents.continuous_agent_loop import _load_agent_rules

        applicable, prohibited = _load_agent_rules(role)
        if applicable or prohibited:
            return applicable, prohibited, "continuous_agent_loop._load_agent_rules"
    except Exception:  # noqa: BLE001 — graceful degradation, কখনো বিল্ডার ভাঙবে না
        pass
    from scripts.agents.role_registry import get_role_contract

    applicable, prohibited = _rules_from_contract_constraints(
        get_role_contract(role).get("constraints") or []
    )
    return applicable, prohibited, "role_registry.constraints-fallback"


def build_instruction(
    role: str,
    *,
    rules: tuple[list[str], list[str]] | None = None,
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """৫-সেকশনের standard instruction block (dict) — pure function।

    # বাংলা মন্তব্য: rules/contract inject করা যায় (testability — ফাইল-নিরপেক্ষ);
    # না দিলে সব SSOT থেকে লাইভ কম্পোজ। আউটপুট গঠন সর্বদা এক — এটাই #104-এর
    # "প্রতি run-এ একই contract একই গঠনে" চুক্তি।
    """
    from scripts.agents.role_registry import get_role_contract

    c = contract if contract is not None else get_role_contract(role)

    if rules is not None:
        applicable, prohibited = list(rules[0]), list(rules[1])
        rules_source = "injected"
    else:
        applicable, prohibited, rules_source = _load_rules(c.get("role", role))

    return {
        "mode": {
            "role": c.get("role", role),
            "authority": c.get("authority", "governed_autonomous"),
        },
        "rules": applicable,
        "actions": {
            "allowed_env_keys": list(c.get("allowed_env_keys") or []),
            "gh_scopes": list(c.get("gh_scopes") or []),
        },
        "forbidden": prohibited,
        "validation": {
            "requirement": c.get(
                "verification", "follow issue Verification Contract"
            ),
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
        f"MODE: role={mode.get('role', 'unknown')} | authority={mode.get('authority', 'unknown')}",
    ]

    lines.append("RULES:")
    rules = block.get("rules") or []
    if rules:
        lines += [f"  - {r}" for r in rules]
    else:
        lines.append("  - none declared")

    lines.append("ACTIONS:")
    env_keys = actions.get("allowed_env_keys") or []
    scopes = actions.get("gh_scopes") or []
    lines.append(f"  - env_keys: {', '.join(env_keys) if env_keys else 'none'}")
    lines.append(f"  - gh_scopes: {', '.join(scopes) if scopes else 'none'}")

    lines.append("FORBIDDEN:")
    forbidden = block.get("forbidden") or []
    if forbidden:
        lines += [f"  - {f}" for f in forbidden]
    else:
        lines.append("  - none declared")

    lines.append("VALIDATION:")
    lines.append(f"  - requirement: {validation.get('requirement', 'follow issue Verification Contract')}")
    for tier in validation.get("tiers") or VALIDATION_TIERS:
        lines.append(f"  - {tier}")

    source = block.get("source", {})
    lines.append(f"--- source: {source.get('rules_source', 'unknown')} | deterministic: {source.get('deterministic', True)}")
    return "\n".join(lines)


def build_and_render(role: str) -> str:
    """সুবিধা-একক: লাইভ SSOT থেকে বিল্ড + রেন্ডার (loop seq:5 wiring-এর এন্ট্রিপয়েন্ট)।"""
    return render_instruction(build_instruction(role))


if __name__ == "__main__":
    import sys

    print(build_and_render(sys.argv[1] if len(sys.argv) > 1 else "coder"))
