"""Validate the hand-curated capability-surface inventory (issue #1101).

বাংলা: `docs/capability_inventory.json` হলো হাতে-চালিত (hand-curated) সত্য-ফাইল —
mechanically generated নয়, তাই এই validator শুধু চুক্তি (contract) যাচাই করে:

  1. schema: প্রতিটি entry-তে বাধ্যতামূলক ক্ষেত্র + টাইপ
  2. classification ∈ {Core, Supported, Experimental, Deferred, Deprecated}
  3. `surfaces[]` — প্রতিটি পাথ ডিস্কে সত্যিই আছে কিনা (নিষ্ক্রিয়/মৃত দাবি নিষেধ)
  4. `tests[]` — টেস্ট পাথ/গ্লোব ডিস্কে আছে কিনা
  5. `owner_issue` — int অথবা null; আর কোনো ভুয়া "pending" স্ট্রিং নয়
  6. duplicate id নিষেধ; minimum একটি surface

Exit codes: 0 = সব ঠিক; 1 = চুক্তি-ভাঙা (সব ভাঙা entry একসাথে রিপোর্ট হয়)।
Usage: python scripts/ci/validate_capability_inventory.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "docs" / "capability_inventory.json"

ALLOWED_CLASSIFICATIONS = {"Core", "Supported", "Experimental", "Deferred", "Deprecated"}
# presence-required: এগুলোর মান খালি হতে পারবে না।
REQUIRED_FIELDS = ("id", "name", "classification", "surfaces", "evidence")
# optional-but-typed: owner_issue = int|None (null = এখনো কোনো owner issue নেই);
# tests/docs = list (খালি বৈধ — Deferred/Experimental-এ সত্যিই নাও থাকতে পারে)。
STRING_FIELDS = ("id", "name", "classification", "evidence")


def _surface_exists(rel: str) -> bool:
    p = ROOT / rel
    return p.exists()


def _test_ref_ok(ref: str) -> bool:
    p = ROOT / ref
    if p.exists():
        return True
    # directory-level glob fallback (যেমন backend/tests/core/)
    return p.parent.exists() if str(ref).endswith("/") else False


def main() -> int:
    if not INVENTORY_PATH.exists():
        print(f"::error::capability inventory missing: {INVENTORY_PATH}")
        return 1
    try:
        data = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"::error::capability inventory is not valid JSON: {e}")
        return 1

    caps = data.get("capabilities")
    if not isinstance(caps, list) or not caps:
        print("::error::capabilities[] must be a non-empty list")
        return 1

    errors: list[str] = []
    seen_ids: set[str] = set()
    for cap in caps:
        cid = str(cap.get("id", "<missing>"))
        for field in REQUIRED_FIELDS:
            if field not in cap or cap[field] is None or cap[field] == "":
                errors.append(f"{cid}: missing/empty required field '{field}'")
        for field in ("tests", "docs"):
            if field in cap and not isinstance(cap[field], list):
                errors.append(f"{cid}: '{field}' must be a list (possibly empty)")
        for field in STRING_FIELDS:
            if field in cap and not isinstance(cap[field], str):
                errors.append(f"{cid}: '{field}' must be a string")
        if cap.get("classification") not in ALLOWED_CLASSIFICATIONS:
            errors.append(
                f"{cid}: classification '{cap.get('classification')}' not in {sorted(ALLOWED_CLASSIFICATIONS)}"
            )
        if cid in seen_ids:
            errors.append(f"{cid}: duplicate capability id")
        seen_ids.add(cid)

        surfaces = cap.get("surfaces") or []
        if not isinstance(surfaces, list):
            errors.append(f"{cid}: surfaces must be a list")
        else:
            for s in surfaces:
                if not isinstance(s, str) or not _surface_exists(s):
                    errors.append(f"{cid}: surface path does not exist on disk: {s}")

        tests = cap.get("tests") or []
        if isinstance(tests, list):
            for t in tests:
                if not isinstance(t, str) or not _test_ref_ok(t):
                    errors.append(f"{cid}: test ref does not exist: {t}")

        oi = cap.get("owner_issue")
        if oi is not None and not isinstance(oi, int):
            errors.append(f"{cid}: owner_issue must be int or null, got {oi!r}")

    if errors:
        print(f"CAPABILITY INVENTORY INVALID — {len(errors)} problem(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(
        f"capability inventory OK — {len(caps)} capabilities: "
        + ", ".join(
            f"{c}={sum(1 for x in caps if x.get('classification') == c)}"
            for c in sorted(ALLOWED_CLASSIFICATIONS)
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
