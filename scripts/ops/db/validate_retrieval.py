#!/usr/bin/env python3
"""
Retrieval gold-set validation for the SupremeAI knowledge base.

Modes:
  --dsn       direct DB retrieval (isolates retrieval/embedding quality)
  --endpoint  POST each query to your real search route, e.g.
              http://localhost:8000/api/hybrid_search   (tests the FULL stack)  # is_local()

Gate: exit 0 if hit@k >= threshold on runnable queries (and, with --strict,
      zero blocked queries). Non-zero exit = CI failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict

try:
    import psycopg2
except ImportError:
    sys.exit("Missing dependency: pip install psycopg2-binary")

try:
    import httpx
except ImportError:
    httpx = None


def embed_texts(texts, base_url, api_key, model):
    if httpx is None:
        sys.exit("Missing dependency: pip install httpx")
    r = httpx.post(
        f"{base_url.rstrip('/')}/embeddings",
        headers={"Authorization": f"Bearer {api_key}"} if api_key else {},
        json={"model": model, "input": list(texts)},
        timeout=120.0,
    )
    r.raise_for_status()
    data = sorted(r.json()["data"], key=lambda d: d["index"])
    return [d["embedding"] for d in data]


def db_search(conn, vec, k, status):
    vec_str = "[" + ",".join(map(str, vec)) + "]"
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, 1 - (embedding <=> %s::vector) AS score "
            "FROM knowledge_chunks WHERE status = %s "
            "ORDER BY embedding <=> %s::vector LIMIT %s",
            (vec_str, status, vec_str, k),
        )
        return [(row[0], float(row[1])) for row in cur.fetchall()]


def http_search(endpoint, query, k, extra_headers):
    if httpx is None:
        sys.exit("Missing dependency: pip install httpx")
    r = httpx.post(endpoint, json={"query": query, "q": query, "top_k": k, "k": k},
                   headers=extra_headers, timeout=60.0)
    r.raise_for_status()
    body = r.json()
    items = body.get("results", body) if isinstance(body, dict) else body
    out = []
    for it in items:
        if isinstance(it, str):
            out.append((it, None))
        elif isinstance(it, dict) and ("id" in it or "chunk_id" in it):
            out.append((it.get("id") or it.get("chunk_id"), it.get("score")))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--goldset", default="goldset.json")
    ap.add_argument("--dsn", help="postgres DSN (default $DATABASE_URL)")
    ap.add_argument("--endpoint", help="HTTP search endpoint (mutually exclusive with --dsn)")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=0.90)
    ap.add_argument("--status", default="active")
    ap.add_argument("--openai-base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    ap.add_argument("--model", default="text-embedding-3-small",
                    help="MUST match the model used at ingestion")
    ap.add_argument("--strict", action="store_true", help="also fail on blocked queries")
    ap.add_argument("--report", default="retrieval_report.json")
    args = ap.parse_args()

    if bool(args.dsn) == bool(args.endpoint):
        sys.exit("Pass exactly one of --dsn / --endpoint")

    gold = json.load(open(args.goldset, encoding="utf-8"))
    queries = gold["queries"]
    conn = None

    # ---- classify runnable vs blocked (db mode only; http mode assumes endpoint filters)
    statuses = {}
    if args.dsn:
        conn = psycopg2.connect(args.dsn or os.environ.get("DATABASE_URL"))
        all_expected = sorted({e for q in queries for e in q["expected_ids"]})
        with conn.cursor() as cur:
            cur.execute("SELECT id, status FROM knowledge_chunks WHERE id = ANY(%s)", (all_expected,))
            statuses = dict(cur.fetchall())

    runnable, blocked = [], []
    for q in queries:
        active = [e for e in q["expected_ids"] if statuses.get(e) == "active"]
        if args.dsn and not active:
            missing = [e for e in q["expected_ids"] if e not in statuses]
            draft = [e for e in q["expected_ids"] if statuses.get(e) == "draft"]
            reason = (f"expected ids not in DB: {missing}" if missing
                      else f"expected ids still draft (needs_review): {draft}")
            blocked.append((q, reason))
        else:
            runnable.append(q)

    # ---- embed queries (db mode); http mode lets the endpoint embed
    vectors = None
    if args.dsn:
        print(f"[embed] {len(runnable)} queries via {args.model} ...")
        vectors = embed_texts([q["query"] for q in runnable],
                              args.openai_base_url, os.environ.get("OPENAI_API_KEY", ""), args.model)

    # ---- evaluate
    results = []
    hits = 0
    rr_sum = 0.0
    for i, q in enumerate(runnable):
        if args.dsn:
            top = db_search(conn, vectors[i], args.k, args.status)
        else:
            top = http_search(args.endpoint, q["query"], args.k, {})
        ids = [t[0] for t in top]
        rank = next((ids.index(e) + 1 for e in q["expected_ids"] if e in ids), None)
        hit = rank is not None
        hits += hit
        rr_sum += (1.0 / rank) if rank else 0.0
        results.append({"id": q["id"], "query": q["query"], "category": q["category"],
                        "language": q.get("language", "en"), "hit": hit,
                        "rank": rank, "expected_ids": q["expected_ids"],
                        "retrieved": [{"id": t[0], "score": t[1]} for t in top[:3]]})

    n = len(runnable)
    hit_rate = hits / n if n else 0.0
    mrr = rr_sum / n if n else 0.0

    by_cat, by_lang = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for r in results:
        for bucket, key in ((by_cat, r["category"]), (by_lang, r["language"])):
            bucket[key][0] += r["hit"]; bucket[key][1] += 1

    # ---- report
    print("\n" + "=" * 60)
    print("RETRIEVAL GOLD-SET REPORT")
    print("=" * 60)
    print(f"Queries: {len(queries)}   runnable: {n}   blocked: {len(blocked)}")
    print(f"Overall hit@{args.k}: {hits}/{n} ({hit_rate:.1%})   MRR: {mrr:.3f}")
    print("-" * 60)
    print("By category:")
    for cat, (h, t) in sorted(by_cat.items()):
        print(f"  {cat:<16} {h}/{t} ({h / t:.0%})")
    print("By language:")
    for lang, (h, t) in sorted(by_lang.items()):
        print(f"  {lang:<16} {h}/{t} ({h / t:.0%})")

    misses = [r for r in results if not r["hit"]]
    if misses:
        print("-" * 60)
        print(f"MISSES ({len(misses)}) — fix corpus (add variants) or goldset:")
        for m in misses:
            print(f"  [{m['id']}] \"{m['query']}\"")
            print(f"     expected: {', '.join(m['expected_ids'])}")
            got_str = ', '.join(f"{t['id']}({t['score']:.3f})" if t.get('score') else str(t['id']) for t in m['retrieved'])
            print(f"     got:      {got_str}")
    if blocked:
        print("-" * 60)
        print(f"BLOCKED ({len(blocked)}) — approve drafts or fix goldset:")
        for q, reason in blocked:
            print(f"  [{q['id']}] {reason}")

    passed = hit_rate >= args.threshold and not (args.strict and blocked)
    print("=" * 60)
    print(f"GATE: {'✅ PASS' if passed else '❌ FAIL'} "
          f"(hit@{args.k} {hit_rate:.1%} vs threshold {args.threshold:.0%})")

    json.dump({"gate": "PASS" if passed else "FAIL", "queries_total": len(queries),
               "runnable": n, "blocked": [q["id"] for q, _ in blocked],
               "hit_at_k": hit_rate, "k": args.k, "mrr": mrr, "results": results,
               "blocked_detail": [{"id": q["id"], "reason": r} for q, r in blocked]},
              open(args.report, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
