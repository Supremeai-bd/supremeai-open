#!/usr/bin/env python3
"""S05 reference implementation: unified queue query construction (#474).

Executable spec for bridge.work_queue's GitHub query building and issue
normalization. The TS handler in bridge.tools.ts must behave identically;
tests/test_s05_unified_queue.py asserts the contract offline.

Contract (from docs/S05_UNIFIED_QUEUE_SPEC.md):
- No label (or empty/whitespace) -> query ALL open issues, label=null.
- Explicit label -> labels=<urlencoded label>, label echoes the filter.
- PRs and closed issues are always excluded (normalization).
- Deterministic ordering: number descending.

Self-test: python3 work_queue_query_reference.py --self-test
"""
from __future__ import annotations

import json
import sys
from urllib.parse import urlencode

REPO = "Supremeai-bd/supremeai-open"


def build_queue_query(label: str | None = None) -> dict:
    """Build the GitHub issues query exactly as the TS handler must.

    Returns {"url", "params", "applied_label"} — applied_label is the
    effective filter or None (all open issues).
    """
    params = {"state": "open", "per_page": "100"}
    applied = None
    if label is not None and label.strip():
        applied = label.strip()
        params["labels"] = applied
    qs = urlencode(params)
    return {"url": f"https://api.github.com/repos/{REPO}/issues?{qs}",
            "params": params, "applied_label": applied}


def is_queue_eligible(issue: dict) -> bool:
    """Normalization filter: open issues only, never PRs."""
    if issue.get("is_pull_request") or "pull_request" in issue:
        return False
    return (issue.get("state") or "").lower() == "open"


def normalize_queue(issues: list, applied_label: str | None = None) -> dict:
    """Tower response shape: newest-first open issues, no PRs/closed."""
    rows = [i for i in (issues or []) if is_queue_eligible(i)]
    rows.sort(key=lambda i: i["number"], reverse=True)
    return {
        "repo": REPO,
        "label": applied_label,
        "authenticatedRead": True,
        "count": len(rows),
        "workOrders": [{"number": i["number"], "title": i.get("title", ""),
                        "state": i.get("state"), "labels": sorted(
                            l.get("name", str(l)) if isinstance(l, dict) else str(l)
                            for l in i.get("labels") or []),
                        "url": i.get("html_url"),
                        "createdAt": i.get("created_at"),
                        "updatedAt": i.get("updated_at"),
                        "comments": i.get("comments", 0)} for i in rows],
    }


def _self_test() -> int:
    q = build_queue_query()
    assert q["applied_label"] is None and "labels=" not in q["url"], q
    q2 = build_queue_query("")
    assert q2["applied_label"] is None, "empty label must mean all-open"
    q3 = build_queue_query("   ")
    assert q3["applied_label"] is None, "whitespace label must mean all-open"
    q4 = build_queue_query("bridge:queued")
    assert "labels=bridge%3Aqueued" in q4["url"], q4
    assert q4["applied_label"] == "bridge:queued"
    rows = [
        {"number": 3, "title": "c", "state": "open", "labels": []},
        {"number": 1, "title": "a", "state": "open", "labels": []},
        {"number": 2, "title": "pr", "state": "open", "is_pull_request": True},
        {"number": 0, "title": "closed", "state": "closed", "labels": []},
    ]
    norm = normalize_queue(rows)
    assert [w["number"] for w in norm["workOrders"]] == [3, 1], norm
    assert norm["label"] is None and norm["count"] == 2
    norm2 = normalize_queue(rows, applied_label="x")
    assert norm2["label"] == "x"
    d = {"number": 5, "title": "dict-label", "state": "open",
         "labels": [{"name": "status:unclaimed"}]}
    nd = normalize_queue([d])
    assert nd["workOrders"][0]["labels"] == ["status:unclaimed"]
    print("self-test OK: work_queue_query_reference")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    if len(sys.argv) == 2 and sys.argv[1].endswith(".json"):
        with open(sys.argv[1], encoding="utf-8") as fh:
            payload = json.load(fh)
        print(json.dumps(build_queue_query(payload.get("label")), indent=2))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
