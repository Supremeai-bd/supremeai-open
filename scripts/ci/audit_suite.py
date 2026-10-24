#!/usr/bin/env python3
"""Topological Sequence Audit — Constitutional Layer-Order Invariant (#2682).

# বাংলা: সাংবিধানিক টপোলজিক্যাল লেয়ারিং ইনভেরিয়েন্ট — অন্ধভাবে UI/API লেয়ারে
# কোড লেখার আগে নিচের লেয়ারের (Schemas → Tools/Workers → Core → API → UI)
# ভিত্তি ঠিক আছে কি না, তা মেশিন-ভেরিফায়েবলভাবে অডিট করে।

Layer model (issue #2682 mandate 1):

    [Layer 1: Schemas & Contracts]
    [Layer 2: Tools / Workers / Sidecars]
    [Layer 3: Core Engine & State Machine]
    [Layer 4: API Endpoints & Routes]
    [Layer 5: Frontend & Client UI]

Enforcement policy (mandate 3 — Topological Sequence Audit):
- একটি PR যদি শুধুমাত্র Layer 4/5 ফাইল বদলায় এবং নিচের কোনো লেয়ারের (1-3)
  grounding ফাইল স্পর্শ না করে, তবে PR body-তে "Reflection Evidence"
  (why + alternatives_rejected) বাধ্যতামূলক — না থাকলে BLOCK (exit 1)।
- নিচের লেয়ারের ফাইল স্পর্শ করলে grounding ধরা হয় (capability-before-construction
  সন্তুষ্ট)।
- rules.yml-এর সিনট্যাক্স/স্কিমা ভ্যালিডেটরও এখানে (3-Tier Verification Contract,
  Tier 1: Rules Consistency)।

CLI:
    python scripts/ci/audit_suite.py --files f1,f2 [--body-file body.md]
    python scripts/ci/audit_suite.py --pr 1234          # gh দিয়ে changed files + body
    python scripts/ci/audit_suite.py --validate-rules   # rules.yml schema check

Exit codes: 0 = PASS, 1 = BLOCK, 2 = configuration/usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = REPO_ROOT / ".github" / "constitution" / "rules.yml"

# বাংলা: লেয়ার নাম — রিপোর্ট ও ব্লক-মেসেজে মানুষের পাঠযোগ্য আউটপুটের জন্য
LAYER_NAMES: dict[int, str] = {
    1: "Schemas & Contracts",
    2: "Tools / Workers / Sidecars",
    3: "Core Engine & State Machine",
    4: "API Endpoints & Routes",
    5: "Frontend & Client UI",
}

# বাংলা: সবচেয়ে-সুনির্দিষ্ট prefix আগে মিলবে — ক্রম অপরিবর্তনীয় (immutable contract)
_LAYER_PREFIXES: list[tuple[str, int]] = [
    # Layer 1: Schemas & Contracts
    ("packages/shared-types/", 1),
    ("backend/schemas/", 1),
    ("backend/models/", 1),
    ("backend/database/", 1),
    ("backend/alembic_migrations/", 1),
    # Layer 2: Tools / Workers / Sidecars
    ("backend/tools/", 2),
    ("backend/workers/", 2),
    ("mini-services/", 2),
    ("scripts/", 2),
    # Layer 3: Core Engine & State Machine
    ("backend/core/", 3),
    ("backend/services/", 3),
    ("backend/engine/", 3),
    ("backend/brain/", 3),
    ("backend/context_engine/", 3),
    ("backend/learning/", 3),
    ("backend/memory/", 3),
    ("packages/core-infrastructure/", 3),
    ("packages/shared-services/", 3),
    ("packages/ui-components/", 3),
    ("packages/design-tokens/", 3),
    # Layer 4: API Endpoints & Routes
    ("backend/api/", 4),
    ("backend/admin/", 4),
    ("backend/ws/", 4),
    # Layer 5: Frontend & Client UI
    ("frontend/", 5),
]


def classify_layer(path: str) -> int | None:
    """পাথ থেকে টপোলজিক্যাল লেয়ার নম্বর — অজানা পাথে None (audited নয়)।"""
    # বাংলা: সামান্য নরমালাইজ — ./ ও leading স্ল্যাশ বাদ, সেপারেটর ইউনিফাই
    norm = path.strip().replace("\\", "/").lstrip("./")
    for prefix, layer in _LAYER_PREFIXES:
        if norm.startswith(prefix):
            return layer
    return None


def classify_layers(files: list[str]) -> dict[int, set[str]]:
    """ফাইল-লিস্ট → {layer: {files}}; অজানা পাথ বাদ।"""
    by_layer: dict[int, set[str]] = {}
    for f in files:
        layer = classify_layer(f)
        if layer is not None:
            by_layer.setdefault(layer, set()).add(f)
    return by_layer


# বাংলা: Reflection Evidence মার্কার — PR body-তে গভীর প্রতিফলনের মেশিন-চেনা চিহ্ন
_REFLECTION_HEADER_RE = re.compile(r"^#{1,3}\s*reflection evidence", re.IGNORECASE | re.MULTILINE)
_WHY_RE = re.compile(r"\bwhy\b", re.IGNORECASE)
_ALTERNATIVES_RE = re.compile(r"alternatives?[\s_]*rejected|বিকল্প.*বাতিল", re.IGNORECASE | re.UNICODE)


def has_reflection_evidence(pr_body: str | None) -> bool:
    """PR body-তে Reflection Evidence সেকশন (why + alternatives_rejected) আছে কি?"""
    if not pr_body:
        return False
    if not _REFLECTION_HEADER_RE.search(pr_body):
        return False
    # বাংলা: হেডারের পরের অংশে why ও alternatives — দুটোই থাকতে হবে (mandate 2.3)
    tail = _REFLECTION_HEADER_RE.split(pr_body, maxsplit=1)[-1]
    return bool(_WHY_RE.search(tail) and _ALTERNATIVES_RE.search(tail))


@dataclass
class TopologicalAuditResult:
    """অডিট ফল — মেশিন-পাঠযোগ্য + মানুষের পাঠযোগ্য উভয় ফিল্ড।"""

    passed: bool
    layers_touched: dict[int, list[str]] = field(default_factory=dict)
    max_layer: int | None = None
    grounded_low_layer_file: str | None = None
    reflection_evidence: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "max_layer": self.max_layer,
            "layers_touched": {str(k): sorted(v) for k, v in self.layers_touched.items()},
            "grounded_low_layer_file": self.grounded_low_layer_file,
            "reflection_evidence": self.reflection_evidence,
            "reason": self.reason,
        }


def audit_topological_sequence(
    changed_files: list[str],
    pr_body: str | None = None,
    *,
    strict_low_layer_required: bool = True,
) -> TopologicalAuditResult:
    """মূল টপোলজিক্যাল অডিট (mandate 3)।

    # বাংলা: Layer 4/5-এর কাজ, নিচের লেয়ারের ফাইল স্পর্শ না করলে শুধুমাত্র
    # তখনই পাস করবে যখন PR body-তে Reflection Evidence আছে — অর্থাৎ এজেন্ট
    # সচেতনভাবে সিদ্ধান্ত নিয়েছে যে underlying capability আগেই আছে।
    """
    by_layer = classify_layers(changed_files)
    layers_touched = {k: sorted(v) for k, v in by_layer.items()}
    max_layer = max(by_layer) if by_layer else None
    evidence = has_reflection_evidence(pr_body)

    result = TopologicalAuditResult(
        passed=True,
        layers_touched=layers_touched,
        max_layer=max_layer,
        reflection_evidence=evidence,
    )

    if max_layer is None:
        # বাংলা: কোনো ক্লাসিফায়েবল ফাইল নেই (docs-only PR) — অডিট প্রাসঙ্গিক নয়
        result.reason = "no classifiable source files — audit not applicable"
        return result

    if max_layer <= 3:
        # বাংলা: নিচের লেয়ারের নিজস্ব কাজ — ভিত্তিই তৈরি করছে, সবসময় অনুমোদিত
        result.reason = f"low-layer work only (max={max_layer}: {LAYER_NAMES[max_layer]}) — foundation building"
        return result

    # max_layer ∈ {4, 5}: নিচের লেয়ারের grounding খুঁজি
    grounding = None
    if strict_low_layer_required:
        for low in (1, 2, 3):
            found = by_layer.get(low)
            if found:
                grounding = sorted(found)[0]
                break
    result.grounded_low_layer_file = grounding

    if grounding is not None:
        result.reason = f"upper-layer work (max={max_layer}) grounded by low-layer file: {grounding}"
        return result

    if evidence:
        result.reason = (
            f"upper-layer work (max={max_layer}) accepted via Reflection Evidence "
            "(why + alternatives_rejected present)"
        )
        return result

    result.passed = False
    result.reason = (
        f"TOPOLOGICAL VIOLATION: PR touches {LAYER_NAMES[max_layer]} (layer {max_layer}) "
        f"without any Layer 1-3 grounding file and without Reflection Evidence. "
        f"Capability Before Construction (mandate 2.1) requires either a tools/worker/"
        f"schema change in this PR or a '## Reflection Evidence' section in the PR body."
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Tier 1 (Verification Contract): rules.yml schema consistency validation
# ─────────────────────────────────────────────────────────────────────────────

_RULE_REQUIRED_KEYS = {"title", "description", "severity", "category"}
_VALID_SEVERITIES = {"BLOCK", "WARN", "INFO"}
_GATE_REQUIRED_KEYS = {"title", "blocks_when", "wired", "workflow"}


# বাংলা: যাচাইযোগ্য সেকশন — নিয়ম-ক্যাটাগরি + গেট ঘোষণা। বাকি টপ-লেভেল কী
# (constitution, self_merge_policy, discovery_policy, bootstrap ইত্যাদি) হলো
# স্ক্যালার/পলিসি সেকশন — রুল-স্কিমার বাইরে, যাচাই করা হয় না।
_RULE_CATEGORIES = {
    "meta", "architecture", "security", "configuration", "mcp_integration",
    "reliability", "cost", "performance", "customer_ux",
}


def validate_rules_schema(rules: dict) -> list[str]:
    """rules.yml লোড করা ডিক্টের স্কিমা যাচাই — এরর লিস্ট (খালি = বৈধ)।"""
    errors: list[str] = []
    for category, entries in rules.items():
        if category != "gates" and category not in _RULE_CATEGORIES:
            continue  # বাংলা: পলিসি/স্ক্যালার সেকশন — স্কিমার সুযোগের বাইরে
        if not isinstance(entries, dict):
            errors.append(f"{category}: expected mapping of rule_NNN -> settings, got {type(entries).__name__}")
            continue
        is_gate_section = category == "gates"
        for rule_id, settings in entries.items():
            where = f"{category}.{rule_id}"
            if not isinstance(settings, dict):
                errors.append(f"{where}: expected mapping, got {type(settings).__name__}")
                continue
            required = _GATE_REQUIRED_KEYS if is_gate_section else _RULE_REQUIRED_KEYS
            for key in required:
                if key not in settings:
                    errors.append(f"{where}: missing required key '{key}'")
            if not is_gate_section:
                sev = settings.get("severity")
                if sev is not None and sev not in _VALID_SEVERITIES:
                    errors.append(f"{where}: invalid severity '{sev}' (allowed: {sorted(_VALID_SEVERITIES)})")
                # বাংলা: canonical rules.yml সংক্ষিপ্ত slug ('arch', 'sec') ব্যবহার করে —
                # সেকশন-নাম সমতা কঠোর ধরলে বাস্তব ফাইল ভাঙ্গা; তাই শুধু non-empty string যাচাই
                cat = settings.get("category")
                if cat is not None and (not isinstance(cat, str) or not cat.strip()):
                    errors.append(f"{where}: category must be a non-empty string, got {cat!r}")
            else:
                # বাংলা: গেট অবশ্যই কোনো ওয়ার্কফ্লো-তে wired থাকতে হবে — অযোগ্য মান এরর
                wf = settings.get("workflow")
                if wf is not None and not str(wf).endswith(".yml"):
                    errors.append(f"{where}: workflow '{wf}' must reference a .yml file")
    return errors


def load_rules(path: Path | None = None) -> dict:
    """rules.yml লোড — yaml প্যাকেজ না থাকলে স্পষ্ট এরর।"""
    try:
        import yaml  # noqa: PLC0415 — বাংলা: lazy import, টেস্ট রানটাইমে ব্যয় এড়াতে
    except ImportError as e:  # pragma: no cover — PyYAML backend ডিপেন্ডেন্সি
        raise SystemExit(f"PyYAML required for rules validation: {e}") from e
    rules_path = path or RULES_PATH
    return yaml.safe_load(rules_path.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Tier 3 (Verification Contract): agent-loop task-selection gate helpers
# ─────────────────────────────────────────────────────────────────────────────

_LAYER_BODY_RE = re.compile(r"^\s*(?:\*\*)?\s*Layer(?:\s*/\s*স্তর)?(?:\*\*)?\s*[:：]\s*(?:\*\*)?\s*[`'\"]?([1-5])", re.MULTILINE)

def parse_layer_from_body(body: str | None) -> int | None:
    """ইস্যু body থেকে ঘোষিত Layer (1-5) পার্স — টেমপ্লেট ফিল্ড আউটপুট সহ।"""
    if not body:
        return None
    m = _LAYER_BODY_RE.search(body)
    return int(m.group(1)) if m else None


def scan_open_issue_layers(issues: list[dict]) -> dict[int, int]:
    """open-issue লিস্ট (number + body) → {issue_number: layer} — শুধু ঘোষিতগুলো।"""
    layers: dict[int, int] = {}
    for issue in issues:
        layer = parse_layer_from_body(issue.get("body") or "")
        if layer is not None:
            layers[int(issue["number"])] = layer
    return layers


def topological_task_gate(
    issue_number: int,
    declared_layer: int | None,
    open_issue_layers: dict[int, int],
) -> tuple[bool, str]:
    """এজেন্টের টাস্ক-সিলেকশন গেট (mandate 1: 'নিচের লেয়ার সম্পন্ন না হলে ওপরের লেয়ার ক্লেইম নিষিদ্ধ')।

    # বাংলা: ওপরের লেয়ারের (>=3) টাস্ক তখনই ব্লক হবে যখন নিচের কোনো লেয়ারের
    # টাস্ক এখনো OPEN — অর্থাৎ ভিত্তি অসম্পূর্ণ। নিচের কোনো লেয়ার টাস্ক খোলা
    # না থাকলে ভিত্তি ধরা হয় সম্পূর্ণ/পরিষ্কার।
    """
    if declared_layer is None or declared_layer <= 2:
        return True, f"issue #{issue_number}: layer {declared_layer} (foundation work) — always claimable"
    lower_open = sorted(
        n for n, layer in open_issue_layers.items()
        if layer < declared_layer and n != issue_number
    )
    if lower_open:
        detail = ", ".join(f"#{n} (L{open_issue_layers[n]})" for n in lower_open)
        return False, (
            f"issue #{issue_number}: Layer {declared_layer} ({LAYER_NAMES[declared_layer]}) "
            f"BLOCKED — lower-layer foundation still open: {detail}"
        )
    return True, f"issue #{issue_number}: layer {declared_layer} — no open lower-layer tasks, foundation clear"


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_pr_files_and_body(pr_number: int) -> tuple[list[str], str | None]:
    """gh CLI দিয়ে PR-এর changed files + body সংগ্রহ (CI ও লোকাল উভয়ে)।"""
    files_res = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "files,body",
         "--jq", r'{body: .body, files: [.files[].path]}'],
        capture_output=True, text=True, timeout=60,
    )
    if files_res.returncode != 0:
        raise SystemExit(f"gh pr view failed: {files_res.stderr.strip()}")
    data = json.loads(files_res.stdout)
    return list(data.get("files") or []), data.get("body")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Topological Sequence Audit (#2682)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--files", help="comma-separated changed file paths")
    group.add_argument("--pr", type=int, help="PR number (fetches via gh)")
    group.add_argument("--validate-rules", action="store_true", help="validate rules.yml schema only")
    parser.add_argument("--body-file", help="optional PR body markdown file")
    parser.add_argument("--rules", help="optional rules.yml path override")
    args = parser.parse_args(argv)

    if args.validate_rules:
        rules = load_rules(Path(args.rules) if args.rules else None)
        errors = validate_rules_schema(rules)
        if errors:
            print("❌ rules.yml schema violations:")
            for e in errors:
                print(f"   - {e}")
            return 1
        print("✅ rules.yml schema consistent (all categories/gates valid)")
        return 0

    if args.pr is not None:
        files, body = _fetch_pr_files_and_body(args.pr)
    else:
        files = [f.strip() for f in args.files.split(",") if f.strip()]
        body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else None

    result = audit_topological_sequence(files, body)
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    print(f"{'✅' if result.passed else '❌'} {result.reason}")
    if not result.passed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
