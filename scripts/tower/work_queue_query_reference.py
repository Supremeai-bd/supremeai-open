#!/usr/bin/env python3
"""S05 reference implementation: unified queue query construction (#474).

r2 (#2115/#2123) adds the completeness contract: pagination + merge-dedupe.
Executable spec for bridge.work_queue's GitHub query building, pagination,
and issue normalization. The TS handler in bridge.tools.ts must behave
identically; tests/test_s05_unified_queue.py asserts the contract offline,
infrastructure/mcp-control-plane/test_queue_fidelity.ts mirrors it TS-side.

Contract (from docs/S05_UNIFIED_QUEUE_SPEC.md r2):
- No label (or empty/whitespace) -> query ALL open issues, label=null.
- Explicit label -> labels=<urlencoded label>, label echoes the filter.
- PRs and closed issues are always excluded (normalization).
- COMPLETE ENUMERATION: pages are fetched until a short page (or
  MAX_PAGES cap) and merged with number-dedupe — a single-page fetch
  turns the queue into a creation-rank window that drops open work as
  traffic flows (#2115: 98 open issues read as 20-35 rows; #2123: rows
  vanished across a ~2.5-6.5h window) — forbidden since r2.
- Deterministic ordering: number descending, applied AFTER the merge so
  ordering can never reintroduce truncation.

Self-test: python3 work_queue_query_reference.py --self-test
"""

from __future__ import annotations

import json
import sys
from urllib.parse import urlencode

REPO = "Supremeai-bd/supremeai-open"
QUEUE_PAGE_SIZE = 100
QUEUE_MAX_PAGES = 5
QUEUE_LIMIT_MAX = 200


def build_queue_query(label: str | None = None, page: int = 1) -> dict:
    """Build the GitHub issues query exactly as the TS handler must.

    Returns {"url", "params", "applied_label", "page"} — applied_label is
    the effective filter or None (all open issues).
    """
    params = {
        "state": "open",
        "per_page": str(QUEUE_PAGE_SIZE),
        "sort": "created",
        "direction": "desc",
        "page": str(max(1, page)),
    }
    applied = None
    if label is not None and label.strip():
        applied = label.strip()
        params["labels"] = applied
    qs = urlencode(params)
    return {
        "url": f"https://api.github.com/repos/{REPO}/issues?{qs}",
        "params": params,
        "applied_label": applied,
        "page": max(1, page),
    }


def fetch_all_pages(fetch_page, max_pages: int = QUEUE_MAX_PAGES) -> list:
    """Page-termination contract: stop at the first short page or the cap.

    fetch_page(page:int) -> list of raw issues (network injected by the
    caller, so this stays pure-logic and offline-testable).
    """
    pages = []
    for page in range(1, max(1, max_pages) + 1):
        rows = fetch_page(page)
        rows = rows if isinstance(rows, list) else []
        pages.append(rows)
        if len(rows) < QUEUE_PAGE_SIZE:
            break
    return pages


def merge_pages(pages: list) -> list:
    """Flatten pages with number-dedupe (first occurrence wins)."""
    seen: set = set()
    out: list = []
    for page in pages or []:
        for item in page if isinstance(page, list) else []:
            if not isinstance(item, dict):
                continue
            num = item.get("number")
            if isinstance(num, int):
                if num in seen:
                    continue
                seen.add(num)
            out.append(item)
    return out


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
        "workOrders": [
            {
                "number": i["number"],
                "title": i.get("title", ""),
                "state": i.get("state"),
                "labels": sorted(
                    l.get("name", str(l)) if isinstance(l, dict) else str(l)
                    for l in i.get("labels") or []
                ),
                "url": i.get("html_url"),
                "createdAt": i.get("created_at"),
                "updatedAt": i.get("updated_at"),
                "comments": i.get("comments", 0),
            }
            for i in rows
        ],
    }


def _self_test() -> int:
    q = build_queue_query()
    assert q["applied_label"] is None and "labels=" not in q["url"], q
    assert "page=1" in q["url"] and "per_page=100" in q["url"], q
    q2 = build_queue_query("")
    assert q2["applied_label"] is None, "empty label must mean all-open"
    q3 = build_queue_query("   ")
    assert q3["applied_label"] is None, "whitespace label must mean all-open"
    q4 = build_queue_query("bridge:queued")
    assert "labels=bridge%3Aqueued" in q4["url"], q4
    assert q4["applied_label"] == "bridge:queued"
    q5 = build_queue_query(None, page=3)
    assert "page=3" in q5["url"] and q5["page"] == 3, q5
    q0 = build_queue_query(None, page=0)
    assert q0["page"] == 1, "page must clamp to 1"
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
    d = {
        "number": 5,
        "title": "dict-label",
        "state": "open",
        "labels": [{"name": "status:unclaimed"}],
    }
    nd = normalize_queue([d])
    assert nd["workOrders"][0]["labels"] == ["status:unclaimed"]

    # Pagination contract (#2115/#2123)
    full = [{"number": i} for i in range(200, 100, -1)]   # 100 rows -> full page
    tail = [{"number": i} for i in range(100, 90, -1)]    # 10 rows -> short page
    pages = fetch_all_pages(lambda p: full if p == 1 else (tail if p == 2 else []))
    assert len(pages) == 2, f"must stop at first short page, got {len(pages)}"
    over = fetch_all_pages(lambda p: full, max_pages=QUEUE_MAX_PAGES)
    assert len(over) == QUEUE_MAX_PAGES, "cap must bound a saturated feed"
    merged = merge_pages(pages)
    assert len(merged) == 110, merged and len(merged)
    dup = merge_pages([[{"number": 7}, {"number": 8}], [{"number": 8}, {"number": 9}]])
    assert [r["number"] for r in dup] == [7, 8, 9], dup
    old = {"number": 1912, "state": "open", "labels": [{"name": "status:unclaimed"}]}
    single_page = normalize_queue(merge_pages([full[:90]]))
    paged = normalize_queue(merge_pages([full[:90], [old]]))
    assert not any(w["number"] == 1912 for w in single_page["workOrders"])
    assert any(w["number"] == 1912 for w in paged["workOrders"]), \
        "the #1912-class drop must be impossible under pagination"
    print("self-test OK: work_queue_query_reference r2 (pagination-complete)")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    if len(sys.argv) == 2 and sys.argv[1].endswith(".json"):
        with open(sys.argv[1], encoding="utf-8") as fh:
            payload = json.load(fh)
        print(json.dumps(build_queue_query(payload.get("label"), payload.get("page", 1)), indent=2))
        sys.exit(0)
    print(__doc__)
    sys.exit(2)
